# Ward backend

FastAPI service. Policies are evaluated by real Cloud Custodian (`c7n`) entirely in memory — no AWS calls
unless you switch inventory to `aws`.

## Run

```bash
cd backend
../.venv/Scripts/python -m pip install -r requirements.txt   # Windows venv path; use bin/ on macOS/Linux
../.venv/Scripts/python -m uvicorn app.main:app --reload --port 8000
../.venv/Scripts/python -m pytest
```

Open http://localhost:8000/docs for interactive API docs.

| Env var | Default | |
|---|---|---|
| `WARD_INVENTORY_SOURCE` | `sample` | `sample` = built-in demo account with 30 days of hourly history. `aws` = read-only boto3 sweep using your default credentials. |
| `WARD_REGION` | `ap-south-1` | |
| `WARD_CORS_ORIGINS` | `http://localhost:5173` | Comma-separated. |

## Features

### Verifier — `POST /rules/verify` (SRS Phase 1)

Runs a candidate policy against labelled fixtures and reports which ones it got wrong.

- Send an **intent** and Ward generates fixtures: at least 2 positive, 2 negative, 1 edge case.
  Intents: `ec2-runtime`, `require-tag`, `ebs-unattached`, `rds-public`, `sg-open-port`.
- Or send your own **fixtures** (`resource_type`, boto3-shaped `resource`, `expected`).
- An invalid policy returns `passed: false` with an `error`, not an HTTP error — it is a result.
- `POST /rules/verify/fixtures` previews the fixtures an intent generates.

Fixtures come from the intent, never from the policy, so a wrong policy can't grade itself. Edge cases target
real mistakes: forgetting the running-state check, case-sensitive tag keys, and SSH open over IPv6 (`::/0`),
which an IPv4-only `0.0.0.0/0` check misses.

### Policy simulator — `POST /rules/simulate` (SRS §16)

Dry-runs a policy against the latest inventory, then replays it over stored snapshots.

- `matched` resources with cost per day, and `breadth` (`broad` when it matches over half of 4+ resources).
- `funnel`: how many resources survive each filter. When nothing matches, `zero_reason` names the filter that
  eliminated everything — "you have none" and "you have 12 and matched none" are different answers.
- `history`: fires over the last `history_days`, counted once per violation (the watcher only notifies on state
  transitions). Snapshots are rebased so Custodian's wall-clock age filters see each snapshot's real ages.

### Also

- `GET /resources` — latest inventory in the frontend's Resources-page shape.
- `GET /health`

## Layout

```
app/
  engine/custodian.py     parse, validate, filter with c7n; filter funnel
  verifier/               intents, fixture generation, runner, report
  simulator/              dry run, time-travel replay
  inventory/              boto3-shaped builders, sample account, pricing, snapshot store
  watcher/poller.py       read-only AWS sweep (Describe* only)
  api/                    routes
tests/                    gold policies per intent, broken-policy cases, API, stubbed poller
```

## Gotchas found while building

Custodian's filters read real describe-* fields, so hand-rolled resources must match boto3 exactly:
`instance-age` uses the root volume's `BlockDeviceMappings[].Ebs.AttachTime` (not `LaunchTime`), timestamps must
be `datetime` objects, security groups need `OwnerId`, and RDS tags must be under `Tags` (boto3's `TagList` is
renamed by Custodian's augment step, which offline evaluation skips).
