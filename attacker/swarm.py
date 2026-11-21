"""Several independent attackers at once, to watch the shadow pool scale."""
import argparse
import subprocess
import sys
import time
from pathlib import Path

CREWS = [("C-1001", "pixel8-emu-7f3a", "185.220.101.47"), ("C-1002", "redmi-root-11ab", "45.155.205.12"),
         ("C-1003", "android-vm-3c9e", "194.26.29.81"), ("C-1004", "genymotion-77d0", "103.152.18.44")]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bank", default="http://127.0.0.1:8000")
    ap.add_argument("-n", type=int, default=3)
    ap.add_argument("--stagger", type=float, default=1.0)
    a = ap.parse_args()
    script = Path(__file__).with_name("attack.py")
    procs = []
    for customer, device, ip in CREWS[: a.n]:
        procs.append((customer, subprocess.Popen([sys.executable, str(script), "--bank", a.bank, "--pace", "0.1",
                                                  "--customer", customer, "--device", device, "--ip", ip],
                                                 stdout=subprocess.PIPE, text=True)))
        print(f"attacker on {customer} from {device} / {ip} started", flush=True)
        time.sleep(a.stagger)
    for customer, p in procs:
        out = p.communicate()[0].strip().splitlines()
        print(f"{customer}: {out[-1].strip() if out else 'no output'}")


if __name__ == "__main__":
    main()
