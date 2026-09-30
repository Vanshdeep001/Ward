"""An LLM judge for the answer half of the RAG evaluation: claim-level faithfulness and answer relevance.

Deliberately a *different* model from the one that writes the answers (default qwen/qwen3.8-27b against
gpt-oss-120b): a model grading its own output is lenient with its own habits, and the score would say
more about that than about the answers.

  faithfulness   the answer is split into factual claims, and each is checked against exactly the context
                 the answering model was shown. Score = supported / claims. An answer with no factual
                 claims (a refusal, "none of your volumes are idle") is judged on that one statement.
  relevance      1–5, how directly and completely the answer addresses the question, regardless of
                 whether it is right. Reported as (score − 1) / 4, so 1.0 is best.

The deterministic checks in evaluate.py (numbers in the documents, citations against gold ids) stay:
the judge covers what they can't — a wrong claim with no number and no id in it.
"""
import json
import re
import time

import httpx

PROMPT = """You grade one answer from a retrieval-augmented assistant that answers questions about an AWS account.
You are given the QUESTION, the CONTEXT the assistant was shown, and its ANSWER.

1. Faithfulness. Split the ANSWER into its factual claims about the account — which resources exist, their
   properties, costs, counts, regions, owners, whether something matches. For each claim, decide whether the
   CONTEXT supports it. Do not use outside knowledge. Ignore pure advice and restatements of the question.
   If the answer says nothing matches or declines, that statement is the claim: check it against the CONTEXT.
2. Relevance. Score 1-5 how directly and completely the ANSWER addresses the QUESTION
   (5 = answers exactly what was asked, 3 = partly, 1 = does not address it). Judge relevance only, not truth.

Reply with JSON only, no other text:
{"claims": [{"claim": "...", "supported": true}], "relevance": 5, "reason": "one short sentence"}"""


class Judge:
    def __init__(self, url: str, api_key: str, model: str, timeout: float = 90.0,
                 transport: httpx.BaseTransport | None = None, max_wait: float = 60.0):
        self.model = model
        self.max_wait = max_wait
        self._url = url.rstrip('/')
        self._client = httpx.Client(timeout=timeout, transport=transport, headers={'Authorization': f'Bearer {api_key}'})

    def score(self, question: str, context: list[dict], answer: str) -> dict | None:
        docs = '\n\n'.join(f'[{c["id"]}] {c["text"]}' for c in context) or '(nothing was retrieved)'
        body = {
            'model': self.model, 'temperature': 0, 'max_tokens': 2500,
            'messages': [
                {'role': 'system', 'content': PROMPT},
                {'role': 'user', 'content': f'QUESTION:\n{question}\n\nCONTEXT:\n{docs}\n\nANSWER:\n{answer}\n\n/no_think'},
            ],
        }
        for _ in range(4):
            try:
                response = self._client.post(f'{self._url}/chat/completions', json=body)
            except httpx.HTTPError:
                return None
            if response.status_code == 429:
                time.sleep(min(self.max_wait, _retry_after(response)))
                continue
            if not response.is_success:
                return None
            text = response.json()['choices'][0]['message']['content'] or ''
            return parse(text)
        return None


def parse(text: str) -> dict | None:
    text = re.sub(r'<think>.*?</think>', '', text, flags=re.S)
    found = re.search(r'\{.*\}', text, re.S)
    if not found:
        return None
    try:
        data = json.loads(found[0])
    except json.JSONDecodeError:
        return None
    claims = [c for c in data.get('claims') or [] if isinstance(c, dict) and 'supported' in c]
    try:
        relevance = int(data.get('relevance'))
    except (TypeError, ValueError):
        return None
    relevance = min(5, max(1, relevance))
    supported = sum(bool(c['supported']) for c in claims)
    return {
        'claims': claims,
        'faithfulness': supported / len(claims) if claims else 1.0,
        'unsupportedClaims': [c.get('claim', '') for c in claims if not c['supported']],
        'relevance': relevance,
        'relevanceScore': (relevance - 1) / 4,
        'reason': data.get('reason', ''),
    }


def _retry_after(response) -> float:
    header = response.headers.get('retry-after')
    if header:
        try:
            return float(header) + 1
        except ValueError:
            pass
    found = re.search(r'try again in ([\d.]+)(ms|s)', response.text)
    return (float(found[1]) / (1000 if found[2] == 'ms' else 1) + 1) if found else 20.0
