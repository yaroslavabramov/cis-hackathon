"""Replays the attacker's exploits against main and against a Devin PR, each in a fresh bank."""
import asyncio
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
FILES = ("__init__.py", "app.py", "seed.py")


def git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, check=True).stdout


def sources(ref: str) -> dict[str, bytes]:
    return {f: git("show", f"{ref}:bank/{f}").encode() for f in FILES}


def fetch_pr(pr_url: str) -> str:
    number = pr_url.rstrip("/").split("/")[-1]
    git("fetch", "-q", "origin", f"pull/{number}/head:mirage-pr-{number}")
    return f"mirage-pr-{number}"


class LocalBanks:
    label = "local processes"

    def __init__(self):
        self.procs, self.urls, self.headers = [], {}, {}

    def boot(self, versions: dict[str, dict[str, bytes]]):
        for i, (name, files) in enumerate(versions.items()):
            d = Path(tempfile.mkdtemp(prefix=f"mirage-verify-{name}-"))
            (d / "bank").mkdir()
            for f, data in files.items():
                (d / "bank" / f).write_bytes(data)
            port = 8013 + i
            self.procs.append(subprocess.Popen([sys.executable, "-m", "uvicorn", "bank.app:app", "--port", str(port),
                                                "--log-level", "warning"], cwd=d, env={**os.environ, "BANK_MODE": "real"}))
            self.urls[name] = f"http://127.0.0.1:{port}"

    def close(self):
        for p in self.procs:
            p.terminate()


class DaytonaBanks:
    label = "fresh Daytona sandbox"

    def __init__(self):
        self.urls, self.headers, self.sandbox = {}, {}, None

    def boot(self, versions: dict[str, dict[str, bytes]]):
        from daytona import Daytona
        from daytona.v0 import CreateSandboxFromSnapshotParams, SessionExecuteRequest

        client = Daytona().v0
        self.sandbox = sb = client.create(CreateSandboxFromSnapshotParams(
            language="python", public=True, auto_stop_interval=15, labels={"app": "mirage-verify"}))
        self.label = f"fresh Daytona sandbox {sb.id[:8]}"
        sb.process.exec("pip install -q fastapi==0.162.7 uvicorn==0.54.0", timeout=300)
        for i, (name, files) in enumerate(versions.items()):
            for f, data in files.items():
                sb.fs.upload_file(data, f"verify/{name}/bank/{f}")
            port = 8013 + i
            sb.process.create_session(f"bank-{name}")
            sb.process.execute_session_command(f"bank-{name}", SessionExecuteRequest(
                command=f"cd verify/{name} && BANK_MODE=real python -m uvicorn bank.app:app --host 0.0.0.0 --port {port}",
                run_async=True))
            link = sb.get_preview_link(port)
            self.urls[name] = link.url.rstrip("/")
            if getattr(link, "token", None):
                self.headers = {"x-daytona-preview-token": link.token}

    def close(self):
        if self.sandbox:
            try:
                self.sandbox.delete()
            except Exception:
                pass


async def replay(url: str, headers: dict, finding: dict, customer_id: str, device_id: str) -> int:
    async with httpx.AsyncClient(base_url=url, headers=headers, timeout=30) as c:
        for _ in range(60):
            try:
                if (await c.get("/health")).status_code == 200:
                    break
            except httpx.HTTPError:
                pass
            await asyncio.sleep(1)
        r = await c.post("/v2/auth/login", json={"customer_id": customer_id, "device_id": device_id, "biometric_score": 0.998})
        auth = {"Authorization": f"Bearer {r.json()['token']}"}
        rp = finding["replay"]
        body = {**rp["body"], "amount": 1.0} if rp["body"] and "amount" in rp["body"] else rp["body"]
        r = await c.request(rp["method"], rp["path"], json=body or None, headers=auth)
        return r.status_code


async def verify(pr_url: str, found: list[dict], customer_id: str, device_id: str) -> dict:
    ref = await asyncio.to_thread(fetch_pr, pr_url)
    banks = DaytonaBanks() if os.getenv("DAYTONA_API_KEY") and os.getenv("MIRAGE_SHADOW", "daytona") == "daytona" else LocalBanks()
    started = time.time()
    try:
        await asyncio.to_thread(banks.boot, {"main": sources("main"), "pr": sources(ref)})
        results = {}
        for f in found:
            before = await replay(banks.urls["main"], banks.headers, f, customer_id, device_id)
            after = await replay(banks.urls["pr"], banks.headers, f, customer_id, device_id)
            results[f["id"]] = {"before": before, "after": after, "fixed": before == 200 and after != 200}
        return {"where": banks.label, "seconds": round(time.time() - started), "results": results}
    finally:
        await asyncio.to_thread(banks.close)
