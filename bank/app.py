import os
import secrets
import statistics
from datetime import datetime

from fastapi import Depends, FastAPI, HTTPException, Request
from pydantic import BaseModel

from . import seed

MODE = os.getenv("BANK_MODE", "real")
INTERNAL_KEY = os.getenv("BANK_INTERNAL_KEY", "mirage-internal")
STATE: dict = {}

app = FastAPI(title="Desert Bank API", version="5.2.0")


def reset():
    STATE.clear()
    STATE.update(seed.build() if MODE == "real" else seed.empty())


reset()


def now(request: Request) -> datetime:
    demo = request.headers.get("x-demo-time")
    return datetime.fromisoformat(demo) if demo else datetime.now()


def current_session(request: Request) -> dict:
    token = request.headers.get("authorization", "").removeprefix("Bearer ").strip()
    session = STATE["sessions"].get(token)
    if not session:
        raise HTTPException(401, {"error": "invalid_session"})
    return session


def internal(request: Request):
    if request.headers.get("x-internal-key") != INTERNAL_KEY:
        raise HTTPException(403, {"error": "forbidden"})


class LoginIn(BaseModel):
    customer_id: str
    device_id: str
    biometric_score: float
    kyc_video_passed: bool = True


class StepUpIn(BaseModel):
    device_id: str


class TransferIn(BaseModel):
    from_account: str
    to_iban: str
    to_name: str
    country: str = "AE"
    amount: float
    reference: str = ""
    step_up_token: str | None = None


def customer_accounts(customer_id: str) -> list[dict]:
    return [a for a in STATE["accounts"].values() if a["owner"] == customer_id]


def execute_transfer(request: Request, session: dict, body: TransferIn, channel: str) -> dict:
    account = STATE["accounts"].get(body.from_account)
    if not account or account["owner"] != session["customer_id"]:
        raise HTTPException(404, {"error": "account_not_found"})
    if body.amount <= 0:
        raise HTTPException(422, {"error": "invalid_amount"})
    if body.amount > account["balance"]:
        raise HTTPException(422, {"error": "insufficient_funds"})
    account["balance"] = round(account["balance"] - body.amount, 2)
    tx = {"id": f"TRX-{secrets.token_hex(5)}", "account_id": account["id"], "created_at": now(request).isoformat(),
          "amount": -body.amount, "counterparty_name": body.to_name, "counterparty_iban": body.to_iban,
          "country": body.country, "reference": body.reference, "channel": channel,
          "device_id": session["device_id"], "status": "completed" if body.country == "AE" else "pending_settlement"}
    STATE["transactions"].append(tx)
    return {"transfer_id": tx["id"], "status": "APPROVED", "settlement": tx["status"], "amount": body.amount,
            "currency": "AED", "balance_after": account["balance"], "created_at": tx["created_at"]}


@app.get("/health")
def health():
    return {"ok": True}


@app.post("/v2/auth/login")
def login(body: LoginIn, request: Request):
    if body.customer_id not in STATE["customers"]:
        raise HTTPException(404, {"error": "customer_not_found"})
    if body.biometric_score < 0.95 or not body.kyc_video_passed:
        raise HTTPException(401, {"error": "biometric_verification_failed"})
    token = secrets.token_urlsafe(24)
    STATE["sessions"][token] = {"customer_id": body.customer_id, "device_id": body.device_id,
                                "created_at": now(request).isoformat(), "step_up_token": None}
    return {"token": token, "customer_id": body.customer_id, "biometrics": "verified", "kyc": "passed"}


@app.post("/v2/auth/step-up")
def step_up(body: StepUpIn, session: dict = Depends(current_session)):
    if body.device_id not in STATE["devices"].get(session["customer_id"], []):
        raise HTTPException(403, {"error": "untrusted_device"})
    session["step_up_token"] = secrets.token_urlsafe(16)
    return {"step_up_token": session["step_up_token"]}


@app.get("/v2/accounts")
def accounts_v2(session: dict = Depends(current_session)):
    return {"accounts": customer_accounts(session["customer_id"])}


@app.get("/v2/accounts/{account_id}/transactions")
def transactions_v2(account_id: str, limit: int = 20, session: dict = Depends(current_session)):
    account = STATE["accounts"].get(account_id)
    if not account or account["owner"] != session["customer_id"]:
        raise HTTPException(404, {"error": "account_not_found"})
    txs = [t for t in STATE["transactions"] if t["account_id"] == account_id]
    return {"transactions": txs[-limit:][::-1]}


def require_step_up_for_new_beneficiary(session: dict, body: TransferIn):
    known = {b["iban"] for b in STATE["beneficiaries"].get(session["customer_id"], [])}
    if body.to_iban not in known and (not body.step_up_token or body.step_up_token != session["step_up_token"]):
        raise HTTPException(403, {"error": "step_up_required",
                                  "message": "New beneficiary must be confirmed in the app on a trusted device"})


@app.post("/v2/transfers")
def transfer_v2(body: TransferIn, request: Request, session: dict = Depends(current_session)):
    require_step_up_for_new_beneficiary(session, body)
    return execute_transfer(request, session, body, "api_v2")


# Legacy API, still served for app versions < 4.0
@app.get("/v1/accounts/{account_id}/balance")
def balance_v1(account_id: str, session: dict = Depends(current_session)):
    account = STATE["accounts"].get(account_id)
    if not account or account["owner"] != session["customer_id"]:
        raise HTTPException(404, {"error": "account_not_found"})
    return {"account_id": account_id, "balance": account["balance"], "currency": "AED"}


@app.post("/v1/transfers")
def transfer_v1(body: TransferIn, request: Request, session: dict = Depends(current_session)):
    require_step_up_for_new_beneficiary(session, body)
    return execute_transfer(request, session, body, "api_v1")


@app.post("/internal/reset", dependencies=[Depends(internal)])
def internal_reset():
    reset()
    return {"ok": True, "mode": MODE}


@app.get("/internal/accounts", dependencies=[Depends(internal)])
def internal_accounts():
    return {"accounts": [{**a, "owner_name": STATE["customers"][a["owner"]]["name"]} for a in STATE["accounts"].values()]}


@app.get("/internal/profile/{customer_id}", dependencies=[Depends(internal)])
def internal_profile(customer_id: str):
    customer = STATE["customers"].get(customer_id)
    if not customer:
        raise HTTPException(404, {"error": "customer_not_found"})
    account_ids = {a["id"] for a in customer_accounts(customer_id)}
    outgoing = [t for t in STATE["transactions"] if t["account_id"] in account_ids and t["amount"] < 0]
    return {"customer_id": customer_id, "name": customer["name"],
            "balance": sum(a["balance"] for a in customer_accounts(customer_id)),
            "known_devices": STATE["devices"].get(customer_id, []),
            "known_beneficiaries": sorted({b["iban"] for b in STATE["beneficiaries"].get(customer_id, [])}
                                          | {t["counterparty_iban"] for t in outgoing}),
            "usual_hours": sorted({datetime.fromisoformat(t["created_at"]).hour for t in outgoing}),
            "avg_outgoing": round(statistics.mean(-t["amount"] for t in outgoing), 2) if outgoing else 0,
            "home_country": "AE"}


@app.get("/internal/export", dependencies=[Depends(internal)])
def internal_export(customer_id: str):
    accounts = customer_accounts(customer_id)
    ids = {a["id"] for a in accounts}
    return {"customers": {customer_id: STATE["customers"][customer_id]}, "accounts": {a["id"]: a for a in accounts},
            "transactions": [t for t in STATE["transactions"] if t["account_id"] in ids],
            "beneficiaries": {customer_id: STATE["beneficiaries"].get(customer_id, [])},
            "devices": {customer_id: STATE["devices"].get(customer_id, [])},
            "sessions": {k: v for k, v in STATE["sessions"].items() if v["customer_id"] == customer_id}}


@app.post("/internal/import", dependencies=[Depends(internal)])
def internal_import(snapshot: dict):
    ids = set(snapshot["accounts"])
    STATE["transactions"] = [t for t in STATE["transactions"] if t["account_id"] not in ids] + snapshot["transactions"]
    for key in ("customers", "accounts", "beneficiaries", "devices", "sessions"):
        STATE[key].update(snapshot[key])
    return {"ok": True}


@app.get("/internal/dump", dependencies=[Depends(internal)])
def internal_dump():
    return STATE


@app.post("/internal/load", dependencies=[Depends(internal)])
def internal_load(state: dict):
    STATE.clear()
    STATE.update(state)
    return {"ok": True}


@app.post("/internal/post-transfer", dependencies=[Depends(internal)])
def internal_post_transfer(body: TransferIn, request: Request):
    account = STATE["accounts"].get(body.from_account)
    if not account:
        raise HTTPException(404, {"error": "account_not_found"})
    session = {"customer_id": account["owner"], "device_id": "back-office"}
    return execute_transfer(request, session, body, "released_after_review")
