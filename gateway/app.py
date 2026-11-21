import asyncio
import hashlib
import json
import os
import secrets
import time
from collections import deque
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles

from . import clock, risk
from .devin import Devin
from .shadow import INTERNAL_KEY, make_shadow

REAL_URL = os.getenv("BANK_URL", "http://127.0.0.1:8001")
PROBE_LIMIT = float(os.getenv("MIRAGE_PROBE_LIMIT", "100"))
FRICTION_MIN = float(os.getenv("MIRAGE_FRICTION_MIN", "100000"))
BAIT_BALANCE = float(os.getenv("MIRAGE_BAIT_BALANCE", "1200000"))
STATIC = Path(__file__).parent / "static"


class Target:
    kind, label, status, detail = "real", "Real bank", "ready", REAL_URL

    def __init__(self, url):
        self.base_url, self.headers = url, {}


REAL = Target(REAL_URL)
SHADOW = make_shadow()
DEVIN = Devin()
HTTP = httpx.AsyncClient(timeout=30)


class Store:
    def __init__(self):
        self.reset()

    def reset(self):
        self.sessions: dict[str, dict] = {}
        self.profiles: dict[str, dict] = {}
        self.events: deque = deque(maxlen=400)
        self.requests = 0
        self.incident_id: str | None = None
        self.accounts: list[dict] = []
        self.mules: dict[str, dict] = {}
        self.protection = os.getenv("MIRAGE_PROTECTION", "on") == "on"


STORE = Store()
SUBSCRIBERS: set[asyncio.Queue] = set()
TASKS: set[asyncio.Task] = set()


@asynccontextmanager
async def lifespan(_):
    spawn(SHADOW.start())
    spawn(refresh_accounts())
    yield
    await HTTP.aclose()


app = FastAPI(title="Mirage Gateway", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=STATIC), name="static")


def spawn(coro):
    task = asyncio.create_task(coro)
    TASKS.add(task)
    task.add_done_callback(TASKS.discard)


def notify():
    for q in list(SUBSCRIBERS):
        if q.empty():
            q.put_nowait(1)


def event(kind: str, text: str, session: dict | None = None, **extra):
    STORE.events.append({"ts": clock.label(), "kind": kind, "text": text,
                         "sid": session["id"] if session else None,
                         "customer": session["name"] if session else None, **extra})
    notify()


def internal_headers(target) -> dict:
    return {"x-internal-key": INTERNAL_KEY, "x-demo-time": clock.now().isoformat(), **target.headers}


async def internal(target, method: str, path: str, **kw) -> dict:
    r = await HTTP.request(method, f"{target.base_url}{path}", headers=internal_headers(target), **kw)
    r.raise_for_status()
    return r.json()


async def profile(customer_id: str) -> dict:
    if customer_id not in STORE.profiles:
        STORE.profiles[customer_id] = await internal(REAL, "GET", f"/internal/profile/{customer_id}")
    return STORE.profiles[customer_id]


async def refresh_accounts():
    STORE.accounts = [{"name": a["owner_name"], "account": a["id"], "balance": a["balance"]}
                      for a in (await internal(REAL, "GET", "/internal/accounts"))["accounts"]]
    notify()


async def refresh_balances(session: dict):
    p = await internal(REAL, "GET", f"/internal/profile/{session['customer_id']}")
    session["balances"]["real"] = p["balance"]
    if session["diverted"]:
        p = await internal(SHADOW, "GET", f"/internal/profile/{session['customer_id']}")
    session["balances"]["attacker"] = p["balance"]


async def divert(session: dict):
    snapshot = await internal(REAL, "GET", "/internal/export", params={"customer_id": session["customer_id"]})
    main = next(iter(snapshot["accounts"].values()))
    bait = {"id": f"{main['id']}-SV", "iban": main["iban"][:-6] + "770412", "owner": session["customer_id"],
            "currency": "AED", "balance": BAIT_BALANCE, "product": "Savings Plus"}
    snapshot["accounts"][bait["id"]] = bait
    session["bait_account"] = bait["id"]
    await internal(SHADOW, "POST", "/internal/import", json=snapshot)
    session["diverted"], session["status"], session["diverted_at"] = True, "diverted", clock.label()
    session["kind"], session["first_diverted"] = "attacker", time.time()
    STORE.incident_id = session["id"]
    event("diverted", f"Session diverted into the shadow bank (risk {session['score']})", session)
    if DEVIN.configured and os.getenv("DEVIN_AUTO", "1") == "1":
        spawn(start_devin(session))


def bearer(request: Request) -> str:
    return request.headers.get("authorization", "").removeprefix("Bearer ").strip()


def redact(body: dict) -> dict:
    return {k: v for k, v in body.items() if k not in ("step_up_token",)}


def describe(path: str, status: int, data: dict) -> str:
    if status >= 400:
        detail = data.get("detail", {})
        return detail.get("error", str(detail)) if isinstance(detail, dict) else str(detail)
    if path.endswith("/transfers"):
        return f"{data.get('status')} · balance {data.get('balance_after'):,.2f}"
    if path.endswith("/login"):
        return "biometrics verified · KYC passed"
    return "ok"


@app.api_route("/v1/{path:path}", methods=["GET", "POST"])
@app.api_route("/v2/{path:path}", methods=["GET", "POST"])
async def proxy(request: Request):
    path, body = request.url.path, await request.body()
    payload = json.loads(body) if body else {}
    session = STORE.sessions.get(bearer(request))
    is_transfer = request.method == "POST" and path.endswith("/transfers")
    STORE.requests += 1

    if session:
        risk.on_request(session, request.headers)
        if is_transfer:
            risk.on_transfer(session, await profile(session["customer_id"]), path, payload)
            mule = None if session["diverted"] else STORE.mules.get(payload.get("to_iban", ""))
            if mule:
                risk.add(session, "known_mule", f"{mule['name']} received AED {mule['total']:,.0f} during incident "
                                                f"{mule['incident']} at {mule['first_seen']}")
                if STORE.protection and not risk.attacker_like(session):
                    return await protect(session, path, payload, mule)
        if session["score"] >= risk.THRESHOLD and not session["diverted"]:
            if STORE.protection:
                await divert(session)
            elif session["status"] == "monitoring":
                session["status"], session["kind"] = "would_divert", "attacker"
                STORE.incident_id = session["id"]
                event("alert", f"Risk {session['score']}: protection is OFF, traffic still hits the real bank", session)

    if path == "/v2/auth/login":
        actor = sticky_actor(payload.get("device_id"), client_ip(request))
        if actor and STORE.protection:
            return await sticky_login(request, body, payload, actor)
    if session and session["diverted"] and is_transfer:
        amount = float(payload.get("amount", 0))
        if amount >= FRICTION_MIN and not payload.get("beneficiary_phone"):
            return friction(session, path, payload)
        if amount <= PROBE_LIMIT:
            await pass_probe(session, payload)
        if payload.get("beneficiary_phone"):
            tactic(session, "friction", f"{payload['to_name']}: {payload['beneficiary_phone']}")

    target = SHADOW if session and session["diverted"] else REAL
    where = "shadow" if target is SHADOW else "real"
    headers = {k: v for k, v in request.headers.items() if k in ("authorization", "content-type", "user-agent")}
    r = await HTTP.request(request.method, f"{target.base_url}{path}", params=request.query_params, content=body,
                           headers={**headers, **internal_headers(target)})
    data = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}

    if path == "/v2/auth/login" and r.status_code == 200:
        risk.on_login(session := register(request, payload, data, await profile(payload["customer_id"])),
                      STORE.profiles[payload["customer_id"]])
    if session:
        if is_transfer and r.status_code == 403 and data.get("detail", {}).get("error") == "step_up_required":
            session["step_up_failed"] = True
        if is_transfer and r.status_code == 200 and session["diverted"]:
            session["held"].append({**redact(payload), "transfer_id": data["transfer_id"], "held_at": clock.label(),
                                    "probe": float(payload.get("amount", 0)) <= PROBE_LIMIT})
            if payload.get("from_account") == session.get("bait_account"):
                tactic(session, "bait", f"AED {float(payload['amount']):,.0f} → {payload['to_name']}")
        if session["diverted"]:
            session["last_seen"] = time.time()
        if is_transfer and r.status_code == 200 and session.get("kind") == "attacker":
            learn_mule(session, payload)
        session["log"].append({"ts": clock.label(), "method": request.method, "path": path,
                               "body": json.dumps(redact(payload)) if payload else "", "status": r.status_code,
                               "result": describe(path, r.status_code, data), "target": where})
        if is_transfer or path == "/v2/auth/login":
            await refresh_balances(session)
    if is_transfer:
        await refresh_accounts()
        event("request", f"{request.method} {path}", session, status=r.status_code, target=where,
              score=session["score"], result=describe(path, r.status_code, data))
    return Response(r.content, r.status_code, media_type=r.headers.get("content-type"))


def client_ip(request: Request) -> str:
    return request.headers.get("x-forwarded-for", request.client.host if request.client else "?")


def tactic(session: dict, key: str, item: str):
    session["tactics"].setdefault(key, []).append({"at": clock.label(), "item": item})
    notify()


def sticky_actor(device_id: str | None, ip: str) -> dict | None:
    return next((s for s in unique_sessions() if s["diverted"] and (s["device_id"] == device_id or s["ip"] == ip)), None)


async def sticky_login(request: Request, body: bytes, payload: dict, actor: dict) -> Response:
    r = await HTTP.post(f"{SHADOW.base_url}/v2/auth/login", content=body,
                        headers={"content-type": "application/json", **internal_headers(SHADOW)})
    if r.status_code == 200:
        STORE.sessions[r.json()["token"]] = actor
        tactic(actor, "sticky", f"re-login from {payload.get('device_id')} / {client_ip(request)}")
    actor["log"].append({"ts": clock.label(), "method": "POST", "path": "/v2/auth/login", "body": json.dumps(payload),
                         "status": r.status_code, "result": "re-login served by the mirage", "target": "shadow"})
    event("request", "POST /v2/auth/login (re-login, kept in mirage)", actor, status=r.status_code, target="shadow",
          score=actor["score"], result="sticky")
    return Response(r.content, r.status_code, media_type="application/json")


def friction(session: dict, path: str, payload: dict) -> JSONResponse:
    body = {"detail": {"error": "additional_info_required", "fields": ["beneficiary_phone", "purpose_of_payment"],
                       "message": "Cross-border transfers above AED 100,000 require the beneficiary's mobile number "
                                  "and purpose of payment (CBUAE AML rules)."}}
    session["log"].append({"ts": clock.label(), "method": "POST", "path": path, "body": json.dumps(redact(payload)),
                           "status": 409, "result": "additional_info_required (mirage friction)", "target": "shadow"})
    event("request", f"POST {path}", session, status=409, target="shadow", score=session["score"], result="friction")
    return JSONResponse(body, 409)


async def pass_probe(session: dict, payload: dict):
    await internal(REAL, "POST", "/internal/post-transfer", json={
        "from_account": payload["from_account"], "to_iban": payload["to_iban"], "to_name": payload["to_name"],
        "country": payload.get("country", "AE"), "amount": float(payload["amount"]), "reference": payload.get("reference", "")})
    tactic(session, "probe", f"AED {float(payload['amount']):,.0f} → {payload['to_name']} really sent")
    event("probe", f"Test transfer of AED {float(payload['amount']):,.0f} passed to the real bank so the attacker's check succeeds", session)


def unique_sessions() -> list[dict]:
    return list({s["id"]: s for s in STORE.sessions.values()}.values())


def learn_mule(session: dict, payload: dict):
    mule = STORE.mules.setdefault(payload["to_iban"], {
        "iban": payload["to_iban"], "name": payload["to_name"], "country": payload.get("country", "AE"),
        "reference": payload.get("reference", ""), "incident": session["id"], "victim": session["name"],
        "first_seen": clock.label(), "total": 0, "hits": 0})
    mule["total"] += float(payload["amount"])
    notify()


WARNING = ("We've paused this transfer. The receiving account was used tonight to receive stolen money. "
           "Desert Bank will never ask you to move money to a 'safe account'. If someone is on the phone with you "
           "right now, hang up and call the number on the back of your card.")


async def protect(session: dict, path: str, payload: dict, mule: dict) -> JSONResponse:
    hold_id = f"HLD-{secrets.token_hex(5)}"
    session["held"].append({**redact(payload), "transfer_id": hold_id, "held_at": clock.label(), "reason": "known_mule"})
    session.update(status="protected", kind="victim", protected_at=clock.label(), matched=mule["iban"])
    mule["hits"] += 1
    STORE.incident_id = session["id"]
    body = {"status": "HELD_FOR_SAFETY", "transfer_id": hold_id, "message": WARNING}
    session["log"].append({"ts": clock.label(), "method": "POST", "path": path, "body": json.dumps(redact(payload)),
                           "status": 202, "result": "HELD_FOR_SAFETY · customer warned", "target": "hold"})
    await refresh_balances(session)
    event("protect", f"Transfer to known mule {mule['name']} held, customer warned", session)
    return JSONResponse(body, 202)


def register(request: Request, payload: dict, data: dict, prof: dict) -> dict:
    sid = hashlib.sha1(data["token"].encode()).hexdigest()[:6]
    session = {"id": sid, "customer_id": payload["customer_id"], "name": prof["name"], "device_id": payload["device_id"],
               "ip": client_ip(request),
               "user_agent": request.headers.get("user-agent", ""), "started": clock.label(), "score": 0,
               "signals": {}, "attempts": [], "step_up_failed": False, "diverted": False, "diverted_at": None,
               "status": "monitoring", "held": [], "log": [], "balances": {"real": 0, "attacker": 0}, "devin": None,
               "kind": None, "protected_at": None, "matched": None, "tactics": {}, "bait_account": None,
               "first_diverted": None, "last_seen": None}
    STORE.sessions[data["token"]] = session
    return session


def by_id(sid: str) -> dict:
    for s in STORE.sessions.values():
        if s["id"] == sid:
            return s
    raise HTTPException(404, "unknown session")


def intel(session: dict) -> list[dict]:
    dest: dict[str, dict] = {}
    for h in session["held"]:
        if h.get("probe"):
            continue
        d = dest.setdefault(h["to_iban"], {"iban": h["to_iban"], "name": h["to_name"], "country": h.get("country", "AE"),
                                           "reference": h.get("reference", ""), "total": 0, "count": 0})
        d["phone"] = h.get("beneficiary_phone") or d.get("phone")
        d["total"] += h["amount"]
        d["count"] += 1
    if not session["diverted"]:
        for entry in session["log"]:
            if entry["path"].endswith("/transfers") and entry["status"] == 200:
                b = json.loads(entry["body"])
                d = dest.setdefault(b["to_iban"], {"iban": b["to_iban"], "name": b["to_name"], "country": b.get("country"),
                                                   "reference": b.get("reference", ""), "total": 0, "count": 0})
                d["total"] += b["amount"]
                d["count"] += 1
    return list(dest.values())


def deception(session: dict) -> dict:
    fake = sum(h["amount"] for h in session["held"] if not h.get("probe"))
    probes = sum(h["amount"] for h in session["held"] if h.get("probe"))
    dests = intel(session)
    engaged = (session["last_seen"] or time.time()) - session["first_diverted"] if session["first_diverted"] else 0
    probe = next((h for h in session["held"] if h.get("probe")), None)
    return {"engaged_s": round(engaged), "fake_stolen": fake, "real_lost": probes, "mules": len(dests),
            "phones": sum(1 for d in dests if d.get("phone")), "relogins": len(session["tactics"].get("sticky", [])),
            "probe_to": {"name": probe["to_name"], "iban": probe["to_iban"]} if probe else None}


def incident_view(session: dict) -> dict:
    endpoints = list(dict.fromkeys(f"{e['method']} {e['path']}" for e in session["log"]))
    return {**{k: session[k] for k in ("id", "customer_id", "name", "device_id", "ip", "user_agent", "started", "score",
                                       "diverted", "diverted_at", "status", "balances", "devin", "kind",
                                       "protected_at", "matched")},
            "mule": STORE.mules.get(session["matched"]) if session["matched"] else None,
            "signals": list(session["signals"].values()), "held": session["held"], "tactics": session["tactics"],
            "deception": deception(session),
            "held_total": sum(h["amount"] for h in session["held"] if not h.get("probe")), "destinations": intel(session),
            "endpoints": endpoints, "log": session["log"][-30:]}


def snapshot() -> dict:
    incident = next((s for s in unique_sessions() if s["id"] == STORE.incident_id), None)
    return {"clock": clock.now().isoformat(), "protection": STORE.protection, "threshold": risk.THRESHOLD,
            "shadow": {"kind": SHADOW.kind, "label": SHADOW.label, "status": SHADOW.status, "detail": SHADOW.detail},
            "devin_configured": DEVIN.configured, "devin_reference": os.getenv("DEVIN_REFERENCE_PR", ""),
            "stats": {"sessions": len(unique_sessions()), "requests": STORE.requests,
                      "diverted": sum(s["diverted"] for s in unique_sessions()),
                      "held": sum(h["amount"] for s in unique_sessions() for h in s["held"])},
            "sessions": sorted(({"id": s["id"], "name": s["name"], "device_id": s["device_id"], "score": s["score"],
                                 "status": s["status"]} for s in unique_sessions()), key=lambda s: -s["score"]),
            "events": list(STORE.events)[-80:], "accounts": STORE.accounts, "mules": list(STORE.mules.values()),
            "incidents": [incident_view(s) for s in unique_sessions() if s["kind"]], "incident": incident_view(incident) if incident else None}


async def start_devin(session: dict):
    session["devin"] = {"status": "starting", "url": None, "prs": [], "started_at": clock.label()}
    notify()
    try:
        created = await DEVIN.start({**incident_view(session), "log": session["log"]})
        session["devin"].update(status=created.get("status", "new"), url=created.get("url"), id=created["session_id"])
        event("devin", "Devin started investigating the attack", session, url=created.get("url"))
        while True:
            await asyncio.sleep(10)
            info = await DEVIN.get(created["session_id"])
            prs = [p["pr_url"] for p in info.get("pull_requests") or []]
            changed = prs != session["devin"]["prs"] or info.get("status") != session["devin"]["status"]
            session["devin"].update(status=info.get("status"), prs=prs, detail=info.get("status_detail"))
            if changed:
                event("devin", f"Devin: {info.get('status')}" + (f" · PR {prs[-1]}" if prs else ""), session)
            if prs or info.get("status") in ("exit", "error", "suspended"):
                return
    except Exception as e:
        session["devin"].update(status="error", detail=f"{type(e).__name__}: {e}"[:200])
        event("devin", "Devin request failed", session)


@app.get("/")
def root():
    return RedirectResponse("/console")


@app.get("/console")
def console():
    return FileResponse(STATIC / "index.html")


@app.get("/api/snapshot")
def api_snapshot():
    return snapshot()


@app.get("/api/stream")
async def api_stream(request: Request):
    q: asyncio.Queue = asyncio.Queue(maxsize=1)
    SUBSCRIBERS.add(q)
    spawn(refresh_accounts())

    async def gen():
        try:
            yield f"data: {json.dumps(snapshot())}\n\n"
            while not await request.is_disconnected():
                try:
                    await asyncio.wait_for(q.get(), 10)
                    await asyncio.sleep(0.05)
                    yield f"data: {json.dumps(snapshot())}\n\n"
                except TimeoutError:
                    yield ": ping\n\n"
        finally:
            SUBSCRIBERS.discard(q)

    return StreamingResponse(gen(), media_type="text/event-stream")


@app.post("/api/protection")
async def api_protection(body: dict):
    STORE.protection = bool(body.get("on"))
    event("system", f"Protection {'ON' if STORE.protection else 'OFF'}")
    return {"protection": STORE.protection}


@app.post("/api/reset")
async def api_reset():
    for task in list(TASKS):
        if task.get_coro().__name__ == "start_devin":
            task.cancel()
    protection = STORE.protection
    STORE.reset()
    STORE.protection = protection
    clock.reset()
    await internal(REAL, "POST", "/internal/reset")
    if SHADOW.status == "ready":
        await internal(SHADOW, "POST", "/internal/reset")
    await refresh_accounts()
    event("system", "Demo reset")
    return {"ok": True}


@app.post("/api/incidents/{sid}/devin")
async def api_devin(sid: str):
    if not DEVIN.configured:
        raise HTTPException(400, "Set DEVIN_API_KEY and DEVIN_ORG_ID")
    spawn(start_devin(by_id(sid)))
    return {"ok": True}


@app.post("/api/incidents/{sid}/release")
async def api_release(sid: str):
    session = by_id(sid)
    for h in (h for h in session["held"] if not h.get("probe")):
        await internal(REAL, "POST", "/internal/post-transfer", json={
            "from_account": h["from_account"], "to_iban": h["to_iban"], "to_name": h["to_name"],
            "country": h.get("country", "AE"), "amount": h["amount"], "reference": h.get("reference", "")})
    session["status"] = "released"
    await refresh_balances(session)
    await refresh_accounts()
    event("release", f"Customer confirmed: {len(session['held'])} held transfers posted to the real ledger", session)
    return {"ok": True}


@app.post("/api/incidents/{sid}/fraud")
async def api_fraud(sid: str):
    session = by_id(sid)
    session["status"] = "confirmed_fraud"
    text = (f"Scam confirmed: transfer to {STORE.mules[session['matched']]['name']} voided" if session["kind"] == "victim"
            else f"Fraud confirmed: {len(intel(session))} destination accounts reported, held transfers voided")
    event("fraud", text, session)
    return {"ok": True}


@app.get("/api/incidents/{sid}/report")
def api_report(sid: str):
    session = by_id(sid)
    view = incident_view(session)
    report = {"incident": sid, "generated_at": clock.now().isoformat(), "customer": view["name"],
              "device": view["device_id"], "ip": view["ip"], "user_agent": view["user_agent"],
              "risk_score": view["score"], "signals": view["signals"], "diverted_at": view["diverted_at"],
              "money_protected_aed": view["held_total"], "destination_accounts": view["destinations"],
              "attack_log": session["log"], "devin": view["devin"]}
    return JSONResponse(report, headers={"Content-Disposition": f"attachment; filename=mirage-incident-{sid}.json"})
