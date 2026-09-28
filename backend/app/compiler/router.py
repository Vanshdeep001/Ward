"""The router: decides whether what the user typed is a guardrail at all, before the compiler sees it.

The fine-tuned compiler was trained only on rules, so it answers anything with a policy — "what is a
server?" came back as a policy named only-t3a-standard. It cannot say "that's a question". So every
sentence is sorted first:

    typed ─► keyword gate ─► router model ─┬─ rule      → the compiler writes and verifies a policy
             (free, instant)                ├─ question  → answered in plain words, no policy
                                            └─ other     → told what the box is for, with an example

The keyword gate (prompt.looks_like_rule) drops sentences that name nothing Ward watches without spending
a model call. The router model — any OpenAI-compatible chat API; Ward uses the one configured for
search — classifies what is left and, for a question, answers it in the same call. If the router model
is unreachable, a simple heuristic stands in: question-shaped sentences are treated as questions, and
everything else goes to the compiler as before.
"""
import json
import re
from dataclasses import dataclass

import httpx

from app.compiler import prompt

EXAMPLE = 'No GPU instance may run for more than 6 hours'
NOT_A_RULE = ('That isn’t a guardrail. This box turns a rule about your AWS resources into a policy — '
              f'for example: “{EXAMPLE}”.')
QUESTION_FALLBACK = ('That looks like a question rather than a rule. Ask it in Ask Ward, which answers from '
                     f'your account. Here, write a rule — for example: “{EXAMPLE}”.')

SYSTEM = f"""You sort what a user typed into the guardrail box of Ward, a tool that watches an AWS account read-only.

Reply with JSON only, no other text: {{"route": "rule" | "question" | "other", "answer": "..."}}

- "rule": an instruction that sets a limit or requirement Ward could check on AWS resources — how long instances or GPUs may run, required tags, unattached volumes, public databases, ports open to the internet, allowed instance types, allowed regions. Informal or imperative wording still counts ("kill any VM up more than 5 hours", "don't expose Redis"). answer: "".
- "question": the user is asking for information or an explanation ("what is a server?", "how much does a t3.micro cost?", "which of my instances have no owner?"). answer: one to three plain sentences. If it is about their own account, say Ask Ward can answer it from their data.
- "other": greetings, chit-chat, nonsense, or requests Ward cannot do (it cannot create, stop or delete anything). answer: one friendly sentence on what the guardrail box is for, with the example "{EXAMPLE}".

When a sentence could be either, prefer "rule" only if it states a limit or requirement."""

QUESTION_SHAPE = re.compile(
    r'^\s*(what|what\'s|whats|why|how|who|when|where|which|is|are|can|could|does|do|did|should|would|will|'
    r'explain|tell me|define|describe)\b|\?\s*$', re.I)


@dataclass
class Route:
    kind: str           # 'rule' | 'question' | 'other'
    answer: str | None  # for question and other: what to show instead of a policy
    by: str             # 'gate' | 'model' | 'heuristic' — who decided, shown so a wrong call is traceable

    @property
    def is_rule(self) -> bool:
        return self.kind == 'rule'


class Router:
    def __init__(self, url: str | None = None, api_key: str | None = None, model: str | None = None,
                 timeout: float = 30.0, transport: httpx.BaseTransport | None = None):
        self.model = model
        self.enabled = bool(url and api_key and model)
        self._url = (url or '').rstrip('/')
        self._client = httpx.Client(timeout=timeout, transport=transport,
                                    headers={'Authorization': f'Bearer {api_key}'}) if self.enabled else None

    def route(self, sentence: str) -> Route:
        if not prompt.looks_like_rule(sentence):
            # Names nothing Ward watches: no model call needed to know it isn't a rule.
            return Route('question' if QUESTION_SHAPE.search(sentence) else 'other',
                         QUESTION_FALLBACK if QUESTION_SHAPE.search(sentence) else NOT_A_RULE, 'gate')
        if self.enabled:
            decided = self._ask(sentence)
            if decided is not None:
                return decided
        if QUESTION_SHAPE.search(sentence):
            return Route('question', QUESTION_FALLBACK, 'heuristic')
        return Route('rule', None, 'heuristic')

    def _ask(self, sentence: str) -> Route | None:
        try:
            response = self._client.post(f'{self._url}/chat/completions', json={
                'model': self.model,
                'messages': [{'role': 'system', 'content': SYSTEM}, {'role': 'user', 'content': sentence}],
                'temperature': 0,
                'max_tokens': 800,  # reasoning models think before answering; leave them room
            })
            response.raise_for_status()
            text = response.json()['choices'][0]['message']['content'] or ''
        except (httpx.HTTPError, KeyError, IndexError, ValueError):
            return None  # the heuristic takes over; a router outage must not stop the compiler
        return _parse(text)


def _parse(text: str) -> Route | None:
    found = re.search(r'\{.*\}', text, re.S)
    if not found:
        return None
    try:
        data = json.loads(found[0])
    except json.JSONDecodeError:
        return None
    kind = str(data.get('route', '')).lower().strip()
    if kind not in ('rule', 'question', 'other'):
        return None
    answer = (data.get('answer') or '').strip() or None
    if kind == 'other' and not answer:
        answer = NOT_A_RULE
    if kind == 'question' and not answer:
        answer = QUESTION_FALLBACK
    return Route(kind, None if kind == 'rule' else answer, 'model')
