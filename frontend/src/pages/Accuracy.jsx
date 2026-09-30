import { Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { usePredictions } from '../api/hooks.js'
import { rupees } from '../lib/format.js'
import { Card, CardHeader, ErrorState, Loading, PageHeader, Stat } from '../components/ui.jsx'

export default function Accuracy() {
  const { data, isLoading, error, refetch } = usePredictions()
  if (isLoading) return <Loading label="Grading past predictions…" />
  if (!data) return <ErrorState error={error} onRetry={() => refetch()} />

  const graded = data.filter((p) => p.actual != null)
  const errors = graded.map((p) => Math.abs(p.predicted - p.actual) / p.actual)
  const mape = errors.reduce((a, b) => a + b, 0) / errors.length
  const pending = data.find((p) => p.actual == null)

  return (
    <>
      <PageHeader title="Prediction accuracy" subtitle="Every month-end prediction is stored when it’s made, then graded when the real bill lands." />

      <div className="grid gap-4 sm:grid-cols-3">
        <Stat label="Mean absolute error" value={`${(mape * 100).toFixed(1)}%`} hint={`over ${graded.length} graded months`} />
        <Stat label="Within 10%" value={`${errors.filter((e) => e <= 0.1).length} of ${graded.length}`} hint="months" />
        <Stat label={`${pending?.month ?? 'Current'} prediction`} value={pending ? rupees(pending.predicted) : '—'} hint="grades when the bill lands" />
      </div>

      <Card className="mt-6">
        <CardHeader title="Predicted vs actual" subtitle="Baseline predictor: linear extrapolation of daily spend" />
        <div className="p-4">
          <ResponsiveContainer width="100%" height={280}>
            <BarChart data={data} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
              <CartesianGrid stroke="#f1f5f9" vertical={false} />
              <XAxis dataKey="month" tick={{ fontSize: 12, fill: '#64748b' }} tickLine={false} axisLine={false} />
              <YAxis tickFormatter={(v) => `₹${v / 1000}k`} tick={{ fontSize: 11, fill: '#64748b' }} tickLine={false} axisLine={false} width={48} />
              <Tooltip formatter={(v) => rupees(v)} contentStyle={{ borderRadius: 8, border: '1px solid #e2e8f0', fontSize: 12 }} />
              <Legend wrapperStyle={{ fontSize: 12 }} />
              <Bar dataKey="predicted" name="Predicted" fill="#94a3b8" radius={[4, 4, 0, 0]} />
              <Bar dataKey="actual" name="Actual" fill="#059669" radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </Card>

      <Card className="mt-6">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="border-b border-slate-100 text-left text-xs text-slate-500">
              <tr>
                <th className="px-5 py-2 font-medium">Month</th>
                <th className="px-3 py-2 text-right font-medium">Predicted</th>
                <th className="px-3 py-2 text-right font-medium">Actual</th>
                <th className="px-5 py-2 text-right font-medium">Error</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {data.map((p) => {
                const err = p.actual != null ? (p.predicted - p.actual) / p.actual : null
                return (
                  <tr key={p.month}>
                    <td className="px-5 py-2.5">{p.month}</td>
                    <td className="px-3 py-2.5 text-right tabular-nums">{rupees(p.predicted)}</td>
                    <td className="px-3 py-2.5 text-right tabular-nums">{p.actual != null ? rupees(p.actual) : <span className="text-slate-400">pending</span>}</td>
                    <td className={`px-5 py-2.5 text-right tabular-nums ${err == null ? 'text-slate-400' : Math.abs(err) > 0.1 ? 'text-amber-700' : 'text-slate-700'}`}>
                      {err == null ? '—' : `${err > 0 ? '+' : ''}${(err * 100).toFixed(1)}%`}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      </Card>
    </>
  )
}
