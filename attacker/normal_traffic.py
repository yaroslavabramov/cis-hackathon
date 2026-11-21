"""Background traffic from ordinary night-time customers so the console shows a living bank."""
import argparse
import random
import time

import httpx

CUSTOMERS = {
    "C-1002": ("galaxys24-rahul", [("Night Bites Cafe", "AE880350000000345672211", "AE", 85),
                                   ("du Telecom", "AE550240001110000000301", "AE", 320)]),
    "C-1003": ("iphone14-olga", [("Careem Pay", "AE910240000000000776611", "AE", 140)]),
    "C-1004": ("pixel8-omar", [("Talabat", "AE440240000000000990012", "AE", 95),
                               ("Haddad Auto Repair", "AE170330000045600011223", "AE", 900)]),
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bank", default="http://127.0.0.1:8000")
    ap.add_argument("--interval", type=float, default=4.0)
    a = ap.parse_args()
    clients = {}
    while True:
        cid = random.choice(list(CUSTOMERS))
        device, payees = CUSTOMERS[cid]
        try:
            if cid not in clients:
                c = httpx.Client(base_url=a.bank, timeout=15, headers={"User-Agent": "DesertBank-iOS/5.2"})
                tok = c.post("/v2/auth/login", json={"customer_id": cid, "device_id": device,
                                                     "biometric_score": 0.99}).json()["token"]
                c.headers["Authorization"] = f"Bearer {tok}"
                clients[cid] = c
            c = clients[cid]
            acc = c.get("/v2/accounts").json()["accounts"][0]
            if random.random() < 0.6:
                name, iban, country, base = random.choice(payees)
                c.post("/v2/transfers", json={"from_account": acc["id"], "to_iban": iban, "to_name": name,
                                              "country": country, "amount": round(base * random.uniform(0.7, 1.3), 2)})
        except (httpx.HTTPError, KeyError, ValueError):
            clients.pop(cid, None)
        time.sleep(a.interval * random.uniform(0.5, 1.5))


if __name__ == "__main__":
    main()
