"""The seam between English and YAML.

Everything downstream — the clarifier, the verifier, the simulator, the API — talks to a `Compiler`,
never to a particular way of producing a policy. Today the only implementation is the deterministic
template compiler (SRS Phase 2 baseline). The RAG pipeline and the fine-tuned 7B model are later
implementations of this same protocol, which is what makes the compile-rate comparison in SRS §9.9 a
swap of one object rather than a rewrite.
"""
from typing import Protocol

from pydantic import BaseModel

from app.verifier.intents import Intent


class Draft(BaseModel):
    """A candidate policy, before the verifier has had a say. Never stored unverified."""
    english: str
    kind: str  # the rule family — 'ec2-runtime', 'require-tag', …
    params: dict = {}
    policy_yaml: str
    intent: Intent
    explanation: str  # what this policy does, in the user's own terms
    assumptions: list[str] = []  # decisions Ward made that the sentence did not state


class Compiler(Protocol):
    name: str

    def compile(self, english: str) -> Draft | None:
        """Return a candidate policy, or None when this compiler cannot handle the sentence."""
