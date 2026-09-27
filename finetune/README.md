# Fine-tuning Ward's compiler

Phase 6 of the SRS. The claim being tested is **N2**: that a 7B model, fine-tuned on outputs a
verifier has already certified, matches frontier performance at a fraction of the inference cost —
and without sending infrastructure configuration to a third party.

Read §9 of the SRS first. This document is the operational companion: what to run, where to run it,
and what it costs.

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

## 5. Running the data pipeline

On the laptop (all of this is cheap):

```bash
cd finetune
python scripts/01_expand_rules.py                       # seeds   → data/generated/rules_expanded.jsonl
python scripts/02_generate.py --teacher templates       # rules   → data/generated/candidates.jsonl
python scripts/03_verify.py                             # grade   → data/verified/pairs.jsonl
python scripts/04_build_dataset.py                      # format  → data/splits/*.jsonl
```

`03_verify.py` prints the compile rate — the number Phase 9 compares everything against.

Then upload `data/splits/` to Kaggle as a private Dataset, and run in a notebook:

```python
!pip -q install "transformers>=4.44" peft trl bitsandbytes accelerate datasets
!python 05_train_qlora.py --config configs/qlora_t4.yaml \
    --train /kaggle/input/ward-splits/train.jsonl \
    --val   /kaggle/input/ward-splits/val.jsonl \
    --out   /kaggle/working/ward-compiler-v1
```

Download the adapter (~100 MB) and commit it under `adapters/ward-compiler-v1/`. The base model stays
in the cloud; the adapter is the only artefact you keep.

---

## 5. Serving it back into Ward

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

**For the laptop demo,** convert the 1.5B adapter to GGUF and run it on CPU:

```bash
python llama.cpp/convert_hf_to_gguf.py merged-1.5b --outfile ward-1.5b.gguf
./llama.cpp/llama-quantize ward-1.5b.gguf ward-1.5b-q4.gguf Q4_K_M
./llama.cpp/llama-server -m ward-1.5b-q4.gguf -c 2048
```

That is ~1 GB of RAM and runs comfortably inside your 16 GB, no GPU involved. It is also a nice line
for the viva: the whole system, compiler included, runs on a laptop with no data leaving it.

---

## 6. What to record

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

All measured on the same locked holdout, with the verifier as the judge.
