"""The fine-tuned compiler model, reached over HTTP (SRS Phase 6).

`LlmCompiler` asks a model server for a policy. The server speaks the OpenAI chat-completions format,
which finetune/scripts/07_serve.py, Ollama and vLLM all implement, so where the model runs is only a
URL (WARD_LLM_URL): the laptop script today, Ollama on the laptop later, a GPU box in production.

The model returns YAML and nothing else. It does not say what the rule *means* — the intent the
verifier builds fixtures from — so on its own its output cannot be verified, and must not grade
itself (SRS §4.1). `HybridCompiler` supplies the intent from the template compiler's reading of the
same sentence when there is one; when there isn't, the draft goes out marked unverified.
"""
import httpx

from app.compiler import prompt
from app.compiler.base import Draft
from app.compiler.templates import TemplateCompiler


class LlmUnavailable(Exception):
    """The model server could not be reached or did not answer. Carries advice fit to show a user."""


class LlmCompiler:
    def __init__(self, url: str, model: str, timeout: float = 120.0, transport: httpx.BaseTransport | None = None):
        self.url = url.rstrip('/')
        self.model = model
        self.name = f'llm:{model}'
        self._client = httpx.Client(timeout=timeout, transport=transport)

    def compile(self, english: str) -> Draft | None:
        # The model was trained only on rules and answers anything with a policy ("hello" became one
        # named require-greeting). A sentence that names nothing Ward watches is not sent at all; None
        # tells the caller Ward could not map it, which is the truth.
        if not prompt.looks_like_rule(english):
            return None
        family, reference = prompt.retrieve(english)
        try:
            response = self._client.post(f'{self.url}/chat/completions', json={
                'model': self.model,
                'messages': prompt.build_messages(english, reference),
                'temperature': 0,  # greedy: the same rule should always produce the same policy
                'max_tokens': 400,
            })
            response.raise_for_status()
            text = response.json()['choices'][0]['message']['content']
        except httpx.ConnectError as exc:
            start = ('open the Ollama app (or run `ollama serve`)' if ':11434' in self.url
                     else 'run `python finetune/scripts/07_serve.py`')
            raise LlmUnavailable(
                f'The compiler model is not running at {self.url}. To start it, {start} — '
                f'or set WARD_COMPILER=templates.'
            ) from exc
        except httpx.TimeoutException as exc:
            raise LlmUnavailable(
                f'The compiler model at {self.url} did not answer in time. On a laptop CPU a rule takes '
                f'~30 s; raise WARD_LLM_TIMEOUT if it is simply slow.'
            ) from exc
        except (httpx.HTTPError, KeyError, IndexError, ValueError) as exc:
            raise LlmUnavailable(f'The compiler model at {self.url} returned an unusable answer: {exc}') from exc

        policy_yaml = _strip_fences(text)
        if not policy_yaml.strip():
            return None
        return Draft(
            english=english,
            kind=family or 'unknown',
            params={},
            policy_yaml=policy_yaml,
            intent=None,  # the model does not say what the rule means; see HybridCompiler
            explanation='Drafted by Ward’s fine-tuned compiler model.',
            assumptions=[],
            drafted_by=self.name,
        )

    def reachable(self) -> bool:
        try:
            return self._client.get(f'{self.url}/models', timeout=1.5).status_code == 200
        except httpx.HTTPError:
            return False


class HybridCompiler:
    """Templates and the model together.

    prefer_llm=False ("hybrid"): the templates write every policy they can read — deterministic and
      verified — and the model only drafts the sentences they can't. Those come back unverified.
    prefer_llm=True ("llm"): the model writes every policy. Where the templates can read the sentence,
      their reading is the intent the model's policy is graded against; where they can't, unverified.
    """

    def __init__(self, llm: LlmCompiler, templates: TemplateCompiler | None = None, prefer_llm: bool = False):
        self.llm = llm
        self.templates = templates or TemplateCompiler()
        self.prefer_llm = prefer_llm
        self.name = 'llm' if prefer_llm else 'hybrid'

    def compile(self, english: str) -> Draft | None:
        reading = self.templates.compile(english)
        if reading is not None and not self.prefer_llm:
            return reading.model_copy(update={'drafted_by': self.templates.name})

        draft = self.llm.compile(english)
        if draft is None or reading is None:
            return draft
        # The model wrote it; the templates say what it should mean. Fixtures come from their intent,
        # so the model's policy is tested against something it did not produce.
        return draft.model_copy(update={
            'intent': reading.intent, 'kind': reading.kind, 'params': reading.params,
            'assumptions': [f'Graded against the template compiler’s reading: {reading.explanation}'],
        })


def _strip_fences(text: str) -> str:
    text = text.strip()
    if text.startswith('```'):
        text = text.split('\n', 1)[1].rsplit('```', 1)[0]
    return text.strip() + '\n'
