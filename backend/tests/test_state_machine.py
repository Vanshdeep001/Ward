from datetime import datetime, timedelta, timezone

import pytest

from app.watcher.state import Event, Observation, State, step, worst
from app.watcher.warnings import warning_variant

NOW = datetime(2026, 9, 15, 12, tzinfo=timezone.utc)
CLEAR, CLOSE, BREACH = Observation(False, False), Observation(False, True), Observation(True, True)


@pytest.mark.parametrize('current,seen,expected', [
    (None, CLEAR, (State.DISCOVERED, None)),
    (None, CLOSE, (State.WARNING, Event.WARNING)),
    (None, BREACH, (State.ALERT, Event.ALERT)),
    (State.DISCOVERED, CLEAR, (State.WATCHED, None)),
    (State.WATCHED, CLEAR, (State.WATCHED, None)),
    (State.WATCHED, CLOSE, (State.WARNING, Event.WARNING)),
    (State.WARNING, CLOSE, (State.WARNING, None)),
    (State.WARNING, BREACH, (State.ALERT, Event.ALERT)),
    (State.ALERT, BREACH, (State.ALERT, None)),
    (State.ALERT, CLOSE, (State.WARNING, Event.RESOLVED)),
    (State.ALERT, CLEAR, (State.RESOLVED, Event.RESOLVED)),
    (State.WARNING, CLEAR, (State.RESOLVED, Event.RESOLVED)),
    (State.RESOLVED, CLEAR, (State.WATCHED, None)),
    (State.RESOLVED, BREACH, (State.ALERT, Event.ALERT)),
])
def test_transitions(current, seen, expected):
    assert step(current, seen, NOW) == expected


def test_staying_in_alert_is_silent():
    state, event = State.ALERT, None
    for _ in range(96):  # a day of 15-minute sweeps
        state, event = step(state, BREACH, NOW)
        assert event is None


def test_snoozed_resource_is_silent_until_the_timer_expires():
    until = NOW + timedelta(hours=4)
    assert step(State.SNOOZED, BREACH, NOW, until) == (State.SNOOZED, None)
    assert step(State.SNOOZED, BREACH, until, until) == (State.ALERT, Event.ALERT)


def test_snoozed_problem_that_fixes_itself_resolves():
    assert step(State.SNOOZED, CLEAR, NOW, NOW + timedelta(hours=4)) == (State.RESOLVED, Event.RESOLVED)


def test_worst_state_wins():
    assert worst([State.WATCHED, State.ALERT, State.SNOOZED]) is State.ALERT
    assert worst([]) is State.DISCOVERED


def test_warning_variant_scales_age_thresholds():
    variant = warning_variant('''
policies:
  - name: gpu
    resource: aws.ec2
    filters:
      - type: instance-age
        op: greater-than
        hours: 6
      - or:
          - type: value
            key: CreateTime
            value_type: age
            op: greater-than
            value: 8
''')
    assert 'hours: 4.5' in variant
    assert 'value: 6.0' in variant
    assert 'name: gpu-warning' in variant


def test_rules_without_an_age_threshold_have_no_warning_stage():
    assert warning_variant('policies:\n  - name: p\n    resource: aws.rds\n    filters:\n      - PubliclyAccessible: true\n') is None
