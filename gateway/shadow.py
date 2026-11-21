import asyncio
import os
from pathlib import Path

import httpx

BANK_DIR = Path(__file__).resolve().parent.parent / "bank"
INTERNAL_KEY = os.getenv("BANK_INTERNAL_KEY", "mirage-internal")


class LocalShadow:
    kind = "local"
    label = "Local shadow process"

    def __init__(self, url: str):
        self.base_url, self.headers, self.status, self.detail = url.rstrip("/"), {}, "starting", url

    async def start(self):
        self.status = "ready" if await healthy(self) else "error"


class DaytonaShadow:
    kind = "daytona"
    label = "Daytona sandbox"

    def __init__(self):
        self.base_url, self.headers, self.status, self.detail = "", {}, "starting", "booting sandbox"

    async def start(self):
        try:
            await asyncio.to_thread(self._boot)
            for _ in range(60):
                if await healthy(self):
                    self.status = "ready"
                    return
                await asyncio.sleep(2)
            self.status, self.detail = "error", "shadow bank did not become healthy"
        except Exception as e:
            self.status, self.detail = "error", f"{type(e).__name__}: {e}"[:200]

    def _boot(self):
        from daytona import Daytona
        from daytona.v0 import CreateSandboxFromSnapshotParams, SessionExecuteRequest

        sandbox = Daytona().v0.create(CreateSandboxFromSnapshotParams(
            language="python", public=True, auto_stop_interval=0, labels={"app": "mirage-shadow-bank"}))
        self.detail = f"sandbox {sandbox.id[:8]}"
        for f in ("__init__.py", "app.py", "seed.py"):
            sandbox.fs.upload_file((BANK_DIR / f).read_bytes(), f"mirage/bank/{f}")
        sandbox.process.exec("pip install -q fastapi==0.162.7 uvicorn==0.54.0", timeout=300)
        sandbox.process.create_session("bank")
        sandbox.process.execute_session_command("bank", SessionExecuteRequest(
            command=f"cd mirage && BANK_MODE=shadow BANK_INTERNAL_KEY={INTERNAL_KEY} "
                    "python -m uvicorn bank.app:app --host 0.0.0.0 --port 8002", run_async=True))
        link = sandbox.get_preview_link(8002)
        self.base_url = link.url.rstrip("/")
        if getattr(link, "token", None):
            self.headers = {"x-daytona-preview-token": link.token}


async def healthy(shadow) -> bool:
    try:
        async with httpx.AsyncClient(timeout=5) as c:
            return (await c.get(f"{shadow.base_url}/health", headers=shadow.headers)).status_code == 200
    except httpx.HTTPError:
        return False


def make_shadow():
    if os.getenv("DAYTONA_API_KEY") and os.getenv("MIRAGE_SHADOW", "daytona") == "daytona":
        return DaytonaShadow()
    return LocalShadow(os.getenv("SHADOW_URL", "http://127.0.0.1:8002"))
