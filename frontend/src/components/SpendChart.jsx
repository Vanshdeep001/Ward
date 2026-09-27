import { Area, AreaChart, CartesianGrid, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { rupees, shortDate } from '../lib/format.js'

// One series, so no legend — the panel title says what is plotted. `budgetPerDay` draws the
// pace the budget allows, which is what makes a given day's height mean anything.
export default function SpendChart({ data, height = 220, budgetPerDay }) {
  return (
    <ResponsiveContainer width="100%" height={height}>
      <AreaChart data={data} margin={{ top: 14, right: 8, left: 0, bottom: 0 }}>
        <defs>
          <linearGradient id="spend" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#3139fb" stopOpacity={0.14} />
            <stop offset="100%" stopColor="#3139fb" stopOpacity={0} />
          </linearGradient>
        </defs>
        <CartesianGrid stroke="#f1f5f9" vertical={false} />
        <XAxis dataKey="date" tickFormatter={shortDate} tick={{ fontSize: 11, fill: '#64748b' }} tickLine={false} axisLine={false} minTickGap={32} />
        <YAxis tickFormatter={(v) => `₹${v}`} tick={{ fontSize: 11, fill: '#64748b' }} tickLine={false} axisLine={false} width={56} />
        <Tooltip
          formatter={(v) => [rupees(v), 'Spend']}
          labelFormatter={shortDate}
          cursor={{ stroke: '#cbd5e1', strokeWidth: 1 }}
          contentStyle={{ borderRadius: 10, border: '1px solid #e2e8f0', fontSize: 12, boxShadow: '0 8px 24px -12px rgb(15 23 42 / 0.25)' }}
        />
        {budgetPerDay > 0 && (
          <ReferenceLine
            y={budgetPerDay}
            stroke="#94a3b8"
            strokeDasharray="5 4"
            label={{
              value: `budget pace ${rupees(budgetPerDay)}/day`,
              position: 'insideTopRight',
              fontSize: 10.5,
              fill: '#64748b',
              offset: 8,
            }}
          />
        )}
        <Area type="monotone" dataKey="amount" stroke="#3139fb" strokeWidth={2} fill="url(#spend)" isAnimationActive={false} />
      </AreaChart>
    </ResponsiveContainer>
  )
}
