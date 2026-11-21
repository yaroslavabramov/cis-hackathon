import pytest
from fastapi.testclient import TestClient

from bank import app as bank

KNOWN = {"to_iban": "AE450260001015333439101", "to_name": "Al Wasl Properties", "country": "AE"}
NEW = {"to_iban": "SC52BAHL01031234567890123456USD", "to_name": "Brightline Trading Ltd", "country": "SC"}


@pytest.fixture
def client():
    bank.reset()
    return TestClient(bank.app)


def login(client, device="iphone15pro-ahmed"):
    r = client.post("/v2/auth/login", json={"customer_id": "C-1001", "device_id": device, "biometric_score": 0.99})
    assert r.status_code == 200
    return {"Authorization": f"Bearer {r.json()['token']}"}


def balance(client, h):
    return client.get("/v2/accounts", headers=h).json()["accounts"][0]["balance"]


def test_transfer_to_known_beneficiary(client):
    h = login(client)
    r = client.post("/v2/transfers", headers=h, json={"from_account": "ACC-1001", "amount": 9500, **KNOWN})
    assert r.status_code == 200 and r.json()["status"] == "APPROVED"
    assert balance(client, h) == 450_000 - 9500


def test_new_beneficiary_requires_step_up(client):
    h = login(client)
    r = client.post("/v2/transfers", headers=h, json={"from_account": "ACC-1001", "amount": 1000, **NEW})
    assert r.status_code == 403 and r.json()["detail"]["error"] == "step_up_required"
    assert balance(client, h) == 450_000


def test_step_up_from_trusted_device_allows_new_beneficiary(client):
    h = login(client)
    tok = client.post("/v2/auth/step-up", headers=h, json={"device_id": "iphone15pro-ahmed"}).json()["step_up_token"]
    r = client.post("/v2/transfers", headers=h, json={"from_account": "ACC-1001", "amount": 1000, "step_up_token": tok, **NEW})
    assert r.status_code == 200


def test_step_up_rejected_from_untrusted_device(client):
    h = login(client, device="pixel8-emu-7f3a")
    r = client.post("/v2/auth/step-up", headers=h, json={"device_id": "pixel8-emu-7f3a"})
    assert r.status_code == 403


def test_insufficient_funds(client):
    h = login(client)
    r = client.post("/v2/transfers", headers=h, json={"from_account": "ACC-1001", "amount": 1_000_000, **KNOWN})
    assert r.status_code == 422
