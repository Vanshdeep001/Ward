import { useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { Code2, ShieldCheck } from 'lucide-react'
import { useRules } from '../api/hooks.js'
import { ago, rupees } from '../lib/format.js'
import { Button, Card, CardHeader, Loading, PageHeader, Pill } from '../components/ui.jsx'
import RuleComposer from '../components/RuleComposer.jsx'

// SRS §2 starter rulebook, plus two that show off clarification and region rules.
const SUGGESTIONS = [
  'Stay inside the free tier',
  'Nothing runs longer than 6 hours unattended',
  'No GPU instance without an expiry tag',
  'Warn before monthly spend crosses the budget',
  'Nothing left running over a weekend',
  'Flag any resource with no owner tag',
  "Don't let anything expensive run too long",
  'No resources outside ap-south-1',
]

export default function Rules() {
  // The draft lives in the URL so links from Copilot, Detective and Guardian work even when this page is already open.
  const [params, setParams] = useSearchParams()
  const draft = params.get('draft') ?? ''
  const { data: rules, isLoading } = useRules()
  const [inspecting, setInspecting] = useState(null)

  return (
    <>
      <PageHeader
        title="Guardrails"
        subtitle="Write a rule in English. Ward compiles it, verifies it, and shows what it would do before anything is activated."
        action={
          <Link to="/health">
            <Button variant="secondary"><ShieldCheck size={16} /> Rule health & conflicts</Button>
          </Link>
        }
      />

      <RuleComposer
        initialText={draft}
        suggestions={SUGGESTIONS}
        onPick={(text) => setParams({ draft: text }, { replace: true })}
      />

      <Card className="mt-10">
        <CardHeader title="Active guardrails" subtitle="Evaluated against your account every 15 minutes" />
        {isLoading ? <Loading /> : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="border-b border-slate-100 text-left text-xs text-slate-500">
                <tr>
                  <th className="px-5 py-2 font-medium">Rule</th>
                  <th className="px-3 py-2 font-medium">Fired (30d)</th>
                  <th className="px-3 py-2 font-medium">Acted on</th>
                  <th className="px-3 py-2 text-right font-medium">Avoided</th>
                  <th className="px-3 py-2 text-right font-medium">Quality</th>
                  <th className="px-5 py-2"><span className="sr-only">Inspect</span></th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {rules.map((r) => (
                  <tr key={r.id} className="transition hover:bg-slate-50/60">
                    <td className="px-5 py-3">
                      <p className="font-medium text-slate-900">{r.english}</p>
                      <p className="text-xs text-slate-500">added {ago(r.createdAt)}</p>
                    </td>
                    <td className="px-3 py-3 tabular-nums">{r.firesLast30d}</td>
                    <td className="px-3 py-3 tabular-nums">
                      {r.firesLast30d ? `${r.actedOn} (${Math.round((r.actedOn / r.firesLast30d) * 100)}%)` : '—'}
                    </td>
                    <td className="px-3 py-3 text-right font-medium tabular-nums text-slate-900">{r.savings30d ? rupees(r.savings30d) : '—'}</td>
                    <td className="px-3 py-3 text-right">
                      {r.quality == null ? <Pill>provisional</Pill> : (
                        <Pill tone={r.quality >= 80 ? 'green' : r.quality >= 60 ? 'amber' : 'red'}>{r.quality}/100</Pill>
                      )}
                    </td>
                    <td className="px-5 py-3 text-right">
                      {r.yaml && (
                        <Button variant="ghost" className="py-1 text-xs" onClick={() => setInspecting(inspecting?.id === r.id ? null : r)}>
                          <Code2 size={13} /> {inspecting?.id === r.id ? 'Close' : 'YAML'}
                        </Button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {inspecting && (
          <div className="space-y-3 border-t border-slate-200 bg-slate-50 p-5">
            <p className="text-sm font-semibold text-slate-900">“{inspecting.english}”</p>
            <pre className="overflow-x-auto rounded-lg bg-slate-900 p-4 font-mono text-xs leading-relaxed text-slate-100">{inspecting.yaml}</pre>
            {inspecting.improvementTip && (
              <p className="rounded-lg bg-arc-50 p-2.5 text-xs text-arc-800">
                <strong>To improve:</strong> {inspecting.improvementTip}
              </p>
            )}
          </div>
        )}
      </Card>
    </>
  )
}
