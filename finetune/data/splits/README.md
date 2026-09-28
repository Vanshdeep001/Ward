# Splits — `test_holdout.jsonl` is LOCKED

| File | Use |
|---|---|
| `train.jsonl` | Training. |
| `val.jsonl` | Watched during training, for early stopping and checkpoint selection. |
| `test_holdout.jsonl` | **Do not open until Phase 9.** |

## Why the holdout is locked

A held-out set measures generalisation exactly once. Every time you look at it and change something
in response — a hyperparameter, a prompt, the data — some of its information leaks into the model,
and the number it reports drifts from the truth toward the number you were hoping for. By the fifth
look it is a validation set wearing a holdout's name, and the figure in the report is not a
measurement any more.

Tune against `val.jsonl`. Open the holdout when the method is frozen, run it once, and report what it
says — including if it is worse than you expected.

## How these were split

By **rule family group**, never by row. Each seed rule and all of its paraphrases and parameter
variants form one group, and a group lands wholly in one split.

A random row-level split would put *"no GPU instance over 6 hours"* in train and *"no GPU instance
over 12 hours"* in test. The model would score well by pattern-matching something it had already been
shown, and the number would mean nothing. `04_build_dataset.py` asserts that no group spans two
splits and fails loudly if one does.

Families are stratified, so each split contains the same mix of rule types.

## What is in here now: v2

Built with `04_build_dataset.py --extend-from data/splits_v1`: 1,254 train / 224 val / 621 holdout
rows. Every group v1 was trained on is still in train, v1's val groups are still in val, and v1's 11
holdout groups are still in the holdout; only the 131 seeds new in v2 were split. v1's own files are
in `data/splits_v1/`.

## Regenerating

```bash
python scripts/04_build_dataset.py
```

Deterministic — each family is shuffled by its own name-seeded generator, so re-running produces the
same split. (Until 2026-09-27 it did not: the builder iterated a Python set, whose order changes per
process, and every run reshuffled. Any split built before then must be restored, not rebuilt.)

**Once a model has been trained, pin the split to the files it actually saw:**

```bash
python scripts/04_build_dataset.py --keep-from path/to/folder-with-train-and-val
```

Train and val groups are taken from those files exactly, and every other group becomes the holdout.
That guarantees the holdout contains nothing the model trained on, whatever the builder would choose
today.

**If you add seed rules,** the split boundaries move. Do that before you start training, not after,
and never once the holdout has been opened.
