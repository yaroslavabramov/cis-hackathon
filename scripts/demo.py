"""Stage walkthrough. This terminal is the attacker's laptop; the browser is the bank's Mirage console.
Every step waits for Enter. Needs ./scripts/run.sh running (DEVIN_AUTO=1 for a live Devin run)."""
import os
import re
import subprocess
import sys
import threading
import time

import httpx

B = "http://127.0.0.1:8000"
API = httpx.Client(base_url=B, timeout=30)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
C, D, G, R, BOLD, X = "\033[96m", "\033[2m", "\033[92m", "\033[91m", "\033[1m", "\033[0m"


COLORS = {"92": "green", "91": "red", "93": "yellow", "96": "cyan", "2": "dim"}


def stage(text: str, color: str = ""):
    try:
        API.post("/api/stage", json={"line": {"text": text, "color": color}})
    except httpx.HTTPError:
        pass


def say(text: str, ansi: str = "", color: str = ""):
    print(f"{ansi}{text}{X}", flush=True)
    stage(text, color)


def title(text: str):
    print(f"\n{BOLD}{C}━━ {text} {'━' * max(0, 60 - len(text))}{X}\n", flush=True)
    stage("")
    stage(f"━━ {text}", "title")


NEXT_HINTS = iter(["next: 1 · the bank blocks him", "next: 1b · a week later, someone quieter",
                   "next: 2 · same attacker, La Mirage on", "next: 3 · Devin fixes, we replay", "next: the end"])


def wait(prompt: str = "Enter ▸"):
    """Advance on → / Space in the stage page, or Enter in this terminal."""
    start = API.get("/api/stage").json()["next"]
    API.post("/api/stage", json={"hint": next(NEXT_HINTS, "")})
    pressed = threading.Event()
    if sys.stdin.isatty():
        threading.Thread(target=lambda: (sys.stdin.readline(), pressed.set()), daemon=True).start()
    print(f"{D}{prompt} (or → in the browser){X}", flush=True)
    while not pressed.is_set() and API.get("/api/stage").json()["next"] == start:
        time.sleep(0.2)
    API.post("/api/stage", json={"hint": ""})


def run_attacker(*args: str):
    p = subprocess.Popen([sys.executable, "-u", os.path.join(ROOT, "attacker", "attack.py"), *args],
                         stdout=subprocess.PIPE, text=True)
    for line in p.stdout:
        line = line.rstrip("\n")
        print(line, flush=True)
        codes = re.findall(r"\x1b\[(\d+)m", line.split("]", 1)[-1] if line.startswith("\x1b[2m[") else line)
        color = next((COLORS[c] for c in codes if c in COLORS and c != "2"), "dim" if "2" in codes else "")
        stage(re.sub(r"\x1b\[[0-9;]*m", "", line), color)
    p.wait()


def attack(pace: str):
    run_attacker("--pace", str(float(pace) * float(os.getenv("DEMO_PACE", "1"))))


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
    API.post("/api/stage", json={"clear": True})
    title("LA MIRAGE · the attacker's laptop")
    say("Target: Desert Bank, customer C-1001.")
    wait()

    title("1 · TODAY: the bank blocks him")
    API.post("/api/reset"); API.post("/api/protection", json={"mode": "block"}); time.sleep(1.5)
    attack("0.3")
    say("Blocked. The bank never learned how he planned to get the money out.", D, "dim")
    wait()

    title("1b · A week later: someone quieter")
    run_attacker("--quiet", "--quiet-pace", "2.7")
    say("Under the risk threshold, through the same legacy API. Real money.", R + BOLD, "red")
    wait()

    title("2 · WITH LA MIRAGE: same first attacker")
    API.post("/api/reset"); API.post("/api/protection", json={"mode": "mirage"}); time.sleep(1.5)
    attack("0.3")
    s = snap()
    inc, found = s["incident"], s["findings"]
    say(f"He 'stole' AED {inc['deception']['fake_stolen']:,.0f} of fake money. Real money out: AED {inc['deception']['real_lost']:,.0f}, to his own account.", G + BOLD, "green")
    say(f"He found {len(found)} real vulnerabilities for us.", G + BOLD, "green")
    wait()

    title("3 · DEVIN fixes what he found, Mirage replays his exploits")
    s = snap()
    dv, sid = s["incident"]["devin"] or {}, s["incident"]["id"]
    if dv.get("url"):
        say(f"Devin is fixing it live: {dv['url']}", C, "cyan")
    say("replaying his exploits against Devin's fix for this attack...", D, "dim")
    API.post(f"/api/incidents/{sid}/verify", json={})
    shown_live, started, printed = False, time.time(), set()
    while time.time() - started < float(os.getenv("DEMO_DEVIN_WAIT", "75")):
        s = snap()
        dv, found = s["incident"]["devin"] or {}, s["findings"]
        states = [(f.get("verify") or {}).get("state") for f in found]
        if found and all(st == "done" for st in states) and found[0].get("pr") not in printed:
            printed.add(found[0].get("pr"))
            fixed = sum(f["status"] == "verified" for f in found)
            say(f"{fixed}/{len(found)} of his exploits blocked by the fix: before 200, after 403/404", G + BOLD, "green")
            if not s["devin_auto"] or shown_live:
                break
        if dv.get("prs") and not shown_live:
            say(f"Live Devin PR just landed: {dv['prs'][-1]} · replaying his exploits against it...", C + BOLD, "cyan")
            shown_live = True
        time.sleep(3)
    else:
        if (s["incident"]["devin"] or {}).get("url") and not shown_live:
            print(f"{D}Devin is still working live: {s['incident']['devin']['url']}{X}")
    title("Every attacker becomes our pentester.")


if __name__ == "__main__":
    main()
