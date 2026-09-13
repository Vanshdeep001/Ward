from datetime import datetime, timezone

from app.engine.custodian import load_policies
from app.inventory.store import Snapshot
from app.simulator.dryrun import simulate_policy
from app.simulator.timetravel import replay

REGION = 'ap-south-1'

GPU_6H = '''
policies:
  - name: gpu-max-6h
    resource: aws.ec2
    filters:
      - State.Name: running
      - type: value
        key: InstanceType
        op: regex
        value: "^(p|g|inf)[0-9].*"
      - type: instance-age
        op: greater-than
        hours: 6
'''


def one(policy_yaml):
    return load_policies(policy_yaml, REGION)[0]


def test_gpu_rule_matches_the_two_long_running_gpus(sample):
    sim = simulate_policy(one(GPU_6H), sample.latest())
    assert sim.population == 14
    assert {m.id for m in sim.matched} == {'i-0a1f2', 'i-0b3d4'}
    assert sim.breadth == 'normal'
    assert sim.zero_reason is None
    ml = next(m for m in sim.matched if m.id == 'i-0a1f2')
    assert ml.name == 'ml-training' and ml.detail == 'g5.xlarge'
    assert 30 <= ml.running_hours <= 32
    assert sim.cost_per_day == round(66.05 * 24 + 101.14 * 24, 2)


def test_funnel_counts_survivors_after_each_filter(sample):
    sim = simulate_policy(one(GPU_6H), sample.latest())
    assert [s.remaining for s in sim.funnel] == [11, 3, 2]


def test_zero_matches_names_the_filter_that_eliminated_everything(sample):
    sim = simulate_policy(one(GPU_6H.replace('hours: 6', 'hours: 48')), sample.latest())
    assert sim.matched == []
    assert sim.breadth == 'none'
    assert sim.zero_reason.startswith('14 EC2 instances exist; 3 reached the filter')
    assert '48 hours' in sim.zero_reason


def test_zero_matches_when_the_resource_type_does_not_exist():
    empty = Snapshot(taken_at=datetime.now(timezone.utc), resources={})
    sim = simulate_policy(one('policies:\n  - name: nat\n    resource: aws.nat-gateway\n'), empty)
    assert sim.zero_reason == 'You have no NAT Gateways, so there is nothing to flag.'


def test_rule_matching_most_of_the_account_is_marked_broad(sample):
    sim = simulate_policy(one('policies:\n  - name: running\n    resource: aws.ec2\n    filters:\n      - State.Name: running\n'), sample.latest())
    assert len(sim.matched) == 11
    assert sim.breadth == 'broad'


def test_history_counts_each_violation_once(sample):
    history = replay([one(GPU_6H)], sample.history(30), days=30)
    # 2 sessions still running + 6 past sessions longer than 6 hours; the 4h and 5.5h sessions never qualify.
    assert history.fires == 8
    assert 'i-0c7e1' not in {e.resource_id for e in history.events}
    assert history.events[0].at > history.events[-1].at
    assert history.alerts_per_week == round(8 / 30 * 7, 1)
    assert history.quiet_days == 22
    assert history.caveats == []


def test_history_is_empty_for_a_rule_that_never_matched(sample):
    history = replay([one(GPU_6H.replace('hours: 6', 'hours: 72'))], sample.history(30), days=30)
    assert history.fires == 0
    assert history.quiet_days == 30


def test_wall_clock_filters_are_flagged_as_approximate(sample):
    offhours = 'policies:\n  - name: wk\n    resource: aws.ec2\n    filters:\n      - type: offhour\n        weekends: true\n        default_tz: Asia/Kolkata\n'
    history = replay([one(offhours)], sample.history(2), days=2)
    assert any('approximate' in c for c in history.caveats)
