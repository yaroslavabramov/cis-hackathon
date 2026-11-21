import random
from datetime import datetime, timedelta

CUSTOMERS = [
    {"id": "C-1001", "name": "Ahmed Al Mansoori", "account": "ACC-1001", "iban": "AE070331234567890123456",
     "balance": 450_000.00, "devices": ["iphone15pro-ahmed"], "hours": range(8, 23),
     "beneficiaries": [("Al Wasl Properties", "AE450260001015333439101", 9_500, 30),
                       ("Fatima Al Mansoori", "AE120350000000123987654", 3_000, 30),
                       ("Dubai Electricity & Water", "AE660240009000000000221", 640, 30),
                       ("Khalid Rahman", "AE330330000019100099822", 450, 9)]},
    {"id": "C-1002", "name": "Rahul Menon", "account": "ACC-1002", "iban": "AE210260001234500987612",
     "balance": 38_420.50, "devices": ["galaxys24-rahul"], "hours": list(range(0, 24)),
     "beneficiaries": [("Anjali Menon", "IN00HDFC0001234567890", 2_500, 30),
                       ("du Telecom", "AE550240001110000000301", 320, 30),
                       ("Night Bites Cafe", "AE880350000000345672211", 85, 3)]},
    {"id": "C-1003", "name": "Olga Petrova", "account": "ACC-1003", "iban": "AE580330000012398765001",
     "balance": 72_115.00, "devices": ["iphone14-olga"], "hours": list(range(0, 3)) + list(range(9, 24)),
     "beneficiaries": [("Marina Yacht Club", "AE290260001019988776655", 1_200, 14),
                       ("Careem Pay", "AE910240000000000776611", 140, 2)]},
    {"id": "C-1004", "name": "Omar Haddad", "account": "ACC-1004", "iban": "AE930350000099887766554",
     "balance": 15_980.75, "devices": ["pixel8-omar"], "hours": list(range(0, 24)),
     "beneficiaries": [("Haddad Auto Repair", "AE170330000045600011223", 900, 10),
                       ("Talabat", "AE440240000000000990012", 95, 2)]},
]


def build(today: datetime | None = None) -> dict:
    rnd = random.Random(42)
    today = (today or datetime.now()).replace(hour=0, minute=0, second=0, microsecond=0)
    state = {"customers": {}, "accounts": {}, "transactions": [], "beneficiaries": {}, "sessions": {}, "devices": {}}
    for c in CUSTOMERS:
        state["customers"][c["id"]] = {"id": c["id"], "name": c["name"]}
        state["accounts"][c["account"]] = {"id": c["account"], "iban": c["iban"], "owner": c["id"],
                                           "currency": "AED", "balance": c["balance"]}
        state["devices"][c["id"]] = list(c["devices"])
        state["beneficiaries"][c["id"]] = [{"name": n, "iban": i, "country": i[:2]} for n, i, _, _ in c["beneficiaries"]]
        hours = list(c["hours"])
        for name, iban, amount, every in c["beneficiaries"]:
            for day in range(90, 0, -every):
                ts = today - timedelta(days=day) + timedelta(hours=rnd.choice(hours), minutes=rnd.randint(0, 59))
                state["transactions"].append({
                    "id": f"TRX-{rnd.getrandbits(40):010x}", "account_id": c["account"], "created_at": ts.isoformat(),
                    "amount": -round(amount * rnd.uniform(0.85, 1.15), 2), "counterparty_name": name,
                    "counterparty_iban": iban, "country": iban[:2], "reference": "", "channel": "app_v2",
                    "device_id": c["devices"][0], "status": "completed"})
    state["transactions"].sort(key=lambda t: t["created_at"])
    return state


def empty() -> dict:
    return {"customers": {}, "accounts": {}, "transactions": [], "beneficiaries": {}, "sessions": {}, "devices": {}}
