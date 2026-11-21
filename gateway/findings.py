import json
import re

from . import clock

RULES = {
    "bola_transfer": ("critical", "Money moved out of another customer's account via {ep}",
                      "A session can only move money out of accounts its own customer owns"),
    "step_up_bypass": ("critical", "Step-up bypass via {ep}",
                       "Money to a new beneficiary requires step-up on a trusted device"),
    "bola_read": ("high", "Another customer's balance readable via {ep}",
                  "A session can only see accounts its own customer owns"),
}


def template(path: str) -> str:
    return re.sub(r"ACC-[\w-]+", "{account_id}", path)


def check(session: dict, method: str, path: str, payload: dict, status: int, profile: dict) -> list[tuple[str, float]]:
    if status != 200:
        return []
    if method == "POST" and path.endswith("/transfers"):
        amount = float(payload.get("amount", 0))
        if payload.get("from_account") not in session["owned"]:
            return [("bola_transfer", amount)]
        if payload.get("to_iban") not in profile["known_beneficiaries"] and not session["stepped_up"]:
            return [("step_up_bypass", amount)]
    m = re.match(r"/v\d/accounts/([\w-]+)/balance", path)
    if method == "GET" and m and m.group(1) not in session["owned"]:
        return [("bola_read", 0.0)]
    return []


def record(store: dict, session: dict, key: str, amount: float, method: str, path: str, payload: dict) -> dict:
    severity, title, rule = RULES[key]
    ep = f"{method} {template(path)}"
    finding = store.get(f"{key}:{ep}")
    if not finding:
        evidence = {k: v for k, v in payload.items() if k != "step_up_token"}
        finding = store[f"{key}:{ep}"] = {
            "id": f"F-{len(store) + 1}", "key": key, "severity": severity, "title": title.format(ep=ep), "rule": rule,
            "endpoint": ep, "incident": session["id"], "first_seen": clock.label(), "count": 0, "at_stake": 0.0,
            "repro": f"{method} {path}" + (f" {json.dumps(evidence)}" if evidence else "") + " → 200",
            "status": "open", "replay": {"method": method, "path": path, "body": evidence or None}}
    finding["count"] += 1
    finding["at_stake"] += amount
    return finding
