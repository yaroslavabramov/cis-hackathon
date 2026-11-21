"""A real customer coached by a phone scammer: his own phone, his own FaceID, his own step-up."""
import argparse
import time

import httpx

R, G, Y, D, B, X = "\033[91m", "\033[92m", "\033[93m", "\033[2m", "\033[1m", "\033[0m"


def say(msg: str, delay: float = 0.8):
    print(msg, flush=True)
    time.sleep(delay)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bank", default="http://127.0.0.1:8000")
    ap.add_argument("--amount", type=float, default=20_000)
    a = ap.parse_args()
    bank = httpx.Client(base_url=a.bank, timeout=30, headers={"User-Agent": "DesertBank-Android/5.2"})

    print(f"\n{B}  Rahul Menon, 02:03. On the phone with 'Desert Bank security'.{X}\n")
    say(f'{D}  scammer: "Your account is compromised. Move your savings to the safe account I give you."{X}', 1.2)
    r = bank.post("/v2/auth/login", json={"customer_id": "C-1002", "device_id": "galaxys24-rahul", "biometric_score": 0.99})
    bank.headers["Authorization"] = f"Bearer {r.json()['token']}"
    say(f"{G}  FaceID ✓ (it really is Rahul, on his own phone){X}")
    acc = bank.get("/v2/accounts").json()["accounts"][0]
    say(f"  balance AED {acc['balance']:,.2f}")
    tok = bank.post("/v2/auth/step-up", json={"device_id": "galaxys24-rahul"}).json()["step_up_token"]
    say(f"{G}  step-up confirmed on his trusted device ✓{X}")
    r = bank.post("/v2/transfers", json={"from_account": acc["id"], "to_iban": "MU17BOMM0101101030300200000MUR",
                                         "to_name": "Kestrel Global FZE", "country": "MU", "amount": a.amount,
                                         "reference": "safe account per security officer", "step_up_token": tok})
    d = r.json()
    if r.status_code == 202:
        print(f"\n{Y}{B}  !! {d['status']}{X}\n{Y}  {d['message']}{X}\n")
    else:
        print(f"\n{R}{B}  {d.get('status', r.status_code)}: AED {a.amount:,.0f} sent to the scammer.{X}\n")


if __name__ == "__main__":
    main()
