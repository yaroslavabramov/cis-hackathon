import asyncio
import os
import time
from collections import deque
from pathlib import Path

import httpx

BANK_DIR = Path(__file__).resolve().parent.parent / "bank"
INTERNAL_KEY = os.getenv("BANK_INTERNAL_KEY", "mirage-internal")
LABELS = {"app": "mirage-shadow-bank"}


class LocalShadow:
    kind = "local"

    def __init__(self, url: str):
        self.base_url, self.headers, self.status, self.detail = url.rstrip("/"), {}, "starting", url

    async def boot(self):
        self.status = "ready" if await healthy(self) else "error"

    async def destroy(self):
        await reset_bank(self)


class DaytonaShadow:
    """One isolated shadow bank: private preview, no outbound network, deleted after the incident."""
    kind = "daytona"

    def __init__(self):
        self.base_url, self.headers, self.status, self.detail, self.sandbox = "", {}, "starting", "booting", None

    async def boot(self):
        try:
            await asyncio.to_thread(self._boot)
            for _ in range(60):
                if await healthy(self):
                    self.status = "ready"
                    return
                await asyncio.sleep(1)
            self.status, self.detail = "error", "shadow bank did not become healthy"
        except Exception as e:
            self.status, self.detail = "error", f"{type(e).__name__}: {e}"[:200]

    def _boot(self):
        from daytona import Daytona
        from daytona.v0 import CreateSandboxFromSnapshotParams, SessionExecuteRequest

        self.sandbox = sb = Daytona().v0.create(CreateSandboxFromSnapshotParams(
            language="python", public=False, auto_stop_interval=30, labels=LABELS))
        self.detail = sb.id[:8]
        for f in ("__init__.py", "app.py", "seed.py"):
            sb.fs.upload_file((BANK_DIR / f).read_bytes(), f"mirage/bank/{f}")
        sb.process.exec("pip install -q fastapi==0.162.7 uvicorn==0.54.0", timeout=300)
        sb.update_network_settings(network_block_all=True)
        sb.process.create_session("bank")
        sb.process.execute_session_command("bank", SessionExecuteRequest(
            command=f"cd mirage && BANK_MODE=shadow BANK_INTERNAL_KEY={INTERNAL_KEY} "
                    "python -m uvicorn bank.app:app --host 0.0.0.0 --port 8002", run_async=True))
        link = sb.get_preview_link(8002)
        self.base_url = link.url.rstrip("/")
        if getattr(link, "token", None):
            self.headers = {"x-daytona-preview-token": link.token}

    async def destroy(self):
        if self.sandbox:
            await asyncio.to_thread(self.sandbox.delete)


class ShadowPool:
    """Warm pool of isolated shadow banks that grows with attacker demand and shrinks when idle."""

    def __init__(self):
        self.daytona = bool(os.getenv("DAYTONA_API_KEY")) and os.getenv("MIRAGE_SHADOW", "daytona") == "daytona"
        self.local = LocalShadow(os.getenv("SHADOW_URL", "http://127.0.0.1:8002"))
        self.min_warm = int(os.getenv("MIRAGE_POOL_MIN", "2"))
        self.max_total = int(os.getenv("MIRAGE_POOL_MAX", "8"))
        self.spares: list[DaytonaShadow] = []
        self.active: set = set()
        self.demand: deque[float] = deque()
        self.tasks: set[asyncio.Task] = set()
        self.on_event = lambda text: None
        self.label = "Daytona sandbox per attacker" if self.daytona else "Local shadow process"
        self.kind = "daytona" if self.daytona else "local"

    def _spawn(self, coro):
        task = asyncio.create_task(coro)
        self.tasks.add(task)
        task.add_done_callback(self.tasks.discard)

    async def start(self):
        if not self.daytona:
            return await self.local.boot()
        await asyncio.to_thread(self._cleanup)
        self._scale()
        self._spawn(self._shrink_loop())

    def _cleanup(self):
        from daytona import Daytona
        from daytona.v0 import ListSandboxesQuery

        client = Daytona().v0
        for sb in client.list(ListSandboxesQuery(labels=LABELS)):
            client.delete(sb)

    def target(self) -> int:
        now = time.time()
        while self.demand and now - self.demand[0] > 120:
            self.demand.popleft()
        return max(0, min(self.max_total - len(self.active), max(self.min_warm, len(self.demand) + 1)))

    def _scale(self):
        self.spares = [s for s in self.spares if s.status != "error"]
        want, added = self.target(), 0
        while len(self.spares) < want:
            shadow = DaytonaShadow()
            self.spares.append(shadow)
            self._spawn(shadow.boot())
            added += 1
        if added and self.demand:
            self.on_event(f"Shadow pool scaling up: +{added} sandbox{'es' if added > 1 else ''} "
                          f"({len(self.demand)} attackers in the last 2 min, target {want} warm)")

    async def _shrink_loop(self):
        while True:
            await asyncio.sleep(20)
            ready = [s for s in self.spares if s.status == "ready"]
            extra = ready[:max(0, len(self.spares) - self.target())]
            for shadow in extra:
                self.spares.remove(shadow)
                self._spawn(shadow.destroy())
            if extra:
                self.on_event(f"Shadow pool scaling down: {len(extra)} idle sandbox{'es' if len(extra) > 1 else ''} switched off")

    async def acquire(self):
        if not self.daytona:
            return self.local
        self.demand.append(time.time())
        self._scale()
        started = time.time()
        while time.time() - started < 120:
            ready = next((s for s in self.spares if s.status == "ready"), None)
            if ready:
                self.spares.remove(ready)
                self.active.add(ready)
                self._scale()
                return ready
            self._scale()
            await asyncio.sleep(0.3)
        raise RuntimeError("no shadow bank became available")

    async def release(self, shadow):
        if shadow is self.local:
            return await self.local.destroy()
        self.active.discard(shadow)
        await shadow.destroy()
        self._scale()

    def info(self) -> dict:
        if not self.daytona:
            s = self.local
            return {"kind": "local", "label": self.label, "status": s.status, "detail": s.detail}
        ready = sum(s.status == "ready" for s in self.spares)
        booting = sum(s.status == "starting" for s in self.spares)
        status = "ready" if ready else "starting" if booting else "error"
        return {"kind": "daytona", "label": self.label, "status": status,
                "detail": f"{len(self.active)} active · {ready} warm · {booting} booting",
                "active": len(self.active), "warm": ready, "booting": booting, "target": self.target()}


async def healthy(shadow) -> bool:
    try:
        async with httpx.AsyncClient(timeout=5) as c:
            return (await c.get(f"{shadow.base_url}/health", headers=shadow.headers)).status_code == 200
    except httpx.HTTPError:
        return False


async def reset_bank(shadow):
    async with httpx.AsyncClient(timeout=10) as c:
        await c.post(f"{shadow.base_url}/internal/reset", headers={"x-internal-key": INTERNAL_KEY, **shadow.headers})
