import { useState } from 'react'
import { Info } from 'lucide-react'
import { rupees } from '../lib/format.js'
import { Panel } from './ui.jsx'

// SRS §17 — savings with a named counterfactual, a stated exclusion, and Ward's own cost
// subtracted. The net figure leads; the arithmetic that produced it sits underneath.
export default function SavingsCard({ savings, className = '' }) {
  const [model, setModel] = useState('next-morning')
  const cf = savings.counterfactuals[model]
  const net = cf.avoided - savings.wardCost
  const actionPct = Math.round((savings.actedOn / Math.max(savings.alertsSent, 1)) * 100)
  const netShare = Math.round((net / Math.max(cf.avoided, 1)) * 100)

  return (
    <Panel className={className} eyebrow="Verified savings" title="Ward, last 30 days">
      {/* The payoff, before the working */}
      <div className="border-b border-slate-100 bg-gradient-to-b from-emerald-50/60 to-transparent px-5 pb-5 pt-4">
        <p className="text-[10px] font-bold uppercase tracking-[0.14em] text-emerald-700/70">Net saved</p>
        <p className="mt-1 font-display text-[2.6rem] font-semibold leading-none text-emerald-700">
          {rupees(net)}
        </p>
        <p className="mt-2 text-[11.5px] font-medium text-slate-500">
          after Ward’s own {rupees(savings.wardCost)} · {cf.hoursAvoided} hours of compute never billed
        </p>
      </div>

      {/* Which counterfactual the number assumes */}
      <div className="border-b border-slate-100 px-5 py-4">
        <div className="flex gap-1 rounded-xl bg-slate-100 p-1">
          {Object.entries(savings.counterfactuals).map(([key, m]) => (
            <button
              key={key}
              onClick={() => setModel(key)}
              aria-pressed={model === key}
              className={`flex-1 rounded-lg px-1.5 py-1.5 text-[10.5px] font-bold transition ${
                model === key ? 'bg-white text-ink shadow-[0_1px_2px_rgb(15_23_42/0.12)]' : 'text-slate-500 hover:text-slate-700'
              }`}
            >
              {m.label.replace(/\s*\(.*\)/, '')}
            </button>
          ))}
        </div>
        <p className="mt-3 flex gap-1.5 text-[11.5px] leading-relaxed text-slate-500">
          <Info size={13} className="mt-px shrink-0 text-slate-400" />
          {cf.description}
        </p>
      </div>

      {/* Where the avoided spend went: what you keep, and what Ward took to find it. */}
      <div className="flex-1 px-5 py-4">
        <div className="flex items-baseline justify-between gap-3">
          <p className="text-[12px] text-slate-600">
            Estimated avoided <span className="text-slate-400">{cf.hoursAvoided} hours</span>
          </p>
          <p className="text-[13px] font-semibold tabular-nums text-ink">{rupees(cf.avoided)}</p>
        </div>

        <div className="mt-2.5 flex h-3 w-full overflow-hidden rounded-[4px]">
          <div className="h-full bg-emerald-600" style={{ width: `calc(${netShare}% - 1px)` }} />
          <div className="h-full bg-slate-400" style={{ width: `calc(${100 - netShare}% - 1px)`, marginLeft: 2 }} />
        </div>

        <ul className="mt-3 space-y-1.5 text-[12px]">
          <LegendRow swatch="bg-emerald-600" label="Net saved" value={rupees(net)} />
          <LegendRow swatch="bg-slate-400" label="Ward’s own cost" value={`−${rupees(savings.wardCost)}`} />
        </ul>

        {/* How much of what Ward said actually got acted on. */}
        <div className="mt-5">
          <div className="flex items-baseline justify-between gap-3 text-[12px]">
            <span className="text-slate-600">Acted on within 2h</span>
            <span className="font-semibold tabular-nums text-ink">
              {savings.actedOn} of {savings.alertsSent} alerts · {actionPct}%
            </span>
          </div>
          <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-arc-100">
            <div className="h-full rounded-full bg-arc-500 transition-all duration-500" style={{ width: `${actionPct}%` }} />
          </div>
        </div>
      </div>

      <div className="space-y-2 border-t border-slate-100 bg-slate-50/60 px-5 py-3.5 text-[11.5px] leading-relaxed text-slate-500">
        <p>
          <span className="font-semibold text-slate-700">Not counted:</span> {rupees(cf.excluded)} stopped more than
          2 hours after an alert, or already scheduled to shut down.
        </p>
        {savings.topRule && (
          <p>
            <span className="font-semibold text-slate-700">Top rule:</span> “{savings.topRule.english}” —{' '}
            {rupees(savings.topRule.savings30d)}
          </p>
        )}
      </div>
    </Panel>
  )
}

// The bar's key. The swatch carries identity; the text stays in ink, never the mark's colour.
function LegendRow({ swatch, label, value }) {
  return (
    <li className="flex items-center gap-2">
      <span className={`h-2.5 w-2.5 shrink-0 rounded-[3px] ${swatch}`} />
      <span className="flex-1 text-slate-600">{label}</span>
      <span className="font-semibold tabular-nums text-ink">{value}</span>
    </li>
  )
}
