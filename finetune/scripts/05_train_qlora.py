"""QLoRA fine-tune (SRS §9.7). Runs on a cloud GPU — never on the development laptop.

QLoRA loads the base model in 4-bit and freezes it, training only small adapter matrices inside the
attention and MLP layers. What you keep at the end is a ~100 MB adapter, not a 15 GB model.

    # Kaggle / Colab, free T4
    !python 05_train_qlora.py --config configs/qlora_t4.yaml \
        --train data/splits/train.jsonl --val data/splits/val.jsonl --out ward-compiler-v1

    # Rented A40 / 4090
    python 05_train_qlora.py --config configs/qlora_v1.yaml ...

Requires: transformers, peft, trl, bitsandbytes, accelerate, datasets, pyyaml.
`bitsandbytes` needs CUDA; this script will refuse to start without a GPU rather than pretend.
"""
import argparse
import json
from pathlib import Path

import yaml


def load_examples(path: Path, tokenizer) -> list[dict]:
    """Render each chat example with the model's own template, so training and serving agree."""
    rows = []
    for line in Path(path).read_text(encoding='utf-8').splitlines():
        if not line.strip():
            continue
        messages = json.loads(line)['messages']
        rows.append({'text': tokenizer.apply_chat_template(messages, tokenize=False)})
    return rows


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--config', type=Path, required=True)
    ap.add_argument('--train', type=Path, required=True)
    ap.add_argument('--val', type=Path, required=True)
    ap.add_argument('--out', type=Path, required=True)
    ap.add_argument('--base-model', default=None, help='override the config, e.g. to try the 7B')
    ap.add_argument('--resume', action='store_true',
                    help='continue from the last checkpoint in --out — for when Colab disconnects mid-run')
    args = ap.parse_args()

    # This script is meant to run on a cloud GPU. Say so plainly instead of dying on an import.
    try:
        import torch
    except ImportError:
        raise SystemExit(
            'PyTorch is not installed here, which is expected: this script runs on a cloud GPU, not\n'
            'on the development laptop. Upload data/splits/ to Kaggle (free T4, 30 h/week) and run it\n'
            'there. See finetune/README.md §1.'
        ) from None

    if not torch.cuda.is_available():
        raise SystemExit(
            'No CUDA GPU. QLoRA cannot run here — 4-bit quantisation is CUDA-only.\n'
            'Use Kaggle (free T4, 30 h/week) or rent an A40. See finetune/README.md §1.'
        )

    from datasets import Dataset
    from peft import LoraConfig
    from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig

    cfg = yaml.safe_load(args.config.read_text(encoding='utf-8'))
    base_model = args.base_model or cfg['base_model']
    train_cfg = cfg['training']
    print(f'base model : {base_model}')
    print(f'gpu        : {torch.cuda.get_device_name(0)}')

    tokenizer = AutoTokenizer.from_pretrained(base_model)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    train_ds = Dataset.from_list(load_examples(args.train, tokenizer))
    val_ds = Dataset.from_list(load_examples(args.val, tokenizer))
    print(f'examples   : {len(train_ds)} train, {len(val_ds)} val')

    q = cfg['quantization']
    compute_dtype = getattr(torch, q['bnb_4bit_compute_dtype'])
    # Load the parts that are not quantised (embeddings, norms, lm_head) in the compute dtype. Left
    # unset, transformers 5 loads them in the checkpoint's own dtype — bfloat16 for Qwen2.5 — and on a
    # T4 the fp16 grad scaler then meets bf16 gradients and dies with
    # "_amp_foreach_non_finite_check_and_unscale_cuda not implemented for 'BFloat16'".
    model = AutoModelForCausalLM.from_pretrained(
        base_model,
        quantization_config=BitsAndBytesConfig(
            load_in_4bit=q['load_in_4bit'],
            bnb_4bit_compute_dtype=compute_dtype,
            bnb_4bit_quant_type=q['bnb_4bit_quant_type'],
            bnb_4bit_use_double_quant=q['bnb_4bit_use_double_quant'],
        ),
        device_map='auto',
        **{_dtype_kwarg(): compute_dtype},
    )
    model.config.use_cache = False  # incompatible with gradient checkpointing

    peft_config = LoraConfig(**cfg['lora'])
    trainer = _build_trainer(model, tokenizer, train_ds, val_ds, peft_config, train_cfg, args.out)
    _trainable_in_fp32(trainer.model, torch)

    trainer.train(resume_from_checkpoint=True if args.resume else None)
    trainer.save_model(str(args.out))
    tokenizer.save_pretrained(str(args.out))

    history = [h for h in trainer.state.log_history if 'eval_loss' in h]
    if history:
        best = min(history, key=lambda h: h['eval_loss'])
        print(f"\nbest eval_loss {best['eval_loss']:.4f} at step {best.get('step')}")
    print(f'adapter saved to {args.out} — this is the artefact to keep (~100 MB)')
    print('Next: 06_evaluate.py --mode generate, then score the predictions on the laptop.')


def _dtype_kwarg() -> str:
    """transformers renamed from_pretrained's `torch_dtype` to `dtype` (4.56); older versions ignore
    `dtype` silently, so ask which one this install understands."""
    import transformers

    major, minor = (int(x) for x in transformers.__version__.split('.')[:2])
    return 'dtype' if (major, minor) >= (4, 56) else 'torch_dtype'


def _trainable_in_fp32(model, torch) -> None:
    """Keep every trainable weight — the LoRA adapters — in float32.

    Mixed precision computes in fp16/bf16 but must hold the weights it updates in fp32: the fp16 grad
    scaler cannot unscale half-precision gradients, and tiny updates vanish when added to half-precision
    weights. The frozen 4-bit base is untouched, so this costs a few MB.
    """
    cast = 0
    for _, param in model.named_parameters():
        if param.requires_grad and param.dtype != torch.float32:
            param.data = param.data.float()
            cast += 1
    trainable = sum(p.numel() for p in model.parameters() if p.requires_grad)
    print(f'trainable  : {trainable / 1e6:.1f}M parameters in float32' + (f' ({cast} tensors upcast)' if cast else ''))


def _build_trainer(model, tokenizer, train_ds, val_ds, peft_config, train_cfg, out):
    """Build the trainer against whichever TRL is installed, by asking it for its own field names.

    TRL renames things between releases — max_seq_length became max_length, tokenizer became
    processing_class — and a hard-coded name fails a few seconds into a Colab session. Reading the
    installed version's fields means the config file never has to track TRL's changelog.
    """
    import dataclasses
    import inspect

    from trl import SFTConfig, SFTTrainer

    fields = {f.name for f in dataclasses.fields(SFTConfig)}
    wanted = {k: v for k, v in train_cfg.items() if k != 'max_seq_length'}
    wanted['max_length' if 'max_length' in fields else 'max_seq_length'] = train_cfg['max_seq_length']
    if 'eval_strategy' in wanted and 'eval_strategy' not in fields:
        wanted['evaluation_strategy'] = wanted.pop('eval_strategy')
    # transformers 5 folded warmup_ratio into warmup_steps, which now reads a float in [0, 1) as a ratio.
    if 'warmup_ratio' in wanted and 'warmup_ratio' not in fields:
        wanted['warmup_steps'] = wanted.pop('warmup_ratio')

    # Say which settings the installed TRL doesn't know, instead of silently dropping them — a quietly
    # ignored fp16 or learning rate is how a run "works" and learns nothing.
    unknown = sorted(k for k in wanted if k not in fields)
    if unknown:
        print(f'  ! installed TRL ignores these config keys: {", ".join(unknown)}')
    sft_args = SFTConfig(output_dir=str(out), dataset_text_field='text',
                         **{k: v for k, v in wanted.items() if k in fields})

    params = inspect.signature(SFTTrainer.__init__).parameters
    tokenizer_arg = 'processing_class' if 'processing_class' in params else 'tokenizer'
    return SFTTrainer(model=model, args=sft_args, train_dataset=train_ds, eval_dataset=val_ds,
                      peft_config=peft_config, **{tokenizer_arg: tokenizer})


if __name__ == '__main__':
    main()
