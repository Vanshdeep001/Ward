import { useState } from 'react'
import { Info } from 'lucide-react'
import { rupees } from '../lib/format.js'
import { Card } from './ui.jsx'

// SRS §17 — savings with a named counterfactual, a stated exclusion, and Ward's own cost subtracted.
export default function SavingsCard({ savings, className = '' }) {
  const [model, setModel] = useState('next-morning')
  const cf = savings.counterfactuals[model]
  const net = cf.avoided - savings.wardCost
  const actionPct = Math.round((savings.actedOn / Math.max(savings.alertsSent, 1)) * 100)

  return (
    <Card className={`flex flex-col ${className}`}>
      <div className="border-b border-slate-100 px-5 py-4">
        <h2 className="text-sm font-semibold text-slate-900">Ward, last 30 days</h2>
        <label className="mt-2 flex items-center gap-2 text-xs text-slate-500">
          Counterfactual
          <select
            value={model}
            onChange={(e) => setModel(e.target.value)}
            className="min-w-0 flex-1 rounded-md border border-slate-200 bg-white px-2 py-1 text-xs font-medium text-slate-700 outline-none focus:border-arc-500"
          >
            {Object.entries(savings.counterfactuals).map(([key, m]) => (
              <option key={key} value={key}>{m.label}</option>
            ))}
          </select>
        </label>
        <p className="mt-2 flex gap-1.5 text-xs text-slate-500">
          <Info size={13} className="mt-px shrink-0" /> {cf.description}
        </p>
      </div>

      <dl className="flex-1 space-y-2.5 px-5 py-4 text-sm">
        <Row label="Estimated avoided" value={rupees(cf.avoided)} hint={`${cf.hoursAvoided} hours`} />
        <Row label="Alerts sent" value={savings.alertsSent} />
        <Row label="Acted on within 2h" value={`${savings.actedOn} (${actionPct}%)`} />
        <Row label="Ward’s own cost" value={`−${rupees(savings.wardCost)}`} />
        <div className="flex items-baseline justify-between border-t border-slate-100 pt-2.5">
          <dt className="font-semibold text-slate-900">Net saved</dt>
          <dd className="text-lg font-bold tabular-nums text-emerald-700">{rupees(net)}</dd>
        </div>
      </dl>

      <div className="space-y-2 border-t border-slate-100 px-5 py-3 text-xs text-slate-500">
        <p>
          <span className="font-medium text-slate-700">Not counted:</span> {rupees(cf.excluded)} stopped more than 2 hours after an alert, or already scheduled to shut down.
        </p>
        {savings.topRule && (
          <p>
            <span className="font-medium text-slate-700">Top rule:</span> “{savings.topRule.english}” — {rupees(savings.topRule.savings30d)}
          </p>
        )}
      </div>
    </Card>
  )
}

function Row({ label, value, hint }) {
  return (
    <div className="flex items-baseline justify-between gap-3">
      <dt className="text-slate-600">
        {label}
        {hint && <span className="ml-1.5 text-xs text-slate-400">{hint}</span>}
      </dt>
      <dd className="tabular-nums text-slate-900">{value}</dd>
    </div>
  )
}
