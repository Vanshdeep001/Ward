// Mock account used until the FastAPI backend exists.
// Everything the UI shows is derived from these tables, so counts and ₹ figures agree across pages.

const H = 3_600_000
const now = Date.now()
export const hAgo = (h) => new Date(now - h * H).toISOString()
export const dAgo = (d) => hAgo(d * 24)

export const BUDGET = 30_000
export const WARD_OWN_COST = 340
export const INVENTORY_AS_OF = new Date(now - 6 * 60_000).toISOString()

// ₹ per hour, ap-south-1. Mirrors the normalised pricing store (SRS §14.3).
export const PRICING = {
  't2.micro': 0.97,
  't3.micro': 0.94,
  't3.small': 1.88,
  't3.medium': 3.76,
  't3.large': 7.52,
  'g4dn.xlarge': 101.14,
  'g5.xlarge': 66.05,
  'db.t3.micro': 1.72,
  'db.t3.medium': 6.0,
  'nat-gateway': 3.9,
  'ebs-gp3-20gb': 0.19,
  's3-standard': 0.11,
}

const GPU_FAMILIES = ['p', 'g', 'inf']
export const isGpu = (r) => r.type === 'ec2' && GPU_FAMILIES.some((f) => r.instanceType?.startsWith(f))

const ec2 = (id, name, instanceType, runningHours, tags, extra = {}) => ({
  id,
  name,
  type: 'ec2',
  instanceType,
  region: 'ap-south-1',
  running: runningHours != null,
  launchedAt: runningHours != null ? hAgo(runningHours) : dAgo(6),
  costPerHour: runningHours != null ? PRICING[instanceType] : 0,
  tags,
  state: 'watched',
  ...extra,
})

export const resources = [
  ec2('i-0a1f2', 'ml-training', 'g5.xlarge', 31, {}, { state: 'alert' }),
  ec2('i-0b3d4', 'riya-notebook', 'g4dn.xlarge', 9, { Owner: 'riya' }, { state: 'warning' }),
  ec2('i-0c7e1', 'arjun-finetune', 'g4dn.xlarge', 2, { Owner: 'arjun' }),
  ec2('i-0d2a9', 'attendance-api', 't3.small', 120, { Owner: 'team', Environment: 'production' }),
  ec2('i-0e5b3', 'bastion', 't3.micro', 300, { Owner: 'team' }),
  ec2('i-0f8c4', 'old-jenkins', 't3.medium', null, { Owner: 'team' }),
  ec2('i-01a2b', 'test-server', 't3.micro', 50, {}, { state: 'warning' }),
  ec2('i-02c3d', 'vansh-lab', 't2.micro', null, { Owner: 'vansh' }),
  ec2('i-03e4f', 'vansh-api', 't3.small', 20, { Owner: 'vansh' }),
  ec2('i-04g5h', 'scratch', 't3.micro', 4, {}, { state: 'warning' }),
  ec2('i-05i6j', 'demo-box', 't3.micro', null, {}, { state: 'snoozed', snoozedUntil: hAgo(-20) }),
  ec2('i-06k7l', 'worker', 't3.small', 70, { Owner: 'team' }),
  ec2('i-07m8n', 'riya-dev', 't3.micro', 8, { Owner: 'riya' }),
  ec2('i-08o9p', 'forgotten-us', 't3.large', 15, {}, { region: 'us-east-1', state: 'warning' }),
  {
    id: 'db-attendance', name: 'attendance-db', type: 'rds', instanceType: 'db.t3.micro', region: 'ap-south-1',
    running: true, launchedAt: dAgo(40), costPerHour: PRICING['db.t3.micro'], tags: { Owner: 'team' },
    publiclyAccessible: false, state: 'watched',
  },
  {
    id: 'db-0d6', name: 'hackathon-db', type: 'rds', instanceType: 'db.t3.medium', region: 'ap-south-1',
    running: true, launchedAt: dAgo(12), costPerHour: PRICING['db.t3.medium'], tags: {},
    publiclyAccessible: true, state: 'alert',
  },
  ...['vol-01', 'vol-02', 'vol-03'].map((id) => ({
    id, name: `${id} (20 GB gp3)`, type: 'ebs', region: 'ap-south-1', running: false, attached: false,
    launchedAt: dAgo(9), costPerHour: PRICING['ebs-gp3-20gb'], tags: {}, state: 'warning',
  })),
  {
    id: 'vol-04', name: 'vol-04 (20 GB gp3)', type: 'ebs', region: 'ap-south-1', running: false, attached: true,
    launchedAt: dAgo(40), costPerHour: PRICING['ebs-gp3-20gb'], tags: { Owner: 'team' }, state: 'watched',
  },
  {
    id: 'nat-0c5', name: 'nat-0c5 (vpc-dev-2)', type: 'nat', region: 'ap-south-1', running: true,
    launchedAt: dAgo(8), costPerHour: PRICING['nat-gateway'], tags: {}, state: 'watched',
  },
  {
    id: 's3-exports', name: 'attendance-exports', type: 's3', region: 'ap-south-1', running: false,
    launchedAt: dAgo(40), costPerHour: PRICING['s3-standard'], tags: { Owner: 'team' }, state: 'watched',
  },
  {
    id: 'sg-0ssh', name: 'launch-wizard-1', type: 'sg', region: 'ap-south-1', running: false,
    launchedAt: dAgo(12), costPerHour: 0, tags: {}, openPorts: [{ port: 22, cidr: '0.0.0.0/0' }], state: 'alert',
  },
]

export const byId = (id) => resources.find((r) => r.id === id)

// Historical GPU sessions over 30 days — the basis for time-travel simulation (SRS §16.3).
// actedOn: whether the owner stopped it within 2h of an alert (SRS §17.3 attribution window).
export const gpuSessions = [
  { resourceId: 'i-0a1f2', daysAgo: 1.3, runtime: 31, actedOn: false },
  { resourceId: 'i-0b3d4', daysAgo: 0.4, runtime: 9, actedOn: false },
  { resourceId: 'i-0a1f2', daysAgo: 3, runtime: 14, actedOn: true },
  { resourceId: 'i-0a1f2', daysAgo: 5, runtime: 11, actedOn: true },
  { resourceId: 'i-0b3d4', daysAgo: 9, runtime: 7.5, actedOn: true },
  { resourceId: 'i-0c7e1', daysAgo: 12, runtime: 4, actedOn: false },
  { resourceId: 'i-0b3d4', daysAgo: 15, runtime: 10, actedOn: false },
  { resourceId: 'i-0a1f2', daysAgo: 18, runtime: 8, actedOn: true },
  { resourceId: 'i-0c7e1', daysAgo: 21, runtime: 5.5, actedOn: false },
  { resourceId: 'i-0a1f2', daysAgo: 24, runtime: 13, actedOn: true },
  { resourceId: 'i-0b3d4', daysAgo: 27, runtime: 3, actedOn: false },
]

// Last four Saturdays the GPU was left on — the behavioural pattern (SRS §31.2).
export const weekendEvidence = [
  { weeksAgo: 0, hours: 38 },
  { weeksAgo: 1, hours: 41 },
  { weeksAgo: 3, hours: 29 },
].map(({ weeksAgo, hours }) => {
  const d = new Date(now)
  d.setDate(d.getDate() - ((d.getDay() + 1) % 7) - 7 * weeksAgo) // most recent Saturday, then back
  d.setHours(2, 0, 0, 0)
  return { date: d.toISOString(), resourceId: 'i-0a1f2', hours }
})

export const rules = [
  {
    id: 'r1', english: 'No GPU instance runs more than 6 hours', status: 'active', createdAt: dAgo(34),
    firesLast30d: 8, actedOn: 5, savings30d: 4774, quality: 87,
    breakdown: {
      specificity: { score: 23, max: 25, note: 'Filters on p/g/inf families + running state' },
      verifiability: { score: 20, max: 20, note: 'Passed verifier on first attempt with 5/5 fixtures' },
      actionability: { score: 16, max: 20, note: 'Suggests stopping, names instance ID in alert' },
      signalRate: { score: 16, max: 20, note: '5 of 8 alerts acted on (63% action rate)' },
      stability: { score: 12, max: 15, note: 'Burstier on weekends when training jobs run' },
    },
    improvementTip: 'Name the instance stop command in alert text for 1-click mitigation (+4).',
    yaml: `policies:
  - name: ec2-gpu-max-runtime-6h
    resource: aws.ec2
    filters:
      - State.Name: running
      - type: value
        key: InstanceType
        op: regex
        value: ^(p|g|inf)
      - type: instance-age
        op: greater-than
        hours: 6`,
  },
  {
    id: 'r2', english: 'Flag any resource with no owner tag', status: 'active', createdAt: dAgo(34),
    firesLast30d: 11, actedOn: 3, savings30d: 0, quality: 64,
    breakdown: {
      specificity: { score: 14, max: 25, note: 'Matches 8 of your 21 resources across all services' },
      verifiability: { score: 20, max: 20, note: 'Clean schema validation for tag:Owner: absent' },
      actionability: { score: 12, max: 20, note: 'Needs explicit tagging instruction' },
      signalRate: { score: 8, max: 20, note: 'Only 3 of 11 alerts acted on (27% action rate)' },
      stability: { score: 10, max: 15, note: 'Fires continually until resources are tagged' },
    },
    improvementTip: 'Add an auto-tagging suggestion or default team owner tag to raise actionability (+8).',
    yaml: `policies:
  - name: require-owner-tag
    resource: aws.ec2
    filters:
      - "tag:Owner": absent`,
  },
  {
    id: 'r3', english: 'Nothing left running over a weekend', status: 'active', createdAt: dAgo(34),
    firesLast30d: 4, actedOn: 2, savings30d: 1920, quality: 72,
    breakdown: {
      specificity: { score: 19, max: 25, note: 'Exempts production tag, targets non-prod EC2' },
      verifiability: { score: 18, max: 20, note: 'Verified with offhour timezone filters' },
      actionability: { score: 15, max: 20, note: 'Clear stop action' },
      signalRate: { score: 10, max: 20, note: '2 of 4 alerts acted on' },
      stability: { score: 10, max: 15, note: 'Only triggers on Saturdays and Sundays' },
    },
    improvementTip: 'Add Monday 08:00 auto-restart reminder to reduce user hesitation (+6).',
    yaml: `policies:
  - name: ec2-no-weekend-running
    resource: aws.ec2
    filters:
      - State.Name: running
      - "tag:Environment": absent
      - type: offhour
        weekends: true
        default_tz: Asia/Kolkata`,
  },
  {
    id: 'r4', english: 'Warn before monthly spend crosses the budget', status: 'active', createdAt: dAgo(34),
    firesLast30d: 1, actedOn: 1, savings30d: 0, quality: 91,
    breakdown: {
      specificity: { score: 24, max: 25, note: 'Evaluates account-wide forecast against ₹10,000 budget' },
      verifiability: { score: 20, max: 20, note: 'Budget trigger verified' },
      actionability: { score: 18, max: 20, note: 'Links to Cost Detective investigation' },
      signalRate: { score: 20, max: 20, note: '100% action rate' },
      stability: { score: 9, max: 15, note: 'Fires once when threshold breaches' },
    },
    improvementTip: 'Great rule. Add early forecast warnings at 75% for earlier notice.',
    yaml: `policies:
  - name: budget-warning-monthly
    resource: aws.account
    filters:
      - type: budget
        threshold_percent: 85`,
  },
  {
    id: 'r5', english: 'Stay inside the free tier', status: 'active', createdAt: dAgo(34),
    firesLast30d: 2, actedOn: 2, savings30d: 610, quality: 78,
    breakdown: {
      specificity: { score: 20, max: 25, note: 'Checks 750h t2/t3.micro & 30GB EBS allowances' },
      verifiability: { score: 17, max: 20, note: 'Composite filter across multiple resources' },
      actionability: { score: 15, max: 20, note: 'Identifies unattached EBS and extra compute' },
      signalRate: { score: 16, max: 20, note: 'Both alerts acted on' },
      stability: { score: 10, max: 15, note: 'Fires toward end of billing period' },
    },
    improvementTip: 'Add per-service usage headroom meters (+5).',
    yaml: `policies:
  - name: free-tier-guardrail
    resource: aws.ebs
    filters:
      - Attachments: []`,
  },
]

export const conflicts = [
  {
    id: 'c1',
    category: 'contradiction',
    severity: 'critical',
    title: 'Contradiction: Minimum training run vs execution limit',
    ruleA: { id: 'draft-train', english: 'Instances must run at least 8 hours for training jobs' },
    ruleB: { id: 'r1', english: 'No GPU instance runs more than 6 hours' },
    detail: 'These cannot both hold. Any training job violates one of them.',
    impact: 'GPU training instances (e.g. i-0a1f2) are guaranteed to trigger an alert at hour 6 while the workload is required to run for 8 hours.',
    suggestion: 'Scope Rule A to "tag:workload=training" and exempt training workloads from Rule B.',
    actionText: 'Exempt training tag',
  },
  {
    id: 'c2',
    category: 'subsumption',
    severity: 'warning',
    title: 'Subsumption: Redundant g4dn instance rule',
    ruleA: { id: 'draft-g4dn', english: 'No g4dn.xlarge over 6 hours' },
    ruleB: { id: 'r1', english: 'No GPU instance runs more than 6 hours' },
    detail: 'Rule "No GPU instance runs more than 6 hours" already matches g4dn, g5, and p-family instances. Rule A is completely subsumed.',
    impact: 'Generates duplicate alerts on i-0b3d4 and i-0c7e1 for the exact same event.',
    suggestion: 'Archive Rule A. It adds zero additional protection and increases alert fatigue.',
    actionText: 'Archive redundant rule',
  },
  {
    id: 'c3',
    category: 'overlap',
    severity: 'warning',
    title: 'Overlap: Double alert on untagged resources',
    ruleA: { id: 'r2', english: 'Flag any resource with no owner tag' },
    ruleB: { id: 'draft-untagged', english: 'Untagged resources are flagged' },
    detail: 'Overlap on 8 of your 21 current resources — those resources trigger two distinct notifications for the same issue.',
    impact: '8 resources send 2 alerts every evaluation window.',
    suggestion: 'Merge into a single tag governance policy or suppress Rule B where Rule A already fired.',
    actionText: 'Merge tag rules',
  },
  {
    id: 'c4',
    category: 'dead',
    severity: 'info',
    title: 'Dead Rule: No matching infrastructure in 90 days',
    ruleA: { id: 'draft-rds-r5', english: 'No RDS instance larger than db.r5.2xlarge' },
    detail: 'Has not matched in 90 days. Your account currently runs only db.t3 instances.',
    impact: '0 alerts fired. May be an intentional preventative guardrail against costly accidental database provisioning.',
    suggestion: 'Keep as a preventive guardrail, or archive if RDS provisioning is managed via Terraform.',
    actionText: 'Keep as preventive guardrail',
  },
]

export const alerts = [
  {
    id: 'a1', resourceId: 'i-0a1f2', ruleId: 'r1', level: 'alert', at: hAgo(25), status: 'open',
    message: 'ml-training (g5.xlarge) has been running 31h — limit is 6h.', projectedMonthly: 66.05 * 24 * 30,
  },
  {
    id: 'a2', resourceId: 'i-0b3d4', ruleId: 'r1', level: 'warning', at: hAgo(3), status: 'open',
    message: 'riya-notebook (g4dn.xlarge) has been running 9h — limit is 6h.', projectedMonthly: 101.14 * 24 * 30,
  },
  {
    id: 'a3', resourceId: 'db-0d6', ruleId: 'r2', level: 'alert', at: hAgo(40), status: 'open',
    message: 'hackathon-db has no Owner tag and is publicly accessible.',
  },
  {
    id: 'a4', resourceId: 'i-05i6j', ruleId: 'r2', level: 'warning', at: dAgo(2), status: 'snoozed',
    message: 'demo-box has no Owner tag.', snoozedUntil: hAgo(-20),
  },
  {
    id: 'a5', resourceId: 'i-0a1f2', ruleId: 'r3', level: 'alert', at: dAgo(6), status: 'resolved',
    message: 'ml-training ran through the weekend (41h).',
  },
  {
    id: 'a6', resourceId: 'vol-01', ruleId: 'r5', level: 'warning', at: dAgo(4), status: 'resolved',
    message: '3 unattached EBS volumes are outside the free tier allowance.',
  },
]

// 60 days of daily spend. Prior week totals ₹5,240, this week ₹8,910 — the Cost Detective scenario.
function spread(total, days, seed) {
  const weights = Array.from({ length: days }, (_, i) => 1 + 0.25 * Math.sin(seed + i * 1.7))
  const sum = weights.reduce((a, b) => a + b, 0)
  return weights.map((w) => (w / sum) * total)
}

export const dailySpend = [
  ...spread(20_400, 46, 1),
  ...spread(5_240, 7, 3),
  ...spread(8_910, 7, 5),
].map((amount, i, arr) => ({ date: dAgo(arr.length - 1 - i), amount: Math.round(amount) }))

export const predictions = [
  { month: 'Apr', predicted: 3_900, actual: 4_210 },
  { month: 'May', predicted: 5_600, actual: 5_180 },
  { month: 'Jun', predicted: 7_200, actual: 8_050 },
  { month: 'Jul', predicted: 9_400, actual: 9_120 },
  { month: 'Aug', predicted: 11_800, actual: 12_640 },
  { month: 'Sep', predicted: 14_200, actual: null },
]
