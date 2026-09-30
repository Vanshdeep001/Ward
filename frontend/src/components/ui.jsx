import { Link } from 'react-router-dom'
import { useState } from 'react'
import { ArrowRight, Check, ChevronDown, Copy, RotateCw, ServerOff, TriangleAlert } from 'lucide-react'

// Sticker-style mark, after Arc's logo: a scalloped-top shield with a white outline and a warm core.
export function WardMark({ emergency, size = 32 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 32 32" aria-hidden className="drop-shadow-[0_2px_3px_rgb(10_8_60/0.35)]">
      <defs>
        <linearGradient id={`ward-core-${emergency ? 'e' : 'n'}`} x1="0" y1="0" x2="1" y2="1">
          <stop offset="0%" stopColor={emergency ? '#ffd29a' : '#ff9a8b'} />
          <stop offset="55%" stopColor={emergency ? '#ff8a65' : '#ff6f91'} />
          <stop offset="100%" stopColor={emergency ? '#e8463f' : '#7b61ff'} />
        </linearGradient>
      </defs>
      <path
        d="M16 3c1.3 1.1 2.7 1.1 4 0 1.3 1.1 2.7 1.1 4 0 1 .9 2.1 1.1 3.3 1v10.5c0 6.7-4.8 11.1-11.3 14.2C9.5 25.6 4.7 21.2 4.7 14.5V4c1.2.1 2.3-.1 3.3-1 1.3 1.1 2.7 1.1 4 0 1.3 1.1 2.7 1.1 4 0Z"
        fill={`url(#ward-core-${emergency ? 'e' : 'n'})`}
        stroke="#fff"
        strokeWidth="2.2"
        strokeLinejoin="round"
      />
      <path d="m11 15.8 3.4 3.4 6.8-7" fill="none" stroke="#fff" strokeWidth="2.8" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}

/* A deeper card than the plain Stat tiles: a tinted header well with an eyebrow above a
   serif title, and a footer that pins to the bottom so panels sitting side by side line up. */
export function Panel({ eyebrow, title, action, className = '', aura, icon, children }) {
  return (
    <section
      className={`group/aura relative flex h-full flex-col overflow-hidden rounded-3xl border border-slate-200/70 bg-white shadow-[0_1px_2px_rgb(15_23_42/0.04),0_20px_44px_-30px_rgb(23_23_60/0.45)] ${className}`}
    >
      <header className="flex items-start justify-between gap-4 border-b border-slate-100 bg-gradient-to-b from-slate-50/80 to-white px-5 py-4">
        <div className="min-w-0">
          {eyebrow && <p className="text-[10px] font-bold uppercase tracking-[0.14em] text-slate-400">{eyebrow}</p>}
          <h2 className="mt-1 font-display text-[1.15rem] font-semibold leading-tight text-ink">{title}</h2>
        </div>
        {action}
      </header>
      {children}
      <Aura color={aura} icon={icon} />
    </section>
  )
}

export function PanelLink({ to, children }) {
  return (
    <Link
      to={to}
      className="group inline-flex shrink-0 items-center gap-1 rounded-full border border-slate-200 bg-white px-2.5 py-1 text-[11px] font-bold text-slate-600 transition hover:border-arc-200 hover:bg-arc-50 hover:text-arc-700"
    >
      {children}
      <ArrowRight size={11} className="transition group-hover:translate-x-0.5" />
    </Link>
  )
}

export function Card({ className = '', aura, icon, children }) {
  return (
    <div className={`group/aura relative overflow-hidden rounded-2xl border border-slate-200/80 bg-white shadow-[0_1px_2px_rgb(15_23_42/0.04)] ${className}`}>
      {children}
      <Aura color={aura} icon={icon} />
    </div>
  )
}

/* The palette as light. Cards carry their colour as a soft glow in the top-right corner and, when they
   have an icon, that icon oversized and faint in the bottom-right, like a watermark. Both multiply onto
   whatever is underneath, so they tint the card without ever sitting over the text in a solid colour.
   The card needs `group/aura relative overflow-hidden`; put <Aura> last among its children. */
export const TINT = {
  arc: '#3139fb',
  peri: '#8e96ff',
  lilac: '#b79bff',
  violet: '#a78bfa',
  pink: '#f5a3c7',
  peach: '#ffb48f',
  coral: '#f7827d',
  amber: '#f5b54a',
  green: '#34c79a',
  slate: '#94a3b8',
}

export function Aura({ color = 'arc', icon: Icon, size = 120 }) {
  const hex = TINT[color] ?? color
  return (
    <>
      <span
        aria-hidden
        className="pointer-events-none absolute -right-16 -top-20 h-52 w-52 rounded-full opacity-70 mix-blend-multiply blur-2xl transition-opacity duration-500 group-hover/aura:opacity-100"
        style={{ background: `radial-gradient(circle, ${hex}40, ${hex}00 70%)` }}
      />
      {Icon && (
        <Icon
          aria-hidden
          size={size}
          strokeWidth={1.2}
          className="pointer-events-none absolute -bottom-6 -right-5 mix-blend-multiply transition-transform duration-500 group-hover/aura:-rotate-6 group-hover/aura:scale-105"
          style={{ color: hex, opacity: 0.1 }}
        />
      )}
    </>
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

export function Stat({ label, value, hint, tone = 'slate', icon }) {
  const color = { slate: 'text-ink', green: 'text-emerald-700', red: 'text-coral-600', amber: 'text-amber-700' }[tone]
  return (
    <Card className="p-5" aura={{ slate: 'arc', green: 'green', red: 'coral', amber: 'amber' }[tone]} icon={icon}>
      <p className="text-xs font-semibold text-slate-500">{label}</p>
      {/* Proportional figures: these sit side by side, so equal-width digits only read loose. */}
      <p className={`mt-2 font-display text-[2rem] font-semibold leading-none ${color}`}>{value}</p>
      {hint && <p className="mt-2 text-xs text-slate-500">{hint}</p>}
    </Card>
  )
}

/* While a page's data loads: Ward's shield in a medallion, a gradient arc circling it (the one moving
   part), and the page's shape sketched underneath, so the wait shows what is coming rather than a blank.
   Everything stops for people who ask for reduced motion. */
export function Loading({ label = 'Loading…', skeleton = true }) {
  return (
    <div role="status" aria-live="polite" className="animate-rise">
      <div className="flex flex-col items-center pb-10 pt-12">
        <span className="relative grid h-24 w-24 place-items-center">
          <span aria-hidden className="loader-halo absolute -inset-6 rounded-full bg-[radial-gradient(circle,rgb(142_150_255/0.38),rgb(245_163_199/0.2)_48%,transparent_70%)] blur-md" />
          <svg aria-hidden viewBox="0 0 96 96" className="loader-arc absolute inset-0 h-24 w-24">
            <defs>
              <linearGradient id="ward-loader-arc" x1="0" y1="0" x2="1" y2="1">
                <stop offset="0%" stopColor="#3139fb" />
                <stop offset="55%" stopColor="#e98bbd" />
                <stop offset="100%" stopColor="#ffb48f" stopOpacity="0" />
              </linearGradient>
            </defs>
            <circle cx="48" cy="48" r="44" fill="none" stroke="rgb(49 57 251 / 0.08)" strokeWidth="3" />
            <circle cx="48" cy="48" r="44" fill="none" stroke="url(#ward-loader-arc)" strokeWidth="3.5" strokeLinecap="round" strokeDasharray="170 277" />
          </svg>
          <span className="relative grid h-16 w-16 place-items-center rounded-full bg-white shadow-[0_0_0_6px_rgb(255_255_255/0.7),0_18px_36px_-14px_rgb(49_57_251/0.55)]">
            <WardMark size={34} />
          </span>
        </span>
        <p className="loader-text mt-6 font-display text-[1.2rem] font-semibold tracking-tight">{label}</p>
      </div>

      {skeleton && (
        <div aria-hidden className="space-y-6 opacity-80">
          <div className="space-y-3">
            <span className="skeleton block h-3 w-40 rounded-full" />
            <span className="skeleton block h-9 w-3/4 max-w-2xl rounded-2xl" />
            <span className="skeleton block h-9 w-1/2 max-w-md rounded-2xl" />
          </div>
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {[0, 1, 2].map((i) => (
              <div key={i} className="rounded-3xl border border-slate-200/60 bg-white/60 p-5" style={{ animationDelay: `${i * 120}ms` }}>
                <span className="skeleton block h-3 w-20 rounded-full" />
                <span className="skeleton mt-4 block h-7 w-2/3 rounded-xl" />
                <span className="skeleton mt-3 block h-3 w-full rounded-full" />
                <span className="skeleton mt-2 block h-3 w-4/5 rounded-full" />
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

export function Empty({ children }) {
  return <p className="py-10 text-center text-sm text-slate-500">{children}</p>
}

/* When a page can't show what it should. Two very different situations get two different messages:
   Ward's server not answering (the fix is to start it — so the command is right there), and a genuine
   bug (a plain apology, with the technical detail folded away for whoever needs it). */
const UNREACHABLE = /not reachable|failed to fetch|networkerror|load failed|econnrefused|→ 50[234]|http proxy error|fetch failed/i

export function isUnreachable(error) {
  return Boolean(error?.unreachable) || UNREACHABLE.test(String(error?.message ?? error ?? ''))
}

export function ErrorState({ error, onRetry, title }) {
  const offline = isUnreachable(error) || error == null
  const detail = String(error?.message ?? error ?? '')
  const [copied, setCopied] = useState(false)
  const command = 'cd backend; python -m uvicorn app.main:app --port 8000'
  const Icon = offline ? ServerOff : TriangleAlert

  return (
    <div role="alert" className="animate-rise mx-auto max-w-2xl pt-10">
      <div className="group/aura relative overflow-hidden rounded-[30px] border border-slate-200/70 bg-white px-8 pb-8 pt-9 text-center shadow-[0_1px_2px_rgb(15_23_42/0.04),0_30px_60px_-40px_rgb(23_23_60/0.5)]">
        <span className="relative mx-auto grid h-20 w-20 place-items-center">
          <span aria-hidden className={`absolute -inset-4 rounded-full blur-md ${offline ? 'bg-[radial-gradient(circle,rgb(142_150_255/0.35),transparent_70%)]' : 'bg-[radial-gradient(circle,rgb(247_130_125/0.35),transparent_70%)]'}`} />
          <span className={`relative grid h-16 w-16 place-items-center rounded-full bg-white shadow-[0_0_0_6px_rgb(255_255_255/0.7),0_16px_32px_-14px_rgb(23_23_60/0.5)] ${offline ? 'text-arc-600' : 'text-coral-500'}`}>
            <Icon size={28} strokeWidth={1.8} />
          </span>
        </span>

        <h2 className="mt-6 font-display text-[1.9rem] font-semibold leading-tight tracking-tight text-ink">
          {title ?? (offline ? 'Ward can’t reach its server' : 'Something went wrong on this page')}
        </h2>
        <p className="mx-auto mt-2 max-w-md text-[14.5px] leading-relaxed text-slate-500">
          {offline
            ? 'The page is fine — the backend isn’t answering. Start it, then try again. Nothing in your account is affected; Ward only reads.'
            : 'This is a bug on Ward’s side, not something you did. Trying again usually clears it.'}
        </p>

        {offline && (
          <div className="mx-auto mt-5 flex max-w-md items-center gap-2 rounded-2xl bg-paper px-4 py-2.5 text-left ring-1 ring-inset ring-slate-200/80">
            <code className="flex-1 overflow-x-auto whitespace-nowrap font-mono text-[12px] text-ink">
              <span className="select-none text-arc-500">$ </span>{command}
            </code>
            <button
              type="button"
              onClick={() => { navigator.clipboard?.writeText(command); setCopied(true); setTimeout(() => setCopied(false), 1500) }}
              className="inline-flex shrink-0 items-center gap-1 rounded-lg px-2 py-1 text-[11.5px] font-bold text-slate-500 transition hover:bg-white hover:text-ink"
            >
              {copied ? <><Check size={12} className="text-emerald-600" /> Copied</> : <><Copy size={12} /> Copy</>}
            </button>
          </div>
        )}

        {onRetry && (
          <button
            type="button"
            onClick={onRetry}
            className="group mt-6 inline-flex items-center gap-2.5 rounded-full bg-arc-600 py-1.5 pl-5 pr-1.5 text-[14px] font-bold text-white shadow-[inset_0_1px_0_rgb(255_255_255/0.2),0_12px_26px_-12px_rgb(49_57_251/0.8)] transition hover:bg-arc-700"
          >
            Try again
            <span className="grid h-8 w-8 place-items-center rounded-full bg-white/20 transition duration-500 group-hover:rotate-180">
              <RotateCw size={14} strokeWidth={2.5} />
            </span>
          </button>
        )}

        {detail && !offline && (
          <details className="group/details mx-auto mt-6 max-w-md text-left">
            <summary className="flex cursor-pointer list-none items-center justify-center gap-1 text-[12px] font-semibold text-slate-400 hover:text-slate-600">
              Technical details <ChevronDown size={13} className="transition group-open/details:rotate-180" />
            </summary>
            <pre className="mt-2 whitespace-pre-wrap break-words rounded-xl bg-paper px-3.5 py-2.5 font-mono text-[11.5px] text-slate-600 ring-1 ring-inset ring-slate-200/80">{detail}</pre>
          </details>
        )}
        <Aura color={offline ? 'arc' : 'coral'} />
      </div>
    </div>
  )
}
