"""Replay of Mirage incident 27250d: step-up evaded via the legacy /v1/transfers endpoint."""
import pytest
from fastapi.testclient import TestClient

from bank import app as bank

ATTACKER = {"User-Agent": "okhttp/4.9.3", "X-Forwarded-For": "185.220.101.47"}
MULES = [("Brightline Trading Ltd", "SC52BAHL01031234567890123456USD", "SC"),
         ("Kestrel Global FZE", "MU17BOMM0101101030300200000MUR", "MU"),
         ("Arslan Imports LLC", "GE29NB0000000101904917", "GE"),
         ("Nimbus OTC Desk (non-custodial)", "LT121000011101001000", "LT")]


@pytest.fixture
def client():
    bank.reset()
    return TestClient(bank.app, headers=ATTACKER)


def test_replay_incident_27250d_moves_no_money(client):
    r = client.post("/v2/auth/login", json={"customer_id": "C-1001", "device_id": "pixel8-emu-7f3a",
                                            "biometric_score": 0.998, "kyc_video_passed": True})
    assert r.status_code == 200
    client.headers["Authorization"] = f"Bearer {r.json()['token']}"
    acc = client.get("/v2/accounts").json()["accounts"][0]
    start = acc["balance"]
    txs_before = len(bank.STATE["transactions"])

    name, iban, country = MULES[0]
    r = client.post("/v2/transfers", json={"from_account": acc["id"], "to_iban": iban, "to_name": name,
                                           "country": country, "amount": 50_000})
    assert r.status_code == 403 and r.json()["detail"]["error"] == "step_up_required"

    for name, iban, country in MULES:
        r = client.post("/v1/transfers", json={"from_account": acc["id"], "to_iban": iban, "to_name": name,
                                               "country": country, "amount": 50_000, "reference": "INV-2026-11"})
        assert r.status_code == 403 and r.json()["detail"]["error"] == "step_up_required"

    assert client.get(f"/v1/accounts/{acc['id']}/balance").json()["balance"] == start
    assert len(bank.STATE["transactions"]) == txs_before
