# Ward

**Natural-language cloud cost guardrails.** You write a rule in English, for example "No GPU instance may
run for more than 6 hours". Ward compiles it into a Cloud Custodian policy, proves the policy is correct
against generated test resources, and then checks your AWS account against it every 15 minutes. It warns
you before the limit is crossed. Ward is read-only by design and never changes your account.

The full design is in [`ward-srs (1).md`](ward-srs%20(1).md). This file describes what has been built so
far. [`backend/README.md`](backend/README.md) and [`finetune/README.md`](finetune/README.md) go into detail.

---

## Contents

1. [Running it](#1-running-it)
2. [Status by phase](#2-status-by-phase)
3. [How it works](#3-how-it-works)
4. [Repository layout](#4-repository-layout)
5. [Data](#5-data)
6. [Train / validation / test split](#6-train--validation--test-split)
7. [Models](#7-models)
8. [Libraries, scripts and classifiers](#8-libraries-scripts-and-classifiers)
9. [Results so far](#9-results-so-far)
10. [Tests](#10-tests)
11. [Git and deployment](#11-git-and-deployment)
12. [Known issues](#12-known-issues)

---

## 1. Running it

Windows, from the repo root. The Python virtual environment is `.venv/` at the root.

```powershell
# backend — http://localhost:8000  (API docs at /docs)
cd backend
..\.venv\Scripts\python -m pip install -r requirements.txt sqlalchemy cryptography
..\.venv\Scripts\python -m uvicorn app.main:app --reload --port 8000

# frontend — http://localhost:5173
cd frontend
npm install
npm run dev
```

- **Frontend data source.** The frontend uses built-in mock data unless `VITE_USE_MOCKS=false` is set
  in `frontend/.env.local`. With it set, the frontend calls the backend through Vite's `/api` proxy.
- **Backend configuration.** Settings live in `backend/.env`, which is not in git; copy
  [`backend/.env.example`](backend/.env.example). Nothing is required to start. Without keys, Ward
  uses a built-in sample AWS account, a local keyword search and the template compiler.
- **Fine-tuned compiler (optional).** Run Ollama with the model registered (see
  [finetune/README.md §6](finetune/README.md)), then set `WARD_COMPILER=hybrid` (or `llm`),
  `WARD_LLM_URL=http://127.0.0.1:11434/v1` and `WARD_LLM_MODEL=ward-compiler`.
- **Admin accounts.** Admins are created from the machine Ward runs on, never from the web:
  `python -m app.admin promote you@example.com`.

`GET /health` reports the inventory source, the Custodian version, the watcher interval, and which
compiler is active and whether its model is reachable.

---

## 2. Status by phase

The phases are the ones in SRS §8.

| Phase | What it is | State |
|---|---|---|
| 0. Foundations | Repo, FastAPI, React app, health check | **Done**, but without Docker. SQLite is used instead of Postgres. Redis and Qdrant aren't used. |
| 1. Verifier | Check a policy against generated fixtures | **Done.** `backend/app/verifier/` |
| 2. Baseline compiler | A number to beat | **Done.** The template compiler is the baseline. gpt-oss-120b was also measured zero-shot. |
| 3. RAG | Retrieval | **Done**, in two places. The compiler prompt carries reference documentation for the needed resource and filter. Ask Ward is a search assistant over the account's own resources (Pinecone or local BM25), with its own evaluation. |
| 4. Watcher | 15-minute sweep, state machine, notifications | **Done.** Telegram works. Email is written and tested but not committed yet. Alerts can be snoozed. The sweep runs against the sample account, or a real one connected through a read-only role. |
| 5. Cost prediction | Projections that grade themselves | **Done** on the sample account. Prediction accuracy page in the frontend. |
| 6. Fine-tuning | Small model trained on verified data | **Done for 1.5B** (v1 and v2), exported to GGUF, running under Ollama. 7B not trained. |
| 7. Deployment | Docker, Terraform, CI/CD | **Not started.** |
| 8. Observability / MLOps | Prometheus, MLflow, DVC | **Not started.** Runs are tracked by hand in `finetune/results/eval_runs.csv`. |
| 9. Evaluation & write-up | Open the holdout once | **Not started.** The holdout is still locked. |

**Beyond the phases (SRS §14–§31):**
- **Built:**
  - clarifier for vague rules
  - policy simulator, with replay over 30 days of history
  - savings with named counterfactuals
  - what-if threshold sweep
  - conflict detector
  - rule quality score
  - Cost Detective
  - Guardian findings
  - Copilot chat
  - Architect
  - rules about one named resource ("stop my algobench server at ₹500")
  - AWS account connection through an assume-role flow
  - sign-in with access and refresh tokens
- **In the frontend only:** emergency budget mode.
- **Not yet built:** multi-tenant scoping. Rules, alerts and predictions aren't scoped per account
  yet, and the sweep uses the first connected account.

---

## 3. How it works

### A rule, from sentence to alert

1. **Keyword gate.** A sentence that names nothing Ward watches (no instance, port, tag, region…) is
   turned away without calling any model.
2. **Router.** A general chat model sorts the sentence into *rule*, *question* or *other*. Questions
   get a plain answer instead of a policy. Without a model key, a heuristic based on the shape of a
   question decides.
3. **Clarifier.** Vague words ("big instances", "for a while") come back as a question. Each option
   shows how many of *your* resources it would match.
4. **Named resources.** A resource name is looked up in the inventory. The sentence is compiled with a
   generic subject, and then Ward adds the ID filter to the policy itself.
5. **Compiler.** English → Cloud Custodian YAML. It can be the template compiler, the fine-tuned model,
   or templates first with the model as a fallback (`hybrid`). All three implement one `Compiler`
   protocol (`backend/app/compiler/base.py`).
6. **Verifier.** Ward generates test resources from the rule's *intent*, never from the policy: at least
   2 that must match, 2 that must not, and 1 edge case. Edge cases include a stopped instance,
   lower-case tag keys, and SSH open over IPv6. Cloud Custodian runs the policy against them in memory,
   with no AWS calls. A policy that fails is returned as a failure. It is never presented as compiled.
7. **Simulator.** The policy is run against the current inventory and replayed over stored snapshots,
   so you see what it would have caught and what that would have saved.
8. **Watcher.** Every 15 minutes it runs a read-only sweep of the account. Each resource moves through
   *Discovered → Watched → Warning → Alert → Resolved*, and can be *Snoozed*. A warning comes from the
   same policy at 75% of its threshold. Only state changes send a notification, so a resource that
   stays in Alert doesn't message you every sweep.

### Other features

- **Costs** (`/costs`): daily spend priced from inventory snapshots, a month-end projection, savings,
  and stored predictions that are graded when the month ends.
- **Cost Detective** (`/costs/investigate`): what changed between two windows, ranked, each with a
  reason and the rule that would have caught it.
- **Guardian** (`/guardian/findings`): problems no rule covers yet, such as public databases, open SSH,
  unattached volumes, missing tags and long-running GPUs. Each has a fix command and a suggested rule.
  `/rules/conflicts` compares rules by what they actually match.
- **Copilot** (`/chat`): answers from the account's data. A request to change something is refused and
  answered with the exact AWS CLI command instead.
- **Ask Ward** (`/search`): RAG over one plain-English document per resource. Guardrails:
  - account-changing requests and prompt injections are refused before search
  - instruction-like text is stripped from tags
  - every ₹ figure in an answer is checked against the documents
  - citations of resources that were never retrieved are dropped
- **Architect** (`/architect`): "what I want to build" → the simplest priced AWS setup. It asks about
  anything the sentence left open.
- **Accounts** (`/accounts`): the user gives a role ARN, never keys. Ward issues an ExternalId,
  provides a CloudFormation template, and assumes the role.
- **Auth** (`/auth`): scrypt password hashes, and short-lived access and refresh tokens in HttpOnly
  cookies.

### Frontend pages

Home · Copilot · Guardrails (rules) · Detective · Guardian · Architect · Resources · Alerts · Rule health ·
Prediction accuracy · Connect · Login / Signup · Landing. There is also an internal system-quality page at
`/quality` (admin). React 18, Vite, Tailwind 4, React Query, Recharts.

---

## 4. Repository layout

```
Ward/
├── ward-srs (1).md        the design document
├── backend/               FastAPI service
│   ├── app/
│   │   ├── api/           HTTP routes
│   │   ├── compiler/      English → policy: templates, LLM client, prompt, router, clarifier, named targets
│   │   ├── verifier/      intents, fixture generation, runner, report
│   │   ├── engine/        Cloud Custodian, in memory
│   │   ├── simulator/     dry run and replay over history
│   │   ├── inventory/     boto3-shaped resources, sample account, pricing, snapshot store
│   │   ├── watcher/       poller, evaluator, state machine, warning variants
│   │   ├── notify/        Telegram / email / record-only
│   │   ├── costs/         spend, projection, savings, Detective
│   │   ├── guardian/      findings, conflicts, rule quality
│   │   ├── rag/           documents, Pinecone/BM25 stores, answerer, guardrails, eval set, judge
│   │   ├── aws/           assume-role connection, CloudFormation onboarding
│   │   └── auth.py, admin.py, db.py, models.py, config.py, library.py (starter rules)
│   ├── evals/             RAG evaluation write-ups (results/rag-*.md, .json)
│   └── tests/             322 tests
├── frontend/              React app (src/pages, src/components, src/api with a mock engine)
├── finetune/              the compiler model: data pipeline, training, evaluation, Ollama
│   ├── data/              seeds, generated, verified, splits, splits_v1  (§5)
│   ├── scripts/           01_expand … 09_export_gguf
│   ├── configs/           QLoRA configs
│   ├── ollama/            Modelfiles
│   ├── models/            GGUF weights (not in git)
│   └── results/           eval_runs.csv, predictions, comparison tables
└── .venv/                 Python environment (not in git)
```

---

## 5. Data

There are two kinds of data. Neither is labelled by a person.

### 5.1 The sample AWS account (backend)

`backend/app/inventory/sample.py` builds a demo account. It has EC2 instances (including GPUs), EBS
volumes, security groups and RDS, with 30 days of hourly snapshots. The resources are in boto3's exact
`describe-*` shapes, so Cloud Custodian's filters read them as if they were real. Every time hangs off
one anchor, so snapshots are consistent. This account drives the costs, simulator, Guardian, Copilot,
watcher and RAG whenever no real account is connected. `ward.db` (SQLite) stores rules, watches,
alerts, notifications, predictions, accounts and users.

The **RAG evaluation set** (`backend/app/rag/evalset.py`) is computed from this account's documents. It
has 58 questions over 26 documents, in nine categories: lookup, filter, paraphrase, aggregate, none,
action, injection, off-topic and poisoned. Two booby-trapped resources carry tags that try to give the
model orders. Each gold answer is derived from resource metadata, so the set is correct by construction.

### 5.2 Compiler training data (finetune)

| Step | Script | Output | Rows |
|---|---|---|---|
| 1. Hand-written seeds | — | `data/seeds/rules_seed.jsonl` | 200 (v1: 69) |
| 2. Expand | `01_expand_rules.py` | `data/generated/rules_expanded.jsonl` | 2,099 (194 seed sentences + 1,905 generated) |
| 3. Write a policy for each | `02_generate.py` | `data/generated/candidates.jsonl` | 2,099 |
| 4. Verify | `03_verify.py` | `data/verified/pairs.jsonl` (+ `failed.jsonl`) | 2,099 passed, 0 failed |
| 5. Format and split | `04_build_dataset.py` | `data/splits/{train,val,test_holdout}.jsonl` | 1,254 / 224 / 621 |

**How the data is synthesised.**
- Each seed has an English sentence, a family (one of 7) and a structured **intent**, for example
  `{kind: ec2-runtime, hours: 6, gpu_only: true}`.
- `01_expand_rules.py` makes variants from it:
  - paraphrases, with 12–14 phrasings per family and durations written many ways ("90 minutes",
    "half a day", "a fortnight")
  - parameter variants: other hours, days, ports, tags, regions and instance types
  - resource variants
- Every sentence is written *from its intent*, never by editing another sentence as a string. That way
  a sentence can't say 6 hours while its intent says 12.
- `02_generate.py` writes the policy for each rule. For v2 the teacher is `intent`, which renders the
  policy from the intent so any wording keeps its correct policy. For v1 it was `templates`, which
  dropped any wording the templates couldn't parse. An `api` teacher (a frontier model) also exists.

**How it is preprocessed.**
- `03_verify.py` runs every candidate through Ward's own verifier, with 5 fixtures built from the
  intent. Only passing pairs are kept.
- `04_build_dataset.py` converts each pair to the chat format the model is trained on:
  - system: "You write Cloud Custodian policies…"
  - user: `RULE: <english>` + `REFERENCE: <resource and filter docs>`
  - assistant: the YAML alone
- It then splits by group (§6).
- The prompt is defined once in `finetune/scripts/prompting.py`. The backend has a copy in
  `backend/app/compiler/prompt.py`, and a test fails if the two differ.

**How it is used.**
- `train.jsonl` trains the QLoRA adapter.
- `val.jsonl` is used for checkpoint selection and for every comparison so far.
- `test_holdout.jsonl` stays locked until Phase 9.

### 5.3 Data folders

| Folder | Contents | In git |
|---|---|---|
| `finetune/data/seeds/` | 200 v2 seeds, 69 v1 seeds | yes |
| `finetune/data/generated/` | expanded rules, candidate policies, failures | no (rebuilt by scripts 01–02) |
| `finetune/data/verified/` | verified pairs | no (rebuilt by script 03) |
| `finetune/data/splits/` | v2 train / val / holdout (what v2 trained on) | yes |
| `finetune/data/splits_v1/` | the exact v1 split, restored from commit `465cac4`. Do not edit | yes |
| `finetune/results/` | `eval_runs.csv`, predictions, comparison tables | yes (two q4/q8 files not yet committed) |
| `finetune/models/` | `ward-compiler-q8_0.gguf` (1.6 GB), `ward-compiler-q4_k_m.gguf` (1.0 GB) | no |
| `backend/evals/results/` | RAG evaluation reports | yes |
| `backend/ward.db` | the app database (SQLite) | no |

---

## 6. Train / validation / test split

- **Split by group.** The split is **by seed group, never by row**. A seed and all of its paraphrases
  and parameter variants land in one split. Otherwise "no GPU over 6 hours" could be in train and "no
  GPU over 12 hours" in test, and the score would mean nothing. `04_build_dataset.py` fails if any
  group spans two splits.
- **Target and stratification.** The target is 60 / 10 / 30, stratified by family.
- **Deterministic.** Each family is shuffled by a generator seeded from its own name, so a rebuild
  gives the same split.
- **v1 groups kept in place.** v2 was built with `--extend-from data/splits_v1`. Every group v1 saw
  stays where it was, so v1's holdout is unseen by both models.
- **Holdout locked.** The holdout is not opened until Phase 9 (see
  [`finetune/data/splits/README.md`](finetune/data/splits/README.md)).

| Split | v1 rows / groups | v2 rows / groups | v2 share |
|---|---|---|---|
| train | 287 / 28 | 1,254 / 118 | 59.7% |
| val | 71 / 7 | 224 / 20 | 10.7% |
| test_holdout | 115 / 11 | 621 / 58 | 29.6% |

v2 rows per family (train / val / holdout):

| ec2-runtime | require-tag | sg-open-port | ebs-unattached | instance-type | region | rds-public |
|---|---|---|---|---|---|---|
| 288 / 48 / 144 | 240 / 36 / 132 | 216 / 36 / 105 | 195 / 36 / 95 | 176 / 36 / 85 | 119 / 31 / 56 | 20 / 1 / 4 |

---

## 7. Models

| Model | Where it runs | Used for |
|---|---|---|
| **Qwen2.5-Coder-1.5B-Instruct + Ward QLoRA adapter (v2)** | Trained on a free Colab/Kaggle T4. Served by Ollama on the laptop as GGUF `ward-compiler` (q8_0) and `ward-compiler-q4` (q4_k_m) | The compiler: English rule → Cloud Custodian YAML. Adapter on the Hub: `vansh-deep/ward-compiler-1.5b-v2` |
| Qwen2.5-Coder-7B-Instruct | — | Planned main result. Not trained yet |
| `openai/gpt-oss-120b` | Groq API | The router (rule / question / other), Ask Ward's answers, and the zero-shot baseline in the comparison |
| `qwen/qwen3.8-27b` | API | Judge in the RAG evaluation (faithfulness, relevance). It's a different model from the answerer, so it isn't grading its own output |
| `llama-text-embed-v2` | Pinecone (hosted, integrated index) | Embeddings for Ask Ward's search |
| `bge-reranker-v2-m3` | Pinecone (hosted) | Re-orders search results |
| BM25 keyword index | backend, local | Search when no Pinecone key is set |
| Template compiler | backend, no model | The baseline the other compilers must beat |

Training config (`finetune/configs/qlora_t4.yaml`):
- 4-bit NF4
- LoRA r=16, α=32, dropout 0.05, on all attention and MLP projections
- 3 epochs, effective batch 16, lr 2e-4 cosine
- max sequence 1024, fp16 (T4s have no bf16)

---

## 8. Libraries, scripts and classifiers

**Backend (Python 3.11):**
- FastAPI and Uvicorn
- Pydantic
- SQLAlchemy (SQLite by default; any SQLAlchemy URL works)
- `c7n` (Cloud Custodian), which is the policy engine and the verifier's judge
- boto3 for read-only AWS calls
- httpx for model APIs (Ollama, Groq, Pinecone)
- PyYAML
- `cryptography` (Fernet) for stored ExternalIds
- pytest

**Fine-tuning:**
- The data steps use the standard library, PyYAML and the backend's own code.
- Training and export use `torch`, `transformers`, `peft`, `trl`, `bitsandbytes`, `accelerate`,
  `datasets`, `huggingface_hub` and llama.cpp. These are installed only on the GPU machine.

**Frontend:** React 18, React Router, TanStack Query, Recharts, Tailwind CSS 4, Vite 8, lucide-react, ogl.

**Scripts:**
- `finetune/scripts/01`–`09`: the data and model pipeline (table in the finetune README).
- `python -m app.admin`: user and admin management, plus an SMTP test.
- `python -m app.rag.evaluate`: the RAG evaluation.
- `frontend/scripts/check-templates.mjs`: a frontend check script.

**Classifiers.** There is **no trained classifier** and no scikit-learn or similar in the project. The
places where something is sorted into categories:

| What | How |
|---|---|
| Is this sentence about anything Ward watches? | Keyword gate (`looks_like_rule`), rule-based |
| Rule, question or other? | gpt-oss-120b prompted to return JSON (zero-shot), with a heuristic fallback |
| Action request or prompt injection? (Ask Ward) | Pattern-based screen in `rag/guardrails.py`, before retrieval |
| Off-topic? (Ask Ward) | The answering model replies `OUT_OF_SCOPE` |
| Vague wording? | Clarifier, rule-based |

The fine-tuned model is a generator (it writes YAML), not a classifier.

---

## 9. Results so far

**Compiler, on v2 val** (224 rules, 20 groups, all graded by the same verifier;
`finetune/results/compare_val_20260928-2203.md`):

| System | Verified correct | Exact match | Per rule | Offline |
|---|---|---|---|---|
| Templates | 62.9% | 62.5% | 0.00 s | yes |
| gpt-oss-120b, zero-shot | 32.1% | 0.0% | 2.06 s | no |
| **Fine-tuned 1.5B (v2)** | **97.8%** | 96.9% | — | yes |

- **v1 to v2.** v1 (287 training rows) scored 91.6% on its own 71-row val.
- **Under Ollama on the laptop.** Both quantizations scored 19/20 on the first 20 val rows, at 7.6 s
  per rule (q8) and 5.0 s (q4).
- **Caveats.** Val has only 20 independent groups. Its sentences come from the same paraphrase
  generator as train, so the number is likely optimistic about truly new phrasings.

**Ask Ward (RAG)**, 58 questions (`backend/evals/results/rag-20260929-1143.md`):

| Retrieval | recall@k | hit@1 | MRR |
|---|---|---|---|
| Local BM25 | 0.84 | 0.82 | 0.83 |
| Pinecone | 0.96 | 0.96 | 0.96 |
| Pinecone + rerank | 0.94 | 0.91 | 0.93 |

The answers (Pinecone + gpt-oss-120b) scored:
- faithfulness 100%
- relevance 99%
- grounded numbers 100%
- citation precision 0.91, recall 0.94
- behaviour 98%
- latency p50 3.3 s

---

## 10. Tests

```powershell
cd backend
..\.venv\Scripts\python -m pytest
```

There are 322 tests across 21 files. Among them:
- gold policies per intent and broken-policy cases for the verifier
- the template and LLM compilers, including a check that the backend prompt matches the training prompt
- the router, simulator, watcher, state machine and stubbed AWS poller
- STS for account connection
- costs and Guardian
- auth
- RAG and its guardrails

No test calls AWS or a paid model. The finetune scripts have no automated tests, but
`06_evaluate.py --mode score` grades any predictions file with the verifier.

---

## 11. Git and deployment

- **Repository.** `github.com/Vanshdeep001/Ward`, single branch `main`.
- **History:**
  1. `first commit`
  2. `backend integration`
  3. `datasets addition`
  4. `rag implementation`
  5. `finetuning v2`
  6. `Ollama implementation and auth page addition`
- **Not committed at the time of writing:**
  - email notifications (`notify/channels.py`, `test_notify_email.py`)
  - template compiler changes
  - the q4/q8 prediction files
  - the deletion of `PROGRESS.md`
- **Kept out of git.** Secrets (`.env`, `.ward-secret`), the database, model weights (`*.gguf`),
  and `finetune/data/generated` and `finetune/data/verified`.
- **Deployment: none yet.** There are no Dockerfiles, docker-compose, CI workflows (no `.github/`) or
  Terraform. Everything runs locally. SRS Phase 7 is the plan: Docker images, Terraform (VPC, EKS,
  RDS, ECR), Helm, and a GitHub Actions pipeline of test → build → push → deploy, with a GPU node for
  the model server.
- **Where the model files live.** The Hugging Face Hub hosts the trained adapter and the GGUF files
  (`vansh-deep/ward-compiler-1.5b-v2`, `vansh-deep/ward-compiler-1.5b-v2-gguf`).

---

## 12. Known issues

- **Missing requirements.** `backend/requirements.txt` doesn't list `sqlalchemy` or `cryptography`,
  though the code imports both. Install them as shown in §1 until the file is fixed.
- **Fine-tuned model not switched on.** With `WARD_COMPILER` unset, the backend runs the template
  compiler even though `WARD_LLM_URL` points at Ollama.
- **Duplicate file.** `finetune/data/splits/preds_v2.jsonl` is a byte-identical copy of
  `finetune/results/preds_v2.jsonl`.
- **Multi-tenant scoping isn't done** (see §2).
- **Small validation set.** `rds-public` has 1 val row and 4 holdout rows, too few to report as a family.
