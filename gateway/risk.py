import os
import time

from . import clock

THRESHOLD = int(os.getenv("MIRAGE_THRESHOLD", "70"))
CANARY_KEY = os.getenv("MIRAGE_CANARY_KEY", "dsrt_live_7Hq2LmX9vB4kP0aZ")
WEIGHTS = {"canary": 100, "known_mule": 50, "machine_speed": 40, "amount_spike": 20, "step_up_evasion": 20, "new_device": 15,
           "unusual_hour": 15, "new_beneficiary": 15, "cross_border": 15, "legacy_endpoint": 15}
TITLES = {"canary": "Honeytoken used", "known_mule": "Known mule account", "machine_speed": "Machine speed", "amount_spike": "Amount spike",
          "step_up_evasion": "Step-up evasion", "new_device": "New device", "unusual_hour": "Unusual hour",
          "new_beneficiary": "New beneficiary", "cross_border": "Cross-border", "legacy_endpoint": "Legacy API"}


def add(session: dict, key: str, detail: str) -> bool:
    if key in session["signals"]:
        return False
    session["signals"][key] = {"key": key, "title": TITLES[key], "weight": WEIGHTS[key], "detail": detail,
                               "at": clock.label()}
    session["score"] = min(100, sum(s["weight"] for s in session["signals"].values()))
    return True


def on_login(session: dict, profile: dict):
    if session["device_id"] not in profile["known_devices"]:
        add(session, "new_device", f"{session['device_id']} has never been used by this customer")


def on_request(session: dict, headers):
    if headers.get("x-api-key") == CANARY_KEY:
        add(session, "canary", "Request carried the decoy API key planted in the mobile app bundle")


def on_transfer(session: dict, profile: dict, path: str, payload: dict):
    now = clock.now()
    hours = profile["usual_hours"]
    if hours and now.hour not in hours:
        add(session, "unusual_hour", f"{now:%H:%M}: this customer only pays between {min(hours):02d}:00 and {max(hours):02d}:59")
    iban, name = payload.get("to_iban", ""), payload.get("to_name", "")
    if iban not in profile["known_beneficiaries"]:
        add(session, "new_beneficiary", f"First ever payment to {name} ({iban[:4]}…{iban[-4:]})")
    country = payload.get("country", "AE")
    if country != profile["home_country"]:
        add(session, "cross_border", f"Outbound cross-border transfer to {country}")
    amount, avg = float(payload.get("amount", 0)), profile["avg_outgoing"] or 1
    if amount > 5 * avg:
        add(session, "amount_spike", f"AED {amount:,.0f} is {amount / avg:.0f}x this customer's usual AED {avg:,.0f}")
    if path.startswith("/v1/"):
        add(session, "legacy_endpoint", "Legacy /v1 API: the current app (v5.2) never calls it")
        if session["step_up_failed"]:
            add(session, "step_up_evasion", "Failed step-up on /v2/transfers, then retried through /v1")
    t = time.time()
    session["attempts"] = [a for a in session["attempts"] if t - a <= 5] + [t]
    if len(session["attempts"]) >= 3:
        span = session["attempts"][-1] - session["attempts"][0]
        add(session, "machine_speed", f"{len(session['attempts'])} transfer attempts in {span:.1f}s: faster than a human can tap")


ATTACKER_SIGNALS = {"new_device", "canary", "machine_speed", "step_up_evasion"}


def attacker_like(session: dict) -> bool:
    return bool(ATTACKER_SIGNALS & session["signals"].keys())
