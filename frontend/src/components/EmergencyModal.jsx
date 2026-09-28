import { useState } from 'react'
import { ArrowRight, Check, Copy, Database, ExternalLink, Flame, Lock, ShieldCheck, X } from 'lucide-react'
import { rupees } from '../lib/format.js'

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

// Small hourly figures would round to ₹1 or ₹0; keep the paise until the number is big enough not to need them.
const perHour = (n) => (n < 100 ? `₹${n.toFixed(2)}` : rupees(n))

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
  const top = stoppable.slice(0, 2)
  const saving = top.reduce((s, r) => s + r.costPerHour, 0) * 24
  const bulkCommand = `aws ec2 stop-instances --region ap-south-1 --instance-ids ${stoppable.map((r) => r.id).join(' ')}`

  function copy(text, id) {
    navigator.clipboard?.writeText(text)
    setCopied(id)
    setTimeout(() => setCopied(null), 1500)
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-ink/50 p-4 backdrop-blur-sm" onClick={onClose}>
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="emergency-title"
        onClick={(e) => e.stopPropagation()}
        className="animate-rise flex max-h-[92vh] w-full max-w-2xl flex-col overflow-hidden rounded-[30px] bg-white shadow-[0_40px_90px_-30px_rgb(120_20_20/0.55)]"
      >
        {/* The headline: what's burning, and what stopping the worst of it saves. */}
        <div className="grain relative bg-coral-500 px-7 pb-7 pt-6 text-white">
          <div className="flex items-start justify-between gap-4">
            <p className="flex items-center gap-2 text-[11px] font-bold uppercase tracking-[0.2em] text-white/80">
              <Flame size={14} /> Emergency budget mode
              {active && <span className="rounded-full bg-white px-2 py-0.5 text-[10px] tracking-[0.12em] text-coral-600">Active</span>}
            </p>
            <button type="button" onClick={onClose} className="-mr-2 -mt-1 grid h-9 w-9 place-items-center rounded-full text-white/80 transition hover:bg-white/15 hover:text-white" aria-label="Close">
              <X size={18} />
            </button>
          </div>

          <h2 id="emergency-title" className="mt-4 font-display text-[clamp(1.9rem,4.5vw,2.7rem)] font-semibold leading-[1.05] tracking-tight">
            {burning.length ? <>{rupees(hourlyBurn * 24)} a day is burning.</> : 'Nothing is burning money right now.'}
          </h2>

          {burning.length > 0 && (
            <dl className="mt-5 flex flex-wrap gap-x-9 gap-y-3">
              <Figure label="Right now" value={`${perHour(hourlyBurn)}/hr`} />
              <Figure label="Running and billing" value={burning.length} />
              {top.length > 0 && (
                <Figure label={top.length === 1 ? `Stop ${top[0].name}` : `Stop the top ${top.length}`} value={`−${rupees(saving)}/day`} />
              )}
            </dl>
          )}

          <p className="mt-5 text-[12.5px] leading-relaxed text-white/85">
            {active
              ? 'Active · checking every 5 minutes · snooze is off · ends by itself after 24 hours.'
              : 'Tier 1 advisory — Ward ranks what to stop and hands you the commands. No new permissions needed.'}
          </p>
        </div>

        <div className="space-y-4 overflow-y-auto px-7 py-6">
          <p className="flex items-start gap-2.5 text-[12.5px] leading-relaxed text-slate-500">
            <ShieldCheck size={15} className="mt-0.5 shrink-0 text-arc-500" />
            Ward is read-only and never changes your account. Production-tagged resources and databases are never in the bulk command.
          </p>

          <div className="flex flex-wrap items-center justify-between gap-3">
            <p className="text-[11px] font-bold uppercase tracking-[0.2em] text-slate-400">Most expensive first</p>
            {stoppable.length > 1 && (
              <button
                type="button"
                onClick={() => copy(bulkCommand, 'bulk')}
                className="inline-flex items-center gap-1.5 rounded-full border border-slate-200 bg-white px-3.5 py-1.5 text-[12px] font-bold text-slate-600 transition hover:border-slate-300 hover:text-ink"
              >
                {copied === 'bulk' ? <Check size={13} className="text-emerald-600" /> : <Copy size={13} />}
                {copied === 'bulk' ? 'Copied' : `Copy one command for all ${stoppable.length}`}
              </button>
            )}
          </div>

          <ol className="space-y-3">
            {burning.map((r, i) => {
              const cmd = stopCommand(r)
              const guarded = isProtected(r) || holdsData(r)
              return (
                <li key={r.id} className="rounded-3xl border border-slate-200/80 bg-white p-4 shadow-[0_1px_2px_rgb(15_23_42/0.04)]">
                  <div className="flex items-center gap-4">
                    <span className="w-8 shrink-0 font-display text-[1.7rem] font-semibold leading-none text-coral-400">{String(i + 1).padStart(2, '0')}</span>
                    <div className="min-w-0 flex-1">
                      <p className="flex flex-wrap items-center gap-2">
                        <span className="font-display text-[1.2rem] font-semibold tracking-tight text-ink">{r.name}</span>
                        {isProtected(r) && (
                          <span className="inline-flex items-center gap-1 rounded-full bg-arc-50 px-2 py-0.5 text-[10.5px] font-bold text-arc-700"><Lock size={10} /> production</span>
                        )}
                        {holdsData(r) && (
                          <span className="inline-flex items-center gap-1 rounded-full bg-amber-50 px-2 py-0.5 text-[10.5px] font-bold text-amber-700"><Database size={10} /> holds data</span>
                        )}
                      </p>
                      <p className="truncate font-mono text-[11px] text-slate-400">{r.id} · {r.instanceType ?? r.type.toUpperCase()}</p>
                    </div>
                    <div className="shrink-0 text-right">
                      <p className="font-display text-[1.35rem] font-semibold leading-none tabular-nums text-coral-600">{rupees(r.costPerHour * 24)}</p>
                      <p className="mt-1 text-[10px] font-bold uppercase tracking-[0.14em] text-slate-400">a day</p>
                    </div>
                    <a href={consoleUrl(r)} target="_blank" rel="noreferrer" className="grid h-9 w-9 shrink-0 place-items-center rounded-full text-slate-400 transition hover:bg-slate-100 hover:text-ink" title="Open in AWS console">
                      <ExternalLink size={15} />
                    </a>
                  </div>
                  {guarded ? (
                    <p className="mt-3 pl-12 text-[12.5px] text-slate-500">
                      {holdsData(r) ? 'Review before stopping — take a snapshot first if the data matters.' : 'Tagged production — Ward won’t suggest stopping it.'}
                    </p>
                  ) : (
                    <div className="mt-3 flex items-center gap-2 rounded-2xl bg-paper px-3.5 py-2 ring-1 ring-inset ring-slate-200/80 md:ml-12">
                      <code className="flex-1 overflow-x-auto whitespace-nowrap font-mono text-[12px] text-ink">
                        <span className="select-none text-coral-500">$ </span>{cmd}
                      </code>
                      <button type="button" onClick={() => copy(cmd, r.id)} className="inline-flex shrink-0 items-center gap-1 rounded-lg px-2 py-1 text-[11.5px] font-bold text-slate-500 transition hover:bg-white hover:text-ink" title="Copy command">
                        {copied === r.id ? <><Check size={12} className="text-emerald-600" /> Copied</> : <><Copy size={12} /> Copy</>}
                      </button>
                    </div>
                  )}
                </li>
              )
            })}
          </ol>
        </div>

        <div className="flex flex-wrap items-center justify-end gap-2 border-t border-slate-100 px-7 py-4">
          <button type="button" onClick={onClose} className="rounded-full px-4 py-2 text-[14px] font-bold text-slate-500 transition hover:bg-slate-100 hover:text-ink">
            Close
          </button>
          {active ? (
            <button type="button" onClick={onExit} className="rounded-full border border-slate-200 bg-white px-5 py-2 text-[14px] font-bold text-ink transition hover:border-slate-300">
              Exit emergency mode
            </button>
          ) : (
            <button
              type="button"
              onClick={onActivate}
              className="group inline-flex items-center gap-2.5 rounded-full bg-coral-500 py-1.5 pl-5 pr-1.5 text-[14.5px] font-bold text-white shadow-[inset_0_1px_0_rgb(255_255_255/0.25),0_14px_28px_-12px_rgb(238_93_88/0.8)] transition hover:bg-coral-600"
            >
              Enter emergency mode
              <span className="grid h-8 w-8 place-items-center rounded-full bg-white/20 transition group-hover:translate-x-0.5">
                <ArrowRight size={15} strokeWidth={2.5} />
              </span>
            </button>
          )}
        </div>
      </div>
    </div>
  )
}

function Figure({ label, value }) {
  return (
    <div>
      <dt className="text-[10.5px] font-bold uppercase tracking-[0.16em] text-white/70">{label}</dt>
      <dd className="mt-1 font-display text-[1.7rem] font-semibold leading-none tabular-nums">{value}</dd>
    </div>
  )
}
