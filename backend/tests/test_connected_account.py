"""After an account connects: the sweep is recorded, spend comes from the real bill, and the
Detective is honest about how little history it has. Nothing here reaches AWS."""
from datetime import date, datetime, timedelta, timezone

import pytest

from app.costs import detective, explorer
from app.crypto import encrypt
from app.inventory.store import Snapshot
from app.models import Account
from app.notify.channels import Channel
from app.watcher.run import active_account, run_sweep
from tests.conftest import REGION


class StubCe:
    """Cost Explorer's shape: one ResultsByTime row per day, amounts as strings, a Unit."""

    def __init__(self, unit='USD', amount='2.50', fail=None):
        self.unit, self.amount, self.fail, self.calls = unit, amount, fail, 0

    def get_cost_and_usage(self, TimePeriod, Granularity, Metrics, NextPageToken=None):  # noqa: N803
        self.calls += 1
        if self.fail:
            raise RuntimeError(self.fail)
        start, end = date.fromisoformat(TimePeriod['Start']), date.fromisoformat(TimePeriod['End'])
        days = [(start + timedelta(days=i)) for i in range((end - start).days)]
        return {'ResultsByTime': [
            {'TimePeriod': {'Start': d.isoformat(), 'End': (d + timedelta(days=1)).isoformat()},
             'Total': {'UnblendedCost': {'Amount': self.amount, 'Unit': self.unit}}}
            for d in days
        ]}


class StubSession:
    def __init__(self, ce):
        self.ce = ce

    def client(self, service, region_name=None):
        assert service == 'ce' and region_name == 'us-east-1', 'Cost Explorer only answers in us-east-1'
        return self.ce


@pytest.fixture(autouse=True)
def fresh_cache():
    explorer._cache.clear()
    yield
    explorer._cache.clear()


# ─── Cost Explorer ────────────────────────────────────────────────────────────

def test_usd_bills_are_converted_to_rupees():
    rows, unit = explorer.daily_spend(StubSession(StubCe('USD', '2.50')), 'acct_1', days=10, usd_to_inr=80)

    assert unit == 'USD'
    assert len(rows) == 10
    assert all(r['amount'] == 200.0 for r in rows)  # $2.50 × ₹80


def test_an_inr_bill_is_not_converted_twice():
    rows, unit = explorer.daily_spend(StubSession(StubCe('INR', '150')), 'acct_2', days=3, usd_to_inr=80)
    assert unit == 'INR' and rows[0]['amount'] == 150.0


def test_results_are_cached_because_every_call_is_billed():
    ce = StubCe()
    session = StubSession(ce)
    explorer.daily_spend(session, 'acct_3', days=5, usd_to_inr=80)
    explorer.daily_spend(session, 'acct_3', days=5, usd_to_inr=80)
    assert ce.calls == 1


def test_a_disabled_cost_explorer_says_what_to_do():
    with pytest.raises(explorer.CostExplorerUnavailable, match='enable it in Billing'):
        explorer.daily_spend(StubSession(StubCe(fail='DataUnavailableException')), 'acct_4', usd_to_inr=80)


def test_missing_permission_points_at_the_template():
    with pytest.raises(explorer.CostExplorerUnavailable, match='redeploy the stack'):
        explorer.daily_spend(StubSession(StubCe(fail='AccessDeniedException')), 'acct_5', usd_to_inr=80)


# ─── Recording the sweep ──────────────────────────────────────────────────────

class NullChannel(Channel):
    def send(self, text):
        from app.notify.channels import Delivery
        return Delivery(channel='log', delivered=False, error=None)


def _connected(session):
    account = Account(label='x', region=REGION, budget_inr=1000, external_id_enc=encrypt('e'),
                      role_arn='arn:aws:iam::123456789012:role/WardReadOnly', status='connected',
                      created_at=datetime.now(timezone.utc), connected_at=datetime.now(timezone.utc))
    session.add(account)
    session.commit()
    return account


def test_a_sweep_records_when_it_ran(session, sample):
    account = _connected(session)
    now = datetime.now(timezone.utc)

    run_sweep(session, sample, NullChannel(), now, REGION)

    assert active_account(session).id == account.id
    assert account.last_sweep_at == now
    assert account.last_error is None


def test_a_failed_sweep_is_written_down_where_the_user_can_see_it(session):
    account = _connected(session)

    class Broken:
        def latest(self):
            raise RuntimeError('role was deleted')

    with pytest.raises(RuntimeError):
        run_sweep(session, Broken(), NullChannel(), datetime.now(timezone.utc), REGION)
    assert 'role was deleted' in account.last_error


# ─── The Detective, on a fresh account ────────────────────────────────────────

def test_the_detective_does_not_call_everything_new_on_day_one():
    now = datetime.now(timezone.utc)
    one_day = Snapshot(taken_at=now - timedelta(hours=5), resources={'aws.ec2': []})

    class OneDay:
        def history(self, days):
            return [one_day]

    report = detective.investigate(OneDay(), window_days=7, now=now)

    assert report['insufficientHistory'] is True
    assert report['causes'] == []
    assert '5 hours' in report['note'] and '14 days' in report['note']
