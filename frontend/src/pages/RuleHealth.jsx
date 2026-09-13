import { useState } from 'react'
import {
  AlertOctagon, AlertTriangle, CheckCircle2, ChevronDown, EyeOff, Layers, RefreshCw, Sparkles, Zap,
} from 'lucide-react'
import { useConflicts, useRules } from '../api/hooks.js'
import { Button, Card, CardHeader, Loading, PageHeader, Pill } from '../components/ui.jsx'

const categoryMeta = {
  contradiction: {
    label: 'Contradiction',
    tone: 'red',
    icon: AlertOctagon,
    desc: 'Two rules cannot both be satisfied simultaneously. Any matching resource is guaranteed to violate one of them.',
  },
  subsumption: {
    label: 'Subsumption',
    tone: 'amber',
    icon: Layers,
    desc: 'One rule matches a strict subset of another rule. The narrower rule is redundant and causes double notifications.',
  },
  overlap: {
    label: 'Overlap',
    tone: 'amber',
    icon: AlertTriangle,
    desc: 'Partial intersection between rules causing duplicate alerts for the same root infrastructure issue.',
  },
  dead: {
    label: 'Dead Rule',
    tone: 'slate',
    icon: EyeOff,
    desc: 'Rule has not matched any resources in 90 days. May be an intentional preventive guardrail or obsolete.',
  },
}

export default function RuleHealth() {
  const { data: conflicts, isLoading: loadingConflicts, refetch } = useConflicts()
  const { data: rules, isLoading: loadingRules } = useRules()
  const [scanning, setScanning] = useState(false)
  const [filter, setFilter] = useState('all')
  const [expandedRule, setExpandedRule] = useState(null)
  const [applied, setApplied] = useState({})

  if (loadingConflicts || loadingRules) return <Loading label="Evaluating rule graph & quality scores…" />

  async function handleScan() {
    setScanning(true)
    await refetch()
    setScanning(false)
  }

  const filteredConflicts = conflicts.filter((c) => filter === 'all' || c.category === filter)
  const criticalCount = conflicts.filter((c) => c.severity === 'critical').length
  const scored = rules.filter((r) => r.quality != null) // new rules stay provisional for two weeks (§22.1)
  const avgQuality = scored.length ? Math.round(scored.reduce((acc, r) => acc + r.quality, 0) / scored.length) : null
  const duplicateRisk = conflicts.filter((c) => c.category === 'overlap').reduce((n, c) => n + (c.affected ?? 0), 0)

  return (
    <>
      <PageHeader
        title="Rule health"
        subtitle="Finds rules that contradict, duplicate or never fire — and scores how useful each one is."
        action={
          <Button variant="secondary" onClick={handleScan} disabled={scanning}>
            <RefreshCw size={15} className={scanning ? 'animate-spin' : ''} />
            {scanning ? 'Scanning rules…' : 'Check my rules'}
          </Button>
        }
      />

      {/* Summary KPI Cards */}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <Card className="p-5">
          <p className="text-xs font-medium uppercase tracking-wide text-slate-500">Conflicts Detected</p>
          <p className="mt-2 text-2xl font-semibold tabular-nums text-slate-900">{conflicts?.length ?? 0}</p>
          <p className="mt-1 text-xs text-slate-500">across static & empirical checks</p>
        </Card>
        <Card className="p-5">
          <p className="text-xs font-medium uppercase tracking-wide text-slate-500">Critical Contradictions</p>
          <p className={`mt-2 text-2xl font-semibold tabular-nums ${criticalCount > 0 ? 'text-rose-600' : 'text-emerald-700'}`}>
            {criticalCount}
          </p>
          <p className="mt-1 text-xs text-slate-500">{criticalCount > 0 ? 'Blocks policy consistency' : 'No logical deadlocks'}</p>
        </Card>
        <Card className="p-5">
          <p className="text-xs font-medium uppercase tracking-wide text-slate-500">Avg Rule Quality</p>
          <p className={`mt-2 text-2xl font-semibold tabular-nums ${avgQuality >= 80 ? 'text-emerald-700' : 'text-amber-700'}`}>
            {avgQuality == null ? '—' : `${avgQuality}/100`}
          </p>
          <p className="mt-1 text-xs text-slate-500">
            {scored.length} scored rule{scored.length === 1 ? '' : 's'}
            {rules.length > scored.length && ` · ${rules.length - scored.length} provisional`}
          </p>
        </Card>
        <Card className="p-5">
          <p className="text-xs font-medium uppercase tracking-wide text-slate-500">Duplicate Alert Risk</p>
          <p className={`mt-2 text-2xl font-semibold tabular-nums ${duplicateRisk ? 'text-amber-700' : 'text-emerald-700'}`}>
            {duplicateRisk} resource{duplicateRisk === 1 ? '' : 's'}
          </p>
          <p className="mt-1 text-xs text-slate-500">alerted twice by overlapping rules</p>
        </Card>
      </div>

      {/* Section 1: Conflict Detector (§19) */}
      <div className="mt-8 space-y-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h2 className="text-lg font-semibold text-slate-900">Conflicts</h2>
            <p className="text-xs text-slate-500">Checked when a rule is activated, nightly, and whenever you click “Check my rules”.</p>
          </div>
          <div className="flex gap-1.5">
            {['all', 'contradiction', 'subsumption', 'overlap', 'dead'].map((cat) => (
              <button
                key={cat}
                onClick={() => setFilter(cat)}
                className={`rounded-full px-3 py-1 text-xs font-medium capitalize transition ${
                  filter === cat ? 'bg-slate-900 text-white' : 'bg-white border border-slate-200 text-slate-600 hover:bg-slate-50'
                }`}
              >
                {cat}
              </button>
            ))}
          </div>
        </div>

        <div className="space-y-4">
          {filteredConflicts.map((c) => {
            const meta = categoryMeta[c.category]
            const Icon = meta.icon
            return (
              <Card key={c.id} className={`p-5 ${c.severity === 'critical' ? 'border-rose-300 ring-1 ring-rose-200' : ''}`}>
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div className="flex items-start gap-3">
                    <div className={`mt-0.5 grid h-8 w-8 shrink-0 place-items-center rounded-lg ${
                      c.severity === 'critical' ? 'bg-rose-100 text-rose-700' : 'bg-amber-100 text-amber-800'
                    }`}>
                      <Icon size={18} />
                    </div>
                    <div>
                      <div className="flex flex-wrap items-center gap-2">
                        <Pill tone={meta.tone}>{meta.label}</Pill>
                        <span className="font-semibold text-slate-900">{c.title}</span>
                      </div>
                      <p className="mt-1.5 text-sm text-slate-600">{c.detail}</p>
                    </div>
                  </div>
                </div>

                {/* Conflicting Rules Comparison */}
                <div className="mt-4 grid gap-3 rounded-lg border border-slate-100 bg-slate-50/70 p-3 sm:grid-cols-2">
                  <div className="rounded bg-white p-3 shadow-xs">
                    <p className="text-[11px] font-semibold uppercase tracking-wider text-slate-400">Rule A</p>
                    <p className="mt-1 text-sm font-medium text-slate-900">“{c.ruleA.english}”</p>
                  </div>
                  {c.ruleB && (
                    <div className="rounded bg-white p-3 shadow-xs">
                      <p className="text-[11px] font-semibold uppercase tracking-wider text-slate-400">Rule B</p>
                      <p className="mt-1 text-sm font-medium text-slate-900">“{c.ruleB.english}”</p>
                    </div>
                  )}
                </div>

                {/* Impact Note */}
                <div className="mt-3 text-xs text-slate-600">
                  <strong className="text-slate-800">Operational impact:</strong> {c.impact}
                </div>

                {/* Resolution Suggestion Box */}
                <div className="mt-4 flex flex-wrap items-center justify-between gap-3 rounded-lg bg-emerald-50/60 px-4 py-3 ring-1 ring-emerald-200/70">
                  <div className="flex items-center gap-2 text-sm text-emerald-900">
                    <Sparkles size={16} className="shrink-0 text-emerald-700" />
                    <span><strong className="font-medium">Ward’s suggestion:</strong> {c.suggestion}</span>
                  </div>
                  {applied[c.id] ? (
                    <Pill tone="green"><CheckCircle2 size={12} /> Queued for review</Pill>
                  ) : (
                    <Button variant="secondary" className="text-xs" onClick={() => setApplied((a) => ({ ...a, [c.id]: true }))}>
                      {c.actionText}
                    </Button>
                  )}
                </div>
              </Card>
            )
          })}
          {filteredConflicts.length === 0 && (
            <Card className="p-8 text-center text-sm text-slate-500">
              <CheckCircle2 size={24} className="mx-auto text-emerald-600 mb-2" />
              No conflicts found in this category. Guardrails are mutually consistent.
            </Card>
          )}
        </div>
      </div>

      {/* Section 2: Rule Quality Scorecards (§22) */}
      <Card className="mt-10">
        <CardHeader
          title="Quality scores"
          subtitle="Specificity 25 · Verifiability 20 · Actionability 20 · Signal rate 20 · Stability 15. Advice only — a low score never blocks a rule."
        />
        <div className="divide-y divide-slate-100">
          {rules?.map((r) => {
            const isExpanded = expandedRule === r.id
            const bd = r.breakdown
            return (
              <div key={r.id} className="p-5 transition hover:bg-slate-50/50">
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2">
                      <p className="text-base font-semibold text-slate-900">“{r.english}”</p>
                      {r.quality == null ? <Pill>provisional</Pill> : (
                        <Pill tone={r.quality >= 80 ? 'green' : r.quality >= 60 ? 'amber' : 'red'}>{r.quality}/100</Pill>
                      )}
                    </div>
                    <p className="mt-1 text-xs text-slate-500">
                      Fired {r.firesLast30d}× in 30 days · {r.actedOn} acted on ({r.firesLast30d ? Math.round((r.actedOn / r.firesLast30d) * 100) : 0}%)
                    </p>
                  </div>
                  <Button variant="ghost" className="text-xs" onClick={() => setExpandedRule(isExpanded ? null : r.id)}>
                    {isExpanded ? 'Hide breakdown' : 'View dimensions'}
                    <ChevronDown size={14} className={`transition ${isExpanded ? 'rotate-180' : ''}`} />
                  </Button>
                </div>

                {/* Expanded 5-Dimension Visual Breakdown */}
                {isExpanded && bd && (
                  <div className="mt-4 space-y-3 rounded-xl border border-slate-200 bg-slate-50/70 p-4">
                    <p className="text-xs font-semibold uppercase tracking-wider text-slate-500">Score Breakdown</p>
                    <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
                      <ScoreBar label="Specificity" score={bd.specificity.score} max={bd.specificity.max} note={bd.specificity.note} />
                      <ScoreBar label="Verifiability" score={bd.verifiability.score} max={bd.verifiability.max} note={bd.verifiability.note} />
                      <ScoreBar label="Actionability" score={bd.actionability.score} max={bd.actionability.max} note={bd.actionability.note} />
                      <ScoreBar label="Signal rate" score={bd.signalRate.score} max={bd.signalRate.max} note={bd.signalRate.note} />
                      <ScoreBar label="Stability" score={bd.stability.score} max={bd.stability.max} note={bd.stability.note} />
                    </div>

                    {r.improvementTip && (
                      <div className="mt-3 flex items-start gap-2 rounded-lg bg-emerald-50 px-3 py-2 text-xs text-emerald-900">
                        <Zap size={14} className="mt-0.5 shrink-0 text-emerald-700" />
                        <span><strong>To improve:</strong> {r.improvementTip}</span>
                      </div>
                    )}

                    {r.yaml && (
                      <div className="mt-2">
                        <p className="text-[11px] font-medium text-slate-500 mb-1">Generated Policy YAML:</p>
                        <pre className="overflow-x-auto rounded bg-slate-900 p-3 font-mono text-xs text-slate-200">{r.yaml}</pre>
                      </div>
                    )}
                  </div>
                )}
              </div>
            )
          })}
        </div>
      </Card>
    </>
  )
}

function ScoreBar({ label, score, max, note }) {
  const pct = Math.round((score / max) * 100)
  return (
    <div className="rounded-lg bg-white p-3 shadow-xs border border-slate-100">
      <div className="flex items-center justify-between text-xs">
        <span className="font-medium text-slate-700">{label}</span>
        <span className="font-semibold tabular-nums text-slate-900">{score}/{max}</span>
      </div>
      <div className="mt-1.5 h-1.5 w-full rounded-full bg-slate-100 overflow-hidden">
        <div
          className={`h-full rounded-full ${pct >= 80 ? 'bg-emerald-600' : pct >= 60 ? 'bg-amber-500' : 'bg-rose-500'}`}
          style={{ width: `${pct}%` }}
        />
      </div>
      <p className="mt-1.5 text-[11px] leading-tight text-slate-500">{note}</p>
    </div>
  )
}
