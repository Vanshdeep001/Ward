import { useEffect, useState } from 'react'
import {
  AlertTriangle, CheckCircle2, ChevronDown, Code2, FileSearch, Info, ShieldCheck, XCircle,
} from 'lucide-react'
import { api } from '../api/client.js'
import { rupees, shortDate } from '../lib/format.js'
import { Button, Card, Pill } from './ui.jsx'

// SRS §28 — consequence first, mechanism on request.
export default function GuardrailCard({ result, onActivate, activating, activated }) {
  const sim = result.simulation
  const [panel, setPanel] = useState(null)
  const toggle = (name) => setPanel((p) => (p === name ? null : name))

  return (
    <Card className="overflow-hidden">
      {/* 1. The rule as written */}
      <div className="border-b border-slate-100 px-5 py-4">
        <p className="text-xs font-medium uppercase tracking-wide text-slate-500">Your rule</p>
        <p className="mt-1 font-display text-2xl font-semibold text-ink">“{result.english}”</p>
        <div className="mt-2 flex flex-wrap gap-2">
          <Pill tone="green"><CheckCircle2 size={12} /> Verified · {result.verifier.fixtures.length}/{result.verifier.fixtures.length} fixtures</Pill>
          {result.assumptions.length > 0 && <Pill tone="amber"><Info size={12} /> {result.assumptions.length} assumption{result.assumptions.length > 1 && 's'}</Pill>}
        </div>
      </div>

      <div className="grid gap-px bg-slate-100 sm:grid-cols-3">
        {/* 2. Live matches */}
        <Metric
          label="Matches right now"
          value={`${sim.matched.length} of ${sim.population}`}
          hint={sim.resourceType}
          tone={sim.breadth === 'broad' ? 'amber' : 'slate'}
        />
        {/* 4. Money */}
        <Metric label="Estimated avoidable" value={sim.savings.monthly ? `${rupees(sim.savings.monthly)}/mo` : '—'} hint={sim.savings.counterfactual ? `if ${sim.savings.counterfactual}` : 'no direct saving'} tone="green" />
        {/* 5. Alert load */}
        <Metric label="Alert load" value={`~${sim.alertsPerWeek}/week`} hint={`quiet on ${sim.quietDays} of 30 days`} tone={sim.alertsPerWeek > 7 ? 'amber' : 'slate'} />
      </div>

      <div className="space-y-4 px-5 py-4">
        {/* 6. Warnings */}
        {sim.breadth === 'broad' && (
          <Warning>This rule matches more than half of your {sim.resourceType}. It’s probably too broad — you’d be notified about most of your account tonight.</Warning>
        )}
        {sim.alertsPerWeek > 7 && <Warning>More than one alert a day. Rules this noisy usually get muted within a week.</Warning>}
        {sim.zeroReason && (
          <p className="flex items-start gap-2 rounded-lg bg-slate-50 px-3 py-2 text-sm text-slate-600">
            <Info size={16} className="mt-0.5 shrink-0" /> {sim.zeroReason}
          </p>
        )}

        {sim.matched.length > 0 && (
          <div>
            <p className="mb-2 text-xs font-medium uppercase tracking-wide text-slate-500">Would flag</p>
            <ul className="divide-y divide-slate-100 rounded-lg border border-slate-200">
              {sim.matched.map((m) => (
                <li key={m.id} className="flex flex-wrap items-center justify-between gap-2 px-3 py-2 text-sm">
                  <span>
                    <span className="font-medium text-slate-900">{m.name}</span>{' '}
                    <span className="font-mono text-xs text-slate-500">{m.id}</span>
                    {m.instanceType && <span className="text-slate-500"> · {m.instanceType}</span>}
                  </span>
                  <span className="text-xs text-slate-500">
                    {m.runtimeHours > 0 && `running ${m.runtimeHours}h · `}{rupees(m.costPerDay)}/day
                  </span>
                </li>
              ))}
            </ul>
          </div>
        )}

        {/* 3. History */}
        {sim.history.length > 0 && (
          <div>
            <p className="mb-2 text-xs font-medium uppercase tracking-wide text-slate-500">
              Would have fired {sim.history.length}× in the last 30 days
            </p>
            <ul className="space-y-1 text-sm text-slate-600">
              {sim.history.slice(0, 5).map((h, i) => (
                <li key={i} className="flex gap-3">
                  <span className="w-14 shrink-0 tabular-nums text-slate-400">{shortDate(h.date)}</span>
                  <span><span className="font-mono text-xs">{h.resourceId}</span> — {h.detail}</span>
                </li>
              ))}
              {sim.history.length > 5 && <li className="text-xs text-slate-400">+ {sim.history.length - 5} more</li>}
            </ul>
          </div>
        )}

        {result.kind === 'gpu-runtime' && <WhatIf kind={result.kind} current={result.params.hours} />}
      </div>

      {/* Disclosures */}
      <div className="border-t border-slate-100">
        <Disclosure icon={ShieldCheck} title="What did Ward understand?" open={panel === 'explain'} onToggle={() => toggle('explain')}>
          <PolicyExplain result={result} />
        </Disclosure>
        {sim.savings.lines.length > 0 && (
          <Disclosure icon={Info} title="Where does the ₹ figure come from?" open={panel === 'cost'} onToggle={() => toggle('cost')}>
            <CostProvenance savings={sim.savings} />
          </Disclosure>
        )}
        <Disclosure icon={CheckCircle2} title="Verifier report" open={panel === 'verify'} onToggle={() => toggle('verify')}>
          <VerifierReport verifier={result.verifier} />
        </Disclosure>
        <Disclosure icon={FileSearch} title={`Sources Ward used (${result.sources.length})`} open={panel === 'sources'} onToggle={() => toggle('sources')}>
          <SourcePanel sources={result.sources} retrieval={result.retrieval} />
        </Disclosure>
        <Disclosure icon={Code2} title="View YAML" open={panel === 'yaml'} onToggle={() => toggle('yaml')}>
          <pre className="overflow-x-auto rounded-lg bg-slate-900 p-4 font-mono text-xs leading-relaxed text-slate-100">{result.yaml}</pre>
        </Disclosure>
      </div>

      {/* 7. Actions */}
      <div className="flex flex-wrap items-center gap-3 border-t border-slate-100 bg-slate-50 px-5 py-4">
        {activated ? (
          <Pill tone="green"><CheckCircle2 size={12} /> Guardrail active — checked every 15 minutes</Pill>
        ) : (
          <>
            <Button onClick={onActivate} disabled={activating}>
              <ShieldCheck size={16} /> {activating ? 'Activating…' : 'This is right — activate'}
            </Button>
            <Button variant="secondary" onClick={() => toggle('explain')}>Not what I meant</Button>
          </>
        )}
      </div>
    </Card>
  )
}

function Metric({ label, value, hint, tone }) {
  const color = { slate: 'text-ink', green: 'text-emerald-700', amber: 'text-amber-700' }[tone]
  return (
    <div className="bg-white px-5 py-4">
      <p className="text-xs text-slate-500">{label}</p>
      <p className={`mt-1 font-display text-[1.75rem] font-semibold leading-tight tabular-nums ${color}`}>{value}</p>
      <p className="mt-0.5 text-xs text-slate-500">{hint}</p>
    </div>
  )
}

function Warning({ children }) {
  return (
    <p className="flex items-start gap-2 rounded-lg bg-amber-50 px-3 py-2 text-sm text-amber-900 ring-1 ring-amber-200">
      <AlertTriangle size={16} className="mt-0.5 shrink-0" /> {children}
    </p>
  )
}

function Disclosure({ icon: Icon, title, open, onToggle, children }) {
  return (
    <div className="border-b border-slate-100 last:border-0">
      <button onClick={onToggle} className="flex w-full items-center justify-between px-5 py-3 text-left text-sm text-slate-700 hover:bg-slate-50">
        <span className="flex items-center gap-2"><Icon size={15} className="text-slate-400" /> {title}</span>
        <ChevronDown size={16} className={`text-slate-400 transition ${open ? 'rotate-180' : ''}`} />
      </button>
      {open && <div className="px-5 pb-4">{children}</div>}
    </div>
  )
}

// SRS §15 — deterministic clause-by-clause rendering, assumptions surfaced.
function PolicyExplain({ result }) {
  return (
    <div className="space-y-3">
      <dl className="grid grid-cols-[6.5rem_1fr] gap-x-3 gap-y-1.5 text-sm">
        {result.explanation.map((c) => (
          <div key={c.label} className="contents">
            <dt className="text-slate-500">{c.label}</dt>
            <dd className="text-slate-900">{c.text}</dd>
          </div>
        ))}
      </dl>
      {result.assumptions.map((a) => (
        <div key={a.term} className="rounded-lg bg-amber-50 px-3 py-2 text-sm text-amber-900 ring-1 ring-amber-200">
          <p>
            <AlertTriangle size={14} className="mr-1 inline" />
            Ward assumed <strong>“{a.term}”</strong> means {a.interpretation}{' '}
            <span className="text-xs text-amber-700">({Math.round(a.confidence * 100)}% confident)</span>
          </p>
          {a.alternatives.length > 0 && <p className="mt-1 text-xs text-amber-800">Other reading: {a.alternatives.join('; ')}</p>}
        </div>
      ))}
    </div>
  )
}

// SRS §28.3 — every line traces to a source.
function CostProvenance({ savings }) {
  return (
    <div>
      <table className="w-full text-sm">
        <tbody className="divide-y divide-slate-100">
          {savings.lines.map((l) => (
            <tr key={l.label}>
              <td className="py-1.5 text-slate-600">{l.label}</td>
              <td className="py-1.5 text-right font-medium tabular-nums text-slate-900">{l.value}</td>
              <td className="py-1.5 pl-4 text-right text-xs text-slate-400">{l.source}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {savings.note && <p className="mt-2 text-xs text-slate-500">ⓘ {savings.note}</p>}
    </div>
  )
}

function VerifierReport({ verifier }) {
  return (
    <div className="space-y-2 text-sm">
      <p className="text-slate-600">
        {verifier.passed ? 'Passed' : 'Failed'} on attempt {verifier.attempts}
        {verifier.durationMs && ` in ${verifier.durationMs}ms`}. Every rule is tested against generated resources before it’s trusted.
      </p>
      <div className="flex flex-wrap gap-2">
        {verifier.fixtures.map((f) => (
          <span key={f.id} className={`inline-flex items-center gap-1 rounded-md px-2 py-1 font-mono text-xs ${f.expected === f.actual ? 'bg-emerald-50 text-emerald-800' : 'bg-rose-50 text-rose-800'}`}>
            {f.expected === f.actual ? <CheckCircle2 size={12} /> : <XCircle size={12} />}
            {f.id} · {f.kind} · {f.expected ? 'flag' : 'pass'}
          </span>
        ))}
      </div>
    </div>
  )
}

// SRS §21 — retrieval trace.
function SourcePanel({ sources, retrieval }) {
  return (
    <div className="space-y-2">
      <p className="text-xs text-slate-500">
        {retrieval.vector} vector + {retrieval.bm25} BM25 → merged {retrieval.merged} → reranked → top {retrieval.kept} · {retrieval.latencyMs}ms
      </p>
      <ol className="space-y-2">
        {sources.map((s, i) => (
          <li key={s.title} className="rounded-lg border border-slate-200 px-3 py-2">
            <div className="flex items-center justify-between gap-2 text-sm">
              <span className="font-medium text-slate-800">{i + 1}. {s.title}</span>
              <span className="flex shrink-0 items-center gap-2">
                <Pill>{s.docType}</Pill>
                <span className="font-mono text-xs text-slate-500">{s.score.toFixed(2)}</span>
              </span>
            </div>
            <p className="mt-1 font-mono text-xs text-slate-500">{s.excerpt}</p>
          </li>
        ))}
      </ol>
    </div>
  )
}

// SRS §18 — change the threshold, see the monthly delta and the alert load.
function WhatIf({ kind, current }) {
  const values = [2, 4, 6, 8, 12, 24]
  const [rows, setRows] = useState(null)
  useEffect(() => {
    api.whatIf(kind, 'hours', values).then(setRows)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [kind])

  if (!rows) return null
  const base = rows.find((r) => r.value === current) ?? rows[2]
  return (
    <div>
      <p className="mb-2 text-xs font-medium uppercase tracking-wide text-slate-500">What if the limit were different?</p>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-xs text-slate-500">
              <th className="py-1 font-medium">Limit</th>
              <th className="py-1 font-medium">Fires / month</th>
              <th className="py-1 font-medium">Alerts / week</th>
              <th className="py-1 text-right font-medium">Avoidable</th>
              <th className="py-1 text-right font-medium">vs {current}h</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {rows.map((r) => {
              const diff = r.savings - base.savings
              return (
                <tr key={r.value} className={r.value === current ? 'bg-emerald-50/60 font-medium' : ''}>
                  <td className="py-1.5">{r.value} hours {r.value === current && <span className="text-xs text-emerald-700">· current</span>}</td>
                  <td className="py-1.5 tabular-nums">{r.fires}</td>
                  <td className="py-1.5 tabular-nums">
                    {r.alertsPerWeek}
                    {r.alertsPerWeek > 7 && <span className="ml-1 text-xs text-amber-700">⚠ noisy</span>}
                  </td>
                  <td className="py-1.5 text-right tabular-nums">{rupees(r.savings)}</td>
                  <td className={`py-1.5 text-right tabular-nums ${diff < 0 ? 'text-rose-600' : diff > 0 ? 'text-emerald-700' : 'text-slate-400'}`}>
                    {diff === 0 ? '—' : `${diff > 0 ? '+' : '−'}${rupees(Math.abs(diff))}`}
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </div>
  )
}
