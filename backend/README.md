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
| `WARD_INVENTORY_SOURCE` | `sample` | `sample` = built-in demo account with 30 days of hourly history. `aws` = read-only boto3 sweep using your default credentials. A **connected account** (see below) overrides both. |
| `WARD_REGION` | `ap-south-1` | |
| `WARD_CORS_ORIGINS` | `http://localhost:5173` | Comma-separated. |
| `WARD_DATABASE_URL` | `sqlite:///./ward.db` | Any SQLAlchemy URL; `postgresql+psycopg://…` needs no code change. |
| `WARD_PRINCIPAL` | detected | The IAM principal customer roles trust. Unset, Ward uses whatever identity its own credentials resolve to (`aws sts get-caller-identity`), converting an assumed-role session to its role ARN. `GET /accounts/setup` shows which. |
| `WARD_CFN_TEMPLATE_URL` | unset | Where the CloudFormation template is hosted, which enables the one-click console link. |
| `WARD_SECRET_KEY` | unset | Fernet key for encrypting stored ExternalIds. Unset in dev: a `.ward-secret` file is generated. |
| `WARD_BUDGET_INR` | `30000` | |

## Features

### Connecting an AWS account — `/accounts` (SRS §7)

Users hand over a **role ARN, never keys**. Ward runs in its own account and assumes a read-only role
in theirs; the temporary credentials live in memory and are refreshed before expiry, so the database
never holds anything usable on its own.

0. `GET /accounts/setup` — is Ward itself ready? It needs AWS credentials of its own on the backend
   machine (`aws configure`), able to `sts:AssumeRole` on `WardReadOnly`. Those keys belong to Ward, not
   to the watched account, which never hands over keys of any kind.
1. `POST /accounts` — Ward issues an ExternalId (encrypted at rest) and returns a pending account.
2. `GET /accounts/{id}/onboarding` — the CloudFormation template, with the principal and ExternalId
   already filled in as parameter defaults, so deploying it takes no typing.
3. `POST /accounts/{id}/connect` — Ward assumes the role once and records which account it landed in
   (`sts:GetCallerIdentity`) before trusting it. A role that can't be assumed is rejected, not stored.

The trust policy requires `sts:ExternalId`, which is what stops someone else from adding Ward's
principal to their own role and having Ward poll an account nobody agreed to watch.

### Compiler — `POST /rules/compile` (SRS Phase 2 baseline)

English in; a verified policy, a question, or an honest failure out — never an HTTP error.

- Vague wording returns `needs-clarification` with one question per ambiguous term, each option
  carrying **how many of your resources it would match**. Answers come back in `choices`.
- A compiled rule is verified against fixtures generated from the *intent* before it is returned, and
  simulated against the current inventory so you see what it would do.
- `POST /rules/whatif` sweeps one threshold (`hours`, `days`) so a limit is chosen against evidence.

`app/compiler/base.py` defines the `Compiler` protocol. The template compiler is the baseline that
RAG (Phase 3) and the fine-tuned model (Phase 6) are measured against — swapping them is one object,
and every draft still goes through the same verifier.

### Costs — `/costs` (SRS §14, §15, §17)

- `GET /costs` — daily spend priced from inventory snapshots, month-to-date, the month-end projection
  at the last 7 days' burn, and savings with **every counterfactual named** (`next-morning`,
  `conservative`, `observed`) and Ward's own cost subtracted.
- `GET /costs/investigate?window=7d` — the Detective: per-resource spend differenced against the
  previous window, ranked, each with a reason, plus the rule that would have caught the biggest mover.
- `GET /costs/predictions` — forecasts stored the day they were made, graded once the month ends. The
  current month is returned ungraded on purpose.

### Guardian — `/guardian/findings`, `/rules/conflicts` (SRS §21, §31)

Findings are what nobody wrote a rule about: public databases, open SSH, unattached volumes, untagged
resources, long-running accelerators. Each carries the resources, the monthly cost, a runnable `fix`
command, and the rule that would catch it next time.

Conflicts compare what rules actually **match** on this account, not how they are worded:
contradiction, subsumption, overlap and dead rules.

### Copilot — `POST /chat` (SRS §19)

Intent routing over the account's own data — spend, changes, risk, what's running, what's watched — so
it cannot invent a number. Asking it to change something returns `REFUSE` with the exact AWS CLI
command, because Ward's credentials are read-only by design.

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
  compiler/               English → policy: the Compiler protocol, templates, the clarifier, pipeline
  verifier/               intents, fixture generation, runner, report
  simulator/              dry run, time-travel replay
  inventory/              boto3-shaped builders, sample account, pricing, snapshot store
  costs/                  spend, projection, savings counterfactuals, the Detective
  guardian/               findings, rule-conflict detection
  aws/                    cross-account role assumption, the onboarding template
  watcher/                read-only sweep, state machine, evaluator, warning variants
  notify/                 channels (Telegram, or logged when unconfigured)
  api/                    routes
tests/                    gold policies per intent, broken-policy cases, API, stubbed poller and STS
```

## Still to build

- **`POST /architect`** — architecture recommendations. Left for the model phase: unlike everything
  above, it cannot be computed from the account's own data.
- **RAG (Phase 3) and fine-tuning (Phase 6)** — both arrive as implementations of the `Compiler`
  protocol, measured against the template baseline.
- **Multi-tenant scoping** — `rules`, `watches`, `alerts`, `notifications` and `predictions` need an
  `account_id` and every query needs to filter on it. The `accounts` table and the assume-role path
  are in place; the sweep currently uses the first connected account.

## Gotchas found while building

Custodian's filters read real describe-* fields, so hand-rolled resources must match boto3 exactly:
`instance-age` uses the root volume's `BlockDeviceMappings[].Ebs.AttachTime` (not `LaunchTime`), timestamps must
be `datetime` objects, security groups need `OwnerId`, and RDS tags must be under `Tags` (boto3's `TagList` is
renamed by Custodian's augment step, which offline evaluation skips).
