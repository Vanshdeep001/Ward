# Ward — Project Progress

*Status as of 30 September 2026.*

Ward is a **read-only AWS cost and security guardian**. You write guardrails in plain English ("No GPU instance runs more than 6 hours"). Ward then:

1. compiles each one into a Cloud Custodian policy with its own fine-tuned model;
2. **proves the policy is correct** before trusting it;
3. watches your account and alerts you when something breaks a rule.

Ward never changes, stops or deletes anything in your account. It only reads and warns.

---

## 1. At a glance

| Area | Status |
|---|---|
| Backend (FastAPI, SQLite, Cloud Custodian) | ✅ Built. 308 automated tests pass. |
| Frontend (React 18, Vite, Tailwind v4) | ✅ Built. 13 app pages plus landing, sign-in and sign-up. |
| Plain-English → policy compiler | ✅ Built in three modes: templates, hybrid, and the fine-tuned model (`llm`) |
| Verifier (proves every policy before use) | ✅ Built |
| Fine-tuned model v2 (Qwen2.5-Coder-1.5B + LoRA) | ✅ Trained. **97.8% verified correct** on 224 held-out rules. |
| RAG search over your inventory ("Ask Ward") | ✅ Built and evaluated. **100% faithfulness, 99% relevance.** |
| Rules about one named resource ("stop my algobench server…") | ✅ Built and tested on the real account |
| Sign-in (access and refresh tokens, admin role) | ✅ Built |
| Fast local model serving (GGUF + Ollama) | 🔄 In progress. Files exported and downloaded; Ollama installer downloading. |

---

## 2. How it works

```
 English rule ──► Router ──► Resolve named resources ──► Compiler ──► Ward adds the ID scope ──► Verifier ──► Dry run ──► Saved rule
                   │          (inventory lookup)        (fine-tuned                          (fixtures from     (what it matches
                   │                                      model)                              the intent)        right now)
                   └── questions / small talk → answered directly, never turned into a fake policy

 Saved rules ──► Watcher (every sweep) ──► state machine ──► Warning / Alert ──► Telegram or the log
```

- **Router.** A quick keyword check first, then a Groq `gpt-oss-120b` classifier (rule / question / other), then a simple fallback if that fails. "hello" or "what is a server?" gets an answer instead of an invented policy.
- **Compiler.**
  - `templates`: deterministic, hand-written rules.
  - `hybrid`: templates first, the model for anything they can't read.
  - `llm`: the fine-tuned model writes every policy. This is the current mode.
- **Verifier.** The core safety idea: a policy never grades itself.
  - Ward builds test resources ("fixtures") from what the rule *means*, and runs the policy against them in Cloud Custodian.
  - Each rule gets at least 2 positives (must be flagged), 2 negatives (must not be) and 1 edge case. Edge cases include stopped instances, case-sensitive tag keys and IPv6.
  - A policy that fails is never saved, and a policy containing an `actions:` block is refused outright.
- **Dry run and time travel.** Before you activate a rule, Ward shows what it matches right now and how often it would have fired over the stored history.

---

## 3. Features completed

### Backend
- **Rule families:**
  - EC2 runtime limits (optionally GPU-only, with exemptions)
  - required tags
  - unattached EBS volumes
  - public RDS databases
  - ports open to the internet (IPv4 and IPv6)
  - instance-type allowlists
  - region limits
- **Clarifier.** Vague words like "expensive" or "too long" become a question. Each option shows how many of *your* resources it would match.
- **Watcher.** Resources move through Discovered → Watched → Warning (at 75% of the limit) → Alert → Resolved, with snoozing. Alerts go to Telegram, or to a log if Telegram isn't set up.
- **Guardian:**
  - findings nobody wrote a rule for
  - conflicts between rules (four kinds)
  - a quality score for each rule across five dimensions
- **Costs:** daily spend, month-end projection, savings attributed to rules, and the **Detective**, which explains *which resources* moved the bill.
- **Architect.** Describe what you need; Ward asks about anything missing (users, budget, data, uploads, load, uptime) and returns a priced AWS design, including the free tier.
- **Accounts.** Connect a real AWS account through a read-only cross-account role, set up with a CloudFormation template and an ExternalId. No access keys are stored.

### Rules about one named resource (the newest feature)
"Stop my algobench server when its cost reaches ₹500" becomes this:

1. **Resolve.** Ward looks the name up in the inventory, deterministically: `algobench` → `i-020728297a4e3cb58`.
   - Spelling doesn't matter: `AlgoBench`, `algo bench` or the ID all work.
   - Not found → Ward says so. Two matches → Ward asks which. It never guesses.
2. **Convert the cost.** ₹500 ÷ ₹0.94/hour is about 532 hours of running, using Ward's own prices. The assumption is shown to you.
3. **Compile the shape only.** The model sees "No EC2 instance runs longer than 531.9 hours", with no name in it.
4. **Pin by ID.** Ward, not the model, adds `InstanceId: i-020728297a4e3cb58` to the policy. Renaming the server later doesn't break the rule.
5. **Prove the scope.** Every "must flag" test gets a **twin**: identical except for its ID. The twin must *not* be flagged, so a rule that forgot its scope fails.
6. **"Stop" becomes an alert.** Ward is read-only, so the alert includes the exact `aws ec2 stop-instances …` command for you to run.

### Frontend
- Pages: Dashboard, **Ask Ward** (Copilot), Rules (guardrail composer), Rule Health, Resources, Alerts, Detective, Guardian, Architect, Accuracy, Connect, and **System quality** (admin only).
- Design:
  - custom editorial styling: Fraunces, Figtree and JetBrains Mono fonts, an indigo "arc" palette and a coral accent
  - blue grain with a WebGL "MicroSlats" effect on the guardrail composer
  - custom loader and error screens that detect when the server is unreachable
- **Sentence-style sign-in and sign-up**, with a live demo of the compiler beside the form. The page doesn't scroll.
- The result card shows who wrote the policy (the fine-tuned model or the templates), the verifier's results, the assumptions made, and for named-resource rules the "Only watches: algobench · i-…" scope.

### Sign-in and security
- Passwords hashed with scrypt; the same error for a wrong password and an unknown email; repeated failed sign-ins are throttled.
- **Access token:** 15 minutes, HMAC-signed, in an HttpOnly cookie.
- **Refresh token:** 7 days from sign-in, stored only as a hash, replaced on every use. Reusing an old one ends that whole sign-in.
- You stay signed in for a week, or until you sign out.
- Everyone who signs up is an ordinary user. **Admins can only be made on the server:** `python -m app.admin promote <email>`.
- **Prompt-injection defences in RAG:**
  - resource tags are cleaned
  - documents are fenced off as data, not instructions
  - numbers in answers are checked
  - 4 of 4 poisoned test cases pass

---

## 4. The fine-tuned model

| | v1 | **v2 (current)** |
|---|---|---|
| Base model | Qwen2.5-Coder-1.5B-Instruct | same |
| Method | QLoRA on a Colab T4 | same |
| Training examples | 287 | **1,254** |
| Held-out rules tested | 71 | **224** (20 independent groups) |
| **Verified correct** | 91.6% | **97.8%** |
| Exact match | 64.8% | 96.9% |

**Comparison on the same 224 rules, graded by the same verifier:**

| System | Verified correct |
|---|---|
| Hand-written templates | 62.9% |
| `gpt-oss-120b` (120B, zero-shot, via API) | 32.1% |
| **Ward's fine-tuned 1.5B model** | **97.8%** |

A model about 80 times smaller, trained for this one job, beats a general 120B model. It is free to run and works offline.

- **Dataset pipeline:** `finetune/scripts/01–04`. It expands 200 seed rules into many phrasings, generates policies, verifies every pair, and splits them by group so near-duplicates can't leak between training and test.
- **Weights:** Hugging Face `vansh-deep/ward-compiler-1.5b-v2` (adapter) and `vansh-deep/ward-compiler-1.5b-v2-gguf` (Ollama files).
- **Known weakness:** specific GPU families. For "g5 or p3" it writes the pattern `^(g|p)3`. This is a target for v3.

---

## 5. RAG evaluation (Ask Ward)

26 documents, 58 questions with known answers, retrieving 6 per question. Report: `backend/evals/results/rag-20260929-1143.md`.

| Metric | Result |
|---|---|
| Faithfulness (judged claim by claim) | **100%** |
| Answer relevance | **99%** |
| Context recall at 6 (Pinecone) | 0.96 |
| Grounded numbers | 100% |
| Citation precision / recall | 0.91 / 0.94 |
| Latency, median / 95th percentile | 3.25 s / 22.6 s |

The pipeline:
- search: Pinecone (`llama-text-embed-v2`), with a local index as fallback
- answers: Groq `gpt-oss-120b`
- judge: a *different* model, `qwen3.8-27b`, so the answers aren't graded by the model that wrote them

Finding: the reranker lowered recall on paraphrased questions (0.95 → 0.83), so plain Pinecone search is the better setup. Admins see these results on the **System quality** page.

---

## 6. In progress — fast local serving

**Why:** running the model at full size in PyTorch takes 30–50 seconds per rule on the laptop CPU. A compressed (quantized) GGUF file run by Ollama should take a few seconds.

| Step | Status |
|---|---|
| Export: merge adapter, convert to GGUF, quantize, upload (`09_export_gguf.py`, on Colab) | ✅ Done: q8_0 at 1.65 GB, q4_k_m at 0.99 GB |
| Download to `D:\Ward\finetune\models` | ✅ Done |
| Ollama models folder set to `D:\Ollama\models` | ✅ Done |
| Install Ollama to `D:\Ollama` | 🔄 Installer downloading (1.57 GB) |
| `ollama create ward-compiler` / `ward-compiler-q4` | ⏳ Next |
| Measure accuracy and speed of q8 against q4 (`06_evaluate.py --url`) | ⏳ Next |
| Point Ward at Ollama (`WARD_LLM_URL=http://127.0.0.1:11434/v1`) | ⏳ Next |

Qwen stays the model. Ollama is only the program that runs it. For v3: train as usual, run `09_export_gguf.py` on the new adapter, then run `ollama create` again. Full steps are in `finetune/README.md`, "Fast on the laptop: Ollama".

---

## 7. Running it

```powershell
# backend (from D:\Ward\backend)
D:\Ward\.venv\Scripts\python.exe -m uvicorn app.main:app --port 8000

# frontend (from D:\Ward\frontend)
npm run dev

# model server, until Ollama is set up (from D:\Ward\finetune\scripts)
D:\Ward\.venv\Scripts\python.exe 07_serve.py

# tests (from D:\Ward\backend)
D:\Ward\.venv\Scripts\python.exe -m pytest -q
```

API keys (Groq, Pinecone, Telegram) are in `backend/.env`, which is never committed. `backend/.env.example` lists them with blank values.

---

## 8. Next

1. **Finish Ollama:** install it, register both models, measure, then switch Ward over.
2. **Re-run the full RAG evaluation**, so the System quality page reflects the injection fix.
3. **v3 fine-tune:**
   - specific GPU families (`g5`, `p3` …)
   - refusing sentences that aren't rules
   - seed rules about named resources
4. **Commit.** A large amount of work is still uncommitted (sign-in, evaluations, named-resource rules, the export script). The last commit is `cc9fa14 finetuning v2`.
