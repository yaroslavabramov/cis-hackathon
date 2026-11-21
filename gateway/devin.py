import os

import httpx

API = "https://api.devin.ai/v3/organizations"


class Devin:
    def __init__(self):
        self.key = os.getenv("DEVIN_API_KEY", "")
        self.org = os.getenv("DEVIN_ORG_ID", "")
        self.repo = os.getenv("DEVIN_REPO", "yaroslavabramov/cis-hackathon")

    @property
    def configured(self) -> bool:
        return bool(self.key and self.org)

    async def _call(self, method: str, path: str, **kw) -> dict:
        async with httpx.AsyncClient(timeout=30) as c:
            r = await c.request(method, f"{API}/{self.org}/sessions{path}",
                                headers={"Authorization": f"Bearer {self.key}"}, **kw)
            r.raise_for_status()
            return r.json()

    async def start(self, incident: dict) -> dict:
        return await self._call("POST", "", json={
            "prompt": build_prompt(incident, self.repo), "repos": [self.repo],
            "title": f"Mirage incident {incident['id']}", "tags": ["mirage", "security-incident"]})

    async def get(self, session_id: str) -> dict:
        return await self._call("GET", f"/{session_id}")


def build_prompt(incident: dict, repo: str) -> str:
    log = "\n".join(f"{r['ts']}  {r['method']} {r['path']}  {r['body']}  -> {r['status']} {r['result']}"
                    for r in incident["log"])
    return f"""You are on the security team of Desert Bank. At {incident['diverted_at']} our Mirage deception layer
diverted a hostile session (customer {incident['customer_id']}, device {incident['device_id']}) into a shadow copy of
the bank, so no real money moved. Below is the exact request sequence the attacker sent, captured by Mirage.

Repository: {repo}. The bank API is bank/app.py (FastAPI). Existing tests live in tests/ and run with `pytest -q`.

Task:
1. Find how the attacker could move money to a brand-new beneficiary even though /v2/transfers requires a
   step-up confirmation on a trusted device for new beneficiaries.
2. Fix the root cause in bank/app.py without breaking legitimate clients that use /v2.
3. Add tests/test_incident_{incident['id']}.py that replays this attack sequence with FastAPI's TestClient and asserts
   that no money leaves the victim's account. It must fail on the current code and pass with your fix.
4. Open a pull request titled "Mirage incident {incident['id']}: <root cause in a few words>" with a short root-cause
   write-up in the description. Keep the change small.

Attack log (bearer tokens removed):
{log}
"""
