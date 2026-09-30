"""Turn the fine-tuned adapter into GGUF files Ollama can run on a laptop CPU. Run on Colab, not the laptop.

    !git clone https://github.com/<you>/Ward.git && cd Ward/finetune/scripts
    from huggingface_hub import login; login()          # a token with WRITE access
    !python 09_export_gguf.py --adapter vansh-deep/ward-compiler-1.5b-v2 \
        --repo vansh-deep/ward-compiler-1.5b-v2-gguf --quants q8_0 q4_k_m

What it does, in order:
  1. merge   — base Qwen2.5-Coder-1.5B-Instruct + the LoRA adapter → one ordinary model (fp16, ~3 GB).
               Ollama can't apply a LoRA adapter on top of a quantized base reliably; a merged model it can.
  2. convert — llama.cpp's converter → ward-compiler-f16.gguf. q8_0 comes straight out of the converter.
  3. quantize— llama.cpp's llama-quantize (built here, ~4 min) → q4_k_m and any other k-quant.
  4. upload  — the quantized files (not the 3 GB f16) to a Hugging Face model repo, to download on the laptop.

Sizes for this 1.5B model: q8_0 ≈ 1.6 GB (practically lossless), q4_k_m ≈ 1.0 GB (fastest, may cost some
accuracy on exact YAML). Export both and let 06_evaluate.py --url decide — the verifier is the judge.
Nothing here needs a GPU; a CPU Colab runtime works, only slower at the merge.
"""
import argparse
import shutil
import subprocess
import sys
from pathlib import Path

LLAMA_CPP = 'https://github.com/ggml-org/llama.cpp'


def run(*cmd, cwd=None) -> None:
    """Run a step, printing its output — minus the converter's line per tensor (hundreds of them)."""
    print('$', ' '.join(str(c) for c in cmd), flush=True)
    proc = subprocess.Popen([str(c) for c in cmd], cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            text=True, bufsize=1)
    skipped, template = 0, False
    for line in proc.stdout:
        if line.startswith('INFO:hf-to-gguf:') and ('torch.' in line and '-->' in line):
            skipped += 1
            continue
        # The chat template is printed in full (~60 lines); its first line is enough.
        if 'Setting chat_template to' in line:
            template = True
            print(line.split(' to ', 1)[0] + ' (Qwen2.5 ChatML)', flush=True)
            continue
        if template:
            if line.startswith('INFO:'):
                template = False
            else:
                continue
        print(line, end='', flush=True)
    if skipped:
        print(f'  ({skipped} per-tensor lines hidden)')
    if proc.wait() != 0:
        raise subprocess.CalledProcessError(proc.returncode, cmd)


def _colab_fixups() -> None:
    """Colab ships torchao 0.10, which current peft refuses to import alongside (it wants >0.16), and a peft
    older than the one the adapter was saved with. The merge needs neither torchao nor anything new, so on
    Colab: remove torchao and upgrade peft. Elsewhere, only say what to do."""
    from importlib.metadata import PackageNotFoundError, version

    try:
        old_torchao = tuple(int(x) for x in version('torchao').split('.')[:2]) < (0, 16)
    except (PackageNotFoundError, ValueError):
        old_torchao = False
    if not old_torchao:
        return
    if not Path('/content').exists():
        raise SystemExit('An old torchao is installed and peft will refuse to load. Run: '
                         'pip uninstall -y torchao && pip install -U peft')
    print('Colab: removing the old torchao and upgrading peft (the merge needs neither) …', flush=True)
    run(sys.executable, '-m', 'pip', 'uninstall', '-y', '-q', 'torchao')
    run(sys.executable, '-m', 'pip', 'install', '-U', '-q', 'peft')


def merge(base_model: str, adapter: str, out: Path) -> None:
    if (out / 'config.json').exists():
        print(f'merged model already at {out}, skipping the merge')
        return
    _colab_fixups()
    import torch
    from peft import PeftModel
    from transformers import AutoModelForCausalLM, AutoTokenizer

    print(f'merging {adapter} into {base_model} …', flush=True)
    try:
        model = AutoModelForCausalLM.from_pretrained(base_model, dtype=torch.float16, low_cpu_mem_usage=True)
    except TypeError:  # older transformers call it torch_dtype
        model = AutoModelForCausalLM.from_pretrained(base_model, torch_dtype=torch.float16, low_cpu_mem_usage=True)
    model = PeftModel.from_pretrained(model, adapter).merge_and_unload()
    model.save_pretrained(out, safe_serialization=True)
    # The adapter's tokenizer carries the chat template the model was trained with.
    AutoTokenizer.from_pretrained(adapter).save_pretrained(out)
    print(f'merged → {out}')


def llama_cpp(workdir: Path) -> Path:
    repo = workdir / 'llama.cpp'
    if not repo.exists():
        run('git', 'clone', '--depth', '1', LLAMA_CPP, repo)
    # Only the converter's own dependencies — the full requirements file can reinstall torch over Colab's.
    run(sys.executable, '-m', 'pip', 'install', '-q', '-e', repo / 'gguf-py', 'sentencepiece', 'protobuf')
    return repo


def quantize_tool(repo: Path) -> Path:
    tool = repo / 'build' / 'bin' / 'llama-quantize'
    if not tool.exists():
        run('cmake', '-S', repo, '-B', repo / 'build', '-DLLAMA_CURL=OFF', '-DGGML_NATIVE=OFF', '-DCMAKE_BUILD_TYPE=Release')
        run('cmake', '--build', repo / 'build', '--target', 'llama-quantize', '-j', '4')
    return tool


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--adapter', default='vansh-deep/ward-compiler-1.5b-v2', help='HF repo or local folder')
    ap.add_argument('--base-model', default='Qwen/Qwen2.5-Coder-1.5B-Instruct')
    ap.add_argument('--quants', nargs='+', default=['q8_0', 'q4_k_m'], help='q8_0, q4_k_m, q5_k_m, q6_k …')
    ap.add_argument('--name', default='ward-compiler', help='file name prefix: <name>-<quant>.gguf')
    ap.add_argument('--workdir', type=Path, default=Path('/content/gguf') if Path('/content').exists() else Path('gguf'))
    ap.add_argument('--repo', help='Hugging Face repo to upload to, e.g. vansh-deep/ward-compiler-1.5b-v2-gguf')
    args = ap.parse_args()

    args.workdir.mkdir(parents=True, exist_ok=True)
    merged = args.workdir / 'merged'
    merge(args.base_model, args.adapter, merged)

    repo = llama_cpp(args.workdir)
    f16 = args.workdir / f'{args.name}-f16.gguf'
    outputs = []
    for quant in [q.lower() for q in args.quants]:
        target = args.workdir / f'{args.name}-{quant}.gguf'
        if quant in ('q8_0', 'f16', 'bf16'):  # the converter writes these itself
            run(sys.executable, repo / 'convert_hf_to_gguf.py', merged, '--outfile', target, '--outtype', quant)
        else:
            if not f16.exists():
                run(sys.executable, repo / 'convert_hf_to_gguf.py', merged, '--outfile', f16, '--outtype', 'f16')
            run(quantize_tool(repo), f16, target, quant.upper())
        outputs.append(target)
        print(f'  {target.name}: {target.stat().st_size / 1e9:.2f} GB')

    if args.repo:
        from huggingface_hub import HfApi

        api = HfApi()
        api.create_repo(args.repo, repo_type='model', exist_ok=True, private=False)
        for path in outputs:
            print(f'uploading {path.name} → {args.repo} …', flush=True)
            api.upload_file(path_or_fileobj=str(path), path_in_repo=path.name, repo_id=args.repo)
        print(f'\ndone: https://huggingface.co/{args.repo}')
    else:
        print('\nno --repo given: download the .gguf files from', args.workdir)

    shutil.rmtree(merged, ignore_errors=True)  # 3 GB of Colab disk back; the GGUFs are what matter


if __name__ == '__main__':
    main()
