import { BellOff } from 'lucide-react'
import { useAlerts, useSnooze } from '../api/hooks.js'
import { ago, rupees } from '../lib/format.js'
import { Button, Card, Loading, PageHeader, Pill } from '../components/ui.jsx'

const statusTone = { open: 'red', snoozed: 'violet', resolved: 'slate' }

export default function Alerts() {
  const { data, isLoading } = useAlerts()
  const snooze = useSnooze()

  if (isLoading) return <Loading />

  return (
    <>
      <PageHeader title="Alerts" subtitle="Ward only notifies on state changes — never every poll." />
      <Card>
        <ul className="divide-y divide-slate-100">
          {data.map((a) => (
            <li key={a.id} className="flex flex-wrap items-start justify-between gap-4 px-5 py-4">
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center gap-2">
                  <Pill tone={a.level === 'alert' ? 'red' : 'amber'}>{a.level}</Pill>
                  <Pill tone={statusTone[a.status]}>{a.status}</Pill>
                  <span className="text-xs text-slate-500">{ago(a.at)}</span>
                </div>
                <p className="mt-1.5 text-sm text-slate-900">{a.message}</p>
                <p className="mt-0.5 text-xs text-slate-500">
                  Rule: “{a.rule.english}”
                  {a.projectedMonthly && ` · ${rupees(a.projectedMonthly)}/month if left running`}
                  {a.status === 'snoozed' && ` · snoozed until ${ago(a.snoozedUntil).replace(' ago', '')} from now`}
                </p>
              </div>
              {a.status === 'open' && (
                <div className="flex gap-2">
                  {[4, 24].map((h) => (
                    <Button key={h} variant="secondary" onClick={() => snooze.mutate({ id: a.id, hours: h })} disabled={snooze.isPending}>
                      <BellOff size={14} /> {h}h
                    </Button>
                  ))}
                </div>
              )}
            </li>
          ))}
        </ul>
      </Card>
      <p className="mt-3 text-xs text-slate-500">Snoozing tells Ward the resource is intentional. It stays silent until the timer expires.</p>
    </>
  )
}
