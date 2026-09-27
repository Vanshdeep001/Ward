"""The compile pipeline: English → (clarify) → policy → verify → simulate.

The guarantee under test is that nothing reaches the user as 'compiled' unless the verifier passed it
against fixtures built from the intent — so a wrong policy can never grade itself.
"""
import pytest

from app.compiler import clarify
from app.compiler.service import compile_rule
from app.compiler.templates import TemplateCompiler
from app.verifier import fixtures as fixture_gen
from app.verifier.runner import verify
from tests.conftest import REGION

RULEBOOK = [
    ('No GPU instance runs more than 6 hours', 'ec2-runtime'),
    ('Only t3.micro and t2.micro instances are allowed', 'instance-type'),
    # Phrasings the fine-tuning corpus exposed as broken, each kept as a regression test.
    ('Instances outside production must not run longer than 8 hours', 'ec2-runtime'),
    ('Clean up storage left unattached for 90 days', 'ebs-unattached'),
    ('Every volume must have a CostCentre tag', 'require-tag'),
    ('GPU instances must not run longer than an hour', 'ec2-runtime'),
    ('Nothing other than t3.micro may run', 'instance-type'),
    ('Nothing should expose SSH on port 22 publicly', 'sg-open-port'),
    ('We only operate in ap-southeast-1', 'region'),
    ('Kill anything running longer than 90 minutes', 'ec2-runtime'),
    ('Nothing runs longer than 6 hours unattended', 'ec2-runtime'),
    ('No GPU instance without an expiry tag', 'require-tag'),
    ('Flag any resource with no Owner tag', 'require-tag'),
    ('Flag EBS volumes unattached for more than 7 days', 'ebs-unattached'),
    ('Stay inside the free tier', 'ebs-unattached'),
    ('No database may be publicly accessible', 'rds-public'),
    ('SSH is open to the entire internet', 'sg-open-port'),
    ('No resources outside ap-south-1', 'region'),
]


@pytest.mark.parametrize('english,kind', RULEBOOK)
def test_the_rulebook_compiles_and_verifies(english, kind, sample):
    result = compile_rule(english, sample, REGION)

    assert result['status'] == 'compiled', result.get('verifier', {}).get('error')
    assert result['kind'] == kind
    assert result['verifier']['passed'] is True
    assert result['simulation']['policies'], 'a compiled rule should simulate against the account'


@pytest.mark.parametrize('english,_kind', RULEBOOK)
def test_every_compiled_policy_survives_its_own_fixtures(english, _kind):
    """Belt and braces: re-run the verifier outside the pipeline, in case the pipeline lies."""
    draft = TemplateCompiler().compile(english)
    report = verify(draft.policy_yaml, fixture_gen.generate(draft.intent), REGION)

    assert report.passed
    assert report.rates.positive_pass == 1.0 and report.rates.negative_pass == 1.0


def test_a_vague_rule_asks_instead_of_guessing(sample):
    result = compile_rule("Don't let anything expensive run too long", sample, REGION)

    assert result['status'] == 'needs-clarification'
    assert {q['term'] for q in result['questions']} == {'expensive', 'too long'}
    for question in result['questions']:
        assert len(question['options']) >= 2
        # Each option is priced against the real account, so the choice is made against consequences.
        assert all(o['matches'] >= 0 for o in question['options'])
        assert any(o['matches'] > 0 for o in question['options'])


def test_answering_the_questions_compiles_the_rewritten_sentence(sample):
    result = compile_rule(
        "Don't let anything expensive run too long", sample, REGION,
        skip_clarify=True,
    )
    assert result['status'] == 'failed'  # unresolved, it is not a policy

    rewritten = clarify.apply_choices(
        "Don't let anything expensive run too long",
        {'expensive': 'GPU', 'too long': 'more than 6 hours'},
    )
    assert 'GPU' in rewritten and '6 hours' in rewritten

    resolved = compile_rule(rewritten, sample, REGION, skip_clarify=True)
    assert resolved['status'] == 'compiled'
    assert resolved['params']['gpu_only'] is True and resolved['params']['hours'] == 6


def test_an_unmappable_sentence_fails_as_a_result_not_an_error(sample):
    result = compile_rule('make the cloud cheaper please', sample, REGION)

    assert result['status'] == 'failed'
    assert result['verifier']['passed'] is False
    assert 'Name a resource type' in result['verifier']['error']


def test_thresholds_are_read_from_the_sentence(sample):
    for hours in (2, 6, 24):
        result = compile_rule(f'No GPU instance runs more than {hours} hours', sample, REGION)
        assert result['params']['hours'] == hours
        assert f'hours: {hours}' in result['yaml']


def test_compiled_rules_state_what_ward_assumed(sample):
    result = compile_rule('No GPU instance runs more than 6 hours', sample, REGION)
    assumptions = ' '.join(result['assumptions']).lower()

    assert 'stopped' in assumptions  # the running-state decision
    assert 'gpu' in assumptions  # what "GPU" was taken to mean


def test_the_compiler_is_swappable(sample):
    """The pipeline talks to the protocol, so the fine-tuned model can take over later (SRS §9)."""

    class NeverCompiles:
        name = 'stub'

        def compile(self, english):
            return None

    result = compile_rule('No GPU instance runs more than 6 hours', sample, REGION, compiler=NeverCompiles())
    assert result['status'] == 'failed'
    assert result['compiler'] == 'stub'
