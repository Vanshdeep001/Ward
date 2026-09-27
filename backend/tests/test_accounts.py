"""Connecting an AWS account. STS is stubbed: no test may reach AWS, and none needs to."""
import re
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_connection, get_database, get_inventory
from app.aws.connection import AwsConnection, ConnectionError_, trustable
from app.crypto import decrypt, encrypt
from app.main import app
from app.models import Account

ROLE = 'arn:aws:iam::123456789012:role/WardReadOnly'


class StubSts:
    """Accepts one ExternalId and refuses everything else, the way a real trust policy does."""

    def __init__(self, expected_external_id=None, expires_in=timedelta(hours=1),
                 identity_arn='arn:aws:iam::999999999999:user/ward-dev'):
        self.expected = expected_external_id
        self.expires_in = expires_in
        self.identity_arn = identity_arn  # None models a backend with no AWS credentials at all
        self.calls = []

    def get_caller_identity(self):
        if self.identity_arn is None:
            raise RuntimeError('NoCredentialsError')
        return {'Arn': self.identity_arn, 'Account': self.identity_arn.split(':')[4]}

    def assume_role(self, RoleArn, ExternalId, RoleSessionName, DurationSeconds=3600):  # noqa: N803 (boto3 casing)
        self.calls.append((RoleArn, ExternalId, RoleSessionName))
        if self.expected is not None and ExternalId != self.expected:
            raise RuntimeError('AccessDenied')
        return {
            'Credentials': {
                'AccessKeyId': 'ASIA_TEST', 'SecretAccessKey': 'secret', 'SessionToken': 'token',
                'Expiration': datetime.now(timezone.utc) + self.expires_in,
            }
        }


class StubSession:
    def __init__(self, account_id='123456789012', **_):
        self._account_id = account_id

    def client(self, service):
        assert service == 'sts'
        return self

    def get_caller_identity(self):
        return {'Account': self._account_id}


def stub_connection(sts=None, **kwargs):
    sts = sts or StubSts()
    return AwsConnection(sts_factory=lambda: sts, session_factory=lambda creds, region: StubSession(), **kwargs)


@pytest.fixture
def client(sample):
    sts = StubSts()
    app.dependency_overrides[get_inventory] = lambda: sample
    app.dependency_overrides[get_connection] = lambda: stub_connection(sts)
    with TestClient(app) as c:
        c.sts = sts
        yield c
    app.dependency_overrides.clear()
    # The test database is shared in memory: a connected account left behind would make every later
    # test's /costs call try to assume a real role.
    with get_database().sessions() as s:
        s.query(Account).delete()
        s.commit()


def create(client, **overrides):
    body = {'label': 'Lab account', 'budget_inr': 12000, **overrides}
    res = client.post('/accounts', json=body)
    assert res.status_code == 201, res.text
    return res.json()


def test_a_new_account_starts_pending_with_no_role(client):
    account = create(client)
    assert account['status'] == 'pending'
    assert account['roleArn'] is None and account['awsAccountId'] is None


def test_the_external_id_is_issued_by_ward_not_the_user(client):
    a, b = create(client), create(client, label='Second')
    onboarding_a = client.get(f"/accounts/{a['id']}/onboarding").json()
    onboarding_b = client.get(f"/accounts/{b['id']}/onboarding").json()

    assert onboarding_a['external_id'] and onboarding_a['external_id'] != onboarding_b['external_id']
    # The listing must never leak it — it is shown only through onboarding.
    assert 'external_id' not in client.get('/accounts').json()['items'][0]


def test_onboarding_hands_over_a_template_that_needs_no_typing(client):
    account = create(client)
    body = client.get(f"/accounts/{account['id']}/onboarding").json()

    # Both parameters are pre-filled, so deploying is click-through rather than copy-paste.
    assert f"Default: {body['external_id']}" in body['template']
    assert f"Default: {body['ward_principal']}" in body['template']
    assert 'sts:ExternalId' in body['template']  # the confused-deputy guard is in the trust policy


def test_the_template_grants_reads_and_nothing_else(client):
    """SRS §7: never Delete, Terminate or iam:*. Checked per granted action, not by text search —
    the trust principal's own ARN legitimately contains 'iam:'."""
    account = create(client)
    template = client.get(f"/accounts/{account['id']}/onboarding").json()['template']

    actions = re.findall(r'^\s+- ([a-z0-9]+):([A-Za-z*]+)$', template, re.MULTILINE)
    assert actions, 'no actions found — the regex or the template shape changed'
    for service, verb in actions:
        assert service != 'iam', f'template grants iam:{verb}'
        assert verb.startswith(('Describe', 'List', 'Get')), f'{service}:{verb} is not a read'


def test_connecting_verifies_the_role_before_trusting_it(client):
    account = create(client)
    external_id = client.get(f"/accounts/{account['id']}/onboarding").json()['external_id']
    client.sts.expected = external_id

    connected = client.post(f"/accounts/{account['id']}/connect", json={'role_arn': ROLE}).json()

    assert connected['status'] == 'connected'
    assert connected['awsAccountId'] == '123456789012'  # discovered, not typed by the user
    assert client.sts.calls[0][:2] == (ROLE, external_id)


def test_a_role_that_cannot_be_assumed_is_rejected_and_recorded(client):
    account = create(client)
    client.sts.expected = 'a-different-external-id'

    res = client.post(f"/accounts/{account['id']}/connect", json={'role_arn': ROLE})

    assert res.status_code == 400
    assert 'ExternalId' in res.json()['detail']
    after = client.get('/accounts').json()['items'][-1]
    assert after['status'] == 'error' and after['roleArn'] is None and after['lastError']


def test_a_malformed_role_arn_never_reaches_sts(client):
    account = create(client)
    res = client.post(f"/accounts/{account['id']}/connect", json={'role_arn': 'not-an-arn'})
    assert res.status_code == 422
    assert client.sts.calls == []


def test_secrets_survive_a_round_trip_but_not_as_plaintext():
    token = encrypt('super-secret')
    assert token != 'super-secret'
    assert decrypt(token) == 'super-secret'


def test_credentials_are_cached_until_they_near_expiry():
    now = datetime.now(timezone.utc)
    clock = {'t': now}
    sts = StubSts(expires_in=timedelta(hours=1))
    conn = stub_connection(sts, now=lambda: clock['t'])
    account = Account(id='acct_1', label='x', region='ap-south-1', budget_inr=1, external_id_enc=encrypt('x'),
                      role_arn=ROLE, status='connected', created_at=now)

    conn.session(account)
    clock['t'] = now + timedelta(minutes=50)
    conn.session(account)
    assert len(sts.calls) == 1, 'credentials still valid — should not re-assume'

    clock['t'] = now + timedelta(minutes=56)  # inside the 5-minute refresh margin
    conn.session(account)
    assert len(sts.calls) == 2, 'expiring credentials should be refreshed'


def test_setup_detects_wards_own_identity_as_the_principal(client):
    body = client.get('/accounts/setup').json()

    assert body['ready'] is True
    assert body['identity']['account'] == '999999999999'
    assert body['principal'] == 'arn:aws:iam::999999999999:user/ward-dev'
    assert body['principalSource'] == 'detected'


def test_the_detected_principal_is_what_the_template_trusts(client):
    account = create(client)
    body = client.get(f"/accounts/{account['id']}/onboarding").json()

    assert body['ready'] is True
    assert 'Default: arn:aws:iam::999999999999:user/ward-dev' in body['template']
    assert any('CAPABILITY_NAMED_IAM' in line for line in body['cli'])


def test_without_credentials_ward_says_so_instead_of_shipping_a_broken_template(client):
    client.sts.identity_arn = None
    setup = client.get('/accounts/setup').json()
    assert setup['ready'] is False and 'aws configure' in setup['error']

    account = create(client)
    body = client.get(f"/accounts/{account['id']}/onboarding").json()
    assert body['ready'] is False
    # No placeholder principal: IAM would reject it, and the console would fail late and cryptically.
    assert 'Default: arn:aws:iam::000000000000' not in body['template']
    assert body['template'].count('Default:') == 1  # only the ExternalId


def test_an_assumed_role_session_becomes_the_role_it_came_from():
    assert trustable('arn:aws:sts::123456789012:assumed-role/ward-poller/i-0abc') == \
        'arn:aws:iam::123456789012:role/ward-poller'
    assert trustable('arn:aws:iam::123456789012:user/vansh') == 'arn:aws:iam::123456789012:user/vansh'


def test_an_account_without_a_role_cannot_produce_a_session():
    account = Account(id='acct_2', label='x', region='ap-south-1', budget_inr=1, external_id_enc=encrypt('x'),
                      status='pending', created_at=datetime.now(timezone.utc))
    with pytest.raises(ConnectionError_, match='no role ARN'):
        stub_connection().session(account)
