import { useState } from 'react'
import { Link } from 'react-router-dom'
import { Copy, Lock, PiggyBank, Settings2, TrendingUp } from 'lucide-react'
import { useFindings } from '../api/hooks.js'
import { rupees, shortDate } from '../lib/format.js'
import { Button, Card, Loading, PageHeader, Pill } from '../components/ui.jsx'

const FAMILY = {
  security: { icon: Lock, label: 'Security', tone: 'red' },
  waste: { icon: PiggyBank, label: 'Waste', tone: 'amber' },
  configuration: { icon: Settings2, label: 'Configuration', tone: 'slate' },
  behavioural: { icon: TrendingUp, label: 'Behavioural', tone: 'violet' },
}

export default function Guardian() {
  const { data, isLoading } = useFindings()
  const [showAll, setShowAll] = useState(false)

  if (isLoading) return <Loading />
  const shown = showAll ? data : data.slice(0, 3)

  return (
    <>
      <PageHeader
        title="Guardian"
        subtitle="Ward reviews your account continuously. Each finding comes with its cost and a guardrail to stop it recurring."
      />

      <div className="mb-4 flex items-center justify-between">
        <p className="text-sm text-slate-600">
          {showAll ? `All ${data.length} findings` : `This week’s top 3 of ${data.length}`} — ranked by impact × confidence
        </p>
        <Button variant="ghost" onClick={() => setShowAll((s) => !s)}>{showAll ? 'Show top 3' : 'Show all'}</Button>
      </div>

      <div className="space-y-4">
        {shown.map((f) => <Finding key={f.id} f={f} />)}
      </div>
    </>
  )
}

function Finding({ f }) {
  const { icon: Icon, label, tone } = FAMILY[f.family]
  return (
    <Card className={`p-5 ${f.severity === 'urgent' ? 'border-rose-300 ring-1 ring-rose-200' : ''}`}>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="flex items-start gap-3">
          <div className="mt-0.5 grid h-8 w-8 shrink-0 place-items-center rounded-lg bg-slate-100 text-slate-600"><Icon size={16} /></div>
          <div>
            <div className="flex flex-wrap items-center gap-2">
              <Pill tone={tone}>{label}</Pill>
              {f.severity === 'urgent' && <Pill tone="red">notified immediately</Pill>}
              {f.confidence && <span className="text-xs text-slate-500">{Math.round(f.confidence * 100)}% confidence</span>}
            </div>
            <p className="mt-1.5 font-medium text-slate-900">{f.title}</p>
            <p className="mt-1 text-sm text-slate-600">{f.detail}</p>
          </div>
        </div>
        {f.monthlyImpact && <span className="text-lg font-semibold tabular-nums text-rose-600">{rupees(f.monthlyImpact)}/mo</span>}
      </div>

      {f.evidence && (
        <div className="mt-3 rounded-lg bg-violet-50/60 px-3 py-2 ring-1 ring-violet-100">
          <p className="text-xs font-medium text-violet-900">Evidence</p>
          <ul className="mt-1 space-y-0.5 text-sm text-slate-700">
            {f.evidence.map((e) => (
              <li key={e.date}>Weekend of {shortDate(e.date)} — <span className="font-mono text-xs">{e.resourceId}</span> ran {e.hours}h</li>
            ))}
          </ul>
        </div>
      )}

      {f.fix && (
        <div className="mt-3 flex items-center gap-2 rounded-lg bg-slate-900 px-3 py-2">
          <code className="flex-1 overflow-x-auto whitespace-nowrap font-mono text-xs text-slate-100">{f.fix}</code>
          <button onClick={() => navigator.clipboard?.writeText(f.fix)} className="text-slate-400 hover:text-white" title="Copy"><Copy size={14} /></button>
        </div>
      )}

      <div className="mt-4 flex flex-wrap items-center justify-between gap-3 border-t border-slate-100 pt-3">
        <span className="text-xs text-slate-400">
          {f.resourceIds.length} resource{f.resourceIds.length > 1 && 's'} · detected by {f.source}
        </span>
        {f.suggestedRule && (
          <Link to={`/rules?draft=${encodeURIComponent(f.suggestedRule)}`}>
            <Button variant="secondary">Review & activate: “{f.suggestedRule}”</Button>
          </Link>
        )}
      </div>
    </Card>
  )
}
