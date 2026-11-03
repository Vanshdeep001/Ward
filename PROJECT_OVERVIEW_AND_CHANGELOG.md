# Ward — Project Overview, Architecture & Recent Changes

> **Date:** November 2, 2026  
> **Status:** Working & Verified (322 tests passing, 0 failures)  
> **Target:** Ready for Demonstration (Phases 0–6)

---

## 1. Project Overview & Architecture

### What is Ward?
**Ward** is an automated, natural-language cloud cost guardrail system. It bridges the gap between natural language intent (written by developers/students) and strict cloud compliance policies.

* **Core Premise:** The user writes a rule in plain English (e.g. *"No GPU instance may run for more than 6 hours"*).
* **Guaranteed Safety:** Ward compiles the English sentence into a **Cloud Custodian (`c7n`)** YAML policy, rigorously **verifies** it against generated test cases in memory, and continuously monitors the AWS account in a **strictly read-only** manner.

---

### How the Pipeline Works (End-to-End)

```
[ English Rule ] 
       │
       ▼
1. GATE & ROUTER
   - Keyword gate (`looks_like_rule`) filters out non-rules.
   - Router sorts input into rule, question, or out-of-scope.
       │
       ▼
2. COMPILER
   - Translates English into Cloud Custodian YAML.
   - Mode A: Template Compiler (deterministic, pattern-based, instant).
   - Mode B: Fine-Tuned 1.5B Model (Qwen2.5-Coder-1.5B via Ollama).
       │
       ▼
3. VERIFIER (Critical Safety Gate)
   - Generates 5 test resource fixtures from the intent:
     • 2 positive fixtures (must trigger)
     • 2 negative fixtures (must not trigger)
     • 1 edge case (e.g., stopped instances, IPv6, case-sensitive tags)
   - Runs `c7n` in memory. If tests fail, policy is REJECTED.
       │
       ▼
4. WATCHER & SCHEDULER
   - Sweeps AWS inventory every 15 minutes (read-only boto3 or sample account).
   - Resource State Machine:
     Discovered ──▶ Watched ──▶ Warning (75% of limit) ──▶ Alert ──▶ Resolved
                                  │
                               Snooze
   - Notifies ONLY on state transitions (Telegram or Email) to avoid alert fatigue.
       │
       ▼
5. FRONTEND & DASHBOARD
   - React 18 + Vite dashboard showing live spend, active guardrails, resource states,
     cost predictions, Cost Detective, and Guardian findings.
```

---

## 2. Complete Summary of Changes Made Till Now

All modifications in this session have been kept in the working files (**zero git commits** made per instruction):

| Category | File / Component | What Was Changed & Why |
|---|---|---|
| **Environment** | `.venv` | Initialized a clean Python virtual environment at `Ward/.venv` and installed all dependencies (`fastapi`, `uvicorn`, `c7n`, `boto3`, `pytest`, `sqlalchemy`, `cryptography`). |
| **Config** | `backend/.env` | Created from `backend/.env.example` so the backend can run out-of-the-box with default sample inventory and template compiler. |
| **Bug Fix** | `backend/requirements.txt` | Added `sqlalchemy>=2.0` and `cryptography>=42`. (Previously missing, forcing manual installation). |
| **Bug Fix** | `finetune/data/splits/preds_v2.jsonl` | Removed this file. It was an accidental byte-for-byte duplicate of `finetune/results/preds_v2.jsonl`. |
| **Documentation** | `backend/.env.example` | Added explicit comments explaining that `WARD_COMPILER` defaults to `templates` unless set to `hybrid` or `llm` for Ollama. |
| **Containerization** | `docker-compose.yml` | Added full local multi-container development stack: PostgreSQL (port 5433), Redis (port 6380), Qdrant (port 6333), FastAPI backend, and React frontend. |
| **Containerization** | `backend/Dockerfile` | Added two-stage slim Docker build with non-root security user. |
| **Containerization** | `frontend/Dockerfile` | Added multi-stage Node 20 build with Vite dev server exposed. |
| **Verification** | `backend/tests/` | Executed all automated tests: **322 passed, 1 skipped, 0 failures**. |

---

## 3. The Model Strategy (1.5B vs. 7B)

### Why 7B is Omitted:
* The 7B model was only an initial proposal in the SRS document and was **never trained**.
* Running a 7B model requires dedicated, high-VRAM cloud GPU instances.

### Why 1.5B is the Target Model:
* **Already Trained:** Fine-tuned on 1,254 verified rule pairs using QLoRA (`vansh-deep/ward-compiler-1.5b-v2` on Hugging Face).
* **Proven Performance:** Achieves **97.8% verified accuracy** on the validation set (219/224 rules passed), with 96.9% exact syntax match.
* **CPU-Friendly:** Quantized into a ~940 MB GGUF (`ward-compiler-q4_k_m.gguf`), taking only ~5 seconds per rule on standard laptop CPU with ~1 GB RAM.

### Ollama Model Configuration (`Modelfile.q4`):
```dockerfile
FROM ../models/ward-compiler-q4_k_m.gguf

TEMPLATE """{{- range .Messages }}<|im_start|>{{ .Role }}
{{ .Content }}<|im_end|>
{{ end }}<|im_start|>assistant
"""

PARAMETER stop "<|im_end|>"
PARAMETER stop "<|endoftext|>"
PARAMETER temperature 0      # Greedy decoding: deterministic policy output
PARAMETER top_k 1
PARAMETER num_ctx 4096       # Sufficient for schema + reference docs
PARAMETER num_predict 400    # Prevents runaway output
```

---

## 4. Current Operational Modes

Ward can be run in two modes:

### Mode 1: Default / Offline Template Engine (`WARD_COMPILER=templates`)
* **Status:** **Active right now.**
* **Requirements:** Zero external downloads or servers.
* **Behavior:** Translates standard guardrail patterns instantly and passes 100% of the verifier checks. Best for zero-risk, stable presentations.

### Mode 2: Hybrid / LLM Engine (`WARD_COMPILER=hybrid`)
* **Requirements:** Ollama running locally with `ward-compiler`.
* **Behavior:** Tries template compilation first. For complex/unusual phrasing, it queries the fine-tuned 1.5B model.

---

## 5. Commands to Run for Tomorrow's Demo

### Backend (Terminal 1)
```powershell
cd f:\Projects\rag-cloud\Ward\backend
..\.venv\Scripts\python -m uvicorn app.main:app --reload --port 8000
```
* **API Documentation:** `http://localhost:8000/docs`
* **Health Check:** `http://localhost:8000/health`

### Frontend (Terminal 2)
```powershell
cd f:\Projects\rag-cloud\Ward\frontend
npm install    # (only needed once)
npm run dev
```
* **Web UI:** `http://localhost:5173`

### Run Verification Tests Anytime
```powershell
cd f:\Projects\rag-cloud\Ward\backend
..\.venv\Scripts\python -m pytest tests/
```
