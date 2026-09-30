import { Link } from 'react-router-dom'
import { Activity, ArrowRight, BellRing, PiggyBank, Radar, Search, Settings2, ShieldAlert, Trash2, TrendingUp, Wallet } from 'lucide-react'
import { useAlerts, useConnection, useCosts, useFindings, useResources } from '../api/hooks.js'
import ConnectBanner from '../components/ConnectBanner.jsx'
import RiskBoard from '../components/RiskBoard.jsx'
import { rupees } from '../lib/format.js'
import { Button, ErrorState, HeroButton, Loading, Panel, PanelLink, Stat } from '../components/ui.jsx'
import SpendChart from '../components/SpendChart.jsx'
import BurnBreakdown from '../components/BurnBreakdown.jsx'
import SavingsCard from '../components/SavingsCard.jsx'

export default function Dashboard() {
  const costs = useCosts()
  const alerts = useAlerts()
  const findings = useFindings()
  const resources = useResources()
  const { isDemo } = useConnection()

  if (costs.isLoading) return <Loading label="Reading your account…" />
  if (!costs.data) return <ErrorState error={costs.error} onRetry={() => costs.refetch()} />
  const c = costs.data
  const budgetPct = Math.round((c.projectedMonthEnd / c.budget) * 100)
  const openAlerts = alerts.data?.filter((a) => a.status === 'open') ?? []
  const burnPerDay = c.daily.slice(-7).reduce((sum, d) => sum + d.amount, 0) / 7
  // What the budget allows per day — the reference the trend is read against.
  const now = new Date()
  const budgetPerDay = c.budget / new Date(now.getFullYear(), now.getMonth() + 1, 0).getDate()

  return (
    <>
      {isDemo && <ConnectBanner />}

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
        <Stat label="Month to date" value={rupees(c.monthToDate)} hint={`Budget ${rupees(c.budget)}`} icon={Wallet} />
        <Stat
          label="Projected month end"
          value={rupees(c.projectedMonthEnd)}
          hint={`${budgetPct}% of budget, at the last 7 days’ burn rate`}
          tone={budgetPct > 100 ? 'red' : budgetPct > 85 ? 'amber' : 'slate'}
          icon={TrendingUp}
        />
        <Stat label="Open alerts" value={openAlerts.length} hint={`${alerts.data?.length ?? 0} in the last 30 days`} tone={openAlerts.length ? 'amber' : 'slate'} icon={BellRing} />
        <Stat label="Net saved, 30 days" value={rupees(c.savings.avoided - c.savings.wardCost)} hint={`after Ward’s own ${rupees(c.savings.wardCost)}`} tone="green" icon={PiggyBank} />
      </div>

      <div className="mt-6 grid items-stretch gap-6 lg:grid-cols-3">
        <Panel
          className="lg:col-span-2"
          eyebrow={c.source === 'cost-explorer' ? `Last ${c.daily.length} days · Cost Explorer` : `${c.daily.length} day${c.daily.length === 1 ? '' : 's'} · priced from inventory`}
          title="Daily spend"
          action={
            <span className="shrink-0 text-right">
              <span className="block font-display text-[1.05rem] font-semibold leading-none text-ink">{rupees(burnPerDay)}</span>
              <span className="mt-1 block text-[9.5px] font-bold uppercase tracking-widest text-slate-400">7-day average</span>
            </span>
          }
        >
          <div className="p-4"><SpendChart data={c.daily} height={272} budgetPerDay={budgetPerDay} /></div>
          {c.sourceNote && c.source !== 'cost-explorer' && (
            <p className="border-t border-slate-100 bg-amber-50/50 px-5 py-2.5 text-[12px] text-amber-800">{c.sourceNote}</p>
          )}
          {resources.data && <BurnBreakdown resources={resources.data.items} />}
        </Panel>

        <SavingsCard savings={c.savings} />
      </div>

      <div className="mt-6 grid items-stretch gap-6 lg:grid-cols-3">
        <RiskBoard alerts={alerts.data ?? []} isLoading={alerts.isLoading} />
        <GuardianPanel findings={findings.data?.slice(0, 3) ?? []} />
      </div>
    </>
  )
}

function greeting() {
  const h = new Date().getHours()
  return h < 12 ? 'Good morning' : h < 17 ? 'Good afternoon' : 'Good evening'
}


const FAMILY = {
  security: { icon: ShieldAlert, chip: 'bg-coral-50 text-coral-600 ring-coral-100' },
  waste: { icon: Trash2, chip: 'bg-amber-50 text-amber-700 ring-amber-200' },
  behavioural: { icon: Activity, chip: 'bg-violet-50 text-violet-700 ring-violet-200' },
  configuration: { icon: Settings2, chip: 'bg-slate-100 text-slate-600 ring-slate-200' },
}

// Findings as a ranked list: the rank is the anchor, the money is the payoff, and the
// c7n filter that produced it sits underneath as the receipt.
function GuardianPanel({ findings }) {
  const biggest = Math.max(...findings.map((f) => f.monthlyImpact || 0), 1)
  const total = findings.reduce((sum, f) => sum + (f.monthlyImpact || 0), 0)

  return (
    <Panel
      eyebrow="Ranked by impact × confidence"
      title="Guardian"
      aura="lilac"
      icon={Radar}
      action={<PanelLink to="/guardian">All</PanelLink>}
    >
      <div className="border-b border-slate-100 bg-gradient-to-b from-violet-50/50 to-transparent px-5 pb-4 pt-4">
        <p className="text-[10px] font-bold uppercase tracking-[0.14em] text-violet-700/70">Nobody wrote a rule for these</p>
        <p className="mt-1 font-display text-[1.9rem] font-semibold leading-none text-ink">
          {total ? `${rupees(total)}/mo` : `${findings.length} to fix`}
        </p>
        <p className="mt-1.5 text-[11.5px] font-medium text-slate-500">
          {findings.filter((f) => f.severity === 'urgent').length} urgent · {findings.length} this week
        </p>
      </div>

      <ul className="flex-1 divide-y divide-slate-100">
        {findings.map((f, i) => {
          const fam = FAMILY[f.family] ?? FAMILY.configuration
          const Icon = fam.icon
          const urgent = f.severity === 'urgent'
          return (
            <li key={f.id} className="relative">
              {urgent && <span aria-hidden className="absolute inset-y-2 left-0 w-[3px] rounded-r-full bg-coral-400" />}
              <Link to="/guardian" className="group block px-5 py-3.5 transition hover:bg-slate-50/70">
                <div className="flex items-start gap-3">
                  <span className="mt-px font-display text-[1.3rem] font-semibold leading-none text-slate-200 transition group-hover:text-arc-300">
                    {String(i + 1).padStart(2, '0')}
                  </span>
                  <div className="min-w-0 flex-1">
                    <p className="text-[13.5px] font-semibold leading-snug text-ink">{f.title}</p>
                    <p className="mt-1 flex items-center gap-1.5 text-[11px] text-slate-500">
                      <Icon size={11} className="shrink-0 text-slate-400" />
                      <span className="truncate font-mono text-[10.5px]">{f.source ?? f.family}</span>
                    </p>
                  </div>
                </div>

                {/* Costed findings get a bar against the biggest; the rest carry their severity. */}
                <div className="mt-2.5 flex items-center gap-3 pl-[1.9rem]">
                  {f.monthlyImpact ? (
                    <>
                      <span className="h-2 flex-1">
                        <span
                          className="block h-full rounded-r-[4px] bg-violet-400 transition-all duration-500"
                          style={{ width: `${Math.max((f.monthlyImpact / biggest) * 100, 3)}%` }}
                        />
                      </span>
                      <span className="shrink-0 text-[11.5px] font-bold tabular-nums text-ink">{rupees(f.monthlyImpact)}/mo</span>
                    </>
                  ) : (
                    <span className={`rounded-full px-2 py-0.5 text-[10.5px] font-bold ring-1 ring-inset ${fam.chip}`}>
                      {urgent ? 'urgent · fix today' : f.family}
                    </span>
                  )}
                </div>
              </Link>
            </li>
          )
        })}
      </ul>
      <Link
        to="/guardian"
        className="group mt-auto flex items-center justify-between gap-2 border-t border-slate-100 bg-slate-50/60 px-5 py-3.5 text-xs font-semibold text-slate-500 transition hover:bg-slate-50 hover:text-arc-700"
      >
        Review and turn findings into guardrails
        <ArrowRight size={13} className="transition group-hover:translate-x-0.5" />
      </Link>
    </Panel>
  )
}
