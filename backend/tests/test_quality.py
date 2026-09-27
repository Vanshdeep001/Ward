"""Rule quality scoring (SRS §22.1) — judged on what a rule has done, not how it is worded."""
from datetime import datetime, timedelta, timezone

from app.guardian import quality
from app.library import STARTER
from tests.conftest import REGION


class FakeAlert:
    def __init__(self, created_at, resolved_at=None, cost_per_day=1200.0):
        self.created_at, self.resolved_at, self.cost_per_day = created_at, resolved_at, cost_per_day


class FakeRule:
    def __init__(self, template, *, age_days=40, verified=True, alerts=()):
        self.english = template.english
        self.policy_yaml = template.policy_yaml
        self.intent = template.intent.model_dump()
        self.verified = verified
        self.created_at = datetime.now(timezone.utc) - timedelta(days=age_days)
        self.alerts = list(alerts)


GPU_RULE = STARTER[0]
TAG_RULE = STARTER[1]


def test_a_new_rule_stays_provisional(sample):
    rule = FakeRule(GPU_RULE, age_days=3)
    assert quality.score(rule, sample.latest(), REGION) is None, 'three days is not enough history to score'


def test_a_scored_rule_totals_its_dimensions(sample):
    scored = quality.score(FakeRule(GPU_RULE), sample.latest(), REGION)

    assert 0 < scored['quality'] <= 100
    assert scored['quality'] == sum(d['score'] for d in scored['breakdown'].values())
    assert set(scored['breakdown']) == set(quality.MAXIMA)
    assert all(d['note'] for d in scored['breakdown'].values()), 'every dimension explains itself'


def test_ignored_alerts_sink_the_signal_rate(sample):
    now = datetime.now(timezone.utc)
    ignored = [FakeAlert(now - timedelta(days=i)) for i in range(1, 9)]
    acted = [FakeAlert(now - timedelta(days=i), now - timedelta(days=i) + timedelta(minutes=20)) for i in range(1, 9)]

    noisy = quality.score(FakeRule(GPU_RULE, alerts=ignored), sample.latest(), REGION)
    useful = quality.score(FakeRule(GPU_RULE, alerts=acted), sample.latest(), REGION)

    assert noisy['breakdown']['signalRate']['score'] < useful['breakdown']['signalRate']['score']
    assert 'ignore' in noisy['breakdown']['signalRate']['note'].lower()
    assert noisy['quality'] < useful['quality']


def test_a_broad_rule_scores_worse_on_specificity_than_a_narrow_one(sample):
    narrow = quality.score(FakeRule(GPU_RULE), sample.latest(), REGION)  # GPUs only
    broad = quality.score(FakeRule(TAG_RULE), sample.latest(), REGION)  # every untagged instance

    assert narrow['breakdown']['specificity']['score'] > broad['breakdown']['specificity']['score']


def test_an_unverified_rule_is_penalised(sample):
    verified = quality.score(FakeRule(GPU_RULE), sample.latest(), REGION)
    unverified = quality.score(FakeRule(GPU_RULE, verified=False), sample.latest(), REGION)

    assert unverified['breakdown']['verifiability']['score'] < verified['breakdown']['verifiability']['score']


def test_the_tip_names_the_weakest_dimension_and_what_it_is_worth(sample):
    now = datetime.now(timezone.utc)
    ignored = [FakeAlert(now - timedelta(days=i)) for i in range(1, 12)]

    scored = quality.score(FakeRule(GPU_RULE, alerts=ignored), sample.latest(), REGION)

    assert scored['improvementTip'].endswith(').')
    assert '+' in scored['improvementTip']
    assert 'archive' in scored['improvementTip'].lower() or 'threshold' in scored['improvementTip'].lower()
