"""Stage walkthrough. This terminal is the attacker's laptop; the browser is the bank's Mirage console.
Every step waits for Enter. Needs ./scripts/run.sh running (DEVIN_AUTO=1 for a live Devin run)."""
import os
import subprocess
import sys
import time

import httpx

B = "http://127.0.0.1:8000"
API = httpx.Client(base_url=B, timeout=30)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
C, D, G, R, BOLD, X = "\033[96m", "\033[2m", "\033[92m", "\033[91m", "\033[1m", "\033[0m"


def title(text: str):
    print(f"\n{BOLD}{C}━━ {text} {'━' * max(0, 60 - len(text))}{X}\n", flush=True)


def wait(prompt: str = "Enter ▸"):
    input(f"{D}{prompt}{X}")


def attack(pace: str):
    subprocess.run([sys.executable, os.path.join(ROOT, "attacker", "attack.py"), "--pace", pace], check=False)


def snap() -> dict:
    return API.get("/api/snapshot").json()


def main():
    try:
        snap()
    except httpx.HTTPError:
        sys.exit("Start ./scripts/run.sh first")
    os.system("clear")
    title("MIRAGE · the attacker's laptop")
    print("Target: Desert Bank. Biometrics, KYC and auth all pass with a deepfake.")
    wait()

    title("1 · TODAY: the bank without Mirage")
    API.post("/api/reset"); API.post("/api/protection", json={"on": False}); time.sleep(1.5)
    attack("0.2")
    print(f"{R}{BOLD}Real money gone. Four customers drained through a forgotten legacy API.{X}")
    wait()

    title("2 · WITH MIRAGE: try us")
    API.post("/api/reset"); API.post("/api/protection", json={"on": True}); time.sleep(1.5)
    attack("0.3")
    s = snap()
    inc, found = s["incident"], s["findings"]
    print(f"{G}{BOLD}He 'stole' AED {inc['deception']['fake_stolen']:,.0f}. Real money out: AED {inc['deception']['real_lost']:,.0f} (his own probe).{X}")
    print(f"{G}{BOLD}He found {len(found)} real vulnerabilities for us.{X}")
    wait()

    title("3 · DEVIN fixes what he found, Mirage replays his exploits")
    started, verify_sent = time.time(), False
    while time.time() - started < 240:
        s = snap()
        dv, found = s["incident"]["devin"] or {}, s["findings"]
        states = [(f.get("verify") or {}).get("state") for f in found]
        if found and all(st == "done" for st in states):
            fixed = sum(f["status"] == "verified" for f in found)
            print(f"\n{G}{BOLD}{fixed}/{len(found)} of his exploits blocked by the fix ({found[0]['verify']['where']}).{X}")
            break
        if not s["devin_auto"] or (not dv and time.time() - started > 20) or time.time() - started > 150:
            if not verify_sent:
                print(f"{D}replaying his exploits against an earlier Devin PR for the same attack...{X}")
                API.post(f"/api/incidents/{s['incident']['id']}/verify", json={})
                verify_sent = True
        print(f"{D}  devin: {dv.get('status', 'waiting')} · PR: {(dv.get('prs') or ['-'])[-1]} · replay: {states}{X}", flush=True)
        time.sleep(5)
    title("Every attacker becomes our pentester.")


if __name__ == "__main__":
    main()
