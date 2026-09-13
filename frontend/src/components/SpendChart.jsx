import { Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { rupees, shortDate } from '../lib/format.js'

export default function SpendChart({ data, height = 220 }) {
  return (
    <ResponsiveContainer width="100%" height={height}>
      <AreaChart data={data} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
        <defs>
          <linearGradient id="spend" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#3139fb" stopOpacity={0.25} />
            <stop offset="100%" stopColor="#3139fb" stopOpacity={0} />
          </linearGradient>
        </defs>
        <CartesianGrid stroke="#f1f5f9" vertical={false} />
        <XAxis dataKey="date" tickFormatter={shortDate} tick={{ fontSize: 11, fill: '#64748b' }} tickLine={false} axisLine={false} minTickGap={32} />
        <YAxis tickFormatter={(v) => `₹${v}`} tick={{ fontSize: 11, fill: '#64748b' }} tickLine={false} axisLine={false} width={56} />
        <Tooltip
          formatter={(v) => [rupees(v), 'Spend']}
          labelFormatter={shortDate}
          contentStyle={{ borderRadius: 8, border: '1px solid #e2e8f0', fontSize: 12 }}
        />
        <Area type="monotone" dataKey="amount" stroke="#3139fb" strokeWidth={2} fill="url(#spend)" isAnimationActive={false} />
      </AreaChart>
    </ResponsiveContainer>
  )
}
