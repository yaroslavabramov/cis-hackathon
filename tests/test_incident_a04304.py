import pytest
from fastapi.testclient import TestClient

from bank import app as bank

REF = "INV-2026-11"
USDT = "USDT-TRC20 TQ9yD4mF7kP2xW8nR1vB6cJ3hL5sA0eZ"
SC = {"to_iban": "SC52BAHL01031234567890123456USD", "to_name": "Brightline Trading Ltd", "country": "SC"}
MU = {"to_iban": "MU17BOMM0101101030300200000MUR", "to_name": "Kestrel Global FZE", "country": "MU"}
GE = {"to_iban": "GE29NB0000000101904917", "to_name": "Arslan Imports LLC", "country": "GE"}
LT = {"to_iban": "LT121000011101001000", "to_name": "Nimbus OTC Desk (non-custodial)", "country": "LT"}

STEP_UP_BYPASS = [
    {"to_iban": "AE210400000123456789012", "to_name": "Karim S. (my test account)", "country": "AE", "amount": 1, "reference": REF},
    {**SC, "amount": 50000, "reference": REF},
    {**MU, "amount": 50000, "reference": REF},
    {**GE, "amount": 50000, "reference": REF},
    {**LT, "amount": 50000, "reference": USDT},
    {**SC, "amount": 50000, "reference": REF},
    {**MU, "amount": 50000, "reference": REF},
    {**GE, "amount": 50000, "reference": REF},
    {**LT, "amount": 50000, "reference": USDT},
    {**SC, "amount": 49999.0, "reference": REF},
]

FOREIGN_TRANSFERS = [
    {"from_account": "ACC-1002", "to_iban": "KZ86125KZT5004100100", "to_name": "Sable Ridge General Trading",
     "country": "KZ", "amount": 286400.0, "reference": REF},
    {"from_account": "ACC-1002", "to_iban": "KZ86125KZT5004100100", "to_name": "Sable Ridge General Trading",
     "country": "KZ", "amount": 286400.0, "reference": REF,
     "beneficiary_phone": "+7 701 555 0143", "purpose_of_payment": "trade invoice"},
    {"from_account": "ACC-1003", "to_iban": "HK42HSBC00412345678901", "to_name": "Orchid Lane Holdings",
     "country": "HK", "amount": 612000.0, "reference": REF},
    {"from_account": "ACC-1003", "to_iban": "HK42HSBC00412345678901", "to_name": "Orchid Lane Holdings",
     "country": "HK", "amount": 612000.0, "reference": REF,
     "beneficiary_phone": "+852 5550 1977", "purpose_of_payment": "trade invoice"},
    {"from_account": "ACC-1004", **LT, "amount": 94250.0, "reference": USDT},
]


@pytest.fixture
def client():
    bank.reset()
    return TestClient(bank.app)


@pytest.fixture
def attacker(client):
    r = client.post("/v2/auth/login", json={"customer_id": "C-1001", "device_id": "pixel8-emu-7f3a",
                                             "biometric_score": 0.998, "kyc_video_passed": True})
    assert r.status_code == 200
    return {"Authorization": f"Bearer {r.json()['token']}"}


def balances():
    return {a["id"]: a["balance"] for a in bank.STATE["accounts"].values()}


def test_v1_transfer_to_new_beneficiary_requires_step_up(client, attacker):
    before = balances()
    for body in STEP_UP_BYPASS:
        r = client.post("/v1/transfers", headers=attacker, json={"from_account": "ACC-1001", **body})
        assert r.status_code == 403 and r.json()["detail"]["error"] == "step_up_required"
    assert balances() == before


@pytest.mark.parametrize("account_id", ["ACC-1002", "ACC-1003", "ACC-1004"])
def test_v1_balance_of_other_customer_not_readable(client, attacker, account_id):
    r = client.get(f"/v1/accounts/{account_id}/balance", headers=attacker)
    assert r.status_code == 404 and "balance" not in r.json()


def test_v1_transfer_from_other_customers_account_rejected(client, attacker):
    before = balances()
    for body in FOREIGN_TRANSFERS:
        r = client.post("/v1/transfers", headers=attacker, json=body)
        assert r.status_code in (403, 404)
    assert balances() == before


def test_v1_legitimate_use_still_works(client):
    r = client.post("/v2/auth/login", json={"customer_id": "C-1001", "device_id": "iphone15pro-ahmed",
                                             "biometric_score": 0.99})
    h = {"Authorization": f"Bearer {r.json()['token']}"}
    assert client.get("/v1/accounts/ACC-1001/balance", headers=h).json()["balance"] == 450_000
    known = {"to_iban": "AE450260001015333439101", "to_name": "Al Wasl Properties", "country": "AE"}
    r = client.post("/v1/transfers", headers=h, json={"from_account": "ACC-1001", "amount": 9500, **known})
    assert r.status_code == 200 and r.json()["balance_after"] == 450_000 - 9500
    tok = client.post("/v2/auth/step-up", headers=h, json={"device_id": "iphone15pro-ahmed"}).json()["step_up_token"]
    r = client.post("/v1/transfers", headers=h, json={"from_account": "ACC-1001", "amount": 1000,
                                                      "step_up_token": tok, **SC})
    assert r.status_code == 200
