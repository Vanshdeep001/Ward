// Every rule the UI offers or suggests must compile in the mock engine. Run: node scripts/check-templates.mjs
globalThis.crypto ??= (await import('node:crypto')).webcrypto
const { mock } = await import('../src/api/mock/engine.js')

const offered = [
  // Starter rulebook (SRS §2)
  'Stay inside the free tier',
  'Nothing runs longer than 6 hours unattended',
  'No GPU instance without an expiry tag',
  'Warn before monthly spend crosses the budget',
  'Nothing left running over a weekend',
  'Flag any resource with no owner tag',
  // Composer examples
  'Never let a GPU instance run more than 6 hours',
  'Flag EBS volumes unattached for more than 7 days',
  'No resources outside ap-south-1',
  // Clarifier output
  'Flag anything costing more than ₹50/day running more than 6 hours',
  // Detective / Guardian / Copilot suggestions
  'GPU instances must not run longer than 6 hours',
  'No RDS instance larger than db.t3.micro',
  'Alert if a NAT Gateway exists in a dev VPC',
  'No RDS instance may be publicly accessible',
  'No security group may allow SSH from 0.0.0.0/0',
  'GPU instances should not run over weekends',
]

let failed = 0
for (const rule of offered) {
  const r = await mock.compileRule(rule, { skipClarify: true })
  const ok = r.status === 'compiled'
  if (!ok) failed++
  console.log(`${ok ? 'ok  ' : 'FAIL'} ${(r.kind ?? '-').padEnd(14)} ${rule}${ok ? ` → ${r.simulation.matched.length}/${r.simulation.population}` : ''}`)
}
const vague = await mock.compileRule("Don't let anything expensive run too long")
console.log(`${vague.status === 'needs-clarification' ? 'ok  ' : 'FAIL'} clarify        ${vague.questions?.map((q) => q.term).join(', ')}`)
if (vague.status !== 'needs-clarification') failed++
process.exit(failed ? 1 : 0)
