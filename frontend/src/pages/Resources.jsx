import { useMemo, useState } from 'react'
import { useResources } from '../api/hooks.js'
import { ago, rupees } from '../lib/format.js'
import { Card, Loading, PageHeader } from '../components/ui.jsx'
import StateBadge from '../components/StateBadge.jsx'

const TYPES = ['all', 'ec2', 'rds', 'ebs', 'nat', 's3', 'sg']

export default function Resources() {
  const { data, isLoading } = useResources()
  const [type, setType] = useState('all')
  const [state, setState] = useState('all')

  const items = useMemo(
    () => (data?.items ?? []).filter((r) => (type === 'all' || r.type === type) && (state === 'all' || r.state === state)),
    [data, type, state],
  )

  if (isLoading) return <Loading />

  return (
    <>
      <PageHeader title="Resources" subtitle={`Everything Ward can see in your account · inventory as of ${ago(data.asOf)}`} />

      <div className="mb-4 flex flex-wrap gap-3">
        <Segmented options={TYPES} value={type} onChange={setType} />
        <select value={state} onChange={(e) => setState(e.target.value)} className="rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-sm">
          {['all', 'watched', 'warning', 'alert', 'snoozed'].map((s) => <option key={s} value={s}>{s === 'all' ? 'Any state' : s}</option>)}
        </select>
      </div>

      <Card>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="border-b border-slate-100 text-left text-xs text-slate-500">
              <tr>
                <th className="px-5 py-2 font-medium">Resource</th>
                <th className="px-3 py-2 font-medium">Type</th>
                <th className="px-3 py-2 font-medium">Region</th>
                <th className="px-3 py-2 font-medium">Running</th>
                <th className="px-3 py-2 font-medium">Owner</th>
                <th className="px-3 py-2 text-right font-medium">₹/day</th>
                <th className="px-5 py-2 font-medium">State</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {items.map((r) => (
                <tr key={r.id} className="hover:bg-slate-50">
                  <td className="px-5 py-2.5">
                    <p className="font-medium text-slate-900">{r.name}</p>
                    <p className="font-mono text-xs text-slate-500">{r.id}</p>
                  </td>
                  <td className="px-3 py-2.5 text-slate-600">{r.instanceType ?? r.type.toUpperCase()}</td>
                  <td className={`px-3 py-2.5 ${r.region !== 'ap-south-1' ? 'font-medium text-amber-700' : 'text-slate-600'}`}>{r.region}</td>
                  <td className="px-3 py-2.5 tabular-nums text-slate-600">{r.running && r.runtimeHours ? `${r.runtimeHours}h` : '—'}</td>
                  <td className="px-3 py-2.5">{r.tags.Owner ?? <span className="text-xs text-rose-600">missing</span>}</td>
                  <td className="px-3 py-2.5 text-right tabular-nums">{r.costPerHour ? rupees(r.costPerHour * 24) : '—'}</td>
                  <td className="px-5 py-2.5"><StateBadge state={r.state} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {!items.length && <p className="py-8 text-center text-sm text-slate-500">No resources match these filters.</p>}
      </Card>
    </>
  )
}

function Segmented({ options, value, onChange }) {
  return (
    <div className="inline-flex flex-wrap rounded-lg border border-slate-300 bg-white p-0.5">
      {options.map((o) => (
        <button
          key={o}
          onClick={() => onChange(o)}
          className={`rounded-md px-2.5 py-1 text-xs font-medium uppercase ${value === o ? 'bg-slate-900 text-white' : 'text-slate-600 hover:bg-slate-100'}`}
        >
          {o}
        </button>
      ))}
    </div>
  )
}
