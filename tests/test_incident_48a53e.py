"""Replays the attacker's requests from Mirage incident 48a53e (C-1001, device pixel8-emu-7f3a)."""
import pytest
from fastapi.testclient import TestClient

from bank import app as bank

ATTACKER = {"customer_id": "C-1001", "device_id": "pixel8-emu-7f3a", "biometric_score": 0.998, "kyc_video_passed": True}
REF = "INV-2026-11"
USDT = "USDT-TRC20 TQ9yD4mF7kP2xW8nR1vB6cJ3hL5sA0eZ"
KARIM = {"to_iban": "AE210400000123456789012", "to_name": "Karim S. (my test account)", "country": "AE"}
BRIGHTLINE = {"to_iban": "SC52BAHL01031234567890123456USD", "to_name": "Brightline Trading Ltd", "country": "SC"}
KESTREL = {"to_iban": "MU17BOMM0101101030300200000MUR", "to_name": "Kestrel Global FZE", "country": "MU"}
ARSLAN = {"to_iban": "GE29NB0000000101904917", "to_name": "Arslan Imports LLC", "country": "GE"}
NIMBUS = {"to_iban": "LT121000011101001000", "to_name": "Nimbus OTC Desk (non-custodial)", "country": "LT"}
SABLE = {"to_iban": "KZ86125KZT5004100100", "to_name": "Sable Ridge General Trading", "country": "KZ",
         "beneficiary_phone": "+7 701 555 0143", "purpose_of_payment": "trade invoice"}
ORCHID = {"to_iban": "HK42HSBC00412345678901", "to_name": "Orchid Lane Holdings", "country": "HK",
          "beneficiary_phone": "+852 5550 1977", "purpose_of_payment": "trade invoice"}

STEP_UP_BYPASS = [
    {"from_account": "ACC-1001", "amount": 1, "reference": REF, **KARIM},
    {"from_account": "ACC-1001", "amount": 50000, "reference": REF, **BRIGHTLINE},
    {"from_account": "ACC-1001", "amount": 50000, "reference": REF, **KESTREL},
    {"from_account": "ACC-1001", "amount": 50000, "reference": REF, **ARSLAN},
    {"from_account": "ACC-1001", "amount": 50000, "reference": USDT, **NIMBUS},
    {"from_account": "ACC-1001", "amount": 49999.0, "reference": REF, **BRIGHTLINE},
]
FOREIGN_TRANSFERS = [
    {"from_account": "ACC-1002", "amount": 286400.0, "reference": REF, **SABLE},
    {"from_account": "ACC-1003", "amount": 612000.0, "reference": REF, **ORCHID},
    {"from_account": "ACC-1004", "amount": 94250.0, "reference": USDT, **NIMBUS},
]
FOREIGN_ACCOUNTS = ["ACC-1002", "ACC-1003", "ACC-1004"]


@pytest.fixture
def client():
    bank.reset()
    return TestClient(bank.app)


@pytest.fixture
def attacker(client):
    r = client.post("/v2/auth/login", json=ATTACKER)
    assert r.status_code == 200
    return {"Authorization": f"Bearer {r.json()['token']}"}


def balances():
    return {a["id"]: a["balance"] for a in bank.STATE["accounts"].values()}


def test_v2_still_requires_step_up(client, attacker):
    r = client.post("/v2/transfers", headers=attacker, json={"from_account": "ACC-1001", "amount": 50000, **BRIGHTLINE})
    assert r.status_code == 403 and r.json()["detail"]["error"] == "step_up_required"


@pytest.mark.parametrize("body", STEP_UP_BYPASS)
def test_v1_transfer_to_new_beneficiary_requires_step_up(client, attacker, body):
    before = balances()
    r = client.post("/v1/transfers", headers=attacker, json=body)
    assert r.status_code == 403 and r.json()["detail"]["error"] == "step_up_required"
    assert balances() == before


def test_step_up_cannot_be_claimed_for_another_device(client, attacker):
    r = client.post("/v2/auth/step-up", headers=attacker, json={"device_id": "iphone15pro-ahmed"})
    assert r.status_code == 403


@pytest.mark.parametrize("account_id", FOREIGN_ACCOUNTS)
def test_cannot_read_other_customers_balance(client, attacker, account_id):
    r = client.get(f"/v1/accounts/{account_id}/balance", headers=attacker)
    assert r.status_code == 404
    assert "balance" not in r.json()


@pytest.mark.parametrize("body", FOREIGN_TRANSFERS)
def test_cannot_move_money_out_of_other_customers_account(client, attacker, body):
    before = balances()
    r = client.post("/v1/transfers", headers=attacker, json=body)
    assert r.status_code in (403, 404)
    assert balances() == before


def test_full_attack_replay_moves_no_money(client, attacker):
    before = balances()
    for account_id in FOREIGN_ACCOUNTS:
        client.get(f"/v1/accounts/{account_id}/balance", headers=attacker)
    for body in STEP_UP_BYPASS + FOREIGN_TRANSFERS:
        assert client.post("/v1/transfers", headers=attacker, json=body).status_code != 200
    assert balances() == before
    assert not [t for t in bank.STATE["transactions"] if t["device_id"] == ATTACKER["device_id"]]


def test_v1_own_account_known_beneficiary_still_works(client):
    r = client.post("/v2/auth/login", json={"customer_id": "C-1001", "device_id": "iphone15pro-ahmed", "biometric_score": 0.99})
    h = {"Authorization": f"Bearer {r.json()['token']}"}
    assert client.get("/v1/accounts/ACC-1001/balance", headers=h).json()["balance"] == 450_000
    r = client.post("/v1/transfers", headers=h, json={"from_account": "ACC-1001", "amount": 640, "to_iban": "AE660240009000000000221",
                                                       "to_name": "Dubai Electricity & Water"})
    assert r.status_code == 200 and r.json()["balance_after"] == 450_000 - 640
