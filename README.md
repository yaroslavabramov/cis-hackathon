# Mirage: try us

> Security tools either keep attackers out or train people not to be fooled. Mirage does the opposite:
> it lets the attacker in, into a private copy of the bank, and turns him into our pentester.

**Track:** Protect the big guy (code, data & infra rails) · CIS Hackathon, Dubai

## The idea

It's 2:00 AM. Biometrics ✓, KYC ✓, auth ✓, and accounts get drained through a forgotten legacy API.

When a bank detects an attacker, it blocks him. He moves on, and the hole he was about to use stays open for the next
attacker who doesn't look suspicious. **Detection tells you *who* is attacking. It doesn't tell you *how* they can
break you.**

Mirage doesn't block. It silently moves the attacker into a **shadow bank**: the bank's real code, running in an
isolated Daytona sandbox, with a clone of the victim's account and synthetic neighbours. He keeps "stealing". Every
bank rule he breaks in there is a real vulnerability in production, captured with an exact reproduction. Devin fixes
it, and Mirage proves the fix by replaying his own exploits.

One detected attacker → a fix for every undetected one.

## What happens in the demo

1. **Without Mirage:** a deepfaked FaceID gets a valid session; `/v2` asks for step-up, so the attacker uses the legacy
   `/v1` API and drains four customers (AED 576k, real).
2. **With Mirage:** the same attacker is diverted on his first transfer attempt. In his private mirage he:
   - sends an AED 1 probe to his own account (it really goes out, so his check passes),
   - re-logs in from a fresh session (still in the mirage, balances consistent),
   - drains the account plus a bait fixed deposit, handing over mule phone numbers for "compliance",
   - discovers the legacy API also lets him move money out of other customers' accounts (synthetic ones).

   He "steals" AED 2.6M of fake money. Mirage records **3 real vulnerabilities**.
3. **Devin** gets the findings once the attacker goes quiet and opens a PR
   ([example: PR #2](https://github.com/yaroslavabramov/cis-hackathon/pull/2), ~1.5 min).
4. **Verified:** Mirage boots `main` and the PR side by side in a fresh Daytona sandbox and replays each exploit:
   `main → 200`, `PR → 403/404`. 3/3 blocked.

## How it works

```
Attacker ──► Mirage gateway ──► Real bank
               │ risk scoring (deterministic, explainable, no LLM in the hot path)
               ├─ risky session ──► private shadow bank (Daytona sandbox from an autoscaling pool)
               │                      └─ invariant checks ──► findings ──► Devin API ──► PR
               └─ console (SSE)                                    fresh sandbox replay ◄─┘
```

| Piece | What it does |
|---|---|
| Risk engine (`gateway/risk.py`) | New device, unusual hour, new beneficiary, cross-border, amount spike, legacy API, step-up evasion, machine speed, honeytoken. Divert at 70. |
| Mirage tactics (`gateway/app.py`) | Sticky sessions (his device, or any untrusted device on the account, returns to the same mirage; real customers on trusted devices never do), probe pass-through, bait account, compliance friction. |
| Findings (`gateway/findings.py`) | Bank invariants checked on shadow traffic: step-up for new beneficiaries, debits and reads only on owned accounts. |
| Shadow pool (`gateway/shadow.py`) | One Daytona sandbox per attacker: private preview, outbound network blocked after boot, per-run internal key. Warm pool grows with demand, idle spares switch off, idle mirages are frozen and resumed in a fresh sandbox with the same state. |
| Devin (`gateway/devin.py`) | Findings + attack log → Devin session → PR with fix and replay tests. |
| Verification (`gateway/verify.py`) | Replays each exploit against `main` and the PR in a fresh sandbox. |

## Run it

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
cp .env.example .env              # DEVIN_API_KEY, DEVIN_ORG_ID, DAYTONA_API_KEY (all optional)
./scripts/run.sh                  # console: http://127.0.0.1:8000/console
.venv/bin/python scripts/demo.py  # guided walkthrough (this terminal is the attacker's laptop)
```

Other scripts: `attacker/attack.py` (one attacker), `attacker/swarm.py -n 3` (several at once, watch the pool scale),
`attacker/normal_traffic.py` (background customers). Without Daytona the shadow runs as a local process; without Devin
credentials the console falls back to replaying exploits against `DEVIN_REFERENCE_PR`.

## Honest limits

- Only detected attackers enter the mirage. The holes they find are closed for everyone, including the ones we miss.
- The mirage lasts until the attacker checks the receiving side or notices latency (the sandbox is slower than the
  real bank).
- The bait appears after a re-login; a careful attacker comparing account lists may get suspicious.
- The toy bank's vulnerabilities are planted; the findings, the Devin PR and the replay verification are real.
