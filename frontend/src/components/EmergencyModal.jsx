import { useState } from 'react'
import { AlertOctagon, Check, Copy, Database, ExternalLink, Flame, X } from 'lucide-react'
import { rupees } from '../lib/format.js'
import { Button, Pill } from './ui.jsx'

const consoleUrl = (r) =>
  r.type === 'rds'
    ? `https://${r.region}.console.aws.amazon.com/rds/home?region=${r.region}#database:id=${r.name}`
    : r.type === 'nat'
      ? `https://${r.region}.console.aws.amazon.com/vpcconsole/home?region=${r.region}#NatGateways:`
      : `https://${r.region}.console.aws.amazon.com/ec2/home?region=${r.region}#InstanceDetails:instanceId=${r.id}`

const stopCommand = (r) =>
  r.type === 'rds'
    ? `aws rds stop-db-instance --db-instance-identifier ${r.name} --region ${r.region}`
    : r.type === 'nat'
      ? `aws ec2 delete-nat-gateway --nat-gateway-id ${r.id} --region ${r.region}`
      : `aws ec2 stop-instances --instance-ids ${r.id} --region ${r.region}`

// SRS §24 Tier 1 — advisory only. Ward ranks what is burning money and hands over the commands;
// it never runs them. Production and data-holding resources are never included in bulk actions.
export default function EmergencyModal({ isOpen, active, onActivate, onExit, onClose, resources = [] }) {
  const [copied, setCopied] = useState(null)

  if (!isOpen) return null

  const burning = resources
    .filter((r) => r.running && r.costPerHour > 0 && ['ec2', 'rds', 'nat'].includes(r.type))
    .sort((a, b) => b.costPerHour - a.costPerHour)
  const isProtected = (r) => r.tags.Environment === 'production' || r.tags['ward:protect']
  const holdsData = (r) => r.type === 'rds'
  const stoppable = burning.filter((r) => r.type === 'ec2' && !isProtected(r))

  const hourlyBurn = burning.reduce((s, r) => s + r.costPerHour, 0)
  const topTwo = stoppable.slice(0, 2)
  const topTwoSaving = topTwo.reduce((s, r) => s + r.costPerHour, 0)
  const bulkCommand = `aws ec2 stop-instances --region ap-south-1 --instance-ids ${stoppable.map((r) => r.id).join(' ')}`

  function copy(text, id) {
    navigator.clipboard?.writeText(text)
    setCopied(id)
    setTimeout(() => setCopied(null), 1500)
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/60 p-4 backdrop-blur-xs" onClick={onClose}>
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="emergency-title"
        onClick={(e) => e.stopPropagation()}
        className="flex max-h-[90vh] w-full max-w-2xl flex-col overflow-hidden rounded-2xl border border-rose-200 bg-white shadow-2xl"
      >
        <div className="flex items-center justify-between border-b border-rose-100 bg-rose-50/80 px-6 py-4">
          <div className="flex items-center gap-3">
            <div className="grid h-9 w-9 place-items-center rounded-xl bg-rose-600 text-white"><Flame size={20} /></div>
            <div>
              <h2 id="emergency-title" className="text-base font-semibold text-rose-950">Emergency budget mode</h2>
              <p className="text-xs text-rose-800">
                {active ? 'Active · polling every 5 minutes · snooze disabled · auto-expires in 24h' : 'Tier 1 advisory — no new permissions needed'}
              </p>
            </div>
          </div>
          <button onClick={onClose} className="rounded-lg p-1.5 text-rose-700 transition hover:bg-rose-100" aria-label="Close"><X size={18} /></button>
        </div>

        <div className="space-y-4 overflow-y-auto p-6">
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
            <Metric label="Burning now" value={`${rupees(hourlyBurn)}/hr`} hint={`${rupees(hourlyBurn * 24)}/day`} danger />
            <Metric label="Running resources" value={burning.length} hint="EC2, RDS and NAT" />
            <Metric label="Stop the top 2" value={`−${rupees(topTwoSaving * 24)}/day`} hint={topTwo.map((r) => r.name).join(', ')} />
          </div>

          <p className="flex items-start gap-2 rounded-xl border border-amber-200 bg-amber-50/70 p-3 text-xs leading-relaxed text-amber-900">
            <AlertOctagon size={14} className="mt-0.5 shrink-0 text-amber-700" />
            Ward has read-only access and never changes your account. Copy a command or open the console to act. Production-tagged resources and databases are never included in the bulk command.
          </p>

          <div className="flex items-center justify-between gap-3 border-b border-slate-100 pb-2">
            <p className="text-xs font-semibold uppercase tracking-wider text-slate-500">Most expensive first</p>
            {stoppable.length > 0 && (
              <Button variant="secondary" className="py-1 text-xs" onClick={() => copy(bulkCommand, 'bulk')}>
                {copied === 'bulk' ? <Check size={14} className="text-emerald-600" /> : <Copy size={14} />}
                {copied === 'bulk' ? 'Copied' : `Copy stop command for ${stoppable.length} non-production instances`}
              </Button>
            )}
          </div>

          <ol className="space-y-2.5">
            {burning.map((r, i) => {
              const cmd = stopCommand(r)
              const guarded = isProtected(r) || holdsData(r)
              return (
                <li key={r.id} className="rounded-xl border border-slate-200 bg-white p-3.5">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
                      <span className="w-5 text-xs tabular-nums text-slate-400">{i + 1}.</span>
                      <span className="text-sm font-semibold text-slate-900">{r.name}</span>
                      <span className="font-mono text-xs text-slate-500">{r.id}</span>
                      <span className="text-xs text-slate-400">{r.instanceType ?? r.type.toUpperCase()}</span>
                      {isProtected(r) && <Pill tone="blue">production</Pill>}
                      {holdsData(r) && <Pill tone="amber"><Database size={11} /> holds data</Pill>}
                    </div>
                    <div className="flex items-center gap-2">
                      <span className="text-sm font-bold tabular-nums text-rose-700">{rupees(r.costPerHour * 24)}/day</span>
                      <a href={consoleUrl(r)} target="_blank" rel="noreferrer" className="p-1 text-slate-400 transition hover:text-slate-700" title="Open in AWS console">
                        <ExternalLink size={14} />
                      </a>
                    </div>
                  </div>
                  {guarded ? (
                    <p className="mt-2 pl-7 text-xs text-slate-500">
                      {holdsData(r) ? 'Review before stopping — take a snapshot first if the data matters.' : 'Tagged production — Ward won’t suggest stopping it.'}
                    </p>
                  ) : (
                    <div className="mt-2 flex items-center gap-2 rounded-lg bg-slate-900 px-3 py-1.5">
                      <code className="flex-1 overflow-x-auto whitespace-nowrap font-mono text-[11px] text-slate-300">{cmd}</code>
                      <button onClick={() => copy(cmd, r.id)} className="text-slate-400 transition hover:text-white" title="Copy command">
                        {copied === r.id ? <Check size={14} className="text-emerald-400" /> : <Copy size={14} />}
                      </button>
                    </div>
                  )}
                </li>
              )
            })}
          </ol>
        </div>

        <div className="flex flex-wrap justify-end gap-2 border-t border-slate-100 bg-slate-50 px-6 py-3">
          {active ? (
            <Button variant="secondary" onClick={onExit}>Exit emergency mode</Button>
          ) : (
            <Button variant="danger" onClick={onActivate}><Flame size={15} /> Enter emergency mode</Button>
          )}
          <Button variant="ghost" onClick={onClose}>Close</Button>
        </div>
      </div>
    </div>
  )
}

function Metric({ label, value, hint, danger }) {
  return (
    <div className={`rounded-xl border p-3 ${danger ? 'border-rose-100 bg-rose-50/40' : 'border-slate-200 bg-slate-50'}`}>
      <p className={`text-[11px] font-medium uppercase tracking-wider ${danger ? 'text-rose-700' : 'text-slate-500'}`}>{label}</p>
      <p className={`mt-1 text-xl font-bold tabular-nums ${danger ? 'text-rose-950' : 'text-slate-900'}`}>{value}</p>
      <p className={`truncate text-[11px] ${danger ? 'text-rose-600' : 'text-slate-500'}`}>{hint}</p>
    </div>
  )
}
