import { Link } from 'react-router-dom'
import { ArrowRight, Search } from 'lucide-react'
import { useAlerts, useCosts, useFindings } from '../api/hooks.js'
import { ago, rupees } from '../lib/format.js'
import { Button, Card, CardHeader, HeroButton, Loading, Pill, Stat } from '../components/ui.jsx'
import SpendChart from '../components/SpendChart.jsx'
import SavingsCard from '../components/SavingsCard.jsx'

export default function Dashboard() {
  const costs = useCosts()
  const alerts = useAlerts()
  const findings = useFindings()

  if (costs.isLoading) return <Loading />
  const c = costs.data
  const budgetPct = Math.round((c.projectedMonthEnd / c.budget) * 100)
  const openAlerts = alerts.data?.filter((a) => a.status === 'open') ?? []
  const burnPerDay = c.daily.slice(-7).reduce((sum, d) => sum + d.amount, 0) / 7

  return (
    <>
      {/* Hero: the account in one sentence, then the one question people actually ask. */}
      <section className="mb-10">
        <p className="text-sm font-semibold text-slate-500">{greeting()} — here’s your AWS account right now</p>
        <h1 className="mt-3 max-w-4xl font-display text-4xl font-semibold leading-[1.08] text-ink md:text-[3.25rem]">
          You’re spending <span className="text-arc-600">{rupees(burnPerDay)}</span> a day, on track for{' '}
          <span className={budgetPct > 100 ? 'text-coral-600' : 'text-ink'}>{rupees(c.projectedMonthEnd)}</span> this month.
        </h1>
        <p className="mt-4 max-w-2xl text-[15px] leading-relaxed text-slate-600">
          {budgetPct > 100
            ? `That’s ${budgetPct - 100}% over your ${rupees(c.budget)} budget. The Detective can trace exactly which resources changed.`
            : `That’s ${budgetPct}% of your ${rupees(c.budget)} budget.`}
        </p>
        <div className="mt-6 flex flex-wrap items-center gap-3">
          <Link to="/detective"><HeroButton icon={Search}>Why did my bill increase?</HeroButton></Link>
          <Link to="/copilot"><Button variant="secondary" className="rounded-2xl px-4 py-3">Ask Ward a question</Button></Link>
        </div>
      </section>

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <Stat label="Month to date" value={rupees(c.monthToDate)} hint={`Budget ${rupees(c.budget)}`} />
        <Stat
          label="Projected month end"
          value={rupees(c.projectedMonthEnd)}
          hint={`${budgetPct}% of budget, at the last 7 days’ burn rate`}
          tone={budgetPct > 100 ? 'red' : budgetPct > 85 ? 'amber' : 'slate'}
        />
        <Stat label="Open alerts" value={openAlerts.length} hint={`${alerts.data?.length ?? 0} in the last 30 days`} tone={openAlerts.length ? 'amber' : 'slate'} />
        <Stat label="Net saved, 30 days" value={rupees(c.savings.avoided - c.savings.wardCost)} hint={`after Ward’s own ${rupees(c.savings.wardCost)}`} tone="green" />
      </div>

      <div className="mt-6 grid items-start gap-6 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardHeader title="Daily spend" subtitle="Last 60 days, from Cost Explorer" />
          <div className="p-4"><SpendChart data={c.daily} height={300} /></div>
        </Card>

        <SavingsCard savings={c.savings} />
      </div>

      <div className="mt-6 grid gap-6 lg:grid-cols-2">
        <Card>
          <CardHeader title="Open alerts" action={<Link to="/alerts" className="text-xs text-arc-700 hover:underline">All alerts</Link>} />
          <ul className="divide-y divide-slate-100">
            {openAlerts.map((a) => (
              <li key={a.id} className="flex items-start gap-3 px-5 py-3 text-sm">
                <Pill tone={a.level === 'alert' ? 'red' : 'amber'}>{a.level}</Pill>
                <div className="min-w-0">
                  <p className="text-slate-800">{a.message}</p>
                  <p className="mt-0.5 text-xs text-slate-500">{ago(a.at)} · {a.rule.english}</p>
                </div>
              </li>
            ))}
            {!openAlerts.length && <li className="px-5 py-6 text-center text-sm text-slate-500">All quiet.</li>}
          </ul>
        </Card>

        <Card>
          <CardHeader title="Guardian — this week’s top 3" action={<Link to="/guardian" className="text-xs text-arc-700 hover:underline">All findings</Link>} />
          <ul className="divide-y divide-slate-100">
            {findings.data?.slice(0, 3).map((f) => (
              <li key={f.id} className="flex items-center justify-between gap-3 px-5 py-3 text-sm">
                <span className="text-slate-800">{f.title}</span>
                {f.monthlyImpact ? <span className="shrink-0 text-xs text-slate-500">{rupees(f.monthlyImpact)}/mo</span> : <Pill tone={f.severity === 'urgent' ? 'red' : 'slate'}>{f.family}</Pill>}
              </li>
            ))}
          </ul>
          <Link to="/guardian" className="flex items-center gap-1 border-t border-slate-100 px-5 py-3 text-xs text-slate-500 hover:text-arc-700">
            Review and turn findings into guardrails <ArrowRight size={12} />
          </Link>
        </Card>
      </div>
    </>
  )
}

function greeting() {
  const h = new Date().getHours()
  return h < 12 ? 'Good morning' : h < 17 ? 'Good afternoon' : 'Good evening'
}
