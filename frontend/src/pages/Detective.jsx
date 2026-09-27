import { useState } from 'react'
import { Link } from 'react-router-dom'
import { ArrowRight, Clock, Search } from 'lucide-react'
import { api } from '../api/client.js'
import { rupees } from '../lib/format.js'
import { Button, Card, HeroButton, PageHeader, Pill } from '../components/ui.jsx'

const ruleTone = { 'working-but-ignored': 'amber', missing: 'red', none: 'slate' }

export default function Detective() {
  const [report, setReport] = useState(null)
  const [busy, setBusy] = useState(false)

  async function investigate() {
    setBusy(true)
    try {
      setReport(await api.investigate())
    } finally {
      setBusy(false)
    }
  }

  return (
    <>
      <PageHeader title="Cost Detective" subtitle="Traces a bill change back to the specific resources that caused it — and the rule that would have stopped it." />

      {!report && (
        <div className="overflow-hidden rounded-3xl">
          <div className="grain relative bg-arc-600 px-6 py-16 text-center text-white md:py-20">
            <p className="text-sm font-semibold text-white/75">Last 7 days vs the 7 before, resource by resource</p>
            <h2 className="mx-auto mt-3 max-w-2xl font-display text-4xl font-semibold leading-tight md:text-5xl">
              Where did the money go?
            </h2>
            <p className="mx-auto mt-3 max-w-lg text-[15px] text-white/80">
              Every rupee of the change is traced to a resource — and whatever Ward can’t explain is shown, not hidden.
            </p>
            <HeroButton icon={Search} light className="mt-8" onClick={investigate} disabled={busy}>
              {busy ? 'Investigating your account…' : 'Why did my AWS bill increase?'}
            </HeroButton>
          </div>
          <div className="scallop" />
        </div>
      )}

      {/* A newly connected account has nothing to compare against yet — say so rather than
          reporting every resource as new. */}
      {report?.insufficientHistory && (
        <div className="mb-6 flex flex-wrap items-center gap-3 rounded-2xl border border-amber-200 bg-amber-50/60 px-4 py-3.5">
          <Clock size={16} className="shrink-0 text-amber-600" />
          <p className="min-w-0 flex-1 text-[13.5px] text-amber-900">{report.note}</p>
          <Link to="/guardian" className="shrink-0 text-[12px] font-bold text-amber-800 underline-offset-2 hover:underline">
            See what Guardian found instead
          </Link>
        </div>
      )}

      {report && !report.insufficientHistory && (
        <div className="space-y-6">
          <Card className="p-5">
            <div className="flex flex-wrap items-baseline gap-x-4 gap-y-1">
              <span className="text-2xl font-semibold tabular-nums text-slate-500">{rupees(report.from.total)}</span>
              <ArrowRight className="text-slate-400" size={20} />
              <span className="text-2xl font-semibold tabular-nums text-slate-900">{rupees(report.to.total)}</span>
              <span className={`text-lg font-semibold tabular-nums ${report.delta > 0 ? 'text-rose-600' : 'text-emerald-700'}`}>
                {report.delta > 0 ? '↑' : '↓'} {rupees(Math.abs(report.delta))}
              </span>
            </div>
            <p className="mt-1 text-xs text-slate-500">{report.from.label} → {report.to.label}</p>
            <Waterfall report={report} />
          </Card>

          <div className="space-y-4">
            {report.causes.map((c) => (
              <Card key={c.id} className="p-5">
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div>
                    <p className="text-xs font-medium uppercase tracking-wide text-slate-500">{c.service}</p>
                    <p className="mt-1 font-medium text-slate-900">{c.headline}</p>
                  </div>
                  <span className="text-lg font-semibold tabular-nums text-rose-600">+{rupees(c.delta)}</span>
                </div>
                <p className="mt-2 text-sm text-slate-600">{c.detail}</p>
                <p className="mt-2 text-xs text-slate-400">Resource <span className="font-mono">{c.resourceId}</span></p>
                <div className="mt-3 flex flex-wrap items-center justify-between gap-3 rounded-lg bg-slate-50 px-3 py-2">
                  <span className="flex items-center gap-2 text-sm text-slate-700">
                    <Pill tone={ruleTone[c.ruleLink.status]}>{c.ruleLink.status === 'missing' ? 'no rule' : c.ruleLink.status === 'none' ? 'expected' : 'rule ignored'}</Pill>
                    {c.ruleLink.text}
                  </span>
                  {c.suggestedRule && (
                    <Link to={`/rules?draft=${encodeURIComponent(c.suggestedRule)}`}>
                      <Button variant="secondary">Create rule: “{c.suggestedRule}”</Button>
                    </Link>
                  )}
                </div>
              </Card>
            ))}
          </div>
        </div>
      )}
    </>
  )
}

// SRS §29.1 — a bill change is a decomposition, so show it as one. The unattributed row stays even at ₹0.
function Waterfall({ report }) {
  const rows = [...report.causes.map((c) => ({ label: c.service, value: c.delta })), { label: 'Unattributed', value: report.unattributed }]
  const max = Math.max(...rows.map((r) => r.value), 1)
  return (
    <div className="mt-5 space-y-2">
      {rows.map((r) => (
        <div key={r.label} className="grid grid-cols-[8rem_1fr_5rem] items-center gap-3 text-sm">
          <span className={r.label === 'Unattributed' ? 'text-slate-400' : 'text-slate-700'}>{r.label}</span>
          <div className="h-3 rounded bg-slate-100">
            <div className={`h-3 rounded ${r.label === 'Unattributed' ? 'bg-slate-300' : 'bg-rose-500'}`} style={{ width: `${(r.value / max) * 100}%` }} />
          </div>
          <span className="text-right tabular-nums text-slate-700">+{rupees(r.value)}</span>
        </div>
      ))}
    </div>
  )
}
