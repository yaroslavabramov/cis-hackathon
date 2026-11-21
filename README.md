# Mirage: a fake bank for real attackers

> Banks block attackers. Mirage lets them think they've won, and watches where the money would have gone.

**Track:** Protect the little guy (human & transaction) · CIS Hackathon, Dubai

## The problem

It's 2:00 AM. Biometrics ✓, KYC ✓, auth ✓, and an account is drained by machine-speed API calls to offshore accounts.
Every gate did its job: the attacker came in through the front door with a deepfaked FaceID, then left through a
forgotten legacy endpoint. When banks do catch this, they block. The attacker learns they were spotted and moves on to
the next victim, and the bank learns almost nothing.

## What Mirage does

1. **Scores every request** with explainable, deterministic signals (no LLM in the hot path): new device, unusual
   hour, new beneficiary, cross-border, amount spike, legacy API, step-up evasion, machine speed, honeytokens.
2. **Diverts instead of blocking.** Above the threshold, the session is silently re-routed to a **shadow bank**: the same
   bank code with a cloned copy of the victim's state, running in a **Daytona sandbox**. The attacker keeps seeing
   `APPROVED` and a falling balance. The real ledger never moves.
3. **Collects intelligence** while the attacker thinks it's working: mule accounts, crypto off-ramp references, device,
   IP, and the exact API path they used.
4. **Learns.** The captured attack log goes to **Devin** via the Devin API. Devin finds the hole (here, the legacy
   `/v1/transfers` endpoint skips step-up), fixes it, adds a regression test that replays the attack, and opens a PR.
5. **Morning decision.** Shadow transfers are *held*, not deleted. If the customer confirms it was them, one click posts
   them to the real ledger, so a false positive costs a delay, not lost money. Otherwise: void, and export an evidence pack.

```
Attacker ──► Mirage Gateway ──► Real bank (real ledger)
                │ risk scoring
                ├─ risky session ──► Shadow bank (Daytona sandbox, cloned state)
                └─ events (SSE) ───► Console ──► Devin API ──► PR with fix + replay test
```

## Run it

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
cp .env.example .env            # optional: DEVIN_API_KEY, DEVIN_ORG_ID, DAYTONA_API_KEY
./scripts/run.sh                # console at http://127.0.0.1:8000/console
```

In other terminals:

```bash
.venv/bin/python attacker/normal_traffic.py   # ordinary customers in the background
.venv/bin/python attacker/attack.py           # the 2:00 AM attack (add --canary to trip the honeytoken)
```

Without `DAYTONA_API_KEY` the shadow bank runs as a local process; without Devin credentials the console still works
and the Devin step is disabled. With credentials, Devin starts automatically when a session is diverted; use
`DEVIN_AUTO=0 ./scripts/run.sh` for rehearsals (the console button still starts it manually).

Example output: [PR #1](https://github.com/yaroslavabramov/cis-hackathon/pull/1) was opened by Devin about two minutes
after an attack was diverted. It routes `/v1/transfers` through the same step-up check as `/v2` and adds a test that
replays the captured attack; the test fails on `main` and passes with the fix.

## Demo script (5 min)

1. Protection **OFF**, run `attack.py`: the real balance drains to AED 0. This is the slide.
2. Reset, protection **ON**, run it again: the attacker's terminal says `APPROVED` nine times; the real ledger still
   shows AED 450,000.
3. Walk through *why* (signals), *where the money was going* (mules, OTC wallet), and the Devin PR.
4. Morning: "it was the customer" releases the held transfers, or "confirm fraud" files the report.

## Layout

| Path | What |
|---|---|
| `bank/` | Toy bank API (FastAPI). `/v2/transfers` needs step-up for new beneficiaries; legacy `/v1/transfers` doesn't. |
| `gateway/` | Mirage: proxy, risk engine, shadow provisioning (local or Daytona), Devin client, console. |
| `attacker/` | The attack script and background traffic. |
| `tests/` | Bank tests (`.venv/bin/python -m pytest -q`). |

## Honest limits

- Deception lasts until the attacker checks the receiving side. For cross-border transfers "pending settlement" is
  plausible for hours; for instant payments it buys minutes.
- A patient attacker who mimics normal behaviour (one transfer of a usual size) won't cross the threshold.
- Showing a fake success to a real customer is a regulatory question; held-and-replayable transfers plus an
  out-of-band notification are our mitigation.
