"""Architect: from "what I want to build" to the simplest AWS setup that fits — built from what the user
said they need, never from a fixed template.

1. Read the sentence: the stack (MERN means MongoDB; Django or Laravel mean a relational database), how
   many people, the budget (a ₹ figure, or "free"), whether files are uploaded, traffic shape, uptime.
2. Ask about whatever the sentence did not settle — one question per missing fact, every option showing
   what it changes. Nothing is added to the setup that the user did not ask for or confirm.
3. Assemble only the pieces they need, keep their stack (a MongoDB app keeps MongoDB), and price every
   line, including the ones people forget: the server's disk and its public IPv4 address.

Rule-based, not a model: the same sentence and answers always give the same setup, and every service
left out comes with the reason.
"""
import re

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.config import settings
from app.inventory.pricing import EBS_GP3_INR_PER_GB_HOUR, HOURLY_INR

router = APIRouter(tags=['architect'])

HOURS = 24 * 30
# Beyond the shared price table: ₹/hour at WARD_USD_TO_INR, ap-south-1 on-demand.
DOCDB_T3_MEDIUM = 0.078 * settings.usd_to_inr
PUBLIC_IPV4 = 0.005 * settings.usd_to_inr  # every public IPv4 address, attached or not, since Feb 2024
ROOT_DISK_GB = 20
S3_SMALL = 40  # ~20 GB of uploads and exports

NOTE = ('On-demand ap-south-1 prices, excluding data transfer. Free-tier figures assume an eligible account — '
        'the 12-month free tier on older accounts, or the credits AWS gives accounts opened since July 2025 — '
        'so check yours. Ward compares the estimate with your real bill after 30 days.')


class ArchitectRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=1000)
    answers: dict[str, str] = Field(default_factory=dict)


# ─── Reading the sentence ────────────────────────────────────────────────────

DOCUMENT = re.compile(r'\b(mern|mean|mongo(db)?|mongoose|nosql|firebase)\b')
RELATIONAL = re.compile(r'\b(postgres(ql)?|mysql|mariadb|sql|django|laravel|rails|spring|php|prisma|sequelize)\b')
STATIC = re.compile(r'\b(static|portfolio|landing page|landing|brochure|blog built with|html site)\b')
NO_DB = re.compile(r"\b(no database|without a database|doesn'?t need a database)\b")
UPLOADS = re.compile(r'\b(upload|uploads|images?|photos?|files?|pdfs?|documents|videos?|attachments?|exports?)\b')
FREE = re.compile(r'\b(free|free tier|zero cost|no cost)\b')
BURST = re.compile(r'\b(same (morning|time|minute|hour)|all at once|rush|spike|at the same time|launch day)\b')
STRICT = re.compile(r'\b(must stay up|always (on|up)|24/7|high availability|mission critical|no downtime)\b')


def read(prompt: str, answers: dict) -> dict:
    t = prompt.lower()
    users = _number(r'(\d[\d,]*)\s*(?:students|users|people|customers|visitors|members|employees)', t)
    budget = _number(r'(?:₹|rs\.?|inr)\s?(\d[\d,]*)', t)
    if STATIC.search(t):
        kind = 'static'
    else:
        kind = 'app'
    if NO_DB.search(t):
        data = 'none'
    elif DOCUMENT.search(t):
        data = 'document'
    elif RELATIONAL.search(t):
        data = 'relational'
    else:
        data = answers.get('data')
    return {
        'kind': kind,
        'users': users or (int(answers['users']) if answers.get('users') else None),
        'free': bool(FREE.search(t)) and not budget or answers.get('budget') == 'free',
        'budget': budget or (int(answers['budget']) if answers.get('budget', '').isdigit() else None),
        'data': data,
        'uploads': True if UPLOADS.search(t) else ({'yes': True, 'no': False}.get(answers.get('uploads'))),
        'load': 'burst' if BURST.search(t) else answers.get('load'),
        'uptime': 'strict' if STRICT.search(t) else answers.get('uptime'),
        'mongoHome': answers.get('mongoHome'),
        'mern': bool(DOCUMENT.search(t)),
    }


def _number(pattern: str, text: str) -> int | None:
    found = re.search(pattern, text)
    return int(found[1].replace(',', '')) if found else None


def _monthly(per_hour: float, factor: float = 1.0) -> int:
    return round(per_hour * HOURS * factor)


# ─── Asking about what's missing ─────────────────────────────────────────────

def questions(need: dict) -> list[dict]:
    qs = []

    def ask(term, question, options, default=0):
        qs.append({'term': term, 'question': question, 'defaultIndex': default,
                   'options': [{'label': label, 'value': value, 'matches': None, 'detail': detail}
                               for label, value, detail in options]})

    if need['users'] is None:
        ask('users', 'Roughly how many people will use it?', [
            ('Up to 100', '100', 'a class, a team'),
            ('Around 1,000', '1000', 'a department, a small product'),
            ('10,000 or more', '10000', 'a larger audience'),
        ], 1)
    if need['budget'] is None and not need['free']:
        ask('budget', 'What can it cost each month?', [
            ('Free tier only', 'free', '₹0 while the free tier lasts'),
            ('Up to ₹1,500', '1500', 'one small server'),
            ('Up to ₹5,000', '5000', 'room for a managed database'),
        ], 1)
    if need['kind'] == 'static':
        return qs
    if need['data'] is None:
        ask('data', 'What does the app need to store?', [
            ('Nothing — no database', 'none', 'no database at all'),
            ('Documents / JSON (MongoDB)', 'document', 'MongoDB'),
            ('Tables (Postgres or MySQL)', 'relational', 'RDS or on the server'),
        ], 2)
    if need['data'] == 'document' and need['mongoHome'] is None:
        free = need['free']
        ask('mongoHome', 'Your app uses MongoDB. Where should it live?', [
            ('On the same server', 'server', '₹0 extra · you look after backups'),
            ('MongoDB Atlas free tier', 'atlas', '₹0 · managed, 512 MB, outside AWS'),
            ('Amazon DocumentDB', 'documentdb', f'managed on AWS · ~₹{_monthly(DOCDB_T3_MEDIUM):,}/month'),
        ], 1 if free else 0)
    if need['uploads'] is None:
        ask('uploads', 'Will people upload files — photos, PDFs, exports?', [
            ('No', 'no', 'nothing extra'),
            ('Yes', 'yes', f'adds S3 · ~₹{S3_SMALL}/month'),
        ])
    if need['load'] is None:
        ask('load', 'Will people use it all at once?', [
            ('Spread through the day', 'spread', 'smallest server that fits'),
            ('All at once (e.g. a 9am rush)', 'burst', 'one size up, for the peak'),
        ])
    if need['uptime'] is None and not need['free']:
        ask('uptime', 'If it goes down for an hour, is that a problem?', [
            ("Not really — it's a project", 'relaxed', 'one of everything'),
            ('Yes, it must stay up', 'strict', 'standby database, or a managed one'),
        ])
    return qs


# ─── Building only what was asked for ────────────────────────────────────────

def line(service, role, size, full, free_tier, explainer, attached=None, where='aws'):
    return {'service': service, 'role': role, 'size': size, 'fullPrice': full, 'freeTier': free_tier,
            'explainer': explainer, 'attachedTo': attached, 'where': where}


def build(need: dict) -> tuple[str, list[dict], list[dict]]:
    users, free = need['users'], need['free']
    why_not = []

    if need['kind'] == 'static':
        parts = [
            line('S3', 'Holds your HTML, CSS and images', 'Standard', 25, True, 'File storage in the cloud.'),
            line('CloudFront', 'Serves the site fast, with HTTPS', 'Standard', 0, True, 'A CDN: copies of your site near your visitors.'),
        ]
        why_not.append({'option': 'EC2 server', 'because': f'A static site has no backend. A server would cost ~₹{_monthly(HOURLY_INR["t3.micro"]):,}/month to hand out files S3 serves for pennies.'})
        return 'static_site', parts, why_not

    self_hosted_db = need['data'] == 'document' and need['mongoHome'] == 'server'
    if free:
        size = 't3.micro'
    elif need['load'] == 'burst' or users > 2000:
        size = 't3.medium'
    elif users > 300 or self_hosted_db:
        size = 't3.small'  # MongoDB on the same box wants the extra memory
    else:
        size = 't3.micro'
    runs = 'your backend and serves the frontend build' + (', plus MongoDB' if self_hosted_db else '')
    parts = [
        line('EC2', f'Runs {runs}', size, _monthly(HOURLY_INR[size]), size == 't3.micro',
             'Your virtual computer — a server you rent by the hour.'),
        line('EBS', 'The server’s disk', f'{ROOT_DISK_GB} GB gp3', round(ROOT_DISK_GB * EBS_GP3_INR_PER_GB_HOUR * HOURS), True,
             'Storage attached to the server. Billed even when the server is stopped.', attached='EC2'),
        line('Public IPv4', 'So people can reach the server', '1 address', _monthly(PUBLIC_IPV4), True,
             'AWS charges for every public IPv4 address since February 2024.', attached='EC2'),
    ]

    if need['data'] == 'document':
        home = need['mongoHome']
        if home == 'atlas':
            parts.append(line('MongoDB Atlas', 'Your MongoDB, managed, on the free M0 cluster', 'M0 · 512 MB', 0, True,
                              'MongoDB’s own hosted service — free up to 512 MB. Runs outside AWS.', where='external'))
        elif home == 'documentdb':
            parts.append(line('DocumentDB', 'Managed MongoDB-compatible database on AWS', 'db.t3.medium',
                              _monthly(DOCDB_T3_MEDIUM), False, 'AWS runs it, backs it up and patches it.'))
        if home != 'documentdb':
            why_not.append({'option': 'Amazon DocumentDB', 'because': f'Managed MongoDB on AWS starts at ~₹{_monthly(DOCDB_T3_MEDIUM):,}/month — you chose a free home for MongoDB instead.'})
        why_not.append({'option': 'RDS (Postgres/MySQL)', 'because': 'Your app is built on MongoDB. Moving to a relational database would mean rewriting its data layer.'})
    elif need['data'] == 'relational':
        strict = need['uptime'] == 'strict'
        parts.append(line('RDS', 'Your database, with automatic backups', 'db.t3.micro' + (', Multi-AZ' if strict else ''),
                          _monthly(HOURLY_INR['db.t3.micro'], 2 if strict else 1), not strict,
                          'A managed database — AWS handles backups, patching and storage.'))
        if not strict:
            why_not.append({'option': 'Multi-AZ database', 'because': 'You said an hour of downtime is acceptable. A standby copy would double the database cost.'})

    if need['uploads']:
        parts.append(line('S3', 'Stores uploaded files and exports', 'Standard', S3_SMALL, True, 'File storage — cheaper and safer than the server’s disk.'))

    why_not += [
        {'option': 'Load balancer', 'because': 'Only needed with more than one server. You have one.'},
        {'option': 'NAT gateway', 'because': f'The server sits in a public subnet, so it needs none — a NAT gateway alone is ~₹{_monthly(HOURLY_INR["nat-gateway"]):,}/month.'},
        {'option': 'Kubernetes (EKS)', 'because': 'At this scale the app runs comfortably on one server; the EKS control plane alone is ~₹6,000/month.'},
    ]
    return 'single_server_webapp', parts, why_not


@router.post('/architect')
def architect(req: ArchitectRequest) -> dict:
    need = read(req.prompt, req.answers)
    asked = questions(need)
    if asked:
        return {'status': 'needs-clarification', 'questions': asked, 'understood': understood(need)}

    pattern, parts, why_not = build(need)
    for p in parts:
        p['perMonth'] = 0 if need['free'] and p['freeTier'] else p['fullPrice']
    now = sum(p['perMonth'] for p in parts)
    after = sum(p['fullPrice'] for p in parts)
    budget = 0 if need['free'] else need['budget']
    return {
        'status': 'recommended',
        'pattern': pattern,
        'users': need['users'],
        'budget': budget,
        'free': need['free'],
        'components': parts,
        'estimate': {'low': round(now * 0.85), 'high': round(now * 1.2)},
        'afterFreeTier': after if need['free'] else None,
        'withinBudget': (now == 0) if need['free'] else (now * 1.2 <= budget if budget else None),
        'complexity': 'Beginner-friendly',
        'understood': understood(need),
        'whyNot': why_not,
        'note': NOTE,
    }


def understood(need: dict) -> list[str]:
    """What Ward read from the sentence, shown back so a misreading is visible."""
    out = []
    if need['kind'] == 'static':
        out.append('a static site')
    elif need['mern']:
        out.append('a MongoDB app (MERN)')
    elif need['data'] == 'relational':
        out.append('an app with a relational database')
    if need['users']:
        out.append(f'~{need["users"]:,} users')
    if need['free']:
        out.append('free tier only')
    elif need['budget']:
        out.append(f'budget ₹{need["budget"]:,}/month')
    if need['uploads']:
        out.append('file uploads')
    if need['load'] == 'burst':
        out.append('everyone at once')
    return out
