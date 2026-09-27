from datetime import datetime, timedelta, timezone

import httpx
import pytest
from sqlalchemy import select

from app.inventory import shapes
from app.inventory.store import Snapshot
from app.library import STARTER
from app.models import Alert, Notification, Watch
from app.notify.channels import LogChannel, TelegramChannel
from app.rules_service import VerificationFailed, create_rule, seed_starter_rules
from app.verifier.intents import Ec2RuntimeIntent
from app.watcher.evaluator import snooze, sweep

REGION = 'ap-south-1'
T0 = datetime.now(timezone.utc).replace(microsecond=0) - timedelta(hours=12)
LAUNCH = T0 - timedelta(hours=2)
GPU = STARTER[0]


class Recorder:
    def __init__(self):
        self.sent = []

    def send(self, text):
        self.sent.append(text)
        return LogChannel().send(text)


def at(hours: float, running: bool = True) -> tuple[Snapshot, datetime]:
    """The account `hours` after T0, with one GPU instance launched two hours before T0."""
    when = T0 + timedelta(hours=hours)
    instance = shapes.ec2('i-gpu', 'g5.xlarge', launched=LAUNCH, running=running, tags={'Name': 'ml-training'})
    return Snapshot(taken_at=when, resources={'aws.ec2': [instance]}), when


def run(session, channel, hours, running=True):
    snapshot, when = at(hours, running)
    return sweep(session, snapshot, channel, when, REGION)


def state(session):
    return session.scalars(select(Watch.state)).one()


@pytest.fixture
def gpu_rule(session):
    return create_rule(session, GPU.english, GPU.policy_yaml, GPU.intent, REGION)


def test_resource_walks_the_state_machine_and_only_transitions_notify(session, gpu_rule):
    ch = Recorder()

    run(session, ch, 0)  # 2h old
    assert state(session) == 'discovered' and ch.sent == []

    run(session, ch, 3)  # 5h old: past 75% of the 6h limit
    assert state(session) == 'warning'
    assert len(ch.sent) == 1 and ch.sent[0].startswith('⚠️ ml-training (g5.xlarge), running 5h')

    run(session, ch, 5)  # 7h old
    assert state(session) == 'alert'
    assert len(ch.sent) == 2 and 'Broke your rule “No GPU instance runs more than 6 hours”' in ch.sent[1]
    assert 'It costs ₹1,585/day' in ch.sent[1]

    for h in (5.25, 5.5, 5.75):  # still over the limit
        run(session, ch, h)
    assert len(ch.sent) == 2

    alerts = session.scalars(select(Alert).order_by(Alert.created_at)).all()
    assert [(a.level, a.status) for a in alerts] == [('warning', 'resolved'), ('alert', 'open')]

    run(session, ch, 6, running=False)  # stopped
    assert state(session) == 'resolved'
    assert session.scalars(select(Alert).where(Alert.level == 'alert')).one().status == 'resolved'
    assert len(ch.sent) == 2  # resolution is logged, not notified


def test_snooze_silences_until_expiry_then_realerts(session, gpu_rule):
    ch = Recorder()
    run(session, ch, 5)
    alert = session.scalars(select(Alert)).one()
    snooze(session, alert, hours=1, now=T0 + timedelta(hours=5))
    assert state(session) == 'snoozed'

    run(session, ch, 5.5)
    assert len(ch.sent) == 1 and state(session) == 'snoozed'

    run(session, ch, 6.25)
    assert state(session) == 'alert'
    assert len(ch.sent) == 2 and 'Still breaking' in ch.sent[1]
    assert session.scalars(select(Alert)).one().status == 'open'  # the same alert, reopened


def test_resource_that_disappears_is_resolved(session, gpu_rule):
    ch = Recorder()
    run(session, ch, 5)
    sweep(session, Snapshot(taken_at=T0 + timedelta(hours=6), resources={'aws.ec2': []}), ch, T0 + timedelta(hours=6), REGION)
    assert state(session) == 'resolved'
    assert session.scalars(select(Alert)).one().status == 'resolved'


def test_paused_rules_are_not_evaluated(session, gpu_rule):
    gpu_rule.status = 'paused'
    session.commit()
    result = run(session, Recorder(), 5)
    assert result.rules == 0 and result.evaluated == 0


def test_every_notification_is_recorded(session, gpu_rule):
    run(session, LogChannel(), 5)
    [note] = session.scalars(select(Notification)).all()
    assert note.channel == 'log' and note.delivered is False
    assert note.alert_id == session.scalars(select(Alert.id)).one()


def test_unverified_policy_is_never_stored(session):
    twelve = GPU.policy_yaml.replace('hours: 6', 'hours: 12')
    with pytest.raises(VerificationFailed) as err:
        create_rule(session, 'No GPU over 6 hours', twelve, Ec2RuntimeIntent(hours=6, gpu_only=True), REGION)
    assert not err.value.report.passed
    assert session.scalars(select(Watch)).all() == []


def test_starter_rules_seed_once_and_flag_the_sample_account(session, sample):
    assert seed_starter_rules(session, REGION) == len(STARTER)
    assert seed_starter_rules(session, REGION) == 0

    ch = Recorder()
    result = sweep(session, sample.latest(), ch, datetime.now(timezone.utc), REGION)
    assert result.errors == []
    flagged = {(a.rule.english, a.resource_id) for a in session.scalars(select(Alert).where(Alert.level == 'alert'))}
    assert flagged == {
        ('No GPU instance runs more than 6 hours', 'i-0a1f2'),
        ('No GPU instance runs more than 6 hours', 'i-0b3d4'),
        *(('Flag any EC2 instance with no Owner tag', i) for i in ('i-0a1f2', 'i-01a2b', 'i-04g5h', 'i-05i6j', 'i-08o9p')),
        *(('Flag EBS volumes unattached for more than 7 days', v) for v in ('vol-01', 'vol-02', 'vol-03')),
        ('No database may be publicly accessible', 'hackathon-db'),
        ('No security group may allow SSH from the internet', 'sg-0ssh'),
    }
    # arjun-finetune has run 2h of its 6h limit: watched, not warned.
    assert session.scalars(select(Watch.state).where(Watch.resource_id == 'i-0c7e1', Watch.rule_id == session.scalars(
        select(Alert.rule_id).where(Alert.resource_id == 'i-0b3d4')).first())).one() == 'discovered'
    assert len(ch.sent) == len(flagged)

    second = sweep(session, sample.latest(), ch, datetime.now(timezone.utc), REGION)
    assert second.notifications == 0


def test_telegram_channel_reports_delivery():
    ok = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, json={'ok': True})))
    bad = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(401, json={'ok': False, 'description': 'Unauthorized'})))
    assert TelegramChannel('t', 'c', ok).send('hi').delivered is True
    failed = TelegramChannel('t', 'c', bad).send('hi')
    assert failed.delivered is False and failed.error == 'Unauthorized'
