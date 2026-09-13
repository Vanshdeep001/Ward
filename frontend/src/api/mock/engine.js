// In-browser stand-in for the FastAPI backend. Same response shapes the real endpoints will return.
import {
  resources, rules, alerts, dailySpend, predictions, conflicts, gpuSessions, weekendEvidence, byId, isGpu,
  PRICING, BUDGET, WARD_OWN_COST, INVENTORY_AS_OF, hAgo, dAgo,
} from './data.js'

const delay = (ms = 350) => new Promise((r) => setTimeout(r, ms + Math.random() * 250))
const runtime = (r) => (r.running ? (Date.now() - new Date(r.launchedAt).getTime()) / 3_600_000 : 0)
const monthly = (perHour) => perHour * 24 * 30
const round = (n) => Math.round(n)
const sumDays = (n) => dailySpend.slice(-n).reduce((s, d) => s + d.amount, 0)

// Month-to-date plus the last 7 days' burn rate carried to month end (SRS Phase 5 baseline predictor).
function projectMonthEnd() {
  const today = new Date()
  const daysInMonth = new Date(today.getFullYear(), today.getMonth() + 1, 0).getDate()
  return round(sumDays(today.getDate()) + (sumDays(7) / 7) * (daysInMonth - today.getDate()))
}

// SRS §17.2 — the same acted-on GPU sessions priced under three stated counterfactuals.
// "next-morning" is the default and equals the per-rule savings shown on the Guardrails page.
function counterfactuals() {
  const ruleTotal = rules.reduce((s, r) => s + r.savings30d, 0)
  const avgPrice = (PRICING['g5.xlarge'] + PRICING['g4dn.xlarge']) / 2
  const model = (label, description, factor, excludedShare) => {
    const avoided = round(ruleTotal * factor)
    return { label, description, avoided, hoursAvoided: +(avoided / avgPrice).toFixed(1), excluded: round(avoided * excludedShare) }
  }
  return {
    'next-morning': model('Next-morning (default)', 'Assumes an un-alerted instance runs until 09:00 the following working day.', 1, 0.17),
    conservative: model('Conservative', 'Assumes an un-alerted instance would have run only 2 more hours.', 0.42, 0.12),
    observed: model('Observed', 'Uses this account’s own median unattended runtime, from resources no rule was watching.', 1.31, 0.2),
  }
}

// ─── Compiler templates ────────────────────────────────────────────────────────
// Each template: detects a rule shape, then provides matcher, YAML, explanation, fixtures and sources.

const TEMPLATES = [
  {
    kind: 'gpu-runtime',
    detect: (t) => /gpu/.test(t) && /(\d+)\s*(h|hour)/.test(t),
    params: (t) => ({ hours: Number(t.match(/(\d+)\s*(h|hour)/)[1]) }),
    resourceType: 'EC2 instances',
    matches: (r, p) => isGpu(r) && r.running && runtime(r) > p.hours,
    population: (r) => r.type === 'ec2',
    yaml: (p) => `policies:
  - name: ec2-gpu-max-runtime-${p.hours}h
    resource: aws.ec2
    filters:
      - State.Name: running
      - type: value
        key: InstanceType
        op: regex
        value: "^(p|g|inf)[0-9].*"
      - type: instance-age
        op: greater-than
        hours: ${p.hours}
    actions:
      - type: notify
        transport: { type: telegram }`,
    explain: (p) => [
      { label: 'Watch', text: 'EC2 instances' },
      { label: 'Only those', text: 'whose instance type starts with p, g, or inf AND are currently running' },
      { label: 'Flag when', text: `the instance has been running for more than ${p.hours} hours` },
      { label: 'Then', text: 'notify you on Telegram' },
      { label: 'Checked', text: 'every 15 minutes' },
    ],
    assumptions: [
      {
        term: 'GPU instance', interpretation: 'instance type in families p, g, inf', confidence: 0.91,
        alternatives: ['any instance with an attached accelerator'],
      },
    ],
    sources: [
      ['aws.ec2 — instance-age filter', 'c7n schema', 0.94, 'type: instance-age · op: greater-than | less-than · hours: int · days: int'],
      ['aws.ec2 — resource schema', 'c7n schema', 0.89, 'resource: aws.ec2 · filters: State.Name, InstanceType, tag:*'],
      ['EC2 accelerated computing families', 'aws docs', 0.71, 'P, G and Inf families provide GPU / inference accelerators.'],
      ['g4dn.xlarge on-demand, ap-south-1', 'pricing', 0.66, '₹101.14 per hour · Linux · effective 2026-01-01'],
      ['Filter operators reference', 'c7n schema', 0.61, 'op: eq | ne | in | not-in | regex | greater-than | less-than'],
    ],
  },
  {
    kind: 'cost-runtime',
    detect: (t) => /more than ₹\s?(\d+)\/day/.test(t) && /(\d+)\s*(h|hour)/.test(t),
    params: (t) => ({ perDay: Number(t.match(/₹\s?(\d+)\/day/)[1]), hours: Number(t.match(/(\d+)\s*(h|hour)/)[1]) }),
    resourceType: 'EC2 and RDS instances',
    matches: (r, p) => r.running && r.costPerHour * 24 > p.perDay && runtime(r) > p.hours,
    population: (r) => r.type === 'ec2' || r.type === 'rds',
    yaml: (p) => `policies:
  - name: expensive-long-running
    resource: aws.ec2
    filters:
      - State.Name: running
      - type: cost
        op: greater-than
        per_day_inr: ${p.perDay}
      - type: instance-age
        op: greater-than
        hours: ${p.hours}`,
    explain: (p) => [
      { label: 'Watch', text: 'EC2 and RDS instances' },
      { label: 'Only those', text: `costing more than ₹${p.perDay}/day AND currently running` },
      { label: 'Flag when', text: `running for more than ${p.hours} hours` },
      { label: 'Then', text: 'notify you on Telegram' },
    ],
    assumptions: [],
    sources: [
      ['aws.ec2 — instance-age filter', 'c7n schema', 0.9, 'type: instance-age · op · hours'],
      ['On-demand pricing, ap-south-1', 'pricing', 0.82, 'Per-hour rates by instance type'],
    ],
  },
  {
    kind: 'weekend',
    detect: (t) => /weekend/.test(t),
    params: (t) => ({ gpuOnly: /gpu/.test(t) }),
    resourceType: 'EC2 instances',
    matches: (r, p) =>
      r.type === 'ec2' && r.running && [0, 6].includes(new Date().getDay()) && !r.tags.Environment && (!p.gpuOnly || isGpu(r)),
    population: (r) => r.type === 'ec2',
    yaml: (p) => `policies:
  - name: ec2-no-weekend-running${p.gpuOnly ? '-gpu' : ''}
    resource: aws.ec2
    filters:
      - State.Name: running
      - "tag:Environment": absent${p.gpuOnly ? `
      - type: value
        key: InstanceType
        op: regex
        value: "^(p|g|inf)[0-9].*"` : ''}
      - type: offhour
        weekends: true
        default_tz: Asia/Kolkata`,
    explain: (p) => [
      { label: 'Watch', text: 'EC2 instances' },
      { label: 'Only those', text: `${p.gpuOnly ? 'GPU instances (p, g, inf families) ' : ''}without an Environment tag (production is exempt)` },
      { label: 'Flag when', text: 'running on Saturday or Sunday (Asia/Kolkata)' },
      { label: 'Then', text: 'notify you on Telegram' },
    ],
    assumptions: [
      { term: 'weekend', interpretation: 'Saturday 00:00 – Sunday 23:59, Asia/Kolkata', confidence: 0.88, alternatives: ['Friday 20:00 – Monday 08:00'] },
      { term: 'anything', interpretation: 'EC2 instances not tagged as production', confidence: 0.7, alternatives: ['every running resource, including RDS'] },
    ],
    sources: [
      ['offhour / onhour filters', 'c7n schema', 0.92, 'type: offhour · weekends: bool · default_tz · tag'],
      ['aws.ec2 — resource schema', 'c7n schema', 0.84, 'resource: aws.ec2 · filters'],
    ],
  },
  {
    kind: 'owner-tag',
    detect: (t) => /owner/.test(t) && /tag/.test(t),
    params: () => ({}),
    resourceType: 'all resources',
    matches: (r) => !r.tags.Owner,
    population: () => true,
    yaml: () => `policies:
  - name: require-owner-tag
    resource: aws.ec2
    filters:
      - "tag:Owner": absent`,
    explain: () => [
      { label: 'Watch', text: 'every resource Ward inventories' },
      { label: 'Flag when', text: 'there is no Owner tag' },
      { label: 'Then', text: 'notify you on Telegram' },
    ],
    assumptions: [],
    sources: [['Tag filters', 'c7n schema', 0.95, '"tag:<key>": absent | present | <value>']],
  },
  {
    kind: 'unattached-ebs',
    detect: (t) => /(ebs|volume)/.test(t),
    params: (t) => ({ days: Number(t.match(/(\d+)\s*day/)?.[1] ?? 0) }),
    resourceType: 'EBS volumes',
    matches: (r) => r.type === 'ebs' && !r.attached,
    population: (r) => r.type === 'ebs',
    yaml: (p) => `policies:
  - name: ebs-unattached${p.days ? `-${p.days}d` : ''}
    resource: aws.ebs
    filters:
      - Attachments: []${p.days ? `
      - type: value
        key: CreateTime
        value_type: age
        op: greater-than
        value: ${p.days}` : ''}`,
    explain: (p) => [
      { label: 'Watch', text: 'EBS volumes' },
      { label: 'Flag when', text: `not attached to any instance${p.days ? ` for more than ${p.days} days` : ''}` },
      { label: 'Then', text: 'notify you on Telegram' },
    ],
    assumptions: [],
    sources: [
      ['aws.ebs — resource schema', 'c7n schema', 0.93, 'resource: aws.ebs · Attachments · State'],
      ['EBS gp3 pricing, ap-south-1', 'pricing', 0.74, '₹7 per GB-month — billed whether attached or not'],
    ],
  },
  {
    kind: 'nat',
    detect: (t) => /\bnat\b/.test(t),
    params: () => ({}),
    resourceType: 'NAT Gateways',
    matches: (r) => r.type === 'nat',
    population: (r) => r.type === 'nat',
    yaml: () => `policies:
  - name: alert-nat-gateway-exists
    resource: aws.nat-gateway
    filters:
      - State: available`,
    explain: () => [
      { label: 'Watch', text: 'NAT Gateways' },
      { label: 'Flag when', text: 'one exists and is available' },
      { label: 'Then', text: 'notify you on Telegram' },
    ],
    assumptions: [],
    sources: [['NAT Gateway pricing', 'pricing', 0.9, '₹3.90/hour to exist, plus per-GB data processed']],
  },
  {
    kind: 'region',
    detect: (t) => /outside\s+([a-z]{2}-[a-z]+-\d)/.test(t),
    params: (t) => ({ region: t.match(/outside\s+([a-z]{2}-[a-z]+-\d)/)[1] }),
    resourceType: 'all resources',
    matches: (r, p) => r.region !== p.region,
    population: () => true,
    yaml: (p) => `policies:
  - name: region-restriction
    resource: aws.ec2
    conditions:
      - type: value
        key: region
        op: ne
        value: ${p.region}`,
    explain: (p) => [
      { label: 'Watch', text: 'every resource Ward inventories' },
      { label: 'Flag when', text: `it lives in any region other than ${p.region}` },
    ],
    assumptions: [],
    sources: [['Policy conditions: region', 'c7n schema', 0.88, 'conditions: type: value · key: region']],
  },
  {
    kind: 'gpu-expiry',
    detect: (t) => /gpu/.test(t) && /expir/.test(t),
    params: () => ({}),
    resourceType: 'GPU instances',
    matches: (r) => isGpu(r) && r.running && !r.tags.ExpiresAt,
    population: (r) => isGpu(r),
    yaml: () => `policies:
  - name: ec2-gpu-require-expiry-tag
    resource: aws.ec2
    filters:
      - State.Name: running
      - type: value
        key: InstanceType
        op: regex
        value: "^(p|g|inf)[0-9].*"
      - "tag:ExpiresAt": absent`,
    explain: () => [
      { label: 'Watch', text: 'EC2 instances' },
      { label: 'Only those', text: 'whose instance type starts with p, g, or inf AND are currently running' },
      { label: 'Flag when', text: 'there is no ExpiresAt tag' },
      { label: 'Then', text: 'notify you on Telegram' },
    ],
    assumptions: [
      { term: 'expiry tag', interpretation: 'a tag named ExpiresAt', confidence: 0.78, alternatives: ['a tag named ttl', 'a tag named expiry'] },
    ],
    sources: [
      ['Tag filters', 'c7n schema', 0.93, '"tag:<key>": absent | present | <value>'],
      ['EC2 accelerated computing families', 'aws docs', 0.8, 'P, G and Inf families provide GPU / inference accelerators.'],
    ],
  },
  {
    kind: 'runtime',
    detect: (t) => /(\d+)\s*(h|hour)/.test(t),
    params: (t) => ({ hours: Number(t.match(/(\d+)\s*(h|hour)/)[1]) }),
    resourceType: 'EC2 instances',
    matches: (r, p) => r.type === 'ec2' && r.running && runtime(r) > p.hours && !r.tags.Environment,
    population: (r) => r.type === 'ec2',
    yaml: (p) => `policies:
  - name: ec2-max-runtime-${p.hours}h
    resource: aws.ec2
    filters:
      - State.Name: running
      - "tag:Environment": absent
      - type: instance-age
        op: greater-than
        hours: ${p.hours}`,
    explain: (p) => [
      { label: 'Watch', text: 'EC2 instances' },
      { label: 'Only those', text: 'without an Environment tag AND currently running' },
      { label: 'Flag when', text: `running for more than ${p.hours} hours` },
      { label: 'Then', text: 'notify you on Telegram' },
    ],
    assumptions: [
      { term: 'unattended', interpretation: 'not tagged with an Environment (production servers are exempt)', confidence: 0.64, alternatives: ['every running instance, including production'] },
    ],
    sources: [['aws.ec2 — instance-age filter', 'c7n schema', 0.94, 'type: instance-age · op: greater-than · hours: int']],
  },
  {
    kind: 'budget',
    detect: (t) => /budget/.test(t),
    params: () => ({ threshold: 85 }),
    resourceType: 'account forecasts',
    matches: () => false,
    population: () => false,
    yaml: (p) => `policies:
  - name: budget-warning-monthly
    resource: aws.account
    filters:
      - type: cost-forecast
        op: greater-than
        percent_of_budget: ${p.threshold}`,
    explain: (p) => [
      { label: 'Watch', text: 'your account’s month-end cost forecast' },
      { label: 'Flag when', text: `the forecast passes ${p.threshold}% of your ₹${BUDGET.toLocaleString('en-IN')} budget` },
      { label: 'Then', text: 'notify you on Telegram' },
    ],
    assumptions: [
      { term: 'before', interpretation: `at ${85}% of the budget`, confidence: 0.72, alternatives: ['at 75%', 'at 100%'] },
    ],
    sources: [['ce:GetCostForecast', 'aws docs', 0.86, 'Returns forecasted spend for a time period and granularity']],
  },
  {
    kind: 'free-tier',
    detect: (t) => /free tier/.test(t),
    params: () => ({}),
    resourceType: 'EC2 instances and EBS volumes',
    matches: (r) => (r.type === 'ec2' && r.running && !/^t[23]\.micro$/.test(r.instanceType)) || (r.type === 'ebs' && !r.attached),
    population: (r) => r.type === 'ec2' || r.type === 'ebs',
    yaml: () => `policies:
  - name: free-tier-compute
    resource: aws.ec2
    filters:
      - State.Name: running
      - type: value
        key: InstanceType
        op: not-in
        value: [t2.micro, t3.micro]
  - name: free-tier-storage
    resource: aws.ebs
    filters:
      - Attachments: []`,
    explain: () => [
      { label: 'Watch', text: 'EC2 instances and EBS volumes' },
      { label: 'Flag when', text: 'an instance is running that isn’t t2.micro or t3.micro, OR a volume is unattached' },
      { label: 'Then', text: 'notify you on Telegram' },
    ],
    assumptions: [
      { term: 'free tier', interpretation: 't2/t3.micro compute and attached storage only', confidence: 0.69, alternatives: ['also track the 750 hours/month allowance'] },
    ],
    sources: [['AWS Free Tier limits', 'pricing', 0.91, '750 hours/month t2.micro or t3.micro · 30 GB EBS · 12 months']],
  },
  {
    kind: 'rds-public',
    detect: (t) => /(rds|database)/.test(t) && /public/.test(t),
    params: () => ({}),
    resourceType: 'RDS instances',
    matches: (r) => r.type === 'rds' && r.publiclyAccessible,
    population: (r) => r.type === 'rds',
    yaml: () => `policies:
  - name: rds-no-public-access
    resource: aws.rds
    filters:
      - PubliclyAccessible: true`,
    explain: () => [
      { label: 'Watch', text: 'RDS database instances' },
      { label: 'Flag when', text: 'the database accepts connections from the internet' },
      { label: 'Then', text: 'notify you immediately on every channel' },
    ],
    assumptions: [],
    sources: [['aws.rds — resource schema', 'c7n schema', 0.95, 'resource: aws.rds · PubliclyAccessible: bool']],
  },
  {
    kind: 'rds-size',
    detect: (t) => /(rds|database)/.test(t) && /(db\.[a-z0-9]+\.[a-z0-9]+)/.test(t),
    params: (t) => ({ max: t.match(/(db\.[a-z0-9]+\.[a-z0-9]+)/)[1] }),
    resourceType: 'RDS instances',
    matches: (r, p) => r.type === 'rds' && r.costPerHour > (PRICING[p.max] ?? Infinity),
    population: (r) => r.type === 'rds',
    yaml: (p) => `policies:
  - name: rds-max-size
    resource: aws.rds
    filters:
      - type: value
        key: DBInstanceClass
        op: not-in
        value: [db.t3.micro${p.max === 'db.t3.micro' ? '' : `, ${p.max}`}]`,
    explain: (p) => [
      { label: 'Watch', text: 'RDS database instances' },
      { label: 'Flag when', text: `the instance class is larger than ${p.max}` },
      { label: 'Then', text: 'notify you on Telegram' },
    ],
    assumptions: [
      { term: 'larger', interpretation: 'costs more per hour', confidence: 0.83, alternatives: ['has more vCPUs or memory'] },
    ],
    sources: [
      ['aws.rds — resource schema', 'c7n schema', 0.9, 'resource: aws.rds · DBInstanceClass'],
      ['RDS on-demand pricing, ap-south-1', 'pricing', 0.81, 'db.t3.micro ₹1.72/h · db.t3.medium ₹6.00/h'],
    ],
  },
  {
    kind: 'ssh-open',
    detect: (t) => /ssh/.test(t),
    params: () => ({}),
    resourceType: 'security groups',
    matches: (r) => r.type === 'sg' && r.openPorts?.some((p) => p.port === 22 && p.cidr === '0.0.0.0/0'),
    population: (r) => r.type === 'sg',
    yaml: () => `policies:
  - name: sg-no-public-ssh
    resource: aws.security-group
    filters:
      - type: ingress
        Ports: [22]
        Cidr:
          value: 0.0.0.0/0`,
    explain: () => [
      { label: 'Watch', text: 'security groups' },
      { label: 'Flag when', text: 'port 22 (SSH) is open to 0.0.0.0/0 — the entire internet' },
      { label: 'Then', text: 'notify you immediately' },
    ],
    assumptions: [],
    sources: [['aws.security-group — ingress filter', 'c7n schema', 0.94, 'type: ingress · Ports · Cidr']],
  },
]

// ─── Clarifier (SRS §20) ───────────────────────────────────────────────────────

const VAGUE = {
  expensive: {
    question: '"expensive" means',
    options: [
      { label: 'costs more than ₹50/day', value: 'costing more than ₹50/day', test: (r) => r.running && r.costPerHour * 24 > 50 },
      { label: 'costs more than ₹200/day', value: 'costing more than ₹200/day', test: (r) => r.running && r.costPerHour * 24 > 200 },
      { label: 'any GPU instance', value: 'GPU', test: (r) => isGpu(r) && r.running },
    ],
    defaultIndex: 0,
  },
  'too long': {
    question: '"too long" means',
    options: [
      { label: 'more than 2 hours', value: 'more than 2 hours', test: (r) => runtime(r) > 2 },
      { label: 'more than 6 hours', value: 'more than 6 hours', test: (r) => runtime(r) > 6 },
      { label: 'more than 24 hours', value: 'more than 24 hours', test: (r) => runtime(r) > 24 },
    ],
    defaultIndex: 1,
  },
}

function clarify(text) {
  const lower = text.toLowerCase()
  return Object.entries(VAGUE)
    .filter(([term]) => lower.includes(term))
    .map(([term, def]) => ({
      term,
      question: def.question,
      defaultIndex: def.defaultIndex,
      options: def.options.map((o) => ({ label: o.label, value: o.value, matches: resources.filter(o.test).length })),
    }))
}

// ─── Simulator (SRS §16–§18) ───────────────────────────────────────────────────

function simulateTemplate(tpl, params) {
  const population = resources.filter(tpl.population)
  const matched = population.filter((r) => tpl.matches(r, params))
  const result = {
    inventoryAsOf: INVENTORY_AS_OF,
    population: population.length,
    resourceType: tpl.resourceType,
    matched: matched.map((r) => ({
      id: r.id, name: r.name, instanceType: r.instanceType, region: r.region,
      runtimeHours: round(runtime(r)), costPerDay: round(r.costPerHour * 24), tags: r.tags,
    })),
    history: [],
    quietDays: 30,
    breadth: 'normal',
    zeroReason: null,
    savings: { monthly: 0, counterfactual: null, lines: [], note: null },
    alertsPerWeek: 0,
  }

  if (matched.length === 0) {
    result.breadth = 'none'
    result.zeroReason = population.length === 0
      ? `You have no ${tpl.resourceType} — nothing to flag.`
      : `${population.length} ${tpl.resourceType} exist, and none currently match the filters.`
  } else if (matched.length / population.length > 0.5 && population.length > 3) {
    result.breadth = 'broad'
  }

  if (tpl.kind === 'budget') {
    const projected = projectMonthEnd()
    const pct = Math.round((projected / BUDGET) * 100)
    result.population = 1
    result.zeroReason = pct >= params.threshold
      ? `Your month-end forecast is ${pct}% of budget (₹${projected.toLocaleString('en-IN')}) — this would fire immediately.`
      : `Your month-end forecast is ${pct}% of budget — quiet for now.`
    result.alertsPerWeek = 0.2
    result.quietDays = 29
    result.savings.note = 'Warning rule — savings depend on what you do once warned.'
  } else if (tpl.kind === 'gpu-runtime') {
    const violations = gpuSessions.filter((s) => s.runtime > params.hours)
    result.history = violations
      .map((s) => ({ date: dAgo(s.daysAgo), resourceId: s.resourceId, detail: `${byId(s.resourceId).instanceType}, ran ${s.runtime}h` }))
      .sort((a, b) => b.date.localeCompare(a.date))
    result.quietDays = 30 - new Set(violations.map((s) => Math.floor(s.daysAgo))).size
    result.alertsPerWeek = +(violations.length / 30 * 7).toFixed(1)

    const excessHours = violations.reduce((sum, s) => sum + (s.runtime - params.hours), 0)
    const cost = violations.reduce((sum, s) => sum + (s.runtime - params.hours) * PRICING[byId(s.resourceId).instanceType], 0)
    result.savings = {
      monthly: round(cost),
      counterfactual: 'stopped at the limit',
      lines: [
        { label: 'Violations in the last 30 days', value: `${violations.length}`, source: 'inventory snapshots' },
        { label: 'Hours past the limit, total', value: `${excessHours.toFixed(1)}h`, source: 'Σ (runtime − limit)' },
        { label: 'g5.xlarge, ap-south-1', value: `₹${PRICING['g5.xlarge']}/h`, source: 'pricing chunk, eff. 2026-01-01' },
        { label: 'g4dn.xlarge, ap-south-1', value: `₹${PRICING['g4dn.xlarge']}/h`, source: 'pricing chunk, eff. 2026-01-01' },
        { label: 'Estimated avoidable', value: `₹${round(cost).toLocaleString('en-IN')}`, source: 'Σ excess hours × hourly price' },
      ],
      note: 'Assumes an alerted instance is stopped when it crosses the limit. Un-alerted, it runs its observed length.',
    }
  } else if (tpl.kind === 'weekend') {
    result.history = weekendEvidence.map((e) => ({ date: e.date, resourceId: e.resourceId, detail: `ran through the weekend, ${e.hours}h` }))
    result.quietDays = 30 - result.history.length * 2
    result.alertsPerWeek = +(result.history.length / 30 * 7).toFixed(1)
    const cost = weekendEvidence.reduce((s, e) => s + e.hours * PRICING['g5.xlarge'], 0)
    result.savings = {
      monthly: round(cost),
      counterfactual: 'stopped Friday night',
      lines: [
        { label: 'Weekend hours observed', value: `${weekendEvidence.reduce((s, e) => s + e.hours, 0)}h`, source: 'inventory snapshots' },
        { label: 'g5.xlarge, ap-south-1', value: `₹${PRICING['g5.xlarge']}/h`, source: 'pricing chunk' },
      ],
      note: 'Assumes flagged instances would have been stopped before Saturday.',
    }
    if (matched.length === 0) result.zeroReason = "It's a weekday, so nothing matches right now — but it fired on 3 recent weekends."
  } else if (['unattached-ebs', 'nat'].includes(tpl.kind)) {
    const cost = matched.reduce((s, r) => s + monthly(byId(r.id).costPerHour), 0)
    result.alertsPerWeek = matched.length ? 0.2 : 0
    result.quietDays = matched.length ? 29 : 30
    result.savings = {
      monthly: round(cost),
      counterfactual: 'deleted when flagged',
      lines: matched.map((m) => ({ label: m.name, value: `₹${round(monthly(byId(m.id).costPerHour))}/mo`, source: 'pricing chunk' })),
      note: 'Full monthly cost of matched resources — assumes they are unused.',
    }
  } else {
    result.alertsPerWeek = +(matched.length * 0.4).toFixed(1)
    result.quietDays = Math.max(0, 30 - matched.length * 2)
    result.savings.note = 'Hygiene rule — no direct saving, but it makes every other alert attributable.'
  }

  return result
}

// ─── Public mock API ───────────────────────────────────────────────────────────

export const mock = {
  async health() {
    await delay(100)
    return { status: 'ok', mode: 'mock' }
  },

  async resources() {
    await delay()
    return { asOf: INVENTORY_AS_OF, items: resources.map((r) => ({ ...r, runtimeHours: round(runtime(r)) })) }
  },

  async alerts() {
    await delay()
    return alerts.map((a) => ({ ...a, resource: byId(a.resourceId), rule: rules.find((r) => r.id === a.ruleId) }))
  },

  async snoozeAlert(id, hours) {
    await delay(200)
    const a = alerts.find((x) => x.id === id)
    a.status = 'snoozed'
    a.snoozedUntil = hAgo(-hours)
    return a
  },

  async rules() {
    await delay()
    return rules
  },

  async compileRule(english, { skipClarify = false } = {}) {
    await delay(900)
    const text = english.toLowerCase()

    if (!skipClarify) {
      const questions = clarify(english)
      if (questions.length) return { status: 'needs-clarification', english, questions }
    }

    const tpl = TEMPLATES.find((t) => t.detect(text))
    if (!tpl) {
      return {
        status: 'failed',
        english,
        verifier: { passed: false, attempts: 3, fixtures: [], error: 'No valid policy after 3 attempts. Flagged for human review.' },
      }
    }
    const params = tpl.params(text)
    return {
      status: 'compiled',
      english,
      kind: tpl.kind,
      params,
      yaml: tpl.yaml(params),
      explanation: tpl.explain(params),
      assumptions: tpl.assumptions,
      verifier: {
        passed: true,
        attempts: 1,
        durationMs: 640,
        fixtures: [
          { id: 'pos-1', kind: 'positive', expected: true, actual: true },
          { id: 'pos-2', kind: 'positive', expected: true, actual: true },
          { id: 'neg-1', kind: 'negative', expected: false, actual: false },
          { id: 'neg-2', kind: 'negative', expected: false, actual: false },
          { id: 'edge-1', kind: 'edge', expected: false, actual: false },
        ],
      },
      retrieval: { vector: 20, bm25: 20, merged: 34, kept: tpl.sources.length, latencyMs: 340 },
      sources: tpl.sources.map(([title, docType, score, excerpt]) => ({ title, docType, score, excerpt })),
      simulation: simulateTemplate(tpl, params),
    }
  },

  async whatIf(kind, param, values) {
    await delay(250)
    const tpl = TEMPLATES.find((t) => t.kind === kind)
    return values.map((v) => {
      const sim = simulateTemplate(tpl, { [param]: v })
      return { value: v, fires: sim.history.length, alertsPerWeek: sim.alertsPerWeek, savings: sim.savings.monthly, matched: sim.matched.length }
    })
  },

  async activateRule(english) {
    await delay(400)
    const rule = { id: `r${rules.length + 1}`, english, status: 'active', createdAt: new Date().toISOString(), firesLast30d: 0, actedOn: 0, savings30d: 0, quality: null }
    rules.push(rule)
    return rule
  },

  async costs() {
    await delay()
    return {
      budget: BUDGET,
      daily: dailySpend,
      monthToDate: sumDays(new Date().getDate()),
      projectedMonthEnd: projectMonthEnd(),
      savings: {
        avoided: counterfactuals()['next-morning'].avoided,
        alertsSent: rules.reduce((s, r) => s + r.firesLast30d, 0),
        actedOn: rules.reduce((s, r) => s + r.actedOn, 0),
        wardCost: WARD_OWN_COST,
        topRule: [...rules].sort((a, b) => b.savings30d - a.savings30d)[0],
        counterfactuals: counterfactuals(),
      },
    }
  },

  async conflicts() {
    await delay(250)
    const untagged = resources.filter((r) => !r.tags.Owner).length
    return conflicts.map((c) =>
      c.category === 'overlap'
        ? { ...c, affected: untagged, detail: `Overlap on ${untagged} of your ${resources.length} current resources — each triggers two notifications for the same issue.`, impact: `${untagged} resources send 2 alerts every evaluation window.` }
        : c,
    )
  },

  async predictions() {
    await delay()
    // The ungraded current month is the same projection the dashboard shows.
    return predictions.map((p) => (p.actual == null ? { ...p, predicted: projectMonthEnd() } : p))
  },

  async investigate() {
    await delay(1200)
    const prev = dailySpend.slice(-14, -7).reduce((s, d) => s + d.amount, 0)
    const curr = dailySpend.slice(-7).reduce((s, d) => s + d.amount, 0)
    const causes = [
      {
        id: 'c1', service: 'EC2 — GPU', delta: 2840, resourceId: 'i-0a1f2',
        headline: 'ml-training (g5.xlarge) ran 43 hours longer than its previous average.',
        detail: '43h × ₹66.05/hour (g5.xlarge, ap-south-1) = ₹2,840. Longest sessions: 31h ending today, 14h three days ago.',
        ruleLink: { status: 'working-but-ignored', text: 'Rule "No GPU instance runs more than 6 hours" fired twice — neither alert was acted on.' },
        suggestedRule: 'GPU instances must not run longer than 6 hours',
      },
      {
        id: 'c2', service: 'RDS', delta: 540, resourceId: 'db-0d6',
        headline: 'hackathon-db (db.t3.medium) was created 12 days ago and has run continuously.',
        detail: '₹6.00/hour × 90h this week above last week. It is also publicly accessible — see Guardian.',
        ruleLink: { status: 'missing', text: 'No rule covers idle or oversized databases.' },
        suggestedRule: 'No RDS instance larger than db.t3.micro',
      },
      {
        id: 'c3', service: 'NAT Gateway', delta: 210, resourceId: 'nat-0c5',
        headline: 'nat-0c5 in vpc-dev-2 processed more data after eks-worker-3 was created.',
        detail: 'Charged ₹3.90/hour to exist, plus per-GB processing. Data processed rose from 6 GB to 41 GB.',
        ruleLink: { status: 'missing', text: 'No rule covers NAT Gateways.' },
        suggestedRule: 'Alert if a NAT Gateway exists in a dev VPC',
      },
      {
        id: 'c4', service: 'S3', delta: 80, resourceId: 's3-exports',
        headline: 'attendance-exports grew by 38 GB of CSV exports.',
        detail: 'Standard storage plus PUT requests from a nightly export job.',
        ruleLink: { status: 'none', text: 'Small and expected. No rule suggested.' },
        suggestedRule: null,
      },
    ]
    const attributed = causes.reduce((s, c) => s + c.delta, 0)
    return {
      from: { label: 'Previous 7 days', total: prev },
      to: { label: 'Last 7 days', total: curr },
      delta: curr - prev,
      causes,
      unattributed: curr - prev - attributed,
    }
  },

  async findings() {
    await delay()
    const untagged = resources.filter((r) => !r.tags.Owner)
    const unattached = resources.filter((r) => r.type === 'ebs' && !r.attached)
    const all = [
      {
        id: 'f1', family: 'security', severity: 'urgent', title: 'Your database is publicly accessible',
        detail: 'hackathon-db accepts connections from the internet. Anyone who finds the endpoint can attempt to log in.',
        resourceIds: ['db-0d6'], monthlyImpact: null, fix: 'aws rds modify-db-instance --db-instance-identifier hackathon-db --no-publicly-accessible --apply-immediately',
        suggestedRule: 'No RDS instance may be publicly accessible', source: 'c7n: rds · publicly-accessible',
      },
      {
        id: 'f2', family: 'security', severity: 'warning', title: 'SSH is open to the entire internet',
        detail: 'Security group launch-wizard-1 allows port 22 from 0.0.0.0/0.',
        resourceIds: ['sg-0ssh'], monthlyImpact: null, fix: 'aws ec2 revoke-security-group-ingress --group-id sg-0ssh --protocol tcp --port 22 --cidr 0.0.0.0/0',
        suggestedRule: 'No security group may allow SSH from 0.0.0.0/0', source: 'c7n: security-group · ingress',
      },
      {
        id: 'f3', family: 'waste', severity: 'warning', title: `${unattached.length} unattached EBS volumes`,
        detail: 'Volumes bill every hour whether or not they are attached. These have been unattached for 9 days.',
        resourceIds: unattached.map((r) => r.id), monthlyImpact: round(unattached.reduce((s, r) => s + monthly(r.costPerHour), 0)),
        suggestedRule: 'Flag EBS volumes unattached for more than 7 days', source: 'c7n: ebs · Attachments: []',
      },
      {
        id: 'f4', family: 'configuration', severity: 'info', title: `${untagged.length} resources have no Owner tag`,
        detail: 'Without an owner, nobody gets the alert when these misbehave.',
        resourceIds: untagged.map((r) => r.id), monthlyImpact: null,
        suggestedRule: 'Flag any resource with no owner tag', source: 'c7n: tag:Owner absent',
      },
      {
        id: 'f5', family: 'behavioural', severity: 'warning', title: 'Your GPU is repeatedly left running over weekends',
        detail: `ml-training (g5.xlarge) ran through ${weekendEvidence.length} of the last 4 weekends.`,
        resourceIds: ['i-0a1f2'], monthlyImpact: round(weekendEvidence.reduce((s, e) => s + e.hours * PRICING['g5.xlarge'], 0)),
        evidence: weekendEvidence, confidence: 0.75,
        suggestedRule: 'GPU instances should not run over weekends', source: 'pattern: weekend runner',
      },
    ]
    // Rank: impact × confidence × actionability (SRS §31.3). Urgent security bypasses ranking.
    const score = (f) => (f.severity === 'urgent' ? 1e9 : (f.monthlyImpact ?? 800) * (f.confidence ?? 1) * (f.suggestedRule ? 1 : 0.5))
    return all.sort((a, b) => score(b) - score(a))
  },

  async architect(prompt, answers = {}) {
    await delay(1100)
    const text = prompt.toLowerCase()
    const users = Number(text.match(/(\d[\d,]*)\s*(students|users|people)/)?.[1]?.replace(/,/g, '') ?? 200)
    const budget = Number(text.match(/₹\s?([\d,]+)/)?.[1]?.replace(/,/g, '') ?? 0)

    const questions = []
    if (!answers.load) {
      questions.push({
        term: 'load', question: 'Will people use it all at once?', defaultIndex: 0,
        options: [
          { label: 'Spread through the day', value: 'spread', matches: null, detail: 't3.small' },
          { label: 'All at once (e.g. 9am rush)', value: 'burst', matches: null, detail: 't3.medium' },
        ],
      })
    }
    if (!answers.uptime) {
      questions.push({
        term: 'uptime', question: 'If it goes down for an hour, is that a problem?', defaultIndex: 0,
        options: [
          { label: "Not really — it's a project", value: 'relaxed', matches: null, detail: 'single instance' },
          { label: 'Yes, it must stay up', value: 'strict', matches: null, detail: 'multi-AZ database, ~₹1,250 more' },
        ],
      })
    }
    if (questions.length) return { status: 'needs-clarification', questions }

    if (/(static|portfolio|landing)/.test(text)) {
      return archResult('static_site', users, budget, [
        { service: 'S3', role: 'Stores your HTML, CSS and images', size: 'Standard', perMonth: 25, explainer: 'Your file storage — like a hard drive in the cloud.' },
        { service: 'CloudFront', role: 'Serves the site fast, with HTTPS', size: 'Free tier', perMonth: 0, explainer: 'A delivery network that caches your site close to users.' },
      ], [
        { option: 'EC2', because: 'A static site has no backend. Running a server would cost ~₹700/month to serve files S3 serves for pennies.' },
      ])
    }

    const burst = answers.load === 'burst'
    const strict = answers.uptime === 'strict'
    const ec2Type = burst || users > 2000 ? 't3.medium' : 't3.small'
    const components = [
      { service: 'EC2', role: 'Runs your Node/Express backend and serves the React build', size: ec2Type, perMonth: round(monthly(PRICING[ec2Type])), explainer: 'Your virtual computer — a server you rent by the hour.' },
      { service: 'RDS', role: 'Your database, with automatic backups', size: strict ? 'db.t3.micro, Multi-AZ' : 'db.t3.micro', perMonth: round(monthly(PRICING['db.t3.micro']) * (strict ? 2 : 1)), explainer: 'A managed database — AWS handles backups, patching and storage.' },
      { service: 'S3', role: 'Stores attendance exports and uploaded files', size: 'Standard', perMonth: 40, explainer: 'Your file storage.' },
    ]
    if (/mern|mongo/.test(text)) {
      components[1] = { ...components[1], role: 'Your database. MongoDB-compatible option is DocumentDB, but Postgres on RDS is far cheaper at this size.', explainer: 'A managed database. Mongoose → Prisma/Sequelize is a small change for an attendance schema.' }
    }
    return archResult('single_server_webapp', users, budget, components, [
      { option: 'Kubernetes (EKS)', because: 'At this scale your app runs comfortably on one server. The EKS control plane alone costs ~₹6,000/month before any workload.' },
      { option: 'DocumentDB (managed MongoDB)', because: 'Smallest instance is ~₹6,500/month — several times your whole budget.' },
      { option: 'Load balancer', because: 'Only needed with more than one backend server. You have one.' },
      ...(strict ? [] : [{ option: 'Multi-AZ database', because: 'You said an hour of downtime is acceptable. Multi-AZ would double the database cost.' }]),
    ])
  },

  async chat(message, state = {}) {
    await delay(700)
    const t = message.toLowerCase()
    const reply = (msg, next = state) => ({ message: { id: crypto.randomUUID(), role: 'ward', ...msg }, state: next })
    const referent = state.referentId ? byId(state.referentId) : null

    if (/\b(delete|terminate|stop|kill|shut ?down|remove)\b/.test(t)) {
      const target = resources.find((r) => t.includes(r.id) || t.includes(r.name)) ?? referent
      return reply({
        intent: 'REFUSE',
        text: 'Ward has read-only access to your account by design, so it can’t change resources. Here’s how to do it yourself:',
        command: target?.type === 'ec2' ? `aws ec2 stop-instances --instance-ids ${target.id} --region ${target.region}` : 'aws ec2 stop-instances --instance-ids <instance-id>',
        consoleUrl: 'https://console.aws.amazon.com/ec2/home?region=ap-south-1#Instances:',
      })
    }

    if (/(create|make|add|set up) (a )?(rule|guardrail)|doesn.?t happen again|prevent this/.test(t)) {
      const draft = referent && isGpu(referent)
        ? `No GPU instance runs more than 6 hours`
        : referent?.type === 'ebs' ? 'Flag EBS volumes unattached for more than 7 days'
        : referent?.type === 'nat' ? 'Alert if a NAT Gateway exists' : null
      if (!draft) {
        return reply({ intent: 'ACT', text: 'Which resource should the rule be about? Ask me about something first — e.g. "what is costing me the most?" — then say "create a rule for that".' })
      }
      return reply({
        intent: 'ACT',
        text: `I generalised that incident into a rule. Check the wording before Ward compiles it — this is where you correct it if it’s too broad or too narrow.`,
        draftRule: draft,
      })
    }

    if (/(deploy|host|architecture|need a|recommend|set up my|launch my)/.test(t)) {
      return reply({
        intent: 'ADVISE',
        text: 'That’s an architecture question — the Architect will ask a couple of questions and recommend the simplest setup that fits your budget.',
        link: { to: `/architect?q=${encodeURIComponent(message)}`, label: 'Open in Architect' },
      })
    }

    if (/why/.test(t) && /(bill|spend|cost|increase|higher|more)/.test(t)) {
      return reply({
        intent: 'EXPLAIN',
        text: 'Your spend rose ₹3,670 over the last 7 days. ₹2,840 of that is one GPU instance, ml-training (g5.xlarge), which ran 43 hours longer than usual.',
        link: { to: '/detective', label: 'Open the full investigation' },
      }, { ...state, referentId: 'i-0a1f2' })
    }

    if (/why is (this|it|that)|what is (this|it|that)/.test(t)) {
      if (!referent) return reply({ intent: 'EXPLAIN', text: 'Which resource do you mean? Ask me to list something first, then refer to it.' })
      return reply({
        intent: 'EXPLAIN',
        text: `${referent.name} (${referent.id}) is ${referent.instanceType ?? referent.type} in ${referent.region}, created ${Math.round((Date.now() - new Date(referent.launchedAt)) / 86_400_000)} days ago. ${
          referent.tags.Owner ? `It’s tagged Owner=${referent.tags.Owner}.` : 'It has no Owner tag, so Ward can’t tell who launched it.'
        } It costs ₹${round(referent.costPerHour * 24)}/day.`,
      })
    }

    const columns = [
      { key: 'name', label: 'Name' }, { key: 'id', label: 'ID' }, { key: 'instanceType', label: 'Type' },
      { key: 'runtime', label: 'Running' }, { key: 'perDay', label: '₹/day' },
    ]
    const toRow = (r) => ({ id: r.id, name: r.name, instanceType: r.instanceType ?? r.type, runtime: r.running ? `${round(runtime(r))}h` : '—', perDay: round(r.costPerHour * 24) })

    if (/(cost|expensive|spend|most|money)/.test(t)) {
      const top = [...resources].filter((r) => r.running).sort((a, b) => b.costPerHour - a.costPerHour).slice(0, 5)
      const total = round(top.reduce((s, r) => s + r.costPerHour * 24, 0))
      return reply({
        intent: 'QUERY',
        text: (() => {
          // Only name a single "largest" when it actually stands alone at the top.
          const perDay = (r) => round(r.costPerHour * 24)
          const tied = top.filter((r) => perDay(r) === perDay(top[0]))
          const lead = tied.length > 1
            ? `${tied.map((r) => r.name).join(' and ')} are tied for the largest at ₹${perDay(top[0]).toLocaleString('en-IN')}/day each.`
            : `${top[0].name} is the largest at ₹${perDay(top[0]).toLocaleString('en-IN')}/day.`
          return `Your top ${top.length} running resources cost ₹${total.toLocaleString('en-IN')}/day together. ${lead}`
        })(),
        columns, rows: top.map(toRow), asOf: INVENTORY_AS_OF,
        suggestions: ['Why is this here?', 'Create a rule so this doesn’t happen again'],
      }, { ...state, referentId: top[0].id })
    }

    if (/(running|servers|instances|machines|ec2)/.test(t)) {
      const running = resources.filter((r) => r.type === 'ec2' && r.running)
      return reply({
        intent: 'QUERY',
        text: `You have ${running.length} EC2 instances running right now, ${running.filter(isGpu).length} of them GPUs.`,
        columns, rows: running.map(toRow), asOf: INVENTORY_AS_OF,
        suggestions: ['What is costing me the most?'],
      }, { ...state, referentId: running.find(isGpu)?.id })
    }

    return reply({
      intent: 'OUT_OF_SCOPE',
      text: 'Ward handles cost, resources and guardrails for your AWS account. Try one of these:',
      suggestions: ['What is currently costing me the most?', 'Show me my running servers', 'Why did my bill go up?', 'I need a database for my college project under ₹500/month'],
    })
  },
}

function archResult(pattern, users, budget, components, whyNot) {
  const total = components.reduce((s, c) => s + c.perMonth, 0)
  return {
    status: 'recommended',
    pattern,
    users,
    budget,
    components,
    estimate: { low: round(total * 0.85), high: round(total * 1.2) },
    withinBudget: budget ? total * 1.2 <= budget : null,
    complexity: 'Beginner-friendly',
    whyNot,
    note: 'Estimate uses on-demand ap-south-1 prices and excludes data transfer. Ward will compare it to your real bill after 30 days.',
  }
}
