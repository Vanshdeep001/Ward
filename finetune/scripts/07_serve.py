"""Serve the fine-tuned compiler over HTTP, so Ward's backend can call it.

    python 07_serve.py                    # http://127.0.0.1:8001, base + vansh-deep/ward-compiler-1.5b
    python 07_serve.py --adapter path\\to\\ward-compiler-v1 --port 8001

Endpoints
    GET  /health                  is the model loaded, and on what
    GET  /v1/models               the one model this server offers
    POST /v1/chat/completions     OpenAI-style chat completion

The request and response follow OpenAI's chat-completions format on purpose. Ollama and vLLM speak it
too, so the backend reaches whichever one is running by URL alone — this server today, Ollama on the
laptop later, vLLM on a GPU box in production — with no code change (WARD_LLM_URL).

This server runs the model with transformers + PEFT, the same way generate.py does. On a laptop CPU
that is ~30 s per rule and ~3 GB of RAM held for as long as the server runs; stop it when you are not
using it. Requests are handled one at a time: there is one model, and on a CPU two generations at
once would each take twice as long.
"""
import argparse
import threading
import time
import uuid

from generate import load_model  # same loading, same cache, same CPU/GPU choices as generate.py

state = {'model': None, 'tokenizer': None, 'name': 'ward-compiler', 'device': None}
lock = threading.Lock()


def create_app():
    from fastapi import FastAPI, HTTPException
    from pydantic import BaseModel, Field

    class Message(BaseModel):
        role: str
        content: str

    class ChatRequest(BaseModel):
        model: str | None = None
        messages: list[Message] = Field(min_length=1)
        temperature: float = 0.0
        max_tokens: int = Field(default=400, ge=1, le=2048)

    app = FastAPI(title='Ward compiler model', version='1')

    @app.get('/health')
    def health():
        return {'status': 'ok' if state['model'] is not None else 'loading',
                'model': state['name'], 'device': state['device']}

    @app.get('/v1/models')
    def models():
        return {'object': 'list', 'data': [{'id': state['name'], 'object': 'model', 'owned_by': 'ward'}]}

    @app.post('/v1/chat/completions')
    def chat(req: ChatRequest):
        if state['model'] is None:
            raise HTTPException(503, 'Model is still loading.')
        import torch

        model, tokenizer = state['model'], state['tokenizer']
        messages = [m.model_dump() for m in req.messages]
        prompt = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
        inputs = tokenizer(prompt, return_tensors='pt').to(model.device)

        # Temperature 0 means greedy — the default, because a policy has one right answer.
        sampling = {'do_sample': True, 'temperature': req.temperature} if req.temperature > 0 else {'do_sample': False}
        with lock, torch.no_grad():
            started = time.perf_counter()
            output = model.generate(**inputs, max_new_tokens=req.max_tokens,
                                    pad_token_id=tokenizer.pad_token_id or tokenizer.eos_token_id, **sampling)
            elapsed = time.perf_counter() - started

        new_tokens = output[0][inputs['input_ids'].shape[1]:]
        text = tokenizer.decode(new_tokens, skip_special_tokens=True)
        prompt_tokens, completion_tokens = int(inputs['input_ids'].shape[1]), int(len(new_tokens))
        return {
            'id': f'chatcmpl-{uuid.uuid4().hex[:12]}',
            'object': 'chat.completion',
            'created': int(time.time()),
            'model': state['name'],
            'choices': [{'index': 0, 'message': {'role': 'assistant', 'content': text}, 'finish_reason': 'stop'}],
            'usage': {'prompt_tokens': prompt_tokens, 'completion_tokens': completion_tokens,
                      'total_tokens': prompt_tokens + completion_tokens},
            'ward': {'latency_s': round(elapsed, 2)},
        }

    return app


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--base-model', default='Qwen/Qwen2.5-Coder-1.5B-Instruct')
    ap.add_argument('--adapter', default='vansh-deep/ward-compiler-1.5b')
    ap.add_argument('--name', default='ward-compiler', help='the model id clients ask for')
    ap.add_argument('--host', default='127.0.0.1', help='127.0.0.1 keeps it off the network')
    ap.add_argument('--port', type=int, default=8001)
    ap.add_argument('--cpu-fp32', action='store_true')
    args = ap.parse_args()

    import torch
    import uvicorn

    state['model'], state['tokenizer'] = load_model(args.base_model, args.adapter, cpu_fp32=args.cpu_fp32)
    state['name'] = args.name
    state['device'] = torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'cpu'
    print(f'Serving {args.name} on http://{args.host}:{args.port}/v1  (Ctrl+C to stop and free the memory)')
    uvicorn.run(create_app(), host=args.host, port=args.port, log_level='warning')


if __name__ == '__main__':
    main()
