import { rupees } from '../lib/format.js'

const LABEL = {
  ec2: 'EC2 compute',
  rds: 'RDS databases',
  ebs: 'EBS volumes',
  nat: 'NAT gateway',
  s3: 'S3 storage',
}

// EBS volumes and S3 buckets bill whether or not anything is attached to them — that is the
// whole point of the unattached-volume rule — so they count even when `running` is false.
const billsNow = (r) => (r.running || r.type === 'ebs' || r.type === 's3' ? r.costPerHour : 0)

/* One series, one hue: these categories have no natural order, so bar length alone carries
   the magnitude. Values sit in an aligned column rather than at each tip, which keeps the
   short bars' labels from colliding with their marks. */
export default function BurnBreakdown({ resources }) {
  const byType = new Map()
  for (const r of resources) {
    const perDay = billsNow(r) * 24
    if (!perDay) continue
    const prev = byType.get(r.type) ?? { perDay: 0, count: 0 }
    byType.set(r.type, { perDay: prev.perDay + perDay, count: prev.count + 1 })
  }

  const rows = [...byType].map(([type, v]) => ({ type, ...v })).sort((a, b) => b.perDay - a.perDay)
  if (!rows.length) return null

  const total = rows.reduce((s, r) => s + r.perDay, 0)
  const max = rows[0].perDay

  return (
    <div className="border-t border-slate-100 px-5 py-4">
      <div className="flex items-baseline justify-between gap-3">
        <p className="text-[10px] font-bold uppercase tracking-[0.14em] text-slate-400">Where the burn goes</p>
        <p className="text-[11px] font-semibold tabular-nums text-slate-500">{rupees(total)}/day</p>
      </div>

      <ul className="mt-3 space-y-1.5">
        {rows.map((r) => (
          <li
            key={r.type}
            title={`${r.count} ${r.count === 1 ? 'resource' : 'resources'} · ${Math.round((r.perDay / total) * 100)}% of the daily burn`}
            className="group grid grid-cols-[6.5rem_1fr_3.75rem] items-center gap-3 rounded-lg py-1 transition hover:bg-slate-50"
          >
            <span className="truncate text-[12px] font-medium text-slate-600">{LABEL[r.type] ?? r.type}</span>
            <span className="h-2.5">
              <span
                className="block h-full rounded-r-[4px] bg-arc-500 transition-all duration-500 group-hover:bg-arc-600"
                style={{ width: `${Math.max((r.perDay / max) * 100, 1.5)}%` }}
              />
            </span>
            <span className="text-right text-[12px] font-semibold tabular-nums text-ink">{rupees(r.perDay)}</span>
          </li>
        ))}
      </ul>
    </div>
  )
}
