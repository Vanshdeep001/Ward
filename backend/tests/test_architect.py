"""Architect: builds from what the user said they need, asks about the rest, and never swaps their stack."""
from fastapi.testclient import TestClient

from app.main import app

MERN_FREE = 'I want to deploy my MERN attendance application for 500 students and keep it free'
MERN_BUDGET = 'I want to deploy my MERN attendance application for 500 students and keep it under ₹1,500/month.'


def ask(prompt, answers=None):
    with TestClient(app) as c:
        return c.post('/architect', json={'prompt': prompt, 'answers': answers or {}}).json()


def terms(body):
    return [q['term'] for q in body['questions']]


def test_it_asks_only_about_what_the_sentence_left_open():
    body = ask(MERN_FREE)
    assert body['status'] == 'needs-clarification'
    # users (500), budget (free) and the database kind (MERN → MongoDB) were all in the sentence
    assert terms(body) == ['mongoHome', 'uploads', 'load']
    assert 'a MongoDB app (MERN)' in body['understood'] and 'free tier only' in body['understood']


def test_a_mern_app_keeps_mongodb_and_free_means_free():
    body = ask(MERN_FREE, {'mongoHome': 'atlas', 'uploads': 'no', 'load': 'spread'})
    services = [c['service'] for c in body['components']]
    assert 'RDS' not in services, 'MongoDB is never swapped for Postgres'
    assert 'MongoDB Atlas' in services
    assert 'S3' not in services, 'no uploads were asked for, so no S3'
    assert body['components'][0]['size'] == 't3.micro'
    assert body['estimate'] == {'low': 0, 'high': 0} and body['withinBudget'] is True
    assert body['afterFreeTier'] > 0, 'and it says what it costs once the free tier ends'


def test_forgotten_costs_are_priced():
    body = ask(MERN_BUDGET, {'mongoHome': 'server', 'uploads': 'no', 'load': 'spread', 'uptime': 'relaxed'})
    services = {c['service']: c for c in body['components']}
    assert services['EBS']['attachedTo'] == 'EC2' and services['Public IPv4']['perMonth'] > 0
    assert services['EC2']['size'] == 't3.small', 'MongoDB on the same server needs the memory'
    assert body['budget'] == 1500


def test_uploads_add_s3_and_a_relational_stack_gets_rds():
    body = ask('A Django app for 300 employees, staff upload PDFs, budget ₹3000',
               {'load': 'spread', 'uptime': 'strict'})
    services = {c['service']: c for c in body['components']}
    assert 'S3' in services and 'Multi-AZ' in services['RDS']['size']


def test_an_unclear_sentence_gets_asked_everything():
    body = ask('I have an app I want to put online')
    assert terms(body) == ['users', 'budget', 'data', 'uploads', 'load', 'uptime']


def test_a_static_site_has_no_server():
    body = ask('A static portfolio site for 100 visitors, keep it free')
    assert body['status'] == 'recommended'
    assert [c['service'] for c in body['components']] == ['S3', 'CloudFront']
