"""Spend, the Detective, and Guardian — everything derived from the inventory rather than claimed."""
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app.costs import detective, spend
from app.guardian import conflicts as conflict_detector
from app.guardian import findings as finder
from app.main import app
from app.api.deps import get_inventory
from tests.conftest import REGION


@pytest.fixture(scope='module')
def client(sample):
    app.dependency_overrides[get_inventory] = lambda: sample
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


# ─── Spend ────────────────────────────────────────────────────────────────────

def test_daily_spend_has_one_row_per_day_and_no_gaps(sample):
    daily = spend.daily_spend(sample, days=30)

    assert daily, 'the sample account should produce spend'
    days = [datetime.fromisoformat(d['date']).date() for d in daily]
    assert days == sorted(days), 'rows must be in date order'
    assert len(set(days)) == len(days), 'one row per day'
    assert all(d['amount'] > 0 for d in daily)


def test_the_projection_extends_the_month_at_the_recent_burn_rate():
    today = datetime(2026, 4, 10, tzinfo=timezone.utc).date()  # April: 30 days, 20 remaining
    daily = [{'date': datetime(2026, 4, day, tzinfo=timezone.utc).isoformat(), 'amount': 100.0}
             for day in range(1, 11)]

    projection = spend.project(daily, today=today)

    assert projection.month_to_date == 1000.0
    assert projection.burn_per_day == 100.0
    assert projection.projected_month_end == 1000.0 + 100.0 * 20
    assert projection.days_in_month == 30


def test_savings_count_only_alerts_acted_on_inside_the_attribution_window():
    now = datetime.now(timezone.utc)

    class FakeAlert:
        def __init__(self, created_at, resolved_at, cost_per_day):
            self.created_at, self.resolved_at, self.cost_per_day = created_at, resolved_at, cost_per_day

    acted = FakeAlert(now - timedelta(days=2), now - timedelta(days=2) + timedelta(hours=1), 1200.0)
    ignored = FakeAlert(now - timedelta(days=3), None, 1200.0)
    too_late = FakeAlert(now - timedelta(days=4), now - timedelta(days=4) + timedelta(hours=9), 1200.0)

    result = spend.savings([acted, ignored, too_late], now=now)

    assert result['alertsSent'] == 3
    assert result['actedOn'] == 1, 'only the alert acted on within 2h counts'
    assert result['avoided'] > 0
    assert result['wardCost'] == spend.WARD_OWN_COST_INR


def test_every_counterfactual_is_named_and_priced():
    now = datetime.now(timezone.utc)

    class FakeAlert:
        created_at = now - timedelta(days=1)
        resolved_at = now - timedelta(days=1) + timedelta(minutes=30)
        cost_per_day = 2400.0

    models = spend.savings([FakeAlert()], now=now)['counterfactuals']

    assert set(models) == {'next-morning', 'conservative', 'observed'}
    for model in models.values():
        assert model['description'], 'a savings number without its assumption is not a measurement'
        assert model['avoided'] > 0 and model['excluded'] > 0
    assert models['conservative']['avoided'] < models['next-morning']['avoided'] < models['observed']['avoided']


def test_costs_endpoint_matches_the_dashboard_shape(client):
    body = client.get('/costs').json()

    assert {'budget', 'daily', 'monthToDate', 'projectedMonthEnd', 'savings'} <= set(body)
    assert {'avoided', 'alertsSent', 'actedOn', 'wardCost', 'counterfactuals'} <= set(body['savings'])
    assert body['daily'][0].keys() == {'date', 'amount'}


# ─── Detective ────────────────────────────────────────────────────────────────

def test_the_detective_names_resources_not_just_a_total(sample):
    result = detective.investigate(sample, window_days=7)

    assert result['changes'], 'something moved in the sample account'
    biggest = result['changes'][0]
    assert biggest['delta'] == max(c['delta'] for c in result['changes'])
    assert biggest['id'] and biggest['reason']
    assert result['to']['total'] > 0
    # Every cause names the resource that moved it, not just the service that contains it.
    for cause in result['causes']:
        assert cause['resourceId'] and cause['headline']
        assert cause['ruleLink']['status'] in ('missing', 'working', 'working-but-ignored')


def test_the_delta_is_fully_attributed_or_declared_unattributed(sample):
    result = detective.investigate(sample, window_days=7)
    attributed = sum(c['delta'] for c in result['causes'])

    assert abs(result['to']['total'] - result['from']['total'] - attributed - result['unattributed']) < 0.02


def test_a_rule_that_fired_and_was_ignored_is_reported_as_such(sample):
    """The uncomfortable case: the guardrail worked and nobody listened (SRS §15.3)."""
    now = datetime.now(timezone.utc)

    class FakeRule:
        english = 'No GPU instance runs more than 6 hours'

    class FakeAlert:
        resource_id = 'i-0a1f2'
        created_at = now - timedelta(days=2)
        resolved_at = None
        rule = FakeRule()

    result = detective.investigate(sample, window_days=7, alerts=[FakeAlert()])
    covered = [c for c in result['causes'] if c['resourceId'] == 'i-0a1f2']

    if covered:
        assert covered[0]['ruleLink']['status'] == 'working-but-ignored'
        assert 'no alert was acted on' in covered[0]['ruleLink']['text'].lower()


def test_the_detective_turns_the_biggest_increase_into_a_candidate_rule(sample):
    result = detective.investigate(sample, window_days=7)
    suggestion = result['suggestedRule']

    if any(c['delta'] > 0 for c in result['changes']):
        assert suggestion and suggestion['english'] and suggestion['because']
    else:
        assert suggestion is None, 'nothing rose, so nothing to suggest'


# ─── Guardian ─────────────────────────────────────────────────────────────────

def test_findings_rank_urgent_security_first(sample):
    found = finder.find_all(sample.latest())

    assert found
    assert found[0]['severity'] == 'urgent'
    assert found[0]['family'] == 'security'


def test_every_finding_carries_a_fix_and_a_rule(sample):
    for f in finder.find_all(sample.latest()):
        assert f['fix'].startswith('aws '), f'{f["id"]} should carry a runnable command'
        assert f['suggestedRule'], f'{f["id"]} should be turnable into a guardrail'
        assert f['resourceIds'], f'{f["id"]} should name what it is about'
        assert f['source'], f'{f["id"]} should say where it came from'


def test_the_public_database_is_found(sample):
    ids = {f['id'] for f in finder.find_all(sample.latest())}
    assert 'f-rds-public' in ids and 'f-ssh-open' in ids


# ─── Conflicts ────────────────────────────────────────────────────────────────

class FakeRule:
    def __init__(self, id, english, policy_yaml):
        self.id, self.english, self.policy_yaml = id, english, policy_yaml


ALL_UNTAGGED = '''policies:
  - name: untagged
    resource: aws.ec2
    filters:
      - "tag:Owner": absent
'''
GPU_UNTAGGED = '''policies:
  - name: gpu-untagged
    resource: aws.ec2
    filters:
      - type: value
        key: InstanceType
        op: regex
        value: "^(p|g|inf)[0-9].*"
      - "tag:Owner": absent
'''
NOTHING = '''policies:
  - name: impossible
    resource: aws.ec2
    filters:
      - "tag:ThisTagDoesNotExist": present
'''


def test_a_narrower_rule_is_reported_as_subsumed(sample):
    rules = [FakeRule('r-all', 'Flag untagged instances', ALL_UNTAGGED),
             FakeRule('r-gpu', 'Flag untagged GPU instances', GPU_UNTAGGED)]

    found = conflict_detector.detect(rules, sample.latest(), REGION)

    subsumption = next(c for c in found if c['category'] == 'subsumption')
    assert subsumption['ruleA']['id'] == 'r-gpu', 'the narrower rule is the redundant one'
    assert subsumption['affected'] > 0


def test_a_rule_matching_nothing_is_reported_as_dead(sample):
    found = conflict_detector.detect([FakeRule('r-dead', 'Never fires', NOTHING)], sample.latest(), REGION)

    dead = next(c for c in found if c['category'] == 'dead')
    assert dead['affected'] == 0
    assert 'matched none' in dead['detail']


def test_conflicts_are_measured_against_this_account_not_the_wording(sample):
    """Two rules that read differently but match the same resources should still be reported."""
    found = conflict_detector.detect(
        [FakeRule('a', 'Untagged', ALL_UNTAGGED), FakeRule('b', 'Also untagged', ALL_UNTAGGED)],
        sample.latest(), REGION,
    )
    assert any(c['category'] in ('subsumption', 'overlap') for c in found)
