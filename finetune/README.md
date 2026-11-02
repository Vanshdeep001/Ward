# Fine-tuning Ward's compiler

Phase 6 of the SRS. The claim being tested is **N2**: that a 7B model, fine-tuned on outputs a
verifier has already certified, matches frontier performance at a fraction of the inference cost —
and without sending infrastructure configuration to a third party.

Read §9 of the SRS first. This document is the operational companion: what to run, where to run it,
and what it costs.

---

## Where this stands (2026-10-28)

| Step | State |
|---|---|
| Seed rules | **Done.** 200 hand-written seeds over 7 families (v1 had 69). |
| Synthetic data | **Done.** 2,099 rules → 2,099 candidates → 2,099 verified pairs (100% pass). |
| Splits | **Done, frozen.** v2: 1,254 / 224 / 621 rows. Grouped by seed rule, and the holdout hasn't been opened. |
| v1 training | **Done.** Qwen2.5-Coder-1.5B + QLoRA on Colab, 287 training rows. Verified correct on val: 91.6%. |
| v2 training | **Done.** Same base model, 1,254 training rows. Verified correct on val: **97.8%**, exact match 96.9%. |
| Comparison on val | **Done.** Templates 62.9%, gpt-oss-120b zero-shot 32.1%, fine-tuned 1.5B 97.8% (§7). |
| GGUF export | **Done.** `q8_0` (1.6 GB) and `q4_k_m` (1.0 GB) are on the Hub as `vansh-deep/ward-compiler-1.5b-v2-gguf` and downloaded to `models/`. |
| Ollama | **Done.** Registered as `ward-compiler` (q8) and `ward-compiler-q4`. On the first 20 val rows each scores 19/20, at 7.6 s/rule (q8) and 5.0 s/rule (q4) on the laptop CPU. |
| Wired into Ward | **Partly.** `backend/.env` points `WARD_LLM_URL` at Ollama, but `WARD_COMPILER` isn't set, so the backend still runs `templates` mode. To switch, set `WARD_COMPILER=hybrid` or `llm`. |
| 7B run | **Not started.** |
| Base-model baseline (`--no-adapter`) | **Not started.** |
| Holdout evaluation | **Not started.** It stays locked until Phase 9. |

---

## Folders

```
finetune/
  configs/            qlora_t4.yaml (T4 / fp16, the one actually used), qlora_v1.yaml (bf16, A40/4090/A100)
  data/
    seeds/            rules_seed.jsonl — the 200 hand-written seeds (v2); rules_seed_v1.jsonl — the 69 v1 seeds
    generated/        rules_expanded.jsonl (2,099 rules), candidates.jsonl (2,099 policies), failed.jsonl (empty)   [not in git]
    verified/         pairs.jsonl — 2,099 rule/policy pairs the verifier passed                                    [not in git]
    splits/           train / val / test_holdout.jsonl — v2, chat format, what v2 was trained on
    splits_v1/        the exact v1 split, restored from commit 465cac4 — do not edit
  models/             the two GGUF files Ollama loads                                                               [not in git]
  ollama/             Modelfile.q8, Modelfile.q4
  results/            eval_runs.csv, preds_*.jsonl, compare_val_*.md
  examples/           try_rules.txt — sentences for trying the model by hand
  scripts/            the numbered pipeline, below
```

`generated/`, `verified/` and `models/` are in `.gitignore`. The first two are rebuilt in about two
minutes by `01`–`03`. The models are downloaded from the Hub (§6). `data/splits/preds_v2.jsonl` is an
accidental copy of `results/preds_v2.jsonl` (the two are byte-identical) and can be deleted.

### What a row looks like at each stage

| Stage | File | Fields |
|---|---|---|
| Seed | `seeds/rules_seed.jsonl` | `id` (e.g. `rt-01`), `family`, `english`, `intent` |
| Expanded | `generated/rules_expanded.jsonl` | `id` (`rt-01-00003`), `group` (= seed id), `family`, `english`, `intent`, `source` (`seed` or `template`) |
| Candidate | `generated/candidates.jsonl` | the above + `policy_yaml`, `teacher` |
| Verified | `verified/pairs.jsonl` | the above + `verified`, `fixtures` (5 per rule) |
| Split | `splits/*.jsonl` | `messages` (system / user / assistant, Qwen chat format) + `meta` (id, group, family, teacher, intent, english) |

The user message is `RULE: <english>` followed by `REFERENCE:`, which holds short documentation for
the resource and filter the rule needs. The assistant message is the policy YAML alone, with no
explanation and no code fences. `scripts/prompting.py` builds the prompt, and the backend has a copy of
it in `backend/app/compiler/prompt.py`. A test fails if the two ever differ.

### The seven families

| Family | Seeds | What the rule says |
|---|---|---|
| `ec2-runtime` | 40 | No instance (or GPU instance) runs longer than N hours |
| `require-tag` | 34 | Instances must carry a given tag |
| `sg-open-port` | 30 | No security group opens port N to the internet (IPv4 or IPv6) |
| `ebs-unattached` | 28 | Volumes unattached for more than N days are flagged |
| `instance-type` | 28 | Only these instance types are allowed |
| `region` | 22 | Nothing runs outside these regions |
| `rds-public` | 18 | No publicly accessible database |

---

## Scripts and libraries

| Script | Runs on | Does |
|---|---|---|
| `01_expand_rules.py` | laptop | Seeds → paraphrases and parameter/resource variants, each written from its intent |
| `02_generate.py` | laptop | A teacher writes a policy per rule: `intent` (default, used for v2), `templates` (v1), or `api` |
| `03_verify.py` | laptop | Runs each candidate through Ward's verifier (Cloud Custodian, in memory). Failures go to `failed.jsonl` |
| `04_build_dataset.py` | laptop | Chat format, group split, stratified by family. `--extend-from` / `--keep-from` pin earlier splits |
| `05_train_qlora.py` | Kaggle / Colab GPU | 4-bit QLoRA fine-tune from a YAML config |
| `06_evaluate.py` | GPU (`generate`) / laptop (`score`) | Generate predictions from an adapter or any OpenAI-compatible URL, then grade them with the verifier |
| `07_serve.py` | laptop | Serves the adapter over an OpenAI-compatible API on :8001 (slow on CPU, replaced by Ollama) |
| `08_compare.py` | laptop | Every compiler on one split, one table → `results/compare_<split>_<time>.md` |
| `09_export_gguf.py` | Colab | Merge adapter → GGUF → quantize → upload to the Hub |
| `generate.py` | laptop | Try the model on your own sentences. Includes the keyword gate |
| `prompting.py` | — | The training prompt and `looks_like_rule`, shared by the scripts above |

Libraries:

- **Data steps (`01`–`04`, `08`):** the standard library, PyYAML, and Ward's backend (`c7n`, `boto3`
  shapes), imported from `../backend`.
- **Training, GPU generation and export (`05`, `06 --mode generate`, `07`, `09`):** `torch`,
  `transformers`, `peft`, `trl`, `bitsandbytes`, `accelerate`, `datasets`, `huggingface_hub`, and
  llama.cpp's converter. Install these only on the GPU machine.

There is no classifier library (no scikit-learn or similar) anywhere in the repo. The model is a
generator: it writes YAML. Deciding whether a sentence is a rule at all happens in front of it (§7,
"Sentences that are not rules").

---

## 0. Your hardware, and what it means

Measured on the development laptop:

| | |
|---|---|
| GPU | Intel Iris Xe (integrated, ~2 GB shared) |
| CPU | i5-1235U — 10 cores, 15 W class |
| RAM | 16 GB |
| CUDA | none |

**Do not train on this machine.** This is not caution, it is arithmetic:

- QLoRA's 4-bit quantisation (`bitsandbytes`) is CUDA-only. There is no Iris Xe path.
- CPU-only LoRA on even a 1.5B model would run for days at 100% on a 15 W chip. It would sit at
  95–100 °C, throttle to a crawl, and run the fan continuously for the whole time.
- Nothing would break — thermal limits protect the silicon — but you would spend a week of laptop
  time to get a worse result than 40 minutes of free cloud GPU.

### What the laptop *is* good for

Everything except the training step itself, and none of it is heavy:

| Task | Load | Time |
|---|---|---|
| Writing seeds, expanding rules | trivial | seconds |
| **Running the verifier over candidates** | one core, brief | ~2 min for 2,000 policies |
| Building splits, formatting datasets | trivial | seconds |
| Calling the teacher API | network-bound | minutes |
| Evaluating a hosted checkpoint | network-bound | minutes |
| Demo inference, 1.5B GGUF on llama.cpp | moderate | ~8–15 tokens/sec |

The verifier is the heaviest local step and it is still light — the backend test suite already runs
c7n over ~150 cases in about 2 seconds.

**Disk:** don't download base models locally. Qwen2.5-Coder-7B is ~15 GB; the cloud machine fetches
it in a minute. The only weights worth keeping on the laptop are a quantised 1.5B GGUF (~1 GB) for
the offline demo.

---

## 1. Where to train

| Option | GPU | Cost | Use it for |
|---|---|---|---|
| **Kaggle Notebooks** | 2× T4 (16 GB) | **free**, 30 h/week, 12 h/session | The main 7B runs. Best free option. |
| Colab (free) | T4 16 GB | free, disconnects | Quick 1.5B experiments |
| Colab Pro | L4 / A100 | ~₹1,000/mo | Comfortable 7B, fewer interruptions |
| **RunPod / Vast.ai** | RTX 4090 24 GB or A40 48 GB | **$0.34–0.69/h** | Final runs, when you want it finished in one sitting |

**Recommendation:** develop on Kaggle's free T4s, then do the runs that go in the report on a rented
A40 for about $2. The entire project's GPU spend should stay under $20.

### The T4 trap — read this before you waste an evening

T4s are Turing and have **no bfloat16**. The SRS's `qlora_v1.yaml` sets `bf16: true`, which is right
for A40/4090/A100 and will fail or silently fall back on a T4. On a T4 use `configs/qlora_t4.yaml`,
which sets `fp16: true`, `bf16: false`, and `max_seq_length: 1024`.

### Expected training time

~1,400 examples, 3 epochs, LoRA r=16, effective batch 16:

| Hardware | 7B | 1.5B |
|---|---|---|
| T4 16 GB (seq 1024) | 4–6 h | ~30 min |
| RTX 4090 24 GB | 1.5–2 h | ~15 min |
| A100 40 GB | 45–60 min | ~10 min |

---

## 2. Which model

| Model | Size | Role |
|---|---|---|
| **Qwen2.5-Coder-7B-Instruct** | 7B | The main result. Strong at structured output, Apache-2.0. |
| **Qwen2.5-Coder-1.5B-Instruct** | 1.5B | Size ablation for the report — *and* the only one that runs on your laptop for the demo. |
| Llama-3.1-8B-Instruct | 8B | Alternative if a reviewer asks for a second family. |

Train both sizes. The 1.5B costs almost nothing extra, gives the report a size-scaling curve, and
means your demo can run entirely offline on the laptop through `llama.cpp`.

**So far only the 1.5B has been trained** (v1 and v2, both on `configs/qlora_t4.yaml`: 4-bit NF4, LoRA
r=16 / α=32 on all attention and MLP projections, 3 epochs, effective batch 16, lr 2e-4 cosine, fp16).
The v2 adapter is `vansh-deep/ward-compiler-1.5b-v2` on the Hugging Face Hub.

### Every model in the project, and what it does

| Model | Where it runs | Used for |
|---|---|---|
| **Qwen2.5-Coder-1.5B-Instruct + Ward adapter (v2)** | Ollama on the laptop (GGUF q8 / q4) | The compiler: English rule → Cloud Custodian YAML |
| Qwen2.5-Coder-7B-Instruct | — | Planned main result, not trained yet |
| `openai/gpt-oss-120b` | Groq API (`WARD_RAG_LLM_*`) | The zero-shot baseline in §7. In the backend it also powers the router (rule / question / other) and writes Ask Ward's answers |
| `qwen/qwen3.8-27b` | API | Judge for the RAG evaluation (faithfulness, relevance). It's a different model from the one that writes the answers, so it isn't grading its own output |
| `llama-text-embed-v2` | Pinecone (hosted) | Embeddings for Ask Ward's search over the account's resources |
| `bge-reranker-v2-m3` | Pinecone (hosted) | Re-orders the search results |
| BM25 keyword index | backend, local | Search fallback when no Pinecone key is set |
| Template compiler | backend, no model | The baseline that the other compilers have to beat |

---

## 3. The dataset

```
200 hand-written seeds
        │  01_expand_rules.py   paraphrase + parameter + resource variation
        ▼
~2,000 rules (English + intent)
        │  02_generate.py       a teacher writes a candidate policy for each
        ▼
~2,000 candidates
        │  03_verify.py         THE VERIFIER GRADES THEM — fixtures come from the
        ▼                       intent, never from the candidate
~1,200–1,600 verified pairs
        │  04_build_dataset.py  chat format, split by family
        ▼
train.jsonl / val.jsonl / test_holdout.jsonl
```

The point, restated because it is the thesis: **no human labels anything.** A kept example is known
correct because a machine tested it against fixtures the candidate never saw.

### You can build v1 today, for free

`02_generate.py` supports two teachers:

- `--teacher templates` — uses `app.compiler.templates.TemplateCompiler`, already in your repo. Free,
  offline, deterministic, and covers every family the compiler knows. **Start here.**
- `--teacher api` — a frontier model writes the candidates. More diverse phrasing-to-policy mappings
  and covers families the templates don't. ~2,000 calls ≈ **$15–20** on a Sonnet-class model.

Do both and keep them as separate arms. "Fine-tuned on template-distilled data" and "fine-tuned on
frontier-distilled data, verifier-filtered" is a genuinely interesting comparison for the report, and
the second is the one that supports N2.

Be straight about this in the write-up: a model trained only on template output learns to imitate
templates. That is still a real translation task, but the held-out test set must contain phrasings and
parameter values the templates never produced, or the number means nothing.

### Splitting — the mistake that invalidates the result

Split **by rule family, not randomly**. "No GPU over 6 hours" in train and "no GPU over 12 hours" in
test is leakage; the model has effectively seen the answer. `04_build_dataset.py` groups by
`(family, resource)` and splits whole groups, 60/10/30.

The 30% holdout goes to `data/splits/test_holdout.jsonl` and **is not opened until Phase 9**.

### The split as built

| Split | v1 rows | v1 groups | v2 rows | v2 groups | v2 share of rows |
|---|---|---|---|---|---|
| train | 287 | 28 | 1,254 | 118 | 59.7% |
| val | 71 | 7 | 224 | 20 | 10.7% |
| test_holdout | 115 | 11 | 621 | 58 | 29.6% |

v2 rows per family:

| Family | train | val | holdout |
|---|---|---|---|
| ec2-runtime | 288 | 48 | 144 |
| require-tag | 240 | 36 | 132 |
| sg-open-port | 216 | 36 | 105 |
| ebs-unattached | 195 | 36 | 95 |
| instance-type | 176 | 36 | 85 |
| region | 119 | 31 | 56 |
| rds-public | 20 | **1** | 4 |

`rds-public` is thin because the intent has no parameter to vary, so its seeds expand into few
variants. Its 100% on val is one example, so don't report it as a family-level result.

v2 was built with `--extend-from data/splits_v1`, so every v1 group stayed in the split it was in. The
split is deterministic: each family is shuffled by its own name-seeded generator. See
`data/splits/README.md` before rebuilding anything.

---

## 4. Do this first: one small run, end to end

Before writing another seed rule, prove the pipeline works. 473 pairs is plenty for that, the 1.5B
takes about half an hour, and Kaggle's T4 is free.

1. **Kaggle → Datasets → New Dataset.** Upload the three files in `data/splits/`. Call it `ward-splits`.
2. **New Notebook → Add Data → `ward-splits`.** In Settings, set Accelerator to **GPU T4 ×2**.
3. Paste `05_train_qlora.py` and `configs/qlora_t4.yaml` into the notebook (or add the repo as a
   second dataset), then run:

   ```python
   !pip -q install -U "transformers>=4.44" peft trl bitsandbytes accelerate datasets
   !python 05_train_qlora.py --config qlora_t4.yaml \
       --train /kaggle/input/ward-splits/train.jsonl \
       --val   /kaggle/input/ward-splits/val.jsonl \
       --out   /kaggle/working/ward-compiler-v1
   ```

4. Still in the notebook, generate predictions for the **validation** split:

   ```python
   !python 06_evaluate.py --mode generate --adapter /kaggle/working/ward-compiler-v1 \
       --split /kaggle/input/ward-splits/val.jsonl --out preds_val.jsonl
   ```

5. Download `preds_val.jsonl` and the adapter. **On the laptop**, where the verifier lives:

   ```bash
   python scripts/06_evaluate.py --mode score --preds results/preds_val.jsonl --record v1-1.5b
   ```

What you are checking at this stage is that the loop runs and the model emits YAML rather than prose.
**Ignore the accuracy.** With 7 validation groups it carries no information — `06_evaluate.py` says so
in its own output. Fix the dataset (§3) before any run whose number you intend to publish.

## 5. Running the data pipeline (v2)

On the laptop (all of this is cheap — a couple of minutes, CPU only):

```bash
cd finetune
python scripts/01_expand_rules.py                              # 200 seeds → 2,099 rules
python scripts/02_generate.py                                  # intent teacher → 2,099 candidates
python scripts/03_verify.py                                    # verifier → 2,099 verified pairs
python scripts/04_build_dataset.py --extend-from data/splits_v1   # → data/splits/: 1,254 / 224 / 621
```

### What changed from v1, and why

| | v1 | v2 |
|---|---|---|
| Seed rules | 69 | **200** (131 new, aimed at v1's failures: GPU/accelerator wording, city names for regions, service names for ports, new instance families) |
| Seed sentences in the data | **none** — only their intents were used, re-worded by 6 templates | **kept**: 194 hand-written sentences are training rows |
| Phrasings per family | 6 | 12–14, with durations said many ways ("90 minutes", "half a day", "a fortnight") |
| Teacher | `templates` — compiled the English, so any wording it could not parse was dropped | `intent` — renders the policy from the intent, so any wording keeps its correct policy |
| Verified pairs | 473 | **2,099** (100% pass) |
| Train / val / holdout rows | 287 / 71 / 115 | **1,254 / 224 / 621** |

`--extend-from data/splits_v1` keeps every group v1 saw in the split it was in; only the 131 new
groups are split. So v1's holdout is still unseen by both models, and the two can be compared on it.
`data/splits_v1/` is the exact split v1 was trained on, restored from git (see its README).

### Training v2 on Kaggle

Upload the three files in `data/splits/` as a **new** Kaggle Dataset, `ward-splits-v2` (keep the v1
dataset as it is), then:

```python
!pip -q install -U "transformers>=4.44" peft trl bitsandbytes accelerate datasets
!python 05_train_qlora.py --config qlora_t4.yaml \
    --train /kaggle/input/ward-splits-v2/train.jsonl \
    --val   /kaggle/input/ward-splits-v2/val.jsonl \
    --out   /kaggle/working/ward-compiler-v2
!python 06_evaluate.py --mode generate --adapter /kaggle/working/ward-compiler-v2 \
    --split /kaggle/input/ward-splits-v2/val.jsonl --out preds_val_v2.jsonl
```

About 4× v1's steps — roughly 30–45 min for the 1.5B on a T4 (the §1 table's ~1,400-example
estimate), 4–6 h for the 7B. Then on the laptop:

```bash
python scripts/06_evaluate.py --mode score --preds results/preds_val_v2.jsonl --record v2-1.5b
```

Push the adapter (~100 MB) to the Hugging Face Hub; v2 is at `vansh-deep/ward-compiler-1.5b-v2`. The
base model stays in the cloud, and the adapter is the only artefact you keep.

**Result:** 219/224 verified correct (97.8%), up from v1's 91.6% on its own 71-row val. Recorded in
`results/eval_runs.csv`, with predictions in `results/preds_v2.jsonl`.

---

## 6. Serving it back into Ward

The backend is already shaped for this. `app/compiler/base.py` defines the `Compiler` protocol, and
`TemplateCompiler` is one implementation. The fine-tuned model becomes another:

```python
class LlmCompiler:
    name = 'qwen2.5-coder-7b-ward-v1'

    def compile(self, english: str) -> Draft | None:
        ...  # retrieve context, prompt the model, parse YAML into a Draft
```

Nothing downstream changes. Every draft still goes through the verifier before the user sees it, so a
hallucinated policy fails exactly the way a bad template would.

### Fast on the laptop: Ollama (6.1)

`07_serve.py` runs the model in full precision through PyTorch: 30–50 s a rule on this CPU. The same
model as a quantized GGUF under Ollama (llama.cpp inside) should take a few seconds. Ward needs no code
change — Ollama speaks the same chat API, so it is two lines in `backend/.env`.

**A. On Colab — export (≈10 min, CPU runtime is fine).** Upload `scripts/09_export_gguf.py`, then:

```python
from huggingface_hub import login; login()   # a token with WRITE access
!python 09_export_gguf.py --adapter vansh-deep/ward-compiler-1.5b-v2 --repo vansh-deep/ward-compiler-1.5b-v2-gguf --quants q8_0 q4_k_m
```

It merges the adapter into the base model, converts to GGUF, quantizes, and uploads
`ward-compiler-q8_0.gguf` (1.6 GB) and `ward-compiler-q4_k_m.gguf` (1.0 GB).

**B. On the laptop — everything on D:, C: is nearly full.**

```powershell
# 1. model files → D:\Ward\finetune\models (nothing lands in the C: Hugging Face cache)
D:\Ward\.venv\Scripts\hf.exe download vansh-deep/ward-compiler-1.5b-v2-gguf ward-compiler-q8_0.gguf ward-compiler-q4_k_m.gguf --local-dir D:\Ward\finetune\models

# 2. where Ollama keeps models, and how long it keeps one loaded — set BEFORE installing
setx OLLAMA_MODELS "D:\Ollama\models"
setx OLLAMA_KEEP_ALIVE "30m"

# 3. install Ollama itself onto D: (download OllamaSetup.exe from ollama.com/download/windows first)
& "$env:USERPROFILE\Downloads\OllamaSetup.exe" /DIR="D:\Ollama"

# 4. open a NEW terminal (so it sees the variables), then register both models
cd D:\Ward\finetune\ollama
ollama create ward-compiler -f Modelfile.q8
ollama create ward-compiler-q4 -f Modelfile.q4
ollama list
```

**C. Measure before switching** — accuracy (the verifier) and seconds per rule, for each quantization:

```powershell
cd D:\Ward\finetune\scripts
python 06_evaluate.py --mode generate --url http://127.0.0.1:11434/v1 --model ward-compiler    --out ../results/preds_val_q8.jsonl
python 06_evaluate.py --mode score --preds ../results/preds_val_q8.jsonl --record v2-q8-ollama
python 06_evaluate.py --mode generate --url http://127.0.0.1:11434/v1 --model ward-compiler-q4 --out ../results/preds_val_q4.jsonl
python 06_evaluate.py --mode score --preds ../results/preds_val_q4.jsonl --record v2-q4-ollama
```

Compare with the v2 compile rate from the GPU run. Use q4 only if it scores within a point or two of q8.

**Measured so far** (`--limit 20`, the first 20 val rows: `results/preds_q8_20.jsonl`,
`preds_q4_20.jsonl`):

| | Verified correct | Per rule (i5-1235U) |
|---|---|---|
| q8_0 | 19/20 | 7.6 s |
| q4_k_m | 19/20 | 5.0 s |

Both miss the same rule the GPU run missed ("GPU boxes are for short experiments, not overnight runs").
These 20 rows come from only 2 groups, so this shows quantization didn't break the model. It doesn't
measure accuracy. Run the full 224 rows before choosing q4.

**D. Point Ward at it** — `backend/.env`, then restart the backend (07_serve.py is no longer needed):

```
WARD_LLM_URL=http://127.0.0.1:11434/v1
WARD_LLM_MODEL=ward-compiler
WARD_LLM_TIMEOUT=60
```

To go back, restore `http://127.0.0.1:8001/v1` and run 07_serve.py again. Nothing is sent anywhere:
Ollama listens only on 127.0.0.1, and the model never leaves the laptop.

---

## 7. Why fine-tune? The comparison

Every compiler on the same split, graded by the same verifier:

```bash
# Colab — the untuned base model, given the identical prompt (the baseline):
!python 06_evaluate.py --mode generate --no-adapter --split /kaggle/input/ward-splits-v2/val.jsonl --out preds_base_val.jsonl

# laptop — templates and a large general model (zero-shot, via WARD_RAG_LLM_* in backend/.env) are
# predicted here; anything from Colab is passed in:
python scripts/08_compare.py --preds finetuned=results/preds_v2.jsonl --preds base=results/preds_base_val.jsonl
```

The table goes to `results/compare_<split>_<time>.md`. Run it on val while things still change, and on
`test_holdout.jsonl` once, at the end, for the report.

**Val results so far** (`results/compare_val_20260928-2203.md`, 224 rules, 20 groups):

| System | Params | Verified correct | Exact match | Per rule | Offline |
|---|---|---|---|---|---|
| templates | — | 62.9% (141) | 62.5% | 0.00 s | yes |
| gpt-oss-120b, zero-shot | 120B | 32.1% (72) | 0.0% | 2.06 s | no |
| **Qwen2.5-Coder-1.5B + Ward adapter** | 1.5B | **97.8% (219)** | 96.9% | — | yes |

The zero-shot model fails mostly on form: a missing `policies:` list, or filters that Custodian's
schema rejects. The templates fail on wording they have no pattern for ("half a day", "GPU box").

Read the 97.8% with two caveats. Val has only 20 independent groups. And the val sentences come from
the same paraphrase generator as train, so they test new parameter values and new seeds, but not
truly new ways of phrasing a rule. The holdout has the same limitation. A small set of hand-written,
never-templated sentences would be the honest test of generalisation.

### Sentences that are not rules

The compiler was trained only on rules, so it answers anything with a policy ("hello" → `require-greeting`,
"what is server ?" → `only-t3a-standard`). Two things sit in front of it — in `generate.py` and in Ward's
compile endpoint:

1. **Keyword gate** (`looks_like_rule`, in `prompting.py` and `backend/app/compiler/prompt.py`): a sentence
   that names nothing Ward watches never reaches any model. Accepts all 2,310 training/seed sentences.
2. **Router** (`backend/app/compiler/router.py`): a general chat model sorts the rest into rule / question /
   other, and answers questions instead of compiling them. Without one, a question-shape heuristic decides.

The lasting fix is v3: non-rules in the training data, answered with a refusal, so the compiler says it
itself.

## 8. What to record

Every run appends to `results/eval_runs.csv`. At minimum: run id, base model, adapter, dataset
version, epochs, LoRA rank, compile rate on validation, and the date. Phase 9 needs a table of these;
reconstructing it afterwards from memory is not possible.

The comparison that matters for the report:

| Arm | Compile rate | Inference cost |
|---|---|---|
| Templates (baseline) | | free |
| Frontier model, zero-shot | | $ per call |
| Frontier model + RAG | | $ per call |
| **7B fine-tuned + RAG** | | self-hosted |
| 1.5B fine-tuned + RAG | | self-hosted |

All measured on the same locked holdout, with the verifier as the judge. The cells stay empty until
Phase 9. The val figures are in §7.

Runs recorded so far (`results/eval_runs.csv`):

| Date | Run | Val rows | Groups | Verified correct | Exact match |
|---|---|---|---|---|---|
| 2026-09-27 | v1-1.5b | 71 | 7 | 91.6% | 64.8% |
| 2026-09-28 | v2-1.5b | 224 | 20 | 97.8% | 96.9% |
