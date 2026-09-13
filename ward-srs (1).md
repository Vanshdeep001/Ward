# Ward
### Natural-Language Cloud Cost Guardrails
**Software Requirements & Design Document — v1.0**

---

## 1. The problem

Cloud providers charge by the second. Students and small teams learning cloud regularly get bills they did not expect — a GPU instance left running over a weekend, a NAT Gateway quietly charging for data transfer, an RDS database forgotten in a region nobody checks.

The tooling that exists does not solve this well:

**AWS's own alerts arrive too late.** Free Tier alerts fire at 85% of the limit or after a forecast breach. By then the money is often already spent. They land in email, which most students do not read.

**Professional tools require professional skills.** Cloud Custodian is an excellent policy engine, but you must write YAML in a domain-specific language to use it. A second-year student who just wants "don't let anything run overnight" is not going to learn a DSL to say that.

**Nothing explains the bill.** Every tool can tell you that you spent money. None tell you *why* the number changed, in words a beginner understands, with a fix attached.

The gap is a translation gap. The rules people want are simple English sentences. The systems that enforce rules speak YAML.

---

## 2. The solution

**Ward turns English rules into running cloud guardrails.**

A user writes:

> "Never let a GPU instance run more than 6 hours."

Ward compiles that into an executable Cloud Custodian policy, verifies the policy is correct by testing it against generated example resources, then runs it against the user's live AWS account every 15 minutes. When a rule is about to break, Ward warns the user on a channel they actually read — before the money is spent.

Three things make this work:

1. **A compiler** — a fine-tuned language model that turns English into policy YAML.
2. **A verifier** — a test harness that proves each generated policy actually works, before it is ever trusted.
3. **A watcher** — a scheduler that runs verified policies against the live account and manages alert state.

### The rulebook

Ward ships with a default rulebook for beginners, so a new user gets value in the first five minutes:

```
Stay inside the free tier
Nothing runs longer than 6 hours unattended
No GPU instance without an expiry tag
Warn before monthly spend crosses the budget
Nothing left running over a weekend
Flag any resource with no owner tag
```

Users then add their own rules in plain English.

---

## 3. Existing systems and where Ward differs

### 3.1 Natural language → policy code

| System | What it does | Gap |
|---|---|---|
| **Prose2Policy (Apple, 2026)** | English access-control policies → Rego, with schema validation, linting, auto-generated tests. Reports 95.3% compile rate. | Access control only. Frontier model only. No live enforcement. |
| **ARPaCCino (2025)** | Agentic LLM + RAG generating Rego for IaC compliance, iteratively refined against tools. | Security/compliance domain. Frontier model. No cost rules. No deployment loop. |

Both are strong prior work, and both should be cited early in the report. Neither covers cost, and neither asks whether a small model can do the job.

### 3.2 Cloud cost and policy tooling

| System | What it does | Gap |
|---|---|---|
| **Cloud Custodian (CNCF)** | YAML rules engine for AWS/Azure/GCP. Filters resources, triggers actions. | You must write the YAML. Steep for beginners. |
| **Komiser** | Inventory + flags idle/untagged resources. | Fixed heuristics, not user-defined rules. Dashboard, not alerts. |
| **AWS Budgets / Free Tier alerts** | Threshold alerts on spend and usage. | Fires late. Email only. No per-resource rules. No explanation. |
| **OpenCost / Kubecost** | Kubernetes cost allocation. | K8s only. Measurement, not guardrails. |

**Cloud Custodian is not a competitor — it is Ward's backend.** Ward does not reimplement the rules engine. It removes the requirement to learn its language.

### 3.3 Novelty claims

State these three plainly, and no more:

**N1 — New domain for NL→policy.** Prior work targets access control and security compliance. Ward targets **cost and budget** rules. This domain has a property the others lack: the monthly bill provides an independent, objective check on whether the system did the right thing.

**N2 — Small model, verifier-distilled.** Prior work uses frontier models with prompting or agentic loops. Ward asks whether a 7B model, fine-tuned on outputs that a verifier has already certified correct, can match frontier performance at a fraction of the inference cost — and without sending infrastructure configuration to a third party.

**N3 — Closed loop from English to enforcement to explanation.** Prior work stops at generating the policy. Ward generates it, verifies it, deploys it, monitors with it, explains what it catches, and turns each explanation into a candidate new rule.

Do not claim novelty for the policy engine, the alerting, or the idea of NL→code. Those are all prior art.

---

## 4. Architecture

```
                        USER (React web app)
                              |
                              v
                    +--------------------+
                    |   FastAPI backend  |
                    +--------------------+
                       |      |       |
        +--------------+      |       +---------------+
        v                     v                       v
+---------------+     +---------------+       +----------------+
|   COMPILER    |     |    WATCHER    |       |   EXPLAINER    |
| English -> YAML|    | runs policies |       | why did cost   |
|               |     | every 15 min  |       | change?        |
+---------------+     +---------------+       +----------------+
        |                     |                       |
        v                     v                       v
+---------------+     +---------------+       +----------------+
|   VERIFIER    |     | Cloud Custodian|      |  RAG (Qdrant)  |
| fixtures pass?|     | + boto3        |      |  AWS pricing   |
+---------------+     +---------------+       |  + service docs|
        |                     |               +----------------+
        v                     v
+------------------------------------------+
|         PostgreSQL  +  Redis             |
|  rules, policies, resource state,        |
|  cost history, alerts, predictions       |
+------------------------------------------+
                     |
                     v
              Notifier (Telegram / email)
```

### 4.1 The compile path

```
English rule
    |
    v
RAG retrieval  -----> Cloud Custodian resource schemas
    |                 AWS service + pricing docs
    v
Fine-tuned model
    |
    v
Candidate YAML policy
    |
    v
VERIFIER: generate fixtures -> run policy -> compare
    |
    +--- fail --> retry (max 3), then flag for human
    |
    +--- pass --> store as active policy
```

### 4.2 The watch path

Every 15 minutes:

```
Poll AWS inventory (boto3)
    |
    v
For each resource, run every active policy
    |
    v
Compare result to stored state
    |
    +--- state unchanged --> do nothing (stay silent)
    |
    +--- state changed --> transition + notify
```

### 4.3 Resource state machine

```
Discovered --> Watched --> Warning --> Alert --> Resolved
                  ^           |                     |
                  |           v                     |
                  |        Snoozed                  |
                  |           |                     |
                  +-----------+---------------------+
```

- **Discovered** — resource seen for the first time.
- **Watched** — all policies passing. The quiet state.
- **Warning** — approaching a limit. One gentle nudge.
- **Alert** — limit breached. Louder, with projected cost.
- **Snoozed** — user said it is intentional. Silent until the timer expires.
- **Resolved** — fixed. Outcome logged for evaluation.

**Only notify on transitions.** Notifying every poll would send 96 messages a day and get the tool uninstalled.

---

## 5. Technology stack

### Backend (Python 3.11+)
| Purpose | Choice |
|---|---|
| API framework | FastAPI |
| AWS access | boto3 |
| Policy engine | Cloud Custodian (`c7n`) |
| Database | PostgreSQL + SQLAlchemy |
| Cache / queue | Redis |
| Background jobs | Celery (or APScheduler for V1) |
| Vector DB | Qdrant |
| Keyword search | `rank_bm25` |
| Embeddings | `sentence-transformers` (bge-small-en-v1.5) |
| Reranker | `bge-reranker-base` |

### Fine-tuning (Python)
| Purpose | Choice |
|---|---|
| Model | Qwen2.5-Coder-7B-Instruct (or Llama-3.1-8B-Instruct) |
| Training | Hugging Face `transformers`, `peft`, `trl` |
| Quantisation | `bitsandbytes` (4-bit) |
| Serving | vLLM |
| Tracking | MLflow |
| Data versioning | DVC |

### Frontend (React)
| Purpose | Choice |
|---|---|
| Framework | React 18 + Vite |
| Language | TypeScript |
| Styling | Tailwind CSS |
| Data fetching | TanStack Query |
| Charts | Recharts |
| Routing | React Router |

### Infrastructure
Docker, Kubernetes (EKS), Terraform, Helm, GitHub Actions, Prometheus, Grafana, OpenTelemetry.

---

## 6. Folder structure

```
ward/
|
├── backend/
│   ├── app/
│   │   ├── main.py                  FastAPI entry point
│   │   ├── config.py                settings, env vars
│   │   ├── api/
│   │   │   ├── rules.py             CRUD for English rules
│   │   │   ├── resources.py         inventory endpoints
│   │   │   ├── alerts.py            alert history, snooze
│   │   │   └── costs.py             spend + predictions
│   │   ├── compiler/
│   │   │   ├── prompt.py            prompt templates
│   │   │   ├── client.py            calls model server
│   │   │   └── postprocess.py       strip fences, parse YAML
│   │   ├── verifier/
│   │   │   ├── fixtures.py          generate test resources
│   │   │   ├── runner.py            run c7n against fixtures
│   │   │   └── report.py            pass/fail result object
│   │   ├── watcher/
│   │   │   ├── poller.py            boto3 inventory sweep
│   │   │   ├── evaluator.py         run policies on resources
│   │   │   └── state.py             state machine transitions
│   │   ├── explainer/
│   │   │   ├── anomaly.py           detect spend spikes
│   │   │   └── narrate.py           RAG-grounded explanation
│   │   ├── rag/
│   │   │   ├── ingest.py            chunk + embed docs
│   │   │   ├── retrieve.py          hybrid search
│   │   │   └── rerank.py            cross-encoder rerank
│   │   ├── notify/
│   │   │   ├── telegram.py
│   │   │   └── email.py
│   │   ├── models/                  SQLAlchemy tables
│   │   └── workers/                 Celery tasks
│   ├── tests/
│   ├── requirements.txt
│   └── Dockerfile
|
├── finetune/
│   ├── data/
│   │   ├── seeds/
│   │   │   ├── rules_seed.jsonl     hand-written English rules
│   │   │   └── policies_gold.yaml   hand-written correct policies
│   │   ├── generated/               model attempts, pre-verification
│   │   ├── verified/                attempts that passed the verifier
│   │   └── splits/
│   │       ├── train.jsonl
│   │       ├── val.jsonl
│   │       └── test_holdout.jsonl   LOCKED. Do not open.
│   ├── scripts/
│   │   ├── 01_expand_rules.py       grow the seed rule set
│   │   ├── 02_generate.py           teacher model writes attempts
│   │   ├── 03_verify.py             verifier filters attempts
│   │   ├── 04_build_dataset.py      format into chat pairs
│   │   ├── 05_train_qlora.py        the training run
│   │   ├── 06_evaluate.py           score a checkpoint
│   │   └── 07_serve.py              launch vLLM with adapter
│   ├── configs/
│   │   ├── qlora_v1.yaml
│   │   └── qlora_v2.yaml
│   ├── adapters/
│   │   ├── ward-compiler-v1/
│   │   └── ward-compiler-v2/
│   └── results/
│       └── eval_runs.csv            every score ever recorded
|
├── frontend/
│   ├── src/
│   │   ├── main.tsx
│   │   ├── App.tsx
│   │   ├── pages/
│   │   │   ├── Dashboard.tsx        spend, active alerts
│   │   │   ├── Rules.tsx            write + review rules
│   │   │   ├── Resources.tsx        inventory + states
│   │   │   ├── Alerts.tsx           history, snooze controls
│   │   │   └── Accuracy.tsx         prediction scorecard
│   │   ├── components/
│   │   │   ├── RuleComposer.tsx     English in, YAML preview out
│   │   │   ├── PolicyDiff.tsx       show generated YAML
│   │   │   ├── ResourceCard.tsx
│   │   │   ├── StateBadge.tsx
│   │   │   └── SpendChart.tsx
│   │   ├── api/client.ts
│   │   └── types/
│   ├── package.json
│   └── Dockerfile
|
├── infra/
│   ├── terraform/
│   │   ├── main.tf
│   │   ├── vpc.tf
│   │   ├── eks.tf
│   │   ├── rds.tf
│   │   ├── ecr.tf
│   │   └── iam.tf
│   └── helm/
│       └── ward/
│           ├── Chart.yaml
│           ├── values.yaml
│           └── templates/
|
├── knowledge/                       RAG source documents
│   ├── c7n_schemas/
│   ├── aws_pricing/
│   └── aws_service_docs/
|
├── .github/workflows/
│   ├── backend-ci.yml
│   ├── frontend-ci.yml
│   ├── model-ci.yml                 train -> eval -> gate -> register
│   └── deploy.yml
|
├── docker-compose.yml               local dev: postgres, redis, qdrant
└── README.md
```

---

## 7. What the user must provide

### Minimum to use Ward
1. An AWS account.
2. A read-only IAM role for Ward to assume. Ward never gets write access in V1.
3. A notification channel — Telegram chat ID or email address.
4. A monthly budget figure.

### The IAM policy Ward asks for
Read-only across the services being watched, plus Cost Explorer:

```
ec2:Describe*
rds:Describe*
s3:List*, s3:GetBucket*
eks:Describe*, eks:List*
ce:GetCostAndUsage
ce:GetCostForecast
cloudwatch:GetMetricStatistics
```

Never request `Delete`, `Terminate`, or `iam:*`. If a future version offers auto-shutdown, it must be a separate, explicitly granted role.

### For the development team
- One AWS account for development, with a hard budget cap set on day one.
- One GPU for fine-tuning: a single 24GB card (RTX 3090/4090, or Colab Pro A100) is sufficient for a 7B model with QLoRA.
- API credits for the teacher model used in data generation.

---

## 8. Phases — and how to start each one

Each phase must end with something that works. Never move on with a half-finished phase behind you.

---

### Phase 0 — Foundations (Week 1)

**Goal:** every team member can run the project locally.

**Start by:**
1. Create the repo with the folder structure above. Empty files are fine.
2. Write `docker-compose.yml` bringing up PostgreSQL, Redis and Qdrant.
3. FastAPI app with one endpoint: `GET /health` returning `{"status": "ok"}`.
4. Vite + React app that calls `/health` and shows the result.
5. Everyone clones, runs `docker compose up`, sees green.

**Done when:** three laptops all show the health check passing.

---

### Phase 1 — The verifier (Weeks 2–3)

**This is the most important phase in the project. Build it before anything else.**

Without a verifier you have no way to know if anything works, no way to generate training data, and no way to evaluate. Everything downstream depends on it.

**Start by:**
1. Install Cloud Custodian: `pip install c7n`.
2. Hand-write 5 policies yourself. Learn the YAML shape.
3. Write `fixtures.py`: given a rule, produce example AWS resource JSON objects — some that should be flagged, some that should not.
4. Write `runner.py`: run a policy against fixtures using c7n's local mode (no AWS calls).
5. Write `report.py`: return `{passed: bool, expected: [...], actual: [...], error: str}`.

**Fixture design.** For the rule "no EC2 instance may run more than 6 hours":

```json
positive (should be flagged): {"InstanceId": "i-1", "LaunchTime": "8 hours ago", "State": "running"}
negative (should pass):       {"InstanceId": "i-2", "LaunchTime": "2 hours ago", "State": "running"}
edge (should pass):           {"InstanceId": "i-3", "LaunchTime": "8 hours ago", "State": "stopped"}
```

Every rule needs at least 2 positive, 2 negative, 1 edge case.

**Done when:** you can run `verify(rule, policy_yaml)` and get a trustworthy pass/fail in under a second.

---

### Phase 2 — Baseline compiler (Week 4)

**Goal:** a number to beat.

**Start by:**
1. Write a prompt: "You are a Cloud Custodian policy author. Convert this rule to YAML. Output only YAML."
2. Send your 20 seed rules through a plain model, no retrieval, no training.
3. Run every output through the verifier.
4. Record the pass rate in `results/eval_runs.csv`.

It will be mediocre — perhaps 30–50%. **Write it down anyway.** This is your starting line and the whole project is measured against it.

**Done when:** you have a baseline number and can reproduce it with one command.

---

### Phase 3 — RAG (Weeks 5–6)

**Goal:** show that retrieval improves the compile rate.

**Start by:**
1. Collect knowledge: Cloud Custodian resource schemas (`custodian schema aws.ec2`), AWS pricing pages, service documentation.
2. Chunk by structure, not by fixed token count. One chunk per resource type, one per filter type, one per pricing table.
3. Attach metadata: `{source, resource_type, doc_type, version}`.
4. Embed with `bge-small-en-v1.5` into Qdrant.
5. Add BM25 over the same chunks with `rank_bm25`.
6. Retrieve 20 candidates from each, merge, rerank with `bge-reranker-base`, keep the top 5.
7. Inject those 5 into the prompt.
8. Re-run the evaluation.

**Done when:** you can show two numbers — pass rate with retrieval, pass rate without — and the gap is real.

---

### Phase 4 — The watcher (Weeks 7–9)

**Goal:** Ward runs against a live AWS account and sends real messages.

**Start by:**
1. `poller.py` — sweep the account with boto3 every 15 minutes.
2. Store each resource with its current state in Postgres.
3. `evaluator.py` — run every active policy against every resource.
4. `state.py` — implement the state machine. Only fire notifications on transitions.
5. `telegram.py` — send messages via the Telegram Bot API.
6. Implement snooze: user replies, Ward sets `snoozed_until` and stays quiet.

**Done when:** you deliberately leave an instance running and get a warning before your own limit.

---

### Phase 5 — Cost prediction (Weeks 10–11)

**Goal:** predictions that grade themselves.

**Start by:**
1. Pull daily spend from Cost Explorer (`ce:GetCostAndUsage`).
2. Project month-end: simple linear extrapolation first. This is your baseline predictor.
3. Store every prediction with the date it was made.
4. When the real bill lands, compute the error and store it.
5. Build the accuracy page in React: predicted vs actual, month by month.

**Done when:** you have at least one month of predicted-vs-actual data.

---

### Phase 6 — Fine-tuning (Weeks 12–16)

Covered in full detail in Section 9 below.

---

### Phase 7 — Deployment (Weeks 17–19)

**Start by:**
1. Terraform: VPC, EKS, RDS, ECR, IAM roles.
2. Dockerfiles for backend, frontend, model server.
3. Helm chart with a deployment per service.
4. GitHub Actions: test → build → push to ECR → `helm upgrade`.
5. The model server gets a GPU node group with a `nodeSelector`.

**Done when:** a push to `main` deploys automatically and the live site works.

---

### Phase 8 — Observability & MLOps (Weeks 20–21)

**Start by:**
1. Prometheus + Grafana on the cluster.
2. OpenTelemetry traces through the compile path.
3. MLflow tracking every training run.
4. `model-ci.yml`: train → evaluate → compare to current production → promote only if better.
5. DVC versioning the dataset splits.

---

### Phase 9 — Evaluation & write-up (Weeks 22–24)

**Start by:**
1. Open the held-out test set. First time. Only time.
2. Run all four system versions against it.
3. Produce the headline chart.
4. Compare against the published P2P and ARPaCCino numbers.
5. Write the report.

---

## 9. Fine-tuning — full detail

This is the research core. Read this section carefully.

### 9.1 What exactly is being learned

**Input:** an English rule + retrieved context (schemas, docs).
**Output:** a valid Cloud Custodian policy in YAML.

That is it. The model is not being taught opinions, judgement, or architecture advice. It is learning a **translation** from one language to another, where correctness is machine-checkable.

This is the right shape for fine-tuning. A task with a verifier is a task you can fine-tune safely.

### 9.2 Where training data comes from

The trick: **the verifier writes the labels.**

```
Seed rules (hand-written, ~200)
        |
        v
Expand with paraphrase + template (~2000 rules)
        |
        v
Teacher model generates a policy for each
        |
        v
VERIFIER runs each against fixtures
        |
        +--- FAIL --> discard (or keep for error analysis)
        |
        +--- PASS --> keep as a training example
        |
        v
~1200-1600 verified pairs
```

Every kept example is **known correct** because a machine tested it. No human labelled anything. No opinions involved.

This is knowledge distillation with a hard oracle. The teacher may be wrong; the verifier catches it.

### 9.3 Building the seed set

Write 200 rules by hand, spread across categories:

| Category | Example | Target count |
|---|---|---|
| Runtime limits | "no instance runs over 6 hours" | 30 |
| Instance types | "only t3.micro and t2.micro allowed" | 25 |
| Tagging | "every resource must have an owner tag" | 25 |
| Idle detection | "flag EBS volumes not attached to anything" | 25 |
| Storage | "no S3 bucket may be public" | 20 |
| Database | "no RDS instance larger than db.t3.small" | 20 |
| Networking | "alert if a NAT Gateway exists" | 15 |
| Schedule | "nothing runs on weekends" | 15 |
| Budget | "warn if monthly spend passes the budget" | 15 |
| Region | "no resources outside ap-south-1" | 10 |

Then expand with `01_expand_rules.py`:
- **Paraphrase** — "no instance runs over 6 hours" / "kill anything running longer than 6h" / "instances must not exceed six hours of runtime"
- **Parameter variation** — swap 6 hours for 2, 12, 24; swap t3.micro for t3.small
- **Resource variation** — the same rule shape applied to RDS, EBS, EKS

200 seeds × ~10 variations = ~2000 rules.

### 9.4 Data format

Chat format, since the base model is instruction-tuned:

```json
{
  "messages": [
    {
      "role": "system",
      "content": "You write Cloud Custodian policies. Given a rule in English and reference documentation, output only valid YAML. No explanation, no markdown fences."
    },
    {
      "role": "user",
      "content": "RULE: No EC2 instance may run for more than 6 hours.\n\nREFERENCE:\n<retrieved chunk 1>\n<retrieved chunk 2>\n<retrieved chunk 3>"
    },
    {
      "role": "assistant",
      "content": "policies:\n  - name: ec2-max-runtime-6h\n    resource: aws.ec2\n    filters:\n      - State.Name: running\n      - type: instance-age\n        op: greater-than\n        hours: 6\n"
    }
  ]
}
```

**Include the retrieved context in training.** The model must learn to *use* retrieval, not ignore it. If you train without context but serve with context, the model has never seen that input shape.

### 9.5 The splits

Do this **on day one of Phase 6**, before any training:

```
2000 rules
    |
    +-- 60% train        (~1200)
    +-- 10% validation   (~200)  used during training
    +-- 30% test HOLDOUT (~600)  LOCKED
```

**Split by rule family, not randomly.** If "no instance over 6 hours" is in train and "no instance over 12 hours" is in test, that is leakage — the model has effectively seen the answer. Group paraphrases and parameter variants of the same underlying rule together, then split whole groups.

Move the holdout to a separate directory. Add a README saying when it may be opened. Do not evaluate against it until Phase 9.

### 9.6 Base model choice

| Model | Size | Notes |
|---|---|---|
| **Qwen2.5-Coder-7B-Instruct** | 7B | Recommended. Strong at structured code output, YAML included. |
| Llama-3.1-8B-Instruct | 8B | Solid general alternative. |
| Qwen2.5-Coder-1.5B | 1.5B | Worth training too — a size ablation makes the report stronger. |

### 9.7 QLoRA configuration

QLoRA means: load the base model in 4-bit (small memory), freeze it entirely, and train only small adapter matrices inserted into the attention layers. You end up with a ~100MB adapter file instead of a 15GB model.

`configs/qlora_v1.yaml`:

```yaml
base_model: Qwen/Qwen2.5-Coder-7B-Instruct

quantization:
  load_in_4bit: true
  bnb_4bit_compute_dtype: bfloat16
  bnb_4bit_quant_type: nf4
  bnb_4bit_use_double_quant: true

lora:
  r: 16
  lora_alpha: 32
  lora_dropout: 0.05
  bias: none
  task_type: CAUSAL_LM
  target_modules:
    - q_proj
    - k_proj
    - v_proj
    - o_proj
    - gate_proj
    - up_proj
    - down_proj

training:
  num_train_epochs: 3
  per_device_train_batch_size: 2
  gradient_accumulation_steps: 8
  learning_rate: 2.0e-4
  lr_scheduler_type: cosine
  warmup_ratio: 0.03
  max_seq_length: 2048
  gradient_checkpointing: true
  bf16: true
  optim: paged_adamw_8bit
  logging_steps: 10
  eval_strategy: steps
  eval_steps: 50
  save_strategy: steps
  save_steps: 50
  load_best_model_at_end: true
```

**What the settings mean, plainly:**

- `r: 16` — adapter size. Bigger learns more but overfits faster. 16 is a good default; try 8 and 32 as an ablation.
- `lora_alpha: 32` — scaling. Convention is 2× the rank.
- `target_modules` — which layers get adapters. Attention plus MLP works better than attention alone for code tasks.
- `batch_size 2 × grad_accum 8` — effective batch of 16, achievable on one 24GB card.
- `learning_rate: 2e-4` — standard for LoRA. Full fine-tuning would use ~100× lower.
- `3 epochs` — with ~1400 examples this is usually right. Watch validation loss; stop if it turns upward.

### 9.8 The training script

`05_train_qlora.py` structure:

```python
# 1. Load config
# 2. Load tokenizer, set pad_token if missing
# 3. Load base model with BitsAndBytesConfig (4-bit)
# 4. prepare_model_for_kbit_training(model)
# 5. Build LoraConfig, wrap with get_peft_model
# 6. model.print_trainable_parameters()   # expect ~0.5% trainable
# 7. Load train.jsonl and val.jsonl as HF Datasets
# 8. Build SFTTrainer from trl with the config
# 9. mlflow.start_run() and log the config
# 10. trainer.train()
# 11. model.save_pretrained("adapters/ward-compiler-v1")
# 12. Log final metrics to MLflow
```

Sanity check at step 6: trainable parameters should be well under 1% of total. If it says 100%, the PEFT wrapping did not take.

### 9.9 Evaluation

`06_evaluate.py` produces these metrics on the **validation** set during development:

| Metric | Definition | Why it matters |
|---|---|---|
| **Parse rate** | Output is valid YAML | Floor. Should reach ~100%. |
| **Schema rate** | c7n accepts the policy | Syntactically real. |
| **Positive pass** | Flags resources it should flag | Does it catch violations? |
| **Negative pass** | Passes resources it should pass | Does it avoid false alarms? |
| **Full pass** | All fixtures correct | **The headline number.** |
| **Latency** | Seconds per policy | vs the frontier baseline. |
| **Cost** | ₹ per 1000 policies | The efficiency argument. |

Negative pass rate deserves attention. A policy that flags everything scores well on positives and is useless.

### 9.10 The four systems to compare

| # | System | What it isolates |
|---|---|---|
| 1 | Base 7B, no RAG, no fine-tune | Raw capability |
| 2 | Base 7B + RAG | Value of retrieval |
| 3 | Fine-tuned 7B + RAG | Value of fine-tuning |
| 4 | Frontier model + RAG | The ceiling you are chasing |

The result you want: **3 approaches 4 at a fraction of the cost.** If 3 beats 4, excellent. If 2 already matches 3, that is a real finding — report it honestly and say so.

### 9.11 Serving

```bash
python -m vllm.entrypoints.openai.api_server \
  --model Qwen/Qwen2.5-Coder-7B-Instruct \
  --enable-lora \
  --lora-modules ward-compiler-v1=adapters/ward-compiler-v1 \
  --max-model-len 4096
```

vLLM serves the base model once and swaps adapters at request time. Multiple adapter versions can be served from one GPU — useful for A/B comparison in production.

The backend calls it through an OpenAI-compatible endpoint, so switching between local and frontier models is a config change.

### 9.12 Common failure modes

| Symptom | Likely cause | Fix |
|---|---|---|
| Val loss rises after epoch 1 | Overfitting | Fewer epochs, lower `r`, more data |
| Output wrapped in ``` fences | Training data had them | Strip fences in the dataset |
| Model ignores retrieved context | Trained without context | Retrain with context in the prompt |
| Great on train, poor on holdout | Leaky split | Re-split by rule family |
| CUDA out of memory | Batch or sequence too large | `batch_size: 1`, `max_seq_length: 1024` |
| Fine-tuned worse than base | LR too high | Try `1e-4` |

### 9.13 Honest expectations

The fine-tuned model may not beat a well-prompted frontier model on raw accuracy. That is a normal outcome, not a failure.

The argument for the fine-tuned model is **cost, latency, and privacy at comparable accuracy**. If it reaches 90% of frontier quality at 2% of the cost and runs entirely on your own hardware, that is the result — state it that way.

Design the evaluation so it can tell you the fine-tuning did not help. An evaluation that can only confirm your hypothesis is not an evaluation.

---

## 10. Team split — three people

The whole project divides into three tracks. Each person owns their track end to end, including its tests, its documentation, and its section of the final report.

---

### Person A — Model & Data
**Owns everything in `finetune/`. Fixed assignment.**

| Phase | Responsibility |
|---|---|
| 1 | Co-design fixture generation with Person B (needs it for data) |
| 2 | Baseline compiler + prompt engineering |
| 3 | Retrieval quality tuning, chunking strategy, reranking |
| 6 | **The entire fine-tuning pipeline** — seeds, expansion, generation, verification filter, splits, QLoRA training, evaluation, ablations |
| 8 | MLflow tracking, model registry, promotion gate |
| 9 | Held-out evaluation, all four system comparisons, comparison to published prior work |

**Deliverables:** the training pipeline, at least two adapter versions, size and rank ablations, the results table, and the research chapter of the report.

**Skills to build:** PyTorch, PEFT, TRL, prompt design, evaluation methodology.

---

### Person B — Backend & Cloud Engine
**Owns `backend/` and the verifier.**

| Phase | Responsibility |
|---|---|
| 0 | Repo setup, docker-compose, FastAPI skeleton |
| 1 | **The verifier** — fixtures, c7n runner, pass/fail reporting |
| 3 | RAG infrastructure — Qdrant, ingestion, hybrid search plumbing |
| 4 | The watcher — boto3 polling, state machine, notifications, snooze |
| 5 | Cost prediction, Cost Explorer integration, accuracy tracking |
| 8 | Explainer module (if reached) |

**Deliverables:** the verifier, the running watcher, the API, and the system-design chapter.

**Skills to build:** FastAPI, boto3, Cloud Custodian, Celery, PostgreSQL, Redis.

**Note:** the verifier is on the critical path for Person A. It must be finished on schedule in Phase 1 — everything else waits on it.

---

### Person C — Frontend, Infrastructure & DevOps
**Owns `frontend/`, `infra/`, and `.github/`.**

| Phase | Responsibility |
|---|---|
| 0 | React scaffold, CI skeleton |
| 2–3 | Rule composer UI, YAML preview, review-before-activate flow |
| 4 | Resource inventory view, state badges, alert history, snooze controls |
| 5 | Spend charts, prediction accuracy scorecard |
| 7 | **Terraform, EKS, Helm, GitHub Actions, full deployment** |
| 8 | Prometheus, Grafana, OpenTelemetry instrumentation |

**Deliverables:** the web application, reproducible infrastructure (`terraform apply` from nothing), the CI/CD pipeline, dashboards, and the deployment chapter.

**Skills to build:** React, TypeScript, Tailwind, Terraform, Kubernetes, Helm, GitHub Actions.

---

### Shared responsibilities

| Item | Who |
|---|---|
| Seed rule writing (200 rules) | All three, ~67 each |
| Weekly integration meeting | All three |
| Report writing | Each writes their own chapters |
| Code review | Cross-review: A↔B, B↔C, C↔A |

### Critical path dependencies

```
Person B's verifier (Phase 1)
        |
        +--> Person A cannot generate data without it
        +--> Person A cannot evaluate without it

Person B's API (Phase 4)
        |
        +--> Person C cannot build real UI without it

Person A's adapter (Phase 6)
        |
        +--> Person C cannot deploy the model service without it
```

The verifier is the single most important dependency in the project. Protect that deadline.

---

## 11. Risks

| Risk | Impact | Mitigation |
|---|---|---|
| AWS bill runs away during development | High | Hard budget cap day one. Ward watches its own account. |
| Verifier slips past Phase 1 | High | Two people on it if needed. Everything else waits. |
| Fine-tuning shows no improvement | Medium | Report honestly. Frame around cost and privacy. This is a valid result. |
| Data leakage between splits | High | Split by rule family. Lock the holdout physically. |
| Scope creep back to the 12-phase plan | High | Anything not in Phases 0–9 is future work. Write it down as future work and move on. |
| GPU unavailable | Medium | Colab Pro fallback. 1.5B model as backup. |

---

## 12. Success criteria

**Minimum viable (must have):**
- Verifier works and is trusted
- English → policy compilation runs, with a measured pass rate
- Ward runs live against an AWS account and sends real warnings
- One fine-tuned adapter exists with an evaluation score
- Deployed on Kubernetes via CI/CD

**Target (should have):**
- All four system comparisons on the held-out set
- Cost prediction with at least one month of accuracy data
- At least five real student users
- Comparison against published P2P / ARPaCCino numbers

**Stretch (nice to have):**
- Cost anomaly explainer
- Size ablation across 1.5B / 7B
- Explanations converted into suggested new rules

---

## 13. Future work

State these as deliberate future phases, not omissions:

- **Cost anomaly explainer** — why the bill changed, grounded in pricing documentation, verified against Cost Explorer's own service breakdown.
- **Explanation-to-rule loop** — each explanation becomes a suggested new rule.
- **Multi-cloud** — Cloud Custodian already supports Azure and GCP; the compiler would need retraining per provider.
- **Auto-remediation** — shutdown actions behind an explicitly granted write role and human approval.

---
---

# Second Iteration

**Features 14–24. Scope for after Phases 0–9 land.**

Everything above builds a system that compiles English into policy and enforces it. It does not yet build a system the user *trusts*. The gap between those two is the Second Iteration.

Three themes run through the features below:

1. **Show your work.** A user who cannot see what Ward understood, what it retrieved, and what it would do will not hand it their AWS account. Features 15, 16, 20 and 21 are all transparency.
2. **Predict before you act.** A rule that fires on production is a bad way to discover the rule was wrong. Features 17, 18 and 19 let the user see the consequence before the consequence happens.
3. **Explain the money.** Features 14 and 23 close the loop the original document opened in §13 — the bill stops being a number and becomes a sentence.

**Sequencing rule.** None of these may start before Phase 9 is signed off. The held-out evaluation is the deliverable that makes this a research project; the features below make it a usable product. Do not trade the first for the second.

---

## 14. RAG #2 — Retrieval for cost explanation

**The problem.** The RAG built in Phase 3 serves one consumer: the compiler. It retrieves Cloud Custodian schemas so the model can write correct YAML. It cannot answer "why did my bill go up ₹2,400 this week," because it has never been asked to index the documents that answer that question.

**The feature.** A second retrieval corpus, separate index, separate chunking strategy, serving the Explainer instead of the Compiler.

### 14.1 Why it must be a second index, not the same one

The two tasks want opposite things from retrieval.

| | RAG #1 (compiler) | RAG #2 (explainer) |
|---|---|---|
| Consumer | Fine-tuned 7B writing YAML | Explainer writing English |
| Query shape | "EC2 instance age filter" | "why is NAT Gateway costing ₹800/day" |
| Corpus | c7n schemas, filter reference | Pricing tables, service billing docs, free-tier terms |
| Chunk unit | One resource type / one filter | One pricing dimension / one billing concept |
| Good retrieval | Exact schema match, high precision | Correct price *number* + the unit it is charged in |
| Failure cost | Invalid policy — verifier catches it | Wrong number told to the user — **nothing catches it** |

That last row is the whole argument. A compiler hallucination hits a verifier. An explainer hallucination hits a human who believes it. The explainer's retrieval therefore has to be stricter, not looser.

### 14.2 Corpus

```
knowledge/
├── c7n_schemas/            (RAG #1 — unchanged)
├── aws_pricing/            (RAG #2)
│   ├── ec2_ondemand.json        per instance type, per region
│   ├── ebs_volumes.json         per GB-month, per volume type
│   ├── rds_ondemand.json
│   ├── data_transfer.json       the one that surprises everyone
│   ├── nat_gateway.json         hourly + per-GB processed
│   └── free_tier_limits.json    what is free, how much, for how long
└── aws_service_docs/       (RAG #2)
    ├── billing_concepts/        what a "GB-month" actually means
    ├── service_overviews/       what a NAT Gateway is, in one paragraph
    └── common_charges/          why an idle load balancer still bills
```

Pull pricing from the AWS Price List Bulk API, not from scraped HTML pages. It is versioned, machine-readable, and it does not silently change shape when AWS redesigns a webpage.

### 14.3 Chunking

One chunk per **priceable dimension**, not per document.

```
BAD:  one chunk = the entire EC2 pricing page
      (retrieval returns 40KB, the model picks the wrong row)

GOOD: one chunk = {
        service: "EC2",
        resource: "g4dn.xlarge",
        region: "ap-south-1",
        dimension: "on-demand hourly",
        price: 1.204,
        currency: "USD",
        unit: "hour",
        effective_date: "2026-01-01"
      } + a one-line natural language gloss
```

The gloss exists so the embedding has something to embed. The structured fields exist so the explainer can do arithmetic on a real number instead of generating one.

### 14.4 The grounding rule

**Every number in an explanation must be traceable to a retrieved chunk or to a Cost Explorer response. The model may compose sentences. It may not compose figures.**

Implement this as a post-generation check in `narrate.py`:

```python
# 1. Extract every numeric token from the generated explanation
# 2. For each, assert it appears in either:
#      - a retrieved pricing chunk, or
#      - the Cost Explorer payload for this window, or
#      - is derivable by arithmetic from those (price × hours, etc.)
# 3. Any ungrounded number -> reject, regenerate once, then fall back
#    to the template explanation with no model text at all
```

The fallback matters. An explanation that says "EC2 costs rose; Ward could not determine why" is honest. An explanation with an invented price is worse than no explanation.

### 14.5 Files

```
backend/app/rag/
├── ingest.py            (extend: --corpus {policy,pricing})
├── retrieve.py          (extend: index selection)
├── rerank.py            (shared)
└── pricing/
    ├── price_list.py    AWS Price List Bulk API client
    ├── normalise.py     raw pricing JSON -> priceable-dimension chunks
    └── ground.py        the numeric grounding check above
```

Qdrant gets a second collection, `ward_pricing`. Same embedding model, same reranker, different collection — sharing the model keeps the GPU footprint flat.

### 14.6 Evaluation

Build a small graded set: 50 real bill-change scenarios with a known cause, drawn from the team's own development account plus synthetic ones.

| Metric | Definition | Target |
|---|---|---|
| Cause identified | The named service is the actual top mover | ≥ 85% |
| Numeric grounding | Zero ungrounded figures | **100%, non-negotiable** |
| Retrieval hit@5 | Correct pricing chunk in top 5 | ≥ 90% |
| Readability | A non-cloud reader understands it | Human rating, 5 judges |

---

## 15. Policy explainability — "here's what Ward understood"

**The problem.** The user writes English. Ward produces YAML. The user cannot read YAML — that is the entire premise of the product. So the review-before-activate step in §10 (Person C, Phases 2–3) currently shows the user something they cannot evaluate, and they click Activate anyway. That is not review. That is a rubber stamp.

**The feature.** Round-trip the compiled policy back into English and show *that* for approval. The YAML stays available behind a disclosure, for the users who do want it.

### 15.1 The round trip

```
User's English
     |
     v
COMPILER  ------>  YAML policy
                       |
                       v
                 DECOMPILER  ------>  Ward's English
                                           |
                                           v
                            Shown side by side with the original
```

The decompiler is **not** a second neural model. It is a deterministic renderer that walks the policy AST and emits a sentence per clause. This is the right choice for three reasons: it cannot hallucinate, it is instant, and when it cannot render something that is itself the signal the policy contains something unexpected.

### 15.2 What the user sees

```
YOU WROTE
  "Never let a GPU instance run more than 6 hours"

WARD UNDERSTOOD
  Watch:      EC2 instances
  Only those: whose instance type starts with p, g, or inf
              AND are currently running
  Flag when:  the instance has been running for more than 6 hours
  Then:       notify you on Telegram
  Checked:    every 15 minutes

  ⚠ Ward assumed "GPU instance" means the p/g/inf instance
    families. 4 instances in your account match right now.

  [ This is right — activate ]  [ Not what I meant ]  [ View YAML ]
```

The count — "4 instances in your account match right now" — comes from the simulator in §17 and does more work than the rest of the panel combined. Abstract correctness is hard to judge. A list of four machines you recognise is easy.

### 15.3 Rendering rules

One clause, one line. Keep the vocabulary small and fixed:

| c7n construct | Rendered as |
|---|---|
| `resource: aws.ec2` | Watch: EC2 instances |
| `type: value` + `op: in` | Only those: whose {key} is one of {values} |
| `type: instance-age` | Flag when: running for more than {n} hours |
| `tag:Owner: absent` | Flag when: there is no Owner tag |
| `type: offhour` / `onhour` | Flag when: running outside {start}–{end} |
| unknown filter type | **Ward used a filter it cannot explain: `{type}`. Review the YAML.** |

That last row is load-bearing. Silence on an unrenderable clause would let an unreviewed filter through under the appearance of full review.

### 15.4 Assumption surfacing

Every inference the compiler made that was not literally in the user's sentence gets its own flagged line. "GPU" → p/g/inf families is an assumption. "Overnight" → 20:00–08:00 is an assumption. "Expensive" → anything above ₹50/day is an assumption *and a large one*.

Assumptions are recorded structurally by the compiler, not extracted from the YAML afterwards:

```json
{
  "policy": "...",
  "assumptions": [
    {"term": "GPU instance",
     "interpretation": "instance type in families p, g, inf",
     "confidence": 0.91,
     "alternatives": ["instances with an attached accelerator"]}
  ]
}
```

This requires the fine-tuning data to carry assumption annotations — which means deciding it **before** the Phase 6 dataset is built, even though the feature ships later. Note it in `04_build_dataset.py` from the start and leave the field empty until needed. Retrofitting an annotation into 1,400 verified examples is a week nobody has.

### 15.5 Files

```
backend/app/compiler/
└── decompile/
    ├── ast.py           parse YAML -> clause tree
    ├── render.py        clause tree -> English
    ├── vocab.py         the fixed rendering table
    └── assumptions.py   structured assumption extraction

frontend/src/components/
├── PolicyExplain.tsx    the side-by-side panel
└── AssumptionChip.tsx   one flagged assumption, clickable to change
```

### 15.6 Evaluation

Show 30 users a policy and its rendered English, then ask them to predict which of 6 resources it flags. Compare against the true answer.

| Condition | Measure |
|---|---|
| YAML only | Prediction accuracy |
| Rendered English only | Prediction accuracy |
| Both | Prediction accuracy, and which they actually looked at |

If rendered English does not beat raw YAML by a wide margin on non-expert users, the renderer is not doing its job. This is a publishable number on its own.

---

## 16. Policy simulator — dry run against live inventory

**The problem.** Activation is currently a leap. The user approves a rule and finds out what it does when it starts messaging them.

**The feature.** Before activation, run the candidate policy against the account's *current* inventory, read-only, and show exactly what it matches.

### 16.1 Why this is cheap to build and worth a lot

The watcher (Phase 4) already polls inventory into Postgres every 15 minutes. The evaluator already runs policies against stored resources. The simulator is those two components pointed at an inactive policy with notifications disabled.

Estimated effort: three days. Estimated effect on user trust: larger than any other item in this section.

```
Candidate policy (not yet active)
        |
        v
Load last inventory snapshot from Postgres  (no new AWS calls)
        |
        v
Evaluate  ->  matched: [i-0a1, i-0b2, i-0c3, i-0d4]
              missed:  everything else
        |
        v
Render the match list with resource names, tags, current cost/day
```

No AWS API calls at simulation time. The snapshot is at most 15 minutes old, which is fresh enough to make the decision and avoids hammering the account every time someone edits a draft rule.

### 16.2 The three answers, and what each means

| Result | Reading | Suggested next step |
|---|---|---|
| Matches 0 resources | Either nothing is currently in violation, or the rule is broken | Show *why* zero: "no resources of this type exist" vs "12 exist, none matched the filters" — these are very different messages |
| Matches 1–10 | Normal | Review the list, activate |
| Matches > 50% of inventory | The rule is almost certainly too broad | Warn hard. Show what the user would be notified about tonight. |

The zero case deserves the extra distinction. "You have no GPU instances" is fine. "You have 12 GPU instances and this rule matched none of them" means the rule is wrong, and the current UI would present both as an identical empty list.

### 16.3 Time-travel simulation

The dry run against current inventory answers "what would fire now." The more useful question is "what would have fired." Ward has the resource state history in Postgres from Phase 4 onward.

```
Simulate over the last 30 days of stored inventory snapshots
        |
        v
"This rule would have fired 7 times in the last 30 days:
   Aug 14, 02:00 — i-0a1 (g4dn.xlarge), running 7h
   Aug 16, 23:15 — i-0b2 (g4dn.xlarge), running 9h
   ...
 It would have been quiet on 23 of 30 days."
```

Seven alerts in thirty days reads as a useful rule. Seventy reads as a rule that will be muted within a week. The user can tune the threshold before the rule ever runs, which is the whole point.

This shares its entire backend with §18 (savings impact) — build them together.

### 16.4 Files

```
backend/app/simulator/
├── dryrun.py            policy vs current snapshot
├── timetravel.py        policy vs historical snapshots
├── explain_zero.py      why did this match nothing
└── breadth.py           over-broad detection

backend/app/api/
└── simulate.py          POST /rules/{id}/simulate

frontend/src/components/
├── SimulationResult.tsx
└── MatchList.tsx
```

### 16.5 Retention note

Time-travel needs inventory history. Phase 4 stores current state; it must also append a snapshot row per poll. At 96 polls/day × ~50 resources that is ~4,800 rows/day — trivial for Postgres, but decide the retention window now (90 days is right) and add the partition before the table is large enough to make the migration annoying.

---

## 17. Savings impact — "this rule would have saved ₹6,180"

**The problem.** A rule's value is invisible. It produces alerts, which are an annoyance, and prevents costs, which never appear on any bill by definition. The user experiences only the cost of the tool and none of its benefit.

**The feature.** For each rule, compute and display the money it plausibly saved.

### 17.1 The honest version of this calculation

There is an easy version of this feature that is dishonest, and it is the version most tools ship. It reports "₹6,180 saved" with no stated assumption and counts a resource the user was going to shut down anyway.

Ward's version states its counterfactual explicitly.

```
Rule: "No GPU instance runs more than 6 hours"

Over the last 30 days:
  - Fired 7 times
  - In 5 of those, the instance was stopped within 20 minutes of
    the alert. In 2, it kept running.

  Of the 5 acted-on alerts:
    Average time from alert to shutdown: 11 minutes
    Assumed counterfactual: without the alert, the instance runs
      until the next working morning (09:00)
    Hours avoided: 47.2
    g4dn.xlarge in ap-south-1: ₹101.14/hour
    ────────────────────────────────────────
    Estimated avoided: ₹4,774

  ⓘ This assumes an un-alerted instance runs until 09:00 the next
    day. Change assumption: [until stopped manually ▾]
```

### 17.2 Counterfactual models

Offer three, default to the middle one, and always name which is in use.

| Model | Assumption | When it fits |
|---|---|---|
| Conservative | Instance would have run 2 more hours | Actively monitored accounts |
| **Next-morning (default)** | Runs until 09:00 the following working day | Student and small-team reality |
| Observed | Use this account's own median unattended runtime, computed from resources that ran with no rule watching them | Best, once ≥ 30 days of history exists |

The observed model is the interesting one and it gets better the longer Ward runs. Ship with next-morning, switch to observed automatically once the history supports it, and tell the user when the switch happens.

### 17.3 Attribution

Only count savings where the alert plausibly caused the action. Requires a causal window and honest exclusions:

- Shutdown within 2 hours of the alert → attributed
- Shutdown beyond 2 hours → not attributed, logged separately as "may be related"
- Resource with a scheduled shutdown tag → **never attributed**, it was going to stop regardless
- Two rules both firing on one resource → split, do not double count

Show the excluded figure too. "₹4,774 attributed, ₹1,900 possibly related but not counted" is more credible than a single large number, and credibility is the entire point of showing the figure at all.

### 17.4 Aggregation

The dashboard headline:

```
Ward, last 30 days
  Estimated avoided:   ₹11,420
  Alerts sent:         23
  Acted on:            17  (74%)
  Ward's own cost:     ₹340   (model serving + infra)
  ─────────────────────────────
  Net:                 ₹11,080

  Top rule: "No GPU over 6 hours" — ₹4,774
```

Including Ward's own running cost is non-negotiable. A cost tool that hides its own cost has no standing to comment on anyone else's.

### 17.5 Files

```
backend/app/savings/
├── counterfactual.py    the three models
├── attribute.py         causal window + exclusions
├── compute.py           hours avoided × price
└── aggregate.py         per-rule and account totals

frontend/src/components/
├── SavingsCard.tsx
└── CounterfactualPicker.tsx
```

Pricing comes from RAG #2's normalised pricing store (§14.3), not a hardcoded table. One price source, one place to be wrong.

---

## 18. Cost what-if simulator

**The problem.** "Should the GPU limit be 6 hours or 12?" is a question with a rupee answer, and the user currently has no way to get it except by choosing and waiting a month.

**The feature.** Change a parameter, see the projected monthly delta immediately.

### 18.1 Interaction

```
Rule: No GPU instance runs more than [ 6 ]──────●──── [24] hours
                                                6h

Against your last 30 days of usage:

   6 hours  →  fires 7×/month   ₹4,774 avoided   ← current
  12 hours  →  fires 3×/month   ₹1,890 avoided
  24 hours  →  fires 1×/month     ₹420 avoided
   4 hours  →  fires 14×/month  ₹7,100 avoided   ⚠ likely noisy

Moving 6h → 12h costs you ₹2,884/month and removes 4 alerts.
```

The slider replays historical inventory (the §16.3 engine) at each threshold. No new infrastructure — the same time-travel simulator with the parameter varied.

### 18.2 The alert-fatigue axis

Money is one axis. Interruptions are the other, and a tool that optimises only the first gets uninstalled. Every what-if result shows both, and the interface says plainly when a setting crosses into noise:

- \> 1 alert/day sustained → "⚠ likely to be muted"
- \> 3 alerts/day → "⚠ this will be ignored"

Derived from the alert-response data the system already collects for §17 attribution: an account whose action rate drops below 40% is not being served, regardless of the modelled savings.

### 18.3 Budget-level what-if

The same mechanism applied to the whole account rather than one rule:

```
Current monthly projection: ₹14,200

  If you also enabled:
    ☐ Stop untagged instances at 20:00     −₹2,100/mo
    ☑ No GPU over 6 hours                  −₹4,774/mo  (active)
    ☐ Delete unattached EBS after 7 days     −₹890/mo
    ☐ No NAT Gateway in dev VPCs           −₹3,400/mo

  With all selected:  ₹3,036/mo  (−79%)
```

The checkboxes come from the default rulebook (§2) plus any rule the user has drafted but not activated. It is a shopping list where the prices are computed from the user's own history.

### 18.4 Files

```
backend/app/simulator/
├── whatif.py            parameter sweep over time-travel
├── fatigue.py           alert-rate scoring
└── portfolio.py         multi-rule account projection

backend/app/api/
└── whatif.py            POST /rules/{id}/whatif?param=hours&values=4,6,12,24

frontend/src/components/
├── WhatIfSlider.tsx
└── RulePortfolio.tsx
```

### 18.5 Caching

A parameter sweep replays 30 days of snapshots per value. Cache aggressively in Redis, keyed on `(policy_hash, param, account_id, snapshot_range)`. Invalidate on the next poll. Without this the slider is unusable; with it the sweep is precomputed for common values and the interaction is instant.

---

## 19. Policy conflict detector

**The problem.** Rules accumulate. A user with fifteen rules written over three months has no idea that rule 3 and rule 11 disagree, that rule 7 has been fully subsumed by rule 12, or that rule 9 has not matched anything since the day it was written.

**The feature.** Static and empirical analysis across the active rule set, surfacing four categories of problem.

### 19.1 The four categories

**Contradiction** — two rules cannot both be satisfied.

```
Rule 3:  "Instances must run at least 8 hours for training jobs"
Rule 11: "Nothing runs longer than 6 hours"

These cannot both hold. Any training job violates one of them.
→ Suggest: scope rule 3 to tag:workload=training and exempt it
  from rule 11.
```

**Subsumption** — one rule's matches are a subset of another's.

```
Rule 7:  "No g4dn.xlarge over 6 hours"
Rule 12: "No GPU instance over 6 hours"

Rule 12 matches everything rule 7 matches. Rule 7 is redundant.
→ Suggest: delete rule 7. (It is not harmful, only noise — it
  double-alerts on the same instances.)
```

**Overlap** — partial intersection, causing duplicate alerts.

```
Rule 4:  "Untagged resources are flagged"
Rule 9:  "Resources without an Owner tag are flagged"

Overlap on 8 of your 12 current resources — those send two
alerts for one problem.
→ Suggest: merge, or suppress rule 9 where rule 4 already fired.
```

**Dead rule** — never matched anything, ever.

```
Rule 6:  "No RDS instance larger than db.r5.2xlarge"
Has not matched in 90 days. You have no RDS instances.
→ Keep (it is a guardrail against a future mistake) or archive.
```

Dead rules are not necessarily wrong — a guardrail that never fires may be working perfectly. Present, do not auto-delete.

### 19.2 How detection works

Two methods, both needed.

**Static — compare compiled policy structure.** Same resource type, then compare filter sets. Subsumption is decidable for the common filter shapes: value comparisons, tag presence, type membership. Contradiction is detectable when two rules constrain the same field in disjoint directions.

Do not attempt general logical inference over arbitrary c7n filters. It is undecidable in the general case and the general case is rare. Handle the shapes that appear in the seed rule set (§9.3) — the ten categories there cover the overwhelming majority — and report `UNKNOWN` for anything else rather than guessing.

**Empirical — compare actual match sets.** Run every rule against the last 30 days of inventory via the §16.3 engine and compare the resulting resource-ID sets:

| Set relation | Conclusion |
|---|---|
| A ⊆ B | A is subsumed by B |
| A ∩ B ≠ ∅, neither contained | Overlap |
| A = ∅ | Dead rule |
| A ∩ B = ∅ on every resource, but static analysis says contradiction | Latent contradiction — has not bitten yet, still real |

The empirical method catches things static analysis misses and vice versa. Static catches a contradiction that has never triggered; empirical catches an overlap between two rules whose YAML looks unrelated. Run both.

### 19.3 When it runs

- On policy activation, against the existing active set — block activation on a hard contradiction, warn on the rest
- Nightly across the whole rule set
- On demand from a "Check my rules" button

### 19.4 Files

```
backend/app/conflicts/
├── static.py            structural comparison
├── empirical.py         match-set comparison
├── classify.py          contradiction / subsumption / overlap / dead
└── suggest.py           the recommended fix per category

backend/app/api/
└── conflicts.py         GET /rules/conflicts

frontend/src/pages/
└── RuleHealth.tsx       conflicts + quality scores (§21) in one view
```

---

## 20. Ambiguity detection — the Guardrail Clarifier

**The problem.** "Don't let anything expensive run too long" contains three undefined terms. The compiler will resolve all three silently and produce a policy that runs. The user will not know which of the eight possible readings they got.

**The feature.** Detect ambiguity *before* compiling and ask one targeted question.

### 20.1 The interaction

```
YOU WROTE
  "Don't let anything expensive run too long"

Before Ward writes this rule, two things need pinning down:

  "expensive" means
    ● costs more than ₹50/day          (3 of your resources)
    ○ costs more than ₹200/day         (1 of your resources)
    ○ any GPU instance                 (4 of your resources)
    ○ let me type it

  "too long" means
    ○ more than 2 hours
    ● more than 6 hours
    ○ more than 24 hours
    ○ let me type it

  [ Build the rule ]
```

Every option carries a live count from the simulator (§16). "3 of your resources" turns an abstract choice into a concrete one — the user recognises which three machines they are talking about.

### 20.2 When to ask, and when to shut up

A tool that interrogates every rule is worse than one that guesses. The threshold must be strict.

**Ask only when all three hold:**
1. The ambiguous term is decision-relevant — different readings produce genuinely different match sets
2. The compiler's confidence in its preferred reading is below 0.75
3. The alternative readings differ by more than a small margin in what they match

**Never ask about** terms the account's own history resolves. If the user has written five rules mentioning "GPU" and accepted the p/g/inf reading every time, stop asking. Store it as an account-level term definition.

```
backend/app/glossary/
└── terms.py    account-scoped term definitions, learned from
                accepted clarifications
```

This makes the feature fade with use, which is the correct trajectory. A clarifier that asks the same question in month six has failed.

### 20.3 Detecting ambiguity

Three signals, combined:

| Signal | Method |
|---|---|
| Vague-term lexicon | A curated list — expensive, large, long, idle, old, unused, soon, too many. Cheap, catches most cases. |
| Compiler confidence | Token-level logprobs on the parameter positions of the generated YAML. Low confidence on a threshold value means the model was guessing. |
| Multi-sample divergence | Generate 5 policies at temperature 0.7. If they disagree on a parameter, that parameter is ambiguous. |

The third is the strongest and the most expensive. Use the lexicon as a cheap gate and only run multi-sample when it fires.

Multi-sample divergence has a second use: it is a genuine research contribution. Self-consistency as an ambiguity detector in NL→policy is not, to our knowledge, in the prior work cited in §3.1. If the evaluation shows it predicts human-judged ambiguity well, that is a paper section.

### 20.4 Evaluation

Build a 100-rule set: 50 deliberately ambiguous, 50 clear. Have three annotators label them independently.

| Metric | Target |
|---|---|
| Detection precision | ≥ 0.85 — a false alarm annoys the user |
| Detection recall | ≥ 0.70 — a miss is recoverable via §15 |
| Questions per rule | ≤ 1.3 average |
| Clarification acceptance | ≥ 60% pick a suggested option over typing |

Precision above recall, deliberately. A missed ambiguity gets caught by the explainability panel (§15) or the simulator (§16). An unnecessary question is a pure tax on every rule the user writes.

### 20.5 Files

```
backend/app/clarifier/
├── lexicon.py           vague-term list
├── confidence.py        logprob analysis on parameter positions
├── divergence.py        multi-sample disagreement
├── question.py          generate the question + options
└── options.py           attach live counts via the simulator

frontend/src/components/
└── Clarifier.tsx
```

---

## 21. RAG source transparency — view retrieved chunks

**The problem.** RAG is the least inspectable part of the system. When a policy is wrong, the cause is either the model or the retrieval, and there is currently no way to tell which. This hurts users, and it hurts the team harder — Phase 3 measures *whether* retrieval helps, never *why* it failed when it did.

**The feature.** Expose the retrieval trace for every compilation and every explanation.

### 21.1 What is shown

```
▾ Sources Ward used  (5 chunks, retrieved in 340ms)

  1. aws.ec2 — instance-age filter          c7n schema      0.94
     "type: instance-age ... op: greater-than ... hours: int"
     [ view full chunk ]

  2. aws.ec2 — resource schema              c7n schema      0.89
  3. EC2 instance families                  aws docs        0.71
  4. g4dn.xlarge on-demand, ap-south-1      pricing         0.66
  5. Filter operators reference             c7n schema      0.61

  Retrieval: 20 vector + 20 BM25 → merged 34 → reranked → top 5
```

For explanations (§14), the same panel with the grounding check made visible: every figure in the explanation linked to the chunk it came from.

### 21.2 Why this is a research instrument, not a UI feature

The retrieval trace is the diagnostic that makes RAG failures analysable. Store every trace:

```sql
retrieval_traces (
  id, request_id, query, corpus,
  vector_candidates jsonb,     -- 20 ids + scores
  bm25_candidates   jsonb,     -- 20 ids + scores
  merged            jsonb,
  reranked          jsonb,     -- final 5 + scores
  latency_ms        int,
  outcome           text       -- did the policy verify?
)
```

Join `outcome` against the trace and the failure analysis Phase 3 could not do becomes routine:

- **Retrieval failure** — the needed chunk was not in the top 5 → fix chunking or the reranker
- **Grounding failure** — the chunk was there and the model ignored it → fix the training data (§9.4's warning about training without context)
- **Knowledge failure** — the chunk does not exist in the corpus → fix ingestion

Those three call for three completely different interventions, and without the trace they are indistinguishable. This table is worth building even if the UI never ships.

### 21.3 Chunk quality feedback

A thumbs-down on any chunk, from the user or the team, writes a labelled row. After a few hundred, that is a reranker fine-tuning set — a second, smaller training loop on the retrieval side, and a natural extension of the verifier-distillation argument in §3.3 N2 from generation to retrieval.

### 21.4 Files

```
backend/app/rag/
├── trace.py             capture + persist the full trace
└── feedback.py          chunk-level thumbs up/down

backend/app/models/
└── retrieval_trace.py

frontend/src/components/
├── SourcePanel.tsx      the collapsible trace
└── ChunkViewer.tsx      full chunk + metadata
```

### 21.5 Storage

One trace is a few KB. At 1,000 compilations/day that is ~5MB/day — keep 90 days hot, archive the rest to S3 as Parquet. Sample rather than store everything only if volume genuinely demands it, and never sample the failures.

---

## 22. Rule quality score

**The problem.** Users write rules of wildly varying quality and get no feedback until the rule misbehaves in production. Ward knows enough at authoring time to say something useful.

**The feature.** A 0–100 score with a per-dimension breakdown, computed at authoring time and recomputed weekly against live behaviour.

### 22.1 The dimensions

| Dimension | Weight | Measures | Source |
|---|---|---|---|
| **Specificity** | 25 | Does it target a defined set, or everything? | Static: filter count and selectivity |
| **Verifiability** | 20 | Did it pass the verifier cleanly, first try? | Verifier report (Phase 1) |
| **Actionability** | 20 | When it fires, is the fix obvious? | Presence of a named action + affected resource detail |
| **Signal rate** | 20 | Of the alerts it sent, how many were acted on? | Alert response history (§17) |
| **Stability** | 15 | Does it fire at a steady rate, or in bursts? | Variance in fire rate over time |

Specificity and verifiability are computable at authoring time. The other three need history, so a new rule scores on two dimensions with the rest marked pending — and the score is labelled provisional until it has run for two weeks.

### 22.2 What a score looks like

```
"No GPU instance runs more than 6 hours"                    87 / 100

  Specificity   ████████████████████░  23/25
  Verifiability ████████████████████   20/20   passed first try
  Actionability ████████████████░░░░   16/20   suggests stopping,
                                                does not say which
  Signal rate   ████████████████░░░░   16/20   17 of 23 acted on
  Stability     ████████████░░░░░░░░   12/15   bursty on weekends

  To improve: name the instance in the alert text so the fix is
  one click. (+4)
```

Compare with a bad rule:

```
"Flag anything unusual"                                     31 / 100

  Specificity    ████░░░░░░░░░░░░░░░░   5/25   matches 47 of your
                                                52 resources
  Verifiability  ████████████░░░░░░░░  12/20   passed on retry 2
  Actionability  ████░░░░░░░░░░░░░░░░   4/20   no clear action
  Signal rate    ████░░░░░░░░░░░░░░░░   4/20   3 of 31 acted on
  Stability      ██████░░░░░░░░░░░░░░   6/15   fires in bursts

  This rule is being ignored. 28 of its 31 alerts went unactioned.
  → Consider narrowing it, or archiving it.
```

### 22.3 Design constraints

**Never block on a low score.** It is advice. A user who wants a broad rule may have a reason, and a tool that refuses to do what it is told stops being used.

**Recompute weekly, not continuously.** A score that moves every time an alert lands is noise, and it invites gaming.

**Do not aggregate into a single account score.** "Your cloud hygiene: 72/100" is a vanity metric that drives the wrong behaviour — users delete useful-but-noisy rules to raise a number. Score rules, not users.

**Separate from the conflict detector (§19).** A rule can score 95 and still contradict another rule. Different questions: quality asks "is this a good rule," conflicts ask "does this rule work with the others." Present both on `RuleHealth.tsx`, computed independently.

### 22.4 Files

```
backend/app/quality/
├── specificity.py       selectivity against inventory
├── verifiability.py     read from verifier reports
├── actionability.py     action presence + alert detail
├── signal.py            acted-on rate
├── stability.py         fire-rate variance
└── score.py             weighted combination + improvement hints

frontend/src/components/
├── QualityScore.tsx
└── ScoreBreakdown.tsx
```

---

## 23. Cost Detective — bill-change investigation

**The problem.** §13 promised a cost anomaly explainer. This is that feature, specified. The user's question is never "what did I spend" — it is "**why is this different from last week?**"

**The feature.** An investigation view that decomposes a bill change into attributed causes.

### 23.1 The decomposition

```
Your spend rose ₹2,340 this week (₹1,890 → ₹4,230, +124%)

Ward traced ₹2,180 of that (93%):

  ▲ ₹1,420  EC2 — g4dn.xlarge in ap-south-1
            One instance (i-0a1f2) ran 14 hours on Aug 14 and
            11 hours on Aug 16. Both outside your usual pattern.
            → Rule "No GPU over 6 hours" was snoozed on Aug 13.
            [ un-snooze ]

  ▲   ₹520  NAT Gateway — data processing
            You processed 41GB through the NAT Gateway, up from
            6GB. Charged at ₹0.056/GB plus ₹1.50/hour to exist.
            → This started when eks-worker-3 was created Aug 15.

  ▲   ₹240  EBS — gp3 volumes
            Three 100GB volumes created Aug 12, still unattached.
            → No rule covers this. [ create one ]

  ▽  ₹160   unattributed
            Small changes across 6 services, none above ₹40.
```

Three properties make this work, and all three are missing from every tool the team looked at:

1. **Every figure is traced to a resource**, not a service total. "EC2 went up ₹1,420" is what AWS already tells you and it is useless. "*This instance* ran 14 hours on *this day*" is actionable.
2. **Each cause links back to a rule** — snoozed, missing, or working. The bill and the rulebook are the same conversation.
3. **The unattributed remainder is shown.** A tool claiming to explain 100% of a change is lying. Showing the 7% it could not explain makes the 93% believable.

### 23.2 How attribution works

```
Cost Explorer, grouped by service + usage type + resource id
        |
        v
Compare window W to window W-1  ->  per-resource deltas
        |
        v
Rank by absolute delta, take everything above ₹40 or 2% of total
        |
        v
For each: join to the inventory history (§16.5 snapshots)
          -> what changed about this resource?
             created / resized / ran longer / more traffic
        |
        v
RAG #2 (§14) -> the pricing dimension + service explanation
        |
        v
Join to rules -> is there a rule for this? was it snoozed?
        |
        v
Narrate, with the §14.4 grounding check
```

Resource-level granularity requires cost allocation tags to be activated on the account — a documented setup step, and one worth surfacing in onboarding, because without it this feature degrades to service-level attribution, which is much weaker.

### 23.3 Triggering

- **Automatic** — daily anomaly check; a day exceeding a rolling-median baseline by more than a threshold opens an investigation
- **Manual** — "Why did my bill change?" against any two windows
- **On the monthly bill** — a full month-over-month investigation when the bill lands

Anomaly detection stays deliberately simple: rolling median plus MAD, with a day-of-week adjustment. A learned detector is not worth the complexity on ~90 data points, and the failure mode of a complicated detector on sparse data is confident nonsense.

### 23.4 The explanation-to-rule loop

This closes the loop §3.3's N3 claims, and it is the feature that makes the claim true rather than aspirational.

```
"Three 100GB gp3 volumes created Aug 12, still unattached, ₹240"
        |
        v
"Want a rule for this?"
        |
        v
Ward drafts: "Flag EBS volumes unattached for more than 7 days"
        |
        v
Simulate (§16)  ->  "matches 3 resources now, would have fired
                     twice in the last 30 days, ₹890 avoided"
        |
        v
Clarify if ambiguous (§20) -> Explain (§15) -> Activate
```

Every earlier feature in this section is a station on this path. The loop is the argument for building them.

### 23.5 Files

```
backend/app/explainer/
├── anomaly.py           (extend) rolling median + MAD
├── attribute.py         per-resource delta attribution
├── investigate.py       the full investigation pipeline
├── narrate.py           (extend) grounded narration
└── to_rule.py           explanation -> draft rule

frontend/src/pages/
└── Detective.tsx

frontend/src/components/
├── CauseCard.tsx
└── UnattributedNote.tsx
```

### 23.6 Evaluation

The 50-scenario graded set from §14.6, extended with the attribution questions:

| Metric | Target |
|---|---|
| Top cause correct | ≥ 85% |
| Attributed fraction | ≥ 80% of the delta explained |
| Over-attribution | 0 — never claim a cause without resource-level evidence |
| Suggested rule accepted | ≥ 40% of drafted rules activated |

---

## 24. Emergency budget mode

**The problem.** Every feature above is preventive. None of them help the user who opens the dashboard on a Sunday and finds ₹18,000 of a ₹5,000 monthly budget already spent. Preventive tools have nothing to say once prevention has failed.

**The feature.** A single control that moves Ward from watching to intervening, with the intervention scoped and approved in advance.

### 24.1 The constraint that shapes everything

§7 states it: **Ward never gets write access in V1.** Emergency mode is the first feature that wants it, and the document's own rule stands — any write capability is a separate IAM role, separately granted, explicitly scoped.

Two tiers, and the boundary between them is a hard one:

```
TIER 1 — ADVISORY  (no new permissions, ships first)
  - Every threshold tightens
  - Notification interval drops to 5 minutes
  - Every running resource ranked by ₹/hour
  - One-click AWS console links to stop each one
  - A copy-pasteable AWS CLI command per resource
  - Snooze disabled account-wide

TIER 2 — ACTIVE  (separate IAM role, opt-in, per-action approval)
  - Stop non-production instances above a ₹/hour threshold
  - Never touches: anything tagged Environment=production,
    anything tagged ward:protect, RDS, anything holding data
  - Every action requires explicit confirmation
  - Full audit log, every action reversible
```

Ship Tier 1 in the Second Iteration. Tier 2 belongs in the same conversation as auto-remediation (§13) and should not be built until that role model is designed properly.

### 24.2 What Tier 1 looks like

```
⚠ EMERGENCY BUDGET MODE — active since 14:02

  Spent this month:  ₹18,240  /  ₹5,000 budget   (365%)
  Burning now:       ₹287/hour
  At this rate:      ₹24,100 more before month end

  RUNNING NOW, MOST EXPENSIVE FIRST

  1. i-0a1f2  g4dn.xlarge   ₹101/hr   running 31h
     tags: none                      [ stop in console ] [ CLI ]
  2. i-0b3d4  g4dn.xlarge   ₹101/hr   running 28h
     tags: none                      [ stop in console ] [ CLI ]
  3. nat-0c5   NAT Gateway   ₹1.50/hr + data
     in vpc-dev-2                    [ open ] [ CLI ]
  4. db-0d6    db.t3.medium  ₹6/hr    ⓘ holds data — review
                                      before stopping

  Stopping 1 and 2 saves ₹202/hour — ₹4,848/day.

  [ Exit emergency mode ]
```

The ranking is the feature. In a real overspend the user does not need analysis, they need to know which two machines to kill first, and they need it above the fold.

### 24.3 Triggering

| Trigger | Condition |
|---|---|
| Automatic | Projected month-end exceeds budget by > 150% |
| Automatic | Spend in any 24h exceeds 20% of the monthly budget |
| Manual | The user hits the button |
| Manual exit | Always available, always the user's call |

Auto-entry sends a notification on every configured channel. This is the one event where the §4.3 "stay quiet" discipline is suspended — but it fires once on entry, not every five minutes. Even here, repeated messaging gets the tool muted precisely when it matters most.

### 24.4 Cost of the mode itself

Polling every 5 minutes instead of 15 triples the API call rate against Cost Explorer, which charges per request. Cap it: emergency mode auto-expires after 24 hours unless renewed, and Ward reports its own additional cost in the panel.

A tool that quietly spends more money during a cost emergency has misunderstood its job.

### 24.5 Files

```
backend/app/emergency/
├── trigger.py           entry conditions
├── rank.py              running resources by ₹/hour
├── actions.py           console links + CLI command generation
└── mode.py              state, expiry, cost accounting

frontend/src/pages/
└── Emergency.tsx        full-screen takeover, deliberately loud
```

---

## 25. Second Iteration — dependencies and sequencing

### 25.1 What depends on what

```
§16 SIMULATOR  ──────────────────────────────────────┐
  (inventory snapshots + time travel)                │
      │                                              │
      ├──> §15 EXPLAINABILITY   (live match counts)  │
      ├──> §17 SAVINGS          (historical replay)  │
      ├──> §18 WHAT-IF          (parameter sweep)    │
      ├──> §19 CONFLICTS        (empirical sets)     │
      ├──> §20 CLARIFIER        (option counts)      │
      └──> §22 QUALITY          (specificity)        │
                                                     │
§14 RAG #2  ─────────────────────────────────────────┤
  (pricing corpus + grounding)                       │
      │                                              │
      ├──> §17 SAVINGS          (₹/hour figures)     │
      ├──> §18 WHAT-IF          (₹ deltas)           │
      ├──> §23 DETECTIVE        (the explanations)   │
      └──> §24 EMERGENCY        (₹/hour ranking)     │
                                                     │
§21 RAG TRACE  ──> diagnostic for §14 and Phase 3 ───┘
```

**The simulator and RAG #2 are the two foundations. Build both before anything else in this section.** Seven of the nine remaining features are blocked on one or the other, and both are useful standalone — which is exactly the property Phase 1's verifier had, and the reason that ordering worked.

### 25.2 Suggested order

| Stage | Features | Why here |
|---|---|---|
| 2A | §16 simulator, §14 RAG #2 | Foundations. Everything else needs them. |
| 2B | §15 explainability, §21 RAG trace | Transparency. Cheap once 2A exists. |
| 2C | §17 savings, §18 what-if | The value story. Same engine, build together. |
| 2D | §19 conflicts, §22 quality | Rule hygiene. Share `RuleHealth.tsx`. |
| 2E | §20 clarifier, §23 detective | Highest complexity, highest research value. |
| 2F | §24 emergency (Tier 1) | Independent of everything. Ship whenever. |

§24 Tier 1 has no dependencies and is small. If morale needs a quick win, take it out of order.

### 25.3 A schema decision that cannot wait

Two items in this section require data that must be captured **before** the feature is built, because history cannot be reconstructed retroactively:

1. **Inventory snapshots per poll** (§16.5) — Phase 4 must append, not overwrite. Without this, time travel has nothing to travel through, and §17, §18, §19 and §23 all lose their historical basis.
2. **Assumption annotations in the training data** (§15.4) — the field must exist in the Phase 6 dataset schema even if it stays empty. Retrofitting it into 1,400 verified examples later costs a week.

Both are one-line decisions now and multi-week problems later. Make them during Phase 4 and Phase 6 respectively.

### 25.4 Ownership

| Feature | Owner | Rationale |
|---|---|---|
| §14 RAG #2 | A (corpus, retrieval) + B (grounding, API) | A already owns retrieval quality from Phase 3 |
| §15 Explainability | B (decompiler) + C (UI) | Deterministic renderer is backend work |
| §16 Simulator | B | Extends the watcher B already owns |
| §17 Savings | B (compute) + C (UI) | |
| §18 What-if | B (sweep) + C (slider) | |
| §19 Conflicts | B | Static analysis over c7n structure |
| §20 Clarifier | **A** | Logprobs and multi-sample divergence are model work |
| §21 RAG trace | A (analysis) + C (UI) | The trace is A's research instrument |
| §22 Quality | B + C | |
| §23 Detective | B (pipeline) + A (narration) + C (UI) | The one genuinely three-person feature |
| §24 Emergency | C | Mostly frontend; backend ranking is small |

### 25.5 Research value, honestly ranked

Not all of these are equally publishable. Ranked by what would survive review:

| Feature | Research contribution |
|---|---|
| §20 Clarifier | **Strong.** Multi-sample divergence as an ambiguity detector in NL→policy is not in the §3.1 prior work. Evaluable with a proper annotated set. |
| §15 Explainability | **Strong.** Round-trip comprehension is measurable (§15.6) and the "can non-experts verify generated policy" question is open. |
| §21 RAG trace | **Moderate.** The retrieval/grounding/knowledge failure taxonomy is a real contribution to RAG evaluation methodology. |
| §14 RAG #2 | **Moderate.** The grounding constraint (§14.4) is a defensible design claim; the retrieval itself is standard. |
| §19 Conflicts | **Moderate.** Policy conflict detection exists in access control; applying it to cost policy is a smaller but real step. |
| §17 §18 §22 §23 §24 | **Product value, not research.** Build them because they make Ward usable. Do not stretch them into contributions they are not. |

That last row is the important one. The §9.13 discipline — design an evaluation that can tell you the answer is no — applies to feature claims as much as to model results. Five excellent product features and two genuine research contributions is a good outcome. Seven claimed contributions with two that hold up is a worse one.

---
---

# Third Iteration

**Features 26–31. The interface layer.**

## 26. What this iteration changes about the project

The Second Iteration made an existing system trustworthy. This one changes what the system *is*.

Everything in §1–§25 describes a **policy compiler with a dashboard**. The user's primary act is writing a rule. Ward's primary act is enforcing it. The Third Iteration inverts that: the user's primary act becomes **asking a question**, and rule-writing becomes one of several things Ward can do in response.

That is a real change of shape, and it should be made deliberately rather than by accumulation.

### 26.1 What gets better

The original framing has a cold-start problem it never solves. §2 says "users then add their own rules in plain English" — but a second-year student who has just opened an AWS account does not know what rules they need, because they do not yet know what a NAT Gateway is or that an unattached EBS volume bills forever. The default rulebook papers over this. A copilot actually fixes it: the user asks what is costing money, learns the answer, and the rule follows from the understanding rather than preceding it.

The Guardian (§31) closes the same gap from the other side — Ward finds the problems the user did not know to ask about.

### 26.2 What gets risked

Three things, stated plainly.

**The research core gets starved.** §11 already lists "scope creep back to the 12-phase plan" as a high-impact risk. This iteration is larger than that plan. Phases 6 and 9 — the fine-tuning pipeline and the held-out evaluation — are what make this a research project rather than a product demo. They must be finished and written up before any of §27–§31 begins. Not "mostly finished." Finished.

**The verifier discipline does not extend to everything here.** §9.1 is precise about why fine-tuning is safe for this task: *correctness is machine-checkable*. That property holds for English→YAML. It does **not** hold for "what architecture should I use," and it holds only partially for conversational answers. §30 addresses this directly, and the answer is to constrain the task until it becomes checkable again rather than to abandon the constraint.

**N2's privacy claim comes under pressure.** §3.3 claims the small model works "without sending infrastructure configuration to a third party." A frontier-backed copilot sends inventory to a third party by construction. §32.2 deals with this. It is solvable, but it must be solved explicitly and not discovered during the viva.

### 26.3 The honest framing for the report

Write it this way:

> Ward's research contribution is a verifier-distilled small model for natural-language cost policy compilation (§3.3, Phases 6 and 9). Ward's product surface is a natural-language interface to AWS cost management, of which the compiler is one component.

Two sentences, clearly separated. A reviewer who reads the copilot as the research claim will ask what the oracle is and there will be no good answer. A reviewer who reads it as the product surface around a verified core will find the structure obvious and correct.

---

## 27. Natural-language AWS copilot

**The core interface.** Instead of navigating the AWS console, the user talks to Ward.

```
"What is currently costing me the most?"
"Show me my running servers."
"I need a database for my college project under ₹500/month."
"Why is this resource here?"
"Create a rule so this doesn't happen again."
```

```
User
  ↓
Plain English
  ↓
Intent understanding
  ↓
RAG + AWS knowledge
  ↓
AWS operation / recommendation
```

### 27.1 Why the console is the thing being replaced

The AWS console is a competent interface for someone who already knows AWS. For a beginner it has a specific failure: **it is organised by service, and the user's question is never about a service.** "What is costing me the most" spans EC2, RDS, VPC and S3, each behind a different console page, none of which shows cost. Cost Explorer shows cost but not resources. The information needed to answer one sentence is scattered across four products.

Ward's inventory database already joins all of it. The copilot is the query interface over a join the user cannot perform themselves.

### 27.2 Intent taxonomy

Every utterance routes to exactly one of four intents. Fixed set, no open-ended agent loop.

| Intent | Example | Handler | Touches AWS? |
|---|---|---|---|
| **QUERY** | "show my running servers", "what costs the most" | Query planner over Postgres inventory + Cost Explorer | Read, cached |
| **EXPLAIN** | "why is this resource here", "why did my bill change" | Explainer (§23) + RAG #2 (§14) | Read |
| **ADVISE** | "I need a database under ₹500/month" | Architect (§30) | No |
| **ACT** | "create a rule so this doesn't happen again" | Compiler (§4.1) → Simulator (§16) → approval | **No — produces a draft** |

The fourth row is the load-bearing one. **ACT never writes to AWS.** It produces a draft guardrail that goes through the existing verify → simulate → explain → approve path. "Create a rule" means "compile a rule and show it to me," not "change my account."

Anything that does not classify into one of the four gets a plain refusal — see §27.7. Do not add a fallback that lets an unclassified utterance reach a general-purpose agent loop with AWS credentials attached.

### 27.3 The query planner

QUERY is the highest-volume intent and it must be the most constrained. The implementation is **not** free-form tool calling.

```
"what is costing me the most this week"
        ↓
Intent: QUERY
        ↓
Slot extraction:  metric=cost, window=7d, group_by=resource,
                  order=desc, limit=5
        ↓
Typed query object  (not SQL text, not a tool call)
        ↓
Validated against a fixed query schema
        ↓
Executed as a parameterised query over the inventory +
cost tables Ward already maintains
        ↓
Rows
        ↓
Narration with the §14.4 grounding check
```

The model fills slots in a typed structure. It does not write SQL and it does not choose which function to call from a menu of AWS operations. The query schema defines what is answerable; anything outside it is a refusal rather than an improvisation.

This is deliberately less flexible than an agent. The trade is worth it: a slot-filling error produces a wrong-but-safe query, while a tool-calling error in a system holding cloud credentials produces an incident. Ward's whole premise is protecting people from their own cloud accounts.

**Never touch AWS live in the query path.** Answer from the inventory snapshots (§16.5) and the cost tables. They are at most 15 minutes old and the freshness is shown in the answer. A copilot that fans out boto3 calls per question will be slow, rate-limited, and — for Cost Explorer, which bills per request — will spend the user's money to tell them about their spending.

### 27.4 Grounding

The §14.4 rule extends to every copilot response, with one addition:

**The model may never emit a resource identifier, instance type, region, or figure that did not appear in the query result.**

Post-generation check in `ground.py`:

```python
# Every i-*, vol-*, db-*, nat-*, arn:* token in the response
# must appear in the result rows.
# Every ₹ figure must appear in the rows or be derivable from them.
# Violation -> regenerate once -> then render the rows as a plain
# table with no prose at all.
```

The plain-table fallback is the important half. A table of real rows with no sentence is a worse answer than a good paragraph and a far better answer than a fluent paragraph containing an instance ID that does not exist. Users check IDs against their console; one hallucinated ID ends the account's trust in the tool permanently.

### 27.5 Conversation state

Keep it small and explicit. The copilot tracks:

- **Referent** — what "this", "it", "that one" points at. Resolved to a resource ID at parse time, then stored. If it cannot be resolved, ask rather than guess.
- **Window** — the active time range, so "and last month?" works.
- **Last result set** — so "create a rule for that" knows what "that" was.

Nothing else. No long-horizon memory of the conversation, no accumulated persona. A three-slot state is debuggable; a transcript-in-the-prompt design is not, and it grows the context window past what a self-hosted model handles well.

Ambiguous referents route to the Clarifier (§20), which already exists for exactly this.

### 27.6 The handoff to rule creation

The sentence that makes the product coherent is "create a rule so this doesn't happen again," and it is worth tracing end to end because it touches almost every component in the document:

```
"create a rule so this doesn't happen again"
        ↓
Referent from conversation state:  i-0a1f2, ran 31h, g4dn.xlarge
        ↓
Draft an English rule from the incident, not from the sentence:
  "No GPU instance runs more than 6 hours"
        ↓
Show the drafted English for confirmation  ← the user edits here
        ↓
COMPILER (§4.1)      English → YAML
        ↓
VERIFIER (Phase 1)   fixtures pass?
        ↓
SIMULATOR (§16)      "matches 2 of your 14 instances now,
                      would have fired 7× in 30 days,
                      ₹4,774 avoided"
        ↓
EXPLAINABILITY (§15) "here is what Ward understood"
        ↓
User approves  →  active guardrail
```

Note the drafting step. The user's sentence says "this" — the incident — not the rule. Ward generalises the incident into a rule and **shows the generalisation in English before compiling it**. Generalising silently is how the user ends up with a rule about `i-0a1f2` specifically, or a rule about all EC2 instances, and no way to tell which.

### 27.7 What Ward refuses

A clear refusal surface, stated in the product and enforced in code:

| Request | Response |
|---|---|
| "delete this instance" / "stop that server" | "Ward has read-only access to your account by design. Here is the console link and the CLI command to do it yourself." |
| "give me my access keys" | Refuse. Ward never reads or stores credentials beyond the assumed role. |
| Anything not in the four intents | "Ward handles cost, resources and guardrails. That question is outside what it can answer." |
| A question whose answer needs data Ward does not collect | Say which data is missing and how to enable it — do not approximate. |

The first row will be the most common and the refusal must come with the alternative attached. "I can't do that" alone reads as a broken tool; "I can't do that, here is exactly how you do it in two clicks" reads as a careful one. §24.2 already generates console links and CLI commands — reuse that renderer.

### 27.8 Files

```
backend/app/copilot/
├── intent.py            four-way classification
├── slots.py             slot extraction into typed query objects
├── schema.py            the fixed query schema — what is answerable
├── plan.py              typed query -> parameterised execution
├── state.py             referent / window / last result
├── narrate.py           rows -> English, grounded
├── ground.py            the §27.4 identifier + figure check
├── refuse.py            refusal surface + alternatives
└── route.py             dispatch to explainer / architect / compiler

backend/app/api/
└── chat.py              POST /chat  (SSE streaming)

frontend/src/pages/
└── Copilot.tsx          the primary interface

frontend/src/components/
├── Message.tsx
├── ResultTable.tsx      the ungrounded-fallback renderer
├── FreshnessNote.tsx    "inventory as of 14:03, 6 minutes ago"
└── SuggestedNext.tsx    follow-up prompts
```

### 27.9 Evaluation

Build a 200-utterance set covering the four intents plus 40 out-of-scope utterances.

| Metric | Definition | Target |
|---|---|---|
| Intent accuracy | Correct of four classes | ≥ 95% |
| Slot F1 | Extracted slots vs gold | ≥ 0.90 |
| Answer correctness | Answer matches ground truth from the database | ≥ 90% |
| **Hallucinated identifiers** | Resource IDs not in the result set | **0. Any occurrence is a bug, not a metric.** |
| Refusal correctness | Out-of-scope correctly refused | ≥ 98% |
| Latency, p95 | End to end | < 3s |

Hallucinated identifiers get a zero target rather than a percentage. A metric implies an acceptable rate; there is not one.

---

## 28. AI cloud guardrails + policy simulator

**The signature feature.** This is the path §1–§25 already builds, packaged as one flow the user recognises.

```
English
   ↓
RAG
   ↓
LLM
   ↓
Cloud Custodian policy
   ↓
VERIFIER
   ↓
SIMULATE
```

```
"Don't let GPU instances run for more than 6 hours."

  2 of your 14 instances would violate this rule.
  Estimated avoidable cost:  ₹2,840/month

  [ Activate guardrail ]   [ What did Ward understand? ]
```

### 28.1 This is a packaging feature, not a new engine

Everything behind that card already has a specification:

| Card element | Comes from |
|---|---|
| English → YAML | Compiler, §4.1 + Phase 6 |
| Correctness before it is trusted | Verifier, Phase 1 |
| "2 of your 14 instances" | Simulator, §16.1 |
| "would have fired 7× in 30 days" | Time travel, §16.3 |
| "₹2,840/month avoidable" | Savings, §17 + pricing from §14 |
| "What did Ward understand?" | Explainability, §15 |
| "too broad / will be ignored" warnings | §16.2 + §18.2 |

Build nothing new here. The work is the card: getting seven components onto one screen in an order that makes the decision obvious.

### 28.2 Card specification

The order is fixed and it matters. Consequence first, mechanism on request.

```
1. The rule, as the user wrote it
2. Match count against live inventory, with the resources named
3. Historical fire rate  — "7 times in 30 days, quiet on 23 days"
4. Money  — with the counterfactual named (§17.2)
5. Alert load  — "~2 notifications/week"          (§18.2)
6. Warnings  — over-broad, noisy, conflicts with an existing rule (§19)
7. [ Activate ]  [ What did Ward understand? ]  [ View YAML ]
```

Rows 1–3 are facts. Row 4 is an estimate and must be labelled as one — the counterfactual assumption goes on the card, not behind a tooltip. Row 5 exists because a rule that saves ₹2,840 and interrupts the user daily will be deleted within a fortnight, and the decision should be made with both numbers visible.

### 28.3 The cost figure's provenance

"₹2,840/month" is the most quoted number in the product and the easiest one to get wrong. It must decompose on click:

```
₹2,840/month estimated avoidable
  = 2 instances × g4dn.xlarge × ap-south-1
  = ₹101.14/hour            ← pricing chunk, §14.3, effective 2026-01-01
  × 28.1 hours/month avoided
      ← 7 historical violations × 4.01h average excess runtime
      ← counterfactual: next-morning (§17.2, default)
  = ₹2,840
```

Every line traces to a source. This is the §14.4 grounding rule applied to the single figure the user will repeat to other people.

### 28.4 Files

No new backend modules. The card lives in:

```
frontend/src/components/
├── GuardrailCard.tsx        the seven-row card
└── CostProvenance.tsx       the §28.3 decomposition

backend/app/api/
└── rules.py                 (extend) GET /rules/{id}/activation-summary
```

One endpoint that assembles the seven elements in a single round trip. Seven separate calls from the frontend would make the most important screen in the product the slowest.

---

## 29. AI cost detective

**One button.** 🔍 *Why did my AWS bill increase?*

```
₹5,240  →  ₹8,910      ↑ ₹3,670

MAIN CAUSE
──────────────────────────────
EC2 GPU usage        +₹2,840
RDS                    +₹540
NAT Gateway            +₹210
S3                      +₹80

WHY
Your g5.xlarge ran 43 hours longer than your previous average.
Estimated additional cost: ₹2,840

RECOMMENDED GUARDRAIL
"GPU instances must not run longer than 6 hours."
                                        [ Create rule ]
```

### 29.1 Relationship to §23

§23 specifies the investigation engine — attribution, the unattributed remainder, RAG #2 grounding, the explanation-to-rule loop. This section adds the two things §23 lacks.

**The button.** §23's triggers are automatic anomaly detection and a two-window comparison form. Neither is what a worried user reaches for. One button, on the dashboard, phrased as the question they are actually asking.

**The waterfall.** §23 renders causes as a list of cards. A bill change is a decomposition and reads better as one:

```
₹5,240 ──────────────────┐
                         │
  EC2 GPU      +₹2,840  ███████████████
  RDS            +₹540  ███
  NAT Gateway    +₹210  █
  S3              +₹80  ▌
  unattributed     +₹0
                         │
₹8,910 ──────────────────┘
```

The bar lengths make "one thing caused this" visible before any text is read. In the common case the answer is a single resource and the chart says so instantly.

### 29.2 Keep the unattributed row

§23.1 is firm that the remainder is shown even when it is zero. The mockup above shows `+₹0`, which looks like a wasted line and is not: it tells the user Ward accounted for the whole change. When it reads `+₹340` the user knows exactly how much to distrust. Removing this row for tidiness removes the reason to believe the other rows.

### 29.3 Files

```
frontend/src/pages/
└── Detective.tsx        (from §23.5 — add the button entry point)

frontend/src/components/
├── Waterfall.tsx        the decomposition chart
└── CauseCard.tsx        (§23.5)

backend/app/api/
└── costs.py             (extend) GET /costs/investigate?window=7d
```

Backend is §23.5 unchanged.

---

## 30. AI AWS architect

**Useful before the user has any AWS architecture at all.**

```
"I want to deploy my MERN attendance application for
 500 students and keep it under ₹1,500/month."
```

```
RECOMMENDED ARCHITECTURE

              Users
                ↓
             Backend              EC2  t3.small
                ↓
          ┌─────┴─────┐
          ↓           ↓
         RDS          S3          db.t3.micro / standard
          │
       Database

Estimated cost:   ₹900–₹1,300/month
Complexity:       Beginner-friendly

WHY THESE SERVICES
  EC2  — your virtual computer, runs the Node backend
  RDS  — your managed database, backups handled for you
  S3   — your file storage, for attendance exports and photos

WHY NOT KUBERNETES
  At 500 users your application runs comfortably on one
  server. Kubernetes would add a control plane charge of
  ~₹6,000/month and a great deal of complexity to solve a
  problem you do not have yet.
```

### 30.1 The verifier problem, stated before the design

Every other generative component in Ward has an oracle. English→YAML has the verifier (Phase 1). Cost explanations have Cost Explorer and the §14.4 grounding check. Query answers have the database.

**"Is this a good architecture" has no oracle.** There is no fixture that fails when the recommendation is wrong. §9.1 is explicit that a task with a verifier is a task you can fine-tune safely — and by that standard this feature is the one place in the document where the discipline does not transfer.

So the design constrains the task until it becomes checkable again. Three constraints, all load-bearing.

### 30.2 Constraint 1 — a pattern catalogue, not free generation

Ward does not invent architectures. It **selects and parameterises** from a hand-written catalogue of roughly 15 reference patterns.

```
knowledge/architectures/
├── static_site.yaml              S3 + CloudFront
├── single_server_webapp.yaml     EC2 + RDS + S3          ← MERN lands here
├── serverless_api.yaml           Lambda + API GW + DynamoDB
├── containerised_small.yaml      ECS Fargate + RDS
├── ml_training_job.yaml          EC2 GPU spot + S3
├── ml_inference_endpoint.yaml    ECS + ALB
├── batch_pipeline.yaml           EventBridge + Lambda + S3
├── internal_tool.yaml            EC2 + RDS, no public ingress
└── ...
```

Each pattern is a hand-written, reviewed document:

```yaml
name: single_server_webapp
fits:
  - node/python/php backend with a relational database
  - under ~2000 daily active users
  - single region, no HA requirement
does_not_fit:
  - needs zero-downtime deploys
  - traffic spikes beyond one instance
  - regulated data with residency requirements
components:
  - service: ec2
    sizing_rule: "t3.small under 500 DAU, t3.medium to 2000"
  - service: rds
    sizing_rule: "db.t3.micro under 500 DAU"
  - service: s3
alternatives_rejected:
  - pattern: containerised_small
    because: "adds orchestration for no benefit at this scale"
  - pattern: kubernetes
    because: "EKS control plane ~₹6000/mo before any workload"
```

The model's job is **matching a requirement to a pattern and sizing it**, not designing. That is a classification-plus-parameterisation task, and it is evaluable: a human expert can label which pattern is correct for a given requirement, and match accuracy becomes a real number.

Free-form architecture generation would produce more impressive demos and would have no defensible evaluation. The catalogue is the trade that keeps this feature honest.

### 30.3 Constraint 2 — the cost estimate is verifiable, so verify it

The architecture recommendation cannot be checked. **The cost estimate attached to it can be**, and this is the feature's saving grace.

```
Recommendation made          "₹900–₹1,300/month"
        ↓
User deploys (or does not)
        ↓
30 days later, if they deployed
        ↓
Actual cost from Cost Explorer:  ₹1,080
        ↓
Logged in results/architecture_estimates.csv
```

This is the same self-grading structure as Phase 5's cost prediction, and it produces a genuine number for the report: *architecture cost estimates fell within the stated range in N of M cases.* An estimate that is right is weak evidence the architecture was right — but it is evidence, and it is the only kind available.

Estimates come from the §14.3 normalised pricing store, never from the model. The model picks the pattern and the sizes; arithmetic is arithmetic.

### 30.4 Constraint 3 — bias hard toward simplicity

The failure mode of every AI architecture advisor is over-engineering. It recommends the architecture that appears in AWS blog posts, which are written about large systems, because that is what the training data contains.

Ward's rule, stated in the product:

> **Recommend the simplest architecture that satisfies the requirement. Complexity must be justified by a requirement the user actually stated.**

Enforced mechanically, not by prompting alone:

```python
# A pattern may only be recommended if every component is
# justified by a stated requirement.
#
# Multi-AZ            requires the user to have said "must not go down"
# Load balancer       requires >1 backend instance
# Kubernetes          requires >1 service AND a stated scaling need
# Auto-scaling group  requires a stated variable-load pattern
# Read replica        requires a stated read-heavy workload
#
# Unjustified component -> drop it, and record why in the
# "why not" section.
```

The **"why not" section is a first-class output**, not a footnote. For a student learning AWS, "why you don't need Kubernetes" is more valuable than the recommendation itself — it is the piece of judgement that no tutorial provides and no console page contains. It also inoculates against the next blog post they read.

### 30.5 Requirement elicitation

The user's sentence is underspecified: "500 students" does not state concurrency, data volume, uptime requirement, or region. Do not guess all four silently.

Reuse the §20 Clarifier, with the same restraint — ask only what changes the pattern:

```
Two things affect the answer:

  Will students use it all at once?
    ● Spread through the day        → t3.small
    ○ All at 9am (attendance rush)  → t3.medium + a queue

  If it goes down for an hour, is that a problem?
    ● Not really — it's a college project   → single instance
    ○ Yes, it must stay up                  → multi-AZ, ~₹1,400 more
```

Two questions, each with its consequence attached in rupees and hardware. Not a form. Every option shows what it changes about the answer, so the user learns the shape of the trade-off even if they pick the default.

### 30.6 Deliberately not in scope: generated Terraform

It is tempting to end this feature with "and here is the Terraform to deploy it." Do not, in this iteration.

Ward's entire thesis is that people should not be handed infrastructure code they cannot read. Generating 200 lines of HCL for a user who does not know what a VPC is, and inviting them to `terraform apply` it against a real account, contradicts the argument in §1 as directly as it is possible to contradict it.

If it ships later it needs the §15 treatment first — every generated resource explained in English, a cost simulation before apply, and a destroy path that is as prominent as the apply path. That is a feature of its own, not a button on this one.

### 30.7 Files

```
backend/app/architect/
├── elicit.py            requirement extraction + clarifying questions
├── match.py             requirement -> pattern, with confidence
├── size.py              pattern + scale -> component sizes
├── estimate.py          sizes × §14.3 pricing -> range
├── justify.py           why these services, in beginner English
├── reject.py            why NOT the alternatives — the key output
└── track.py             log estimate, grade against actual at 30d

knowledge/architectures/       the hand-written catalogue
frontend/src/pages/
└── Architect.tsx

frontend/src/components/
├── ArchitectureDiagram.tsx
├── ServiceExplainer.tsx        "EC2: your virtual computer"
└── WhyNot.tsx
```

### 30.8 Evaluation

| Metric | Method | Target |
|---|---|---|
| Pattern match accuracy | 60 requirements, expert-labelled correct pattern | ≥ 80% |
| **Over-engineering rate** | Components recommended without a stated requirement | **< 5%** |
| Cost estimate accuracy | Actual within stated range at 30 days (§30.3) | ≥ 70% |
| Explanation quality | Non-technical readers rate "I understand why" | ≥ 4/5, 20 readers |
| Clarifying questions | Average per requirement | ≤ 2 |

Over-engineering rate is the metric that distinguishes this from a well-prompted chatbot, and it is measurable by static inspection of the output against the requirement — no human judgement needed.

---

## 31. AI AWS guardian

**Continuous review of the account, with every finding attached to a fix.**

```
SECURITY
  🚨  Your database is publicly accessible.
  ⚠️  SSH is open to the entire internet (0.0.0.0/0).

WASTE
  💸  3 unattached EBS volumes — ~₹420/month.

CONFIGURATION
  ⚠️  7 resources have no owner tag.

BEHAVIOURAL
  💡  Your GPU is repeatedly left running over weekends.
      → Suggested guardrail:
        "GPU instances should not run over weekends."
                                    [ Review & activate ]
```

```
WARD WATCHES AWS
       ↓
Finds problem
       ↓
Explains problem
       ↓
Calculates impact
       ↓
Suggests solution
       ↓
Generates guardrail
       ↓
Verifies guardrail
       ↓
User approves
```

### 31.1 Three of the four detector families are prior art — say so

This matters for the report, and it is the kind of claim that gets a project marked down when overstated.

| Family | Prior art | Ward's position |
|---|---|---|
| Security | AWS Trusted Advisor, Security Hub, Prowler, ScoutSuite, and ~40 c7n built-in filters | **Use them. Do not reimplement.** Public RDS and open SSH are solved detections. |
| Waste | Komiser (§3.2), Trusted Advisor, c7n filters | Already in the document as prior art. |
| Configuration | c7n tag filters, AWS Config rules | Trivial with c7n. |
| **Behavioural** | Largely absent from the tools surveyed | **This is the new part.** |

Implement security, waste and configuration as a curated set of existing Cloud Custodian policies shipped with Ward — perhaps 40 of them, hand-written once, no model involved. They are deterministic checks and a language model adds nothing but risk.

**Ward's contribution in this feature is the loop, not the detection.** Existing tools produce a findings list and stop. Ward explains the finding in beginner English, prices it, and converts it into a guardrail that prevents recurrence. That is the §3.3 N3 claim applied to security and waste rather than cost alone, and it is defensible. "We detect public databases" is not.

### 31.2 Behavioural detection — the part worth building

The other three families ask *what is true right now*. This one asks *what keeps happening*, and it needs the inventory snapshot history from §16.5.

```
90 days of inventory snapshots
        ↓
Mine for recurring patterns
        ↓
"GPU instance running at 02:00 on Saturday"
  observed on 3 of the last 4 weekends
        ↓
Confidence: 0.75  (3/4, and the 4th weekend had no GPU at all)
        ↓
Not a one-off. A habit.
        ↓
Draft: "GPU instances should not run over weekends"
        ↓
Simulate (§16) -> "would have fired 3× in 30 days,
                   ₹5,200 avoided"
```

Pattern families to mine, in priority order:

| Pattern | Signal | Why it matters |
|---|---|---|
| **Weekend runner** | Resource active Sat/Sun across ≥ 3 occurrences | The single most common student overspend |
| **Overnight runner** | Active 00:00–06:00 repeatedly | Same cause, finer grain |
| **Create-and-forget** | Resource created, never modified, never accessed, still billing | Unattached volumes, idle load balancers |
| **Ratchet** | A resource type that only ever grows — sizes up, never down | Silent monthly increase, invisible in any single bill |
| **Post-deadline** | Usage spike followed by resources that outlive the spike | Exam projects, hackathons — reliably left running |

These are pattern-matching over a time series, not machine learning. Explicit rules with counts and thresholds. With 90 days of data and a handful of resources there is nothing for a learned model to learn, and a learned detector on sparse data produces confident nonsense — the same argument made in §23.3 about anomaly detection.

Behavioural detection is the strongest argument for the §25.3 warning about inventory snapshots. Without per-poll history this entire family is impossible, and the history cannot be backfilled.

### 31.3 Noise control

Guardian will find more than the user will act on. A fresh student account plausibly produces 25 findings on day one, and 25 findings is the same as zero.

**Show three. Ranked. Weekly.**

```
rank = impact(₹/month) × confidence × actionability / age_penalty
```

- **Impact** — priced from §14.3; security findings get a fixed notional weight since "publicly accessible database" has no rupee figure
- **Confidence** — deterministic checks are 1.0; behavioural patterns carry their observed frequency
- **Actionability** — is there a one-click fix or a draftable guardrail? A finding with no fix ranks below one with a fix
- **Age penalty** — a finding shown three times and ignored moves down, then to a "dismissed" list

Everything else lives on a full findings page the user can open. The weekly digest shows three. §22's discipline about alert fatigue applies with equal force here: Guardian competes for the same attention budget as the guardrails, and it must lose that competition when the guardrails have something to say.

### 31.4 Security findings are the exception

One finding type bypasses the weekly digest and the three-item cap: **a publicly exposed data store.** Public RDS, public S3 bucket with objects, an open database port on 0.0.0.0/0.

These notify immediately, on every channel, once. They are not cost findings — the loss is unbounded and the window matters. §4.3's "only notify on transitions" still holds (notify when it *becomes* public, not every poll), but the transition fires at full volume rather than waiting for Sunday's digest.

This is the second exception to the quiet discipline, after §24.3's emergency entry. There should not be a third.

### 31.5 Files

```
backend/app/guardian/
├── policies/                 ~40 curated c7n policies, hand-written
│   ├── security/
│   ├── waste/
│   └── configuration/
├── scan.py                   run the curated set on a schedule
├── behavioural/
│   ├── weekend.py
│   ├── overnight.py
│   ├── forgotten.py
│   ├── ratchet.py
│   └── deadline.py
├── impact.py                 price the finding
├── rank.py                   the §31.3 ranking
├── digest.py                 weekly three
├── urgent.py                 the §31.4 exception path
└── to_rule.py                shared with §23.5 — one implementation

frontend/src/pages/
└── Guardian.tsx

frontend/src/components/
├── Finding.tsx
├── FindingDigest.tsx
└── PatternEvidence.tsx       "observed on 3 of the last 4 weekends"
```

`PatternEvidence.tsx` earns its place. A behavioural claim the user cannot check is a claim they will not believe — showing the three specific weekends, with dates and hours, turns an assertion into an observation.

### 31.6 Evaluation

| Metric | Definition | Target |
|---|---|---|
| Security detection | vs Prowler on the same account | Parity — it is the same underlying checks |
| Behavioural precision | Patterns confirmed real by the user | ≥ 75% |
| Behavioural recall | Known planted patterns detected | ≥ 70% |
| Digest action rate | Of three weekly findings, acted on | ≥ 50% |
| Suggested guardrail acceptance | Drafted rules activated | ≥ 40% |

Digest action rate is the honest measure of whether Guardian works. A findings list nobody acts on is a list nobody needed.

---

## 32. The five together

### 32.1 Composed architecture

```
                    ┌──────────────────┐
                    │   NORMAL USER    │
                    └────────┬─────────┘
                             │
                      Plain English
                             │
                             ▼
                 ┌───────────────────────┐
                 │  §27  AWS COPILOT     │
                 │  intent → slots       │
                 └───────────┬───────────┘
                             │
                             ▼
                    ┌────────────────┐
                    │  RAG + LLM     │
                    │  #1 schemas    │
                    │  #2 pricing    │
                    └───────┬────────┘
                            │
        ┌───────────────────┼───────────────────┐
        ▼                   ▼                   ▼
   §30 ARCHITECT      §28 GUARDRAILS      QUERY / EXPLAIN
   pattern match           │                    │
   + sizing                ▼                    │
        │            §16 SIMULATOR              │
        │                  │                    │
        │              VERIFIER                 │
        │            (Phase 1)                  │
        │                  │                    │
        └──────────────────┤                    │
                           ▼                    │
                    ┌──────────────┐            │
                    │ AWS ACCOUNT  │◄───────────┘
                    │  (read-only) │
                    └──────┬───────┘
                           │
                 ┌─────────┴─────────┐
                 ▼                   ▼
         §29 COST DETECTIVE     §31 GUARDIAN
                 │                   │
                 └─────────┬─────────┘
                           ▼
                   AI EXPLANATION
                    (grounded, §14.4)
                           │
                           ▼
                   SUGGESTED RULES
                           │
                           └──────► back to §28
```

The loop closes twice. Detective and Guardian both feed suggested rules back into the guardrail path, and both use the same `to_rule.py`. That single shared module is what makes the diagram a cycle rather than two pipelines drawn near each other — build it once, in §23.5, and import it in §31.5.

### 32.2 Model strategy — and what it does to N2

The fine-tuned 7B compiler cannot be the copilot's brain. It was trained on one task with one output format (§9.1) and would be poor at conversation, routing and advice. Different jobs need different models.

| Job | Model | Why |
|---|---|---|
| English → c7n YAML | **Fine-tuned 7B** (Phase 6) | Narrow translation, verifier-checked. The research artefact. |
| Intent classification (§27.2) | Small classifier or 1.5B | Four labels, very high volume, must be cheap and fast |
| Slot extraction (§27.3) | Fine-tuned 1.5B, or the 7B | Structured extraction — same shape as the compiler task |
| Conversation, narration | 8B instruct, or frontier | Open-ended, needs breadth |
| Architecture matching (§30) | Frontier + catalogue retrieval | Judgement, no verifier — use the strongest available |
| Behavioural patterns (§31.2) | **No model** | Deterministic time-series rules |
| Security/waste detection | **No model** | Curated c7n policies |

Two rows deserve emphasis. The last two: a large part of this iteration is best served by no language model at all, and choosing that deliberately is a design result worth stating in the report.

**Now the problem.** §3.3's N2 claims the fine-tuned model works "without sending infrastructure configuration to a third party." A frontier-backed copilot sends inventory to a third party on every question.

This does not invalidate N2 — but the report must be exact about scope, or a reviewer will read it as overreach:

> N2 concerns the **policy compiler**. The compiler runs entirely on self-hosted infrastructure; no resource configuration leaves the deployment during policy generation. Ward's conversational surface may optionally use a hosted model, and the privacy claim does not extend to that path.

Three mitigations, in order of preference:

1. **Redaction layer.** Resource IDs, account IDs and ARNs are replaced with local aliases before leaving the deployment, and restored on the way back. Sizes, services and rupee figures still go out; identifiers do not. Cheap, and it removes most of the objection.
2. **Local model option.** An 8B instruct model on the same GPU already serving the compiler, selectable in config. Lower answer quality, zero egress. Ward's own §9.11 serving setup makes this close to free — vLLM already swaps adapters on one base model.
3. **Local-only mode.** A deployment flag that disables every hosted path. The Architect (§30) degrades to catalogue matching with template explanations. Worth having for the thesis defence alone, as a demonstration that the claim is structural and not aspirational.

Ship 1 and 2. Document 3.

### 32.3 What can be cut, and in what order

This iteration will not fit. Deciding the cut order now, while it is cheap, prevents deciding it in week 22 under pressure.

| Priority | Feature | If cut |
|---|---|---|
| Must | §28 guardrails + simulator | It is §1–§25 packaged. Cutting it means cutting the project. |
| Must | §27 QUERY + ACT intents only | The minimum copilot: ask about resources, create a rule. Defer EXPLAIN and ADVISE routing. |
| Should | §29 detective button | §23's engine already exists. The button is a day's work. |
| Should | §31 Guardian, curated policies only | Ship the ~40 c7n checks. Defer behavioural mining. |
| Could | §31 behavioural patterns | The novel half. First thing to cut, and the most painful. |
| Could | §30 Architect | Largest, weakest evaluation story, most vulnerable to over-engineering criticism. |

If only one thing survives, it is §28 — because it is not new work, and because it is the demonstration the whole document has been building toward.

If §30 survives, it survives with the catalogue (§30.2). A free-generation architect built under time pressure in the final weeks is the single most likely way this project acquires an indefensible claim.

### 32.4 Ownership

| Feature | Owner | Note |
|---|---|---|
| §27 Copilot | **A** (intent, slots, narration) + **B** (query planner, grounding) + **C** (chat UI) | Genuinely three-person. A owns model behaviour, B owns the data path, C owns the surface. |
| §28 Guardrails | **C** | Almost entirely assembly — one endpoint from B, the rest is the card. |
| §29 Detective | **C** | Engine is §23. This is the button and the waterfall. |
| §30 Architect | **A** (matching, elicitation) + **C** (diagram, explainer UI) | Catalogue written by all three, ~5 patterns each, same as the §10 seed-rule split. |
| §31 Guardian | **B** (curated policies, scan, behavioural) + **C** (digest UI) | The c7n policies are B's territory; behavioural mining is time-series work over B's snapshots. |

The catalogue split matters. Fifteen reference architectures written by one person reflect one person's habits; written by three and cross-reviewed, they are a better artefact and the review catches over-engineering before a user sees it.

### 32.5 Research value, honestly ranked

Same discipline as §25.5. Most of this iteration is product, and that is fine — it should be labelled as product.

| Feature | Contribution |
|---|---|
| §31.2 Behavioural patterns | **Moderate.** Mining resource history for recurring waste habits, then auto-drafting a preventive policy, is not in the §3.2 tools. Small, specific, evaluable — the best research in this iteration. |
| §27.3 Constrained query planning | **Moderate, methodological.** "Typed slot-filling instead of tool-calling for credentialed systems" is a defensible safety argument with a measurable outcome (§27.9's zero-hallucination target). |
| §30.2 Catalogue-constrained advice | **Moderate.** Making unverifiable generative advice evaluable by constraining it to a labelled selection task — and grading the attached cost estimate (§30.3) — is a reusable pattern. |
| §28, §29 | **Packaging.** Excellent product work. No new claims — the components beneath them already carry their own. |
| §31 security/waste | **None. Prior art.** Say so in §3.2's table. |

Note what is absent: "natural-language interface to AWS" is not on this list. It is the most impressive thing in the iteration and the least novel — NL interfaces to cloud APIs exist, and the contribution would have to be in *how* it is constrained, which is why §27.3 appears above and the copilot as a whole does not.

§9.13 applies unchanged: design the evaluation so it can tell you the answer is no. Three moderate contributions that survive scrutiny beat five claimed ones that do not.
