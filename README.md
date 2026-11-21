# La Mirage

La Mirage sits in front of a bank's API. When a session looks like an attack, La Mirage doesn't block it. It moves the
session into a private copy of the bank and lets the attacker carry on. The copy runs the bank's real code, so any bank
rule the attacker breaks in there is a vulnerability in production. La Mirage records it, Devin fixes it, and La Mirage
checks the fix by replaying the attacker's own requests against it.

Track: Protect the big guy (code, data and infra rails).

## Why not just block

Risk scoring looks at behaviour: a new device, a payment at an hour the customer never pays, a first-time offshore
payee. That tells you who looks suspicious. It doesn't tell you how they intend to get the money out.

In the demo the attacker is flagged on his first transfer attempt, which the bank rejects anyway because the payee is
new. The hole he then uses, a legacy endpoint that skips step-up, he finds later, inside the copy. If we had blocked him
at that first attempt, the endpoint would still be open for the next attacker, one who doesn't trip the risk rules.

## Demo

1. Protection off. The attacker logs in with a deepfaked selfie, gets refused on `/v2/transfers`, switches to
   `/v1/transfers` and empties four accounts (AED 576k of real money).
2. Protection on, same attacker. He is moved to his own shadow bank on the first transfer attempt. Inside it he sends
   AED 1 to his own account to check the bank isn't onto him (La Mirage lets that one through for real), logs in again from
   a fresh session, empties the account, and finds that `/v1` will also move money out of other customers' accounts.
   The other customers in the copy are synthetic. When he moves large sums out of them, the copy asks for the
   beneficiary's phone number "for compliance", and he gives up his mules' numbers. He walks away with AED 1.4M of fake
   money; La Mirage has three findings.
3. When he goes quiet, the findings go to Devin. Devin opened [PR #2](https://github.com/yaroslavabramov/cis-hackathon/pull/2)
   about a minute and a half later.
4. La Mirage boots `main` and the PR side by side in a fresh Daytona sandbox and replays each exploit. `main` returns 200,
   the PR returns 403 or 404 for all three.

## How it's built

```
attacker ──► La Mirage gateway ──► real bank
               │  risk score above 70
               ├──────────────► private shadow bank (Daytona sandbox, one per attacker)
               │                  invariant checks ──► findings ──► Devin ──► PR
               │                                         replay in a fresh sandbox ◄┘
               └── console (server-sent events)
```

| File | Role |
|---|---|
| `gateway/risk.py` | Deterministic risk signals with weights. No model in the request path. |
| `gateway/app.py` | Proxy, diversion, and the shadow tactics: sticky sessions, probe pass-through, compliance friction. |
| `gateway/findings.py` | Bank rules checked on shadow traffic: step-up before paying a new beneficiary, debits and balance reads only on the session's own accounts. |
| `gateway/shadow.py` | Sandbox pool. Each sandbox has a private preview URL and no outbound network once the bank is running. The pool keeps a couple warm, grows with recent attacker count, switches idle spares off, and freezes a quiet attacker's mirage so it can be resumed later in a new sandbox with the same state. |
| `gateway/devin.py` | Sends findings and the attack log to the Devin API. |
| `gateway/verify.py` | Replays each finding against `main` and the PR. |
| `bank/` | Toy bank with a legacy API that has two planted bugs. |
| `attacker/` | `attack.py`, `swarm.py` (several attackers at once), `normal_traffic.py`. |

Sticky sessions follow the attacker without catching real customers. His device always goes back to his mirage. A
matching IP address or account only counts if the device is not one the customer has used before, so a customer on
their own phone, even behind the same NAT, always reaches the real bank.

## Running it

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
cp .env.example .env              # DEVIN_API_KEY, DEVIN_ORG_ID, DAYTONA_API_KEY, all optional
./scripts/run.sh                  # console at http://127.0.0.1:8000/console
.venv/bin/python scripts/demo.py  # the three demo steps, Enter to advance
```

Without a Daytona key the shadow bank runs as a local process. Without Devin credentials, step 3 replays the exploits
against `DEVIN_REFERENCE_PR` instead.

## Limits

Only attackers who get flagged end up in a mirage; the bugs they find are fixed for everyone else. The deception holds
until the attacker checks whether the money arrived, or notices that the sandbox answers slower than the real bank. The bank's
bugs are planted. The findings, the Devin PR and the replay are not.
