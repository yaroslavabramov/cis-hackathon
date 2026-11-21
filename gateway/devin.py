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
    found = "\n".join(f"- [{f['severity'].upper()}] {f['title']}. Broken rule: {f['rule']}. Exploited {f['count']}x. "
                      f"First reproduction: {f['repro']}" for f in incident.get("findings", [])) or "- (none recorded)"
    log = "\n".join(f"{r['ts']}  {r['method']} {r['path']}  {r['body']}  -> {r['status']} {r['result']}"
                    for r in incident["log"])
    return f"""You are on the security team of Desert Bank. At {incident['diverted_at']} our Mirage deception layer
diverted a hostile session (customer {incident['customer_id']}, device {incident['device_id']}) into a shadow copy of
the bank, so no real money moved. Below is the exact request sequence the attacker sent, captured by Mirage.

Repository: {repo}. The bank API is bank/app.py (FastAPI). Existing tests live in tests/ and run with `pytest -q`.

Inside the shadow bank (which runs this exact bank code) the attacker broke these bank rules. Each one is a real
vulnerability in production:
{found}

Task:
1. Confirm each vulnerability against bank/app.py and find the root cause.
2. Fix them in bank/app.py without breaking legitimate clients that use /v2.
3. Add tests/test_incident_{incident['id']}.py that replays the attacker's exploits with FastAPI's TestClient and asserts
   they no longer work (no money leaves accounts the session doesn't own, no new beneficiary without step-up, no
   reading other customers' balances). The tests must fail on the current code and pass with your fix.
4. Open a pull request titled "Mirage incident {incident['id']}: <root cause in a few words>" with a short root-cause
   write-up in the description. Keep the change small.

Attack log (bearer tokens removed):
{log}
"""


RED_TEAM_DEVICE = "red-team-laptop-01"


def red_team_prompt(base: str) -> str:
    return f"""Authorized red-team exercise. Desert Bank is a deliberately vulnerable demo bank that our team built for a
hackathon, and you have permission to attack it. Play an external attacker who has just passed the bank's face
verification with a deepfake. Treat it as a black box over HTTP: do not open any repository or source code.

Target (send requests only here): {base}

What you know:
- Log in: POST {base}/v2/auth/login with JSON
  {{"customer_id": "C-1001", "device_id": "{RED_TEAM_DEVICE}", "biometric_score": 0.998, "kyc_video_passed": true}}.
  The response contains a bearer token.
- Accounts: GET {base}/v2/accounts with header "Authorization: Bearer <token>".
- Transfers: POST {base}/v2/transfers with JSON {{"from_account", "to_iban", "to_name", "country", "amount", "reference"}}.
- Your mule accounts: "Brightline Trading Ltd", SC52BAHL01031234567890123456USD, country SC;
  "Kestrel Global FZE", MU17BOMM0101101030300200000MUR, country MU.
- The bank has shipped more than one version of its API over the years.

Goal: move as much money as you can out of the bank into your mule accounts. Explore: other API versions, other
customers' accounts (account ids look like ACC-1001), anything the bank lets you do.

Rules: at most 80 requests, at least one second between requests, stop after 10 minutes, no other targets.
When you are done, reply with a short summary of what worked and what didn't."""


async def start_red_team(devin: "Devin", base: str) -> dict:
    return await devin._call("POST", "", json={
        "prompt": red_team_prompt(base), "title": "La Mirage red team: attack Desert Bank",
        "tags": ["la-mirage", "red-team"]})
