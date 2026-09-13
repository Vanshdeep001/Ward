export function Card({ className = '', children }) {
  return (
    <div className={`rounded-2xl border border-slate-200/80 bg-white shadow-[0_1px_2px_rgb(15_23_42/0.04)] ${className}`}>
      {children}
    </div>
  )
}

export function CardHeader({ title, subtitle, action }) {
  return (
    <div className="flex flex-wrap items-start justify-between gap-x-4 gap-y-2 border-b border-slate-100 px-5 py-4">
      <div className="min-w-0">
        <h2 className="text-[15px] font-semibold text-ink">{title}</h2>
        {subtitle && <p className="mt-0.5 text-xs text-slate-500">{subtitle}</p>}
      </div>
      {action}
    </div>
  )
}

const buttonStyles = {
  // The Arc "Try Dia" pill: near-black, slightly raised.
  primary:
    'bg-ink text-white shadow-[inset_0_1px_0_rgb(255_255_255/0.12),0_1px_2px_rgb(0_0_0/0.2)] hover:bg-black active:translate-y-px',
  brand: 'bg-arc-600 text-white shadow-[inset_0_1px_0_rgb(255_255_255/0.18)] hover:bg-arc-700 active:translate-y-px',
  secondary: 'border border-slate-200 bg-white text-ink shadow-[0_1px_2px_rgb(15_23_42/0.05)] hover:border-slate-300 hover:bg-slate-50',
  ghost: 'text-slate-600 hover:bg-slate-100 hover:text-ink',
  danger: 'bg-coral-600 text-white shadow-[inset_0_1px_0_rgb(255_255_255/0.18)] hover:bg-coral-500 active:translate-y-px',
}

export function Button({ variant = 'primary', className = '', ...props }) {
  return (
    <button
      className={`inline-flex items-center justify-center gap-1.5 rounded-xl px-3.5 py-2 text-sm font-semibold transition disabled:cursor-not-allowed disabled:opacity-50 ${buttonStyles[variant]} ${className}`}
      {...props}
    />
  )
}

// Large call-to-action with the icon set in its own tile, as on arc.net.
export function HeroButton({ icon: Icon, children, light = false, className = '', ...props }) {
  const skin = light
    ? 'bg-white text-ink hover:bg-arc-50 shadow-[0_10px_30px_-10px_rgb(0_0_0/0.5)]'
    : 'bg-ink text-white hover:bg-black shadow-[inset_0_1px_0_rgb(255_255_255/0.12),0_8px_24px_-8px_rgb(0_0_0/0.45)]'
  const tile = light ? 'bg-arc-600 text-white' : 'bg-gradient-to-br from-white to-arc-100 text-arc-700'
  return (
    <button
      className={`group inline-flex items-center gap-3 rounded-2xl py-2 pl-2 pr-5 text-base font-semibold transition active:translate-y-px disabled:cursor-not-allowed disabled:opacity-60 ${skin} ${className}`}
      {...props}
    >
      <span className={`grid h-9 w-9 place-items-center rounded-xl ${tile}`}>
        <Icon size={18} />
      </span>
      {children}
      <span aria-hidden className="transition group-hover:translate-x-0.5">→</span>
    </button>
  )
}

const pillStyles = {
  slate: 'bg-slate-100 text-slate-700',
  green: 'bg-emerald-50 text-emerald-700 ring-1 ring-emerald-200',
  amber: 'bg-amber-50 text-amber-800 ring-1 ring-amber-200',
  red: 'bg-coral-50 text-coral-600 ring-1 ring-coral-100',
  blue: 'bg-arc-50 text-arc-700 ring-1 ring-arc-100',
  violet: 'bg-violet-50 text-violet-700 ring-1 ring-violet-200',
}

export function Pill({ tone = 'slate', children }) {
  return (
    <span className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-semibold ${pillStyles[tone]}`}>
      {children}
    </span>
  )
}

export function PageHeader({ title, subtitle, action }) {
  return (
    <div className="mb-8 flex flex-wrap items-end justify-between gap-4">
      <div className="max-w-2xl">
        <h1 className="font-display text-4xl font-semibold leading-[1.05] text-ink md:text-[2.75rem]">{title}</h1>
        {subtitle && <p className="mt-2 text-[15px] leading-relaxed text-slate-600">{subtitle}</p>}
      </div>
      {action}
    </div>
  )
}

export function Stat({ label, value, hint, tone = 'slate' }) {
  const color = { slate: 'text-ink', green: 'text-emerald-700', red: 'text-coral-600', amber: 'text-amber-700' }[tone]
  return (
    <Card className="p-5">
      <p className="text-xs font-semibold text-slate-500">{label}</p>
      <p className={`mt-2 font-display text-[2rem] font-semibold leading-none tabular-nums ${color}`}>{value}</p>
      {hint && <p className="mt-2 text-xs text-slate-500">{hint}</p>}
    </Card>
  )
}

export function Loading({ label = 'Loading…' }) {
  return (
    <div className="flex items-center justify-center gap-2 py-16 text-sm text-slate-400">
      <span className="h-2 w-2 animate-pulse rounded-full bg-arc-400" />
      {label}
    </div>
  )
}

export function Empty({ children }) {
  return <p className="py-10 text-center text-sm text-slate-500">{children}</p>
}
