"""Creating rules. A policy is only stored once the verifier has passed it (SRS §4.1: fail -> never trusted)."""
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.library import STARTER
from app.models import Rule
from app.verifier import fixtures as fixture_gen
from app.verifier.report import VerifyReport
from app.verifier.runner import verify


class VerificationFailed(Exception):
    def __init__(self, report: VerifyReport):
        super().__init__(report.error or 'Policy did not pass its fixtures.')
        self.report = report


def create_rule(session: Session, english: str, policy_yaml: str, intent, region: str,
                created_at: datetime | None = None) -> Rule:
    report = verify(policy_yaml, fixture_gen.generate(intent), region)
    if not report.passed:
        raise VerificationFailed(report)
    rule = Rule(english=english, policy_yaml=policy_yaml.strip() + '\n', intent=intent.model_dump(), verified=True,
                created_at=created_at or datetime.now(timezone.utc))
    session.add(rule)
    session.commit()
    return rule


# The starter rulebook is dated to when the demo account's history begins, so it is past the
# provisional window and carries real quality scores. A rule the user writes is dated now.
STARTER_AGE = timedelta(days=34)


def seed_starter_rules(session: Session, region: str) -> int:
    """Give a fresh install the default rulebook, so a new user gets value in the first five minutes."""
    if session.scalar(select(Rule.id).limit(1)):
        return 0
    seeded_at = datetime.now(timezone.utc) - STARTER_AGE
    for template in STARTER:
        create_rule(session, template.english, template.policy_yaml, template.intent, region, created_at=seeded_at)
    return len(STARTER)
