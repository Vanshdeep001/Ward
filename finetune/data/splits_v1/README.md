# v1 split — exactly what `v1-1.5b` was trained on

Restored from commit `465cac4` ("datasets addition"): the files uploaded to Colab for the v1 run. Its
`val.jsonl` groups (`ebs-04, reg-02, rt-08, rt-15, sg-01, tag-06, type-04`) match
`results/preds_val.jsonl`, which is how we know these are the right files. The copy that was in
`data/splits/` afterwards had been reshuffled by the old nondeterministic builder and did **not**
match.

Do not edit these. v2 is built with

```bash
python scripts/04_build_dataset.py --extend-from data/splits_v1
```

which keeps every v1 group in the split it was in — train stays train, val stays val, and v1's
holdout groups stay in the holdout — and splits only the groups that are new in v2. That keeps the
holdout clean for both models, so v1 and v2 can be compared on it.
