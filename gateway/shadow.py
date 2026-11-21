import asyncio
import os
import time
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
    """Keeps one warm shadow ready so a diverted attacker gets a fresh, private bank instantly."""

    def __init__(self):
        self.daytona = bool(os.getenv("DAYTONA_API_KEY")) and os.getenv("MIRAGE_SHADOW", "daytona") == "daytona"
        self.local = LocalShadow(os.getenv("SHADOW_URL", "http://127.0.0.1:8002"))
        self.spare: DaytonaShadow | None = None
        self.warming: asyncio.Task | None = None
        self.active = 0
        self.label = "Daytona sandbox per attacker" if self.daytona else "Local shadow process"
        self.kind = "daytona" if self.daytona else "local"

    async def start(self):
        if not self.daytona:
            return await self.local.boot()
        await asyncio.to_thread(self._cleanup)
        self._warm()

    def _cleanup(self):
        from daytona import Daytona
        from daytona.v0 import ListSandboxesQuery

        client = Daytona().v0
        for sb in client.list(ListSandboxesQuery(labels=LABELS)):
            client.delete(sb)

    def _warm(self):
        self.spare = DaytonaShadow()
        self.warming = asyncio.create_task(self.spare.boot())

    async def acquire(self):
        if not self.daytona:
            return self.local
        started = time.time()
        while self.spare.status != "ready" and time.time() - started < 90:
            if self.spare.status == "error":
                self._warm()
            await asyncio.sleep(0.5)
        shadow = self.spare
        self.active += 1
        self._warm()
        return shadow

    async def release(self, shadow):
        if shadow is self.local:
            return await self.local.destroy()
        self.active -= 1
        await shadow.destroy()

    def info(self) -> dict:
        if not self.daytona:
            s = self.local
            return {"kind": "local", "label": self.label, "status": s.status, "detail": s.detail}
        spare = self.spare
        status = spare.status if spare else "starting"
        detail = f"{self.active} active · spare {spare.detail if spare else '-'} {status}"
        return {"kind": "daytona", "label": self.label, "status": status, "detail": detail}


async def healthy(shadow) -> bool:
    try:
        async with httpx.AsyncClient(timeout=5) as c:
            return (await c.get(f"{shadow.base_url}/health", headers=shadow.headers)).status_code == 200
    except httpx.HTTPError:
        return False


async def reset_bank(shadow):
    async with httpx.AsyncClient(timeout=10) as c:
        await c.post(f"{shadow.base_url}/internal/reset", headers={"x-internal-key": INTERNAL_KEY, **shadow.headers})
