"""Guardrails around the RAG pipeline: what may go in, and what may come out.

In, from the user:
  • requests to change the account ("delete algobench") are refused before retrieval — Ward is
    read-only, and no model should be the thing standing between a sentence and an action;
  • attempts to rewrite the assistant's instructions ("ignore your rules…") are refused.

In, from the account (the less obvious risk):
  • tag values and names are written by whoever can tag a resource, and they are pasted into the
    documents the model reads. `clean` shortens them, strips brackets and line breaks that could fake a
    document boundary, and replaces anything that reads like an instruction. The prompt also tells the
    model that document text is data, never instructions.

Out, from the model:
  • off-topic questions: the model is asked to answer with the sentinel OUT_OF_SCOPE, which becomes a
    polite refusal and no sources;
  • numbers: every ₹ amount and every counted quantity ("91 days", "15 resources") in the answer must
    appear in the retrieved documents or the question. Ones that don't are reported, never silently
    trusted — a wrong figure is the most damaging thing a cost assistant can say.
  • citations of resources that were never retrieved are dropped (answer.cited).
"""
import re
from dataclasses import dataclass, field

OUT_OF_SCOPE = 'OUT_OF_SCOPE'

# An instruction to act, not a question about acting: "delete X", "please stop X", "can you terminate X".
# "Which instances should I stop?" is advice, and is allowed through.
ACTION = re.compile(
    r'^\s*(?:please\s+|pls\s+|kindly\s+)?(?:(?:can|could|would|will)\s+you\s+(?:please\s+)?)?'
    r'(delete|terminate|stop|kill|shut\s*down|remove|resize|restart|reboot|detach|modify|destroy|start|launch|create)\b',
    re.I,
)

INJECTION = re.compile(
    r'\b(ignore|disregard|forget|override|bypass)\b[^.]{0,40}\b(instructions?|rules?|prompts?|previous|above|guardrails?|system)\b'
    r'|\bsystem\s+prompt\b|\byou\s+are\s+now\b|\bact\s+as\b|\bjailbreak\b|\bdeveloper\s+mode\b'
    r'|\b(reveal|print|show|repeat)\b[^.]{0,30}\b(prompt|instructions)\b'
    r'|\bnew\s+instructions?\b|<\s*/?\s*(system|assistant|user)\s*>',
    re.I,
)

REMOVED = '[suspicious text removed]'
MAX_UNTRUSTED = 80


def clean(value: object) -> str:
    """Make account-supplied text (a tag, a name) safe to put in a document the model reads."""
    text = re.sub(r'[\r\n\t]+', ' ', str(value))
    text = text.replace('[', '(').replace(']', ')')  # "[i-0abc]" is how documents begin; don't let a tag fake one
    if INJECTION.search(text):
        return REMOVED
    return text[:MAX_UNTRUSTED] + ('…' if len(text) > MAX_UNTRUSTED else '')


@dataclass
class Verdict:
    blocked: str | None = None  # 'action' | 'injection' | 'off-topic'
    message: str | None = None


def screen_question(question: str) -> Verdict:
    if INJECTION.search(question):
        return Verdict('injection', 'I can only answer questions about your AWS account — I can’t change how I work.')
    match = ACTION.search(question)
    if match:
        return Verdict('action', f'Ward has read-only access by design, so it can’t {match[1].lower()} anything. '
                                 'Ask me about the resource instead, and I’ll tell you what it is and what it costs.')
    return Verdict()


def off_topic(answer: str) -> Verdict:
    if answer.strip().strip('.').upper() == OUT_OF_SCOPE:
        return Verdict('off-topic', 'I can only answer questions about your AWS account — its resources, costs, '
                                    'owners, regions and guardrails.')
    return Verdict()


# ─── Numbers ─────────────────────────────────────────────────────────────────

MONEY = re.compile(r'₹\s?(\d[\d,]*(?:\.\d+)?)')
COUNTED = re.compile(
    r'(?<![\w.-])(\d[\d,]*(?:\.\d+)?)\s*(days?|hours?|months?|weeks?|GB|resources?|instances?|volumes?|databases?|'
    r'security groups?|gateways?|servers?)\b', re.I)
NUMBER = re.compile(r'(?<![\w-])(\d[\d,]*(?:\.\d+)?)(?![\w-])')
ID_LIKE = re.compile(r'\[[^\]]+\]|\b[a-z]+-[0-9a-z]+\b|\b[a-z]\d[a-z]?\.\w+\b', re.I)  # ids, t3.micro, g4dn.xlarge


@dataclass
class NumberCheck:
    checked: int = 0
    unsupported: list[str] = field(default_factory=list)

    @property
    def grounded(self) -> bool:
        return not self.unsupported


def check_numbers(answer: str, sources: list[str], question: str = '') -> NumberCheck:
    """Every ₹ amount and counted quantity in `answer` must appear (to the paisa, or as the documents
    round it) somewhere in `sources` or the question."""
    known = _numbers(' '.join(sources) + ' ' + question)
    text = ID_LIKE.sub(' ', answer)
    claims = [(m[0], m[1]) for m in MONEY.finditer(text)] + [(m[0], m[1]) for m in COUNTED.finditer(text)]
    result = NumberCheck(checked=len(claims))
    for shown, raw in claims:
        value = _value(raw)
        if value is None or not any(_close(value, k) for k in known):
            result.unsupported.append(shown.strip())
    return result


def _numbers(text: str) -> set[float]:
    text = ID_LIKE.sub(' ', text)
    return {v for m in NUMBER.finditer(text) if (v := _value(m[1])) is not None}


def _value(raw: str) -> float | None:
    try:
        return float(raw.replace(',', ''))
    except ValueError:
        return None


def _close(a: float, b: float) -> bool:
    # Rounding the model may reasonably do: ₹676.80 → ₹677, ₹22.56 → ₹22.6.
    return abs(a - b) <= max(0.51, abs(b) * 0.005)
