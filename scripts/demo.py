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
    pace = str(float(pace) * float(os.getenv("DEMO_PACE", "1")))
    subprocess.run([sys.executable, os.path.join(ROOT, "attacker", "attack.py"), "--pace", pace], check=False)


def snap() -> dict:
    return API.get("/api/snapshot").json()


def main():
    try:
        snap()
    except httpx.HTTPError:
        sys.exit("Start ./scripts/run.sh first")
    traffic = subprocess.Popen([sys.executable, os.path.join(ROOT, "attacker", "normal_traffic.py"), "--interval", "2"],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        run()
    finally:
        traffic.terminate()


def run():
    os.system("clear")
    title("LA MIRAGE · the attacker's laptop")
    print("Target: Desert Bank, customer C-1001.")
    wait()

    title("1 · TODAY: the bank blocks him")
    API.post("/api/reset"); API.post("/api/protection", json={"mode": "block"}); time.sleep(1.5)
    attack("0.3")
    print(f"{D}Blocked. The bank never learned how he planned to get the money out.{X}")
    wait()

    title("1b · A week later: someone quieter")
    subprocess.run([sys.executable, os.path.join(ROOT, "attacker", "attack.py"), "--quiet", "--quiet-pace", "2.7"], check=False)
    print(f"{R}{BOLD}Under the risk threshold, through the same legacy API. Real money.{X}")
    wait()

    title("2 · WITH LA MIRAGE: same first attacker")
    API.post("/api/reset"); API.post("/api/protection", json={"mode": "mirage"}); time.sleep(1.5)
    attack("0.3")
    s = snap()
    inc, found = s["incident"], s["findings"]
    print(f"{G}{BOLD}He 'stole' AED {inc['deception']['fake_stolen']:,.0f}. Real money out: AED {inc['deception']['real_lost']:,.0f} (his own probe).{X}")
    print(f"{G}{BOLD}He found {len(found)} real vulnerabilities for us.{X}")
    wait()

    title("3 · DEVIN fixes what he found, Mirage replays his exploits")
    s = snap()
    dv, sid = s["incident"]["devin"] or {}, s["incident"]["id"]
    if dv.get("url"):
        print(f"{C}Devin is fixing it live: {dv['url']}{X}")
    print(f"{D}replaying his exploits against Devin's PR for this same attack (made earlier today)...{X}")
    API.post(f"/api/incidents/{sid}/verify", json={})
    shown_live, started, printed = False, time.time(), set()
    while time.time() - started < float(os.getenv("DEMO_DEVIN_WAIT", "75")):
        s = snap()
        dv, found = s["incident"]["devin"] or {}, s["findings"]
        states = [(f.get("verify") or {}).get("state") for f in found]
        if found and all(st == "done" for st in states) and found[0].get("pr") not in printed:
            printed.add(found[0].get("pr"))
            fixed = sum(f["status"] == "verified" for f in found)
            print(f"{G}{BOLD}{fixed}/{len(found)} of his exploits blocked by the fix · main → 200, PR → 403/404 "
                  f"({found[0]['verify']['where']}){X}")
            if not s["devin_auto"] or shown_live:
                break
        if dv.get("prs") and not shown_live:
            print(f"{C}{BOLD}Live Devin PR just landed: {dv['prs'][-1]} · replaying his exploits against it...{X}")
            shown_live = True
        time.sleep(3)
    else:
        if (s["incident"]["devin"] or {}).get("url") and not shown_live:
            print(f"{D}Devin is still working live: {s['incident']['devin']['url']}{X}")
    title("Every attacker becomes our pentester.")


if __name__ == "__main__":
    main()
