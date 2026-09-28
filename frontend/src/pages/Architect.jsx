import { useEffect, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { ArrowRight, Check, Cloud, Database, Globe2, HardDrive, Server, Users, X } from 'lucide-react'
import { api } from '../api/client.js'
import { rupees } from '../lib/format.js'

/* Architect. A sentence in, a priced blueprint out. Before the first answer the page shows what you'll
   get — the three steps, and a ghost of the blueprint — so it is never an empty field on an empty page.
   The answer leads with a verdict and a budget gauge, then draws the setup on blueprint paper, prices it
   line by line, and lists what was left out on purpose, with the reason. */

const DEFAULT = 'I want to deploy my MERN attendance application for 500 students and keep it under ₹1,500/month.'

const EXAMPLES = [
  { label: 'MERN app · 500 students', prompt: DEFAULT },
  { label: 'Portfolio site', prompt: 'I need a static portfolio website for myself, as cheap as possible, under ₹300/month.' },
  { label: 'Fest registrations · 2,000 users', prompt: 'A registration site for our college fest, 2,000 users signing up on the same morning, under ₹3,000/month.' },
]

const SERVICE = {
  EC2: { icon: Server, color: '#3139fb', what: 'Server' },
  EBS: { icon: HardDrive, color: '#8e96ff', what: 'Disk' },
  'Public IPv4': { icon: Globe2, color: '#ffb48f', what: 'Address' },
  RDS: { icon: Database, color: '#b79bff', what: 'Database' },
  DocumentDB: { icon: Database, color: '#b79bff', what: 'Database' },
  'MongoDB Atlas': { icon: Database, color: '#34c79a', what: 'Database' },
  S3: { icon: HardDrive, color: '#8e96ff', what: 'Storage' },
  CloudFront: { icon: Globe2, color: '#f7827d', what: 'Delivery' },
}
const svc = (name) => SERVICE[name] ?? { icon: Cloud, color: '#94a3b8', what: 'Service' }

export default function Architect() {
  const [params] = useSearchParams()
  const [prompt, setPrompt] = useState(params.get('q') ?? DEFAULT)
  const [result, setResult] = useState(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const [answers, setAnswers] = useState({})

  // Answers build up across rounds: choosing "MongoDB" can raise "where should it live?", and the
  // first round's answers must travel with the second. A new sentence starts over.
  async function run(more) {
    const all = more ? { ...answers, ...more } : {}
    setAnswers(all)
    setBusy(true)
    setError(null)
    try {
      setResult(await api.architect(prompt, all))
    } catch (e) {
      setError(e.message)
    } finally {
      setBusy(false)
    }
  }

  useEffect(() => {
    if (params.get('q')) run()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  return (
    <>
      <header className="mb-8">
        <p className="text-[11px] font-bold uppercase tracking-[0.2em] text-slate-400">Architect · the simplest setup that fits</p>
        <h1 className="mt-3 max-w-3xl font-display text-[clamp(2.3rem,5vw,3.7rem)] font-semibold leading-[1.02] tracking-tight text-ink">
          Tell Ward what you’re building. Get a <span className="text-arc-600">priced blueprint</span>.
        </h1>
      </header>

      <form
        onSubmit={(e) => {
          e.preventDefault()
          if (prompt.trim()) run()
        }}
        className="rounded-[30px] bg-gradient-to-br from-arc-300 via-[#f5c6dc] to-[#ffd2bd] p-[1.5px] shadow-[0_26px_60px_-30px_rgb(49_57_251/0.55)]"
      >
        <div className="rounded-[28.5px] bg-white px-6 pb-4 pt-5">
          <label htmlFor="arch" className="text-[10.5px] font-bold uppercase tracking-[0.16em] text-slate-400">
            What are you building, for how many people, on what budget?
          </label>
          <textarea
            id="arch"
            rows={2}
            value={prompt}
            onChange={(e) => setPrompt(e.target.value)}
            className="mt-2 w-full resize-none bg-transparent font-display text-[clamp(1.35rem,2.6vw,1.8rem)] font-semibold leading-snug tracking-tight text-ink outline-none placeholder:text-slate-300"
          />
          <div className="mt-3 flex flex-wrap items-center justify-between gap-3 border-t border-slate-100 pt-4">
            <div className="flex flex-wrap items-center gap-1.5">
              <span className="mr-1 text-[11.5px] text-slate-400">Try</span>
              {EXAMPLES.map((ex) => (
                <button
                  key={ex.label}
                  type="button"
                  onClick={() => { setPrompt(ex.prompt); setResult(null) }}
                  className={`rounded-full px-3 py-1 text-[12px] font-semibold transition ${
                    prompt === ex.prompt ? 'bg-arc-50 text-arc-700 ring-1 ring-inset ring-arc-200' : 'bg-slate-50 text-slate-600 hover:bg-slate-100 hover:text-ink'
                  }`}
                >
                  {ex.label}
                </button>
              ))}
            </div>
            <button
              type="submit"
              disabled={!prompt.trim() || busy}
              className="group inline-flex items-center gap-2.5 rounded-full bg-arc-600 py-2 pl-5 pr-2 text-[15px] font-bold text-white shadow-[inset_0_1px_0_rgb(255_255_255/0.2),0_14px_28px_-12px_rgb(49_57_251/0.8)] transition hover:bg-arc-700 disabled:bg-slate-300 disabled:shadow-none"
            >
              {busy ? 'Drawing…' : 'Draw my blueprint'}
              <span className="grid h-8 w-8 place-items-center rounded-full bg-white/20 transition group-hover:translate-x-0.5">
                <ArrowRight size={16} strokeWidth={2.5} />
              </span>
            </button>
          </div>
        </div>
      </form>

      {error && <p className="mt-4 rounded-2xl bg-coral-50 px-4 py-3 text-[13px] text-coral-600 ring-1 ring-inset ring-coral-100">{error}</p>}

      {result?.understood?.length > 0 && <Understood items={result.understood} />}
      {!result && <Preview />}
      {result?.status === 'needs-clarification' && (
        <Questions key={result.questions.map((q) => q.term).join()} questions={result.questions} onSubmit={run} busy={busy} />
      )}
      {result?.status === 'recommended' && <Recommendation r={result} />}
    </>
  )
}

/* ── Before the first answer ──────────────────────────────────────────────── */

function Preview() {
  const steps = [
    ['Describe it', 'What it is, roughly how many people, and what you can spend.'],
    ['Answer two questions', 'Does everyone arrive at once? Does an hour of downtime matter?'],
    ['Get a priced blueprint', 'Every service with its monthly cost — and what you can safely skip.'],
  ]
  return (
    <div className="mt-8 grid gap-6 lg:grid-cols-[0.9fr_1.1fr]">
      <ol className="space-y-3">
        {steps.map(([title, text], i) => (
          <li key={title} className="animate-rise flex gap-5 rounded-3xl border border-slate-200/70 bg-white/70 p-5 backdrop-blur" style={{ animationDelay: `${i * 70}ms` }}>
            <span className="font-display text-[2.6rem] font-semibold leading-none text-arc-600/25">{i + 1}</span>
            <div>
              <p className="font-display text-[1.25rem] font-semibold tracking-tight text-ink">{title}</p>
              <p className="mt-1 text-[13.5px] leading-relaxed text-slate-500">{text}</p>
            </div>
          </li>
        ))}
      </ol>
      <Blueprint ghost components={[{ service: 'EC2', size: 't3.small' }, { service: 'RDS', size: 'db.t3.micro' }, { service: 'S3', size: 'Standard' }]} />
    </div>
  )
}

/* ── The two questions ────────────────────────────────────────────────────── */

function Questions({ questions, onSubmit, busy }) {
  const [choices, setChoices] = useState(() => Object.fromEntries(questions.map((q) => [q.term, q.options[q.defaultIndex].value])))
  return (
    <section className="mt-8">
      <p className="text-[11px] font-bold uppercase tracking-[0.2em] text-slate-400">
        {questions.length === 1 ? 'One thing' : `${questions.length} things`} your sentence didn’t say
      </p>
      <div className="mt-4 space-y-7">
        {questions.map((q, qi) => (
          <fieldset key={q.term} className="animate-rise" style={{ animationDelay: `${qi * 80}ms` }}>
            <legend className="mb-3 font-display text-[1.45rem] font-semibold tracking-tight text-ink">{q.question}</legend>
            <div className={`grid gap-3 ${q.options.length === 3 ? 'sm:grid-cols-3' : 'sm:grid-cols-2'}`}>
              {q.options.map((o) => {
                const on = choices[q.term] === o.value
                return (
                  <button
                    key={o.value}
                    type="button"
                    onClick={() => setChoices((c) => ({ ...c, [q.term]: o.value }))}
                    aria-pressed={on}
                    className={`relative rounded-3xl border p-5 text-left transition duration-300 ${
                      on ? 'border-arc-500 bg-white shadow-[0_0_0_4px_rgb(49_57_251/0.1),0_18px_36px_-22px_rgb(49_57_251/0.6)]' : 'border-slate-200 bg-white/70 hover:-translate-y-0.5 hover:border-slate-300 hover:bg-white'
                    }`}
                  >
                    <span className={`absolute right-4 top-4 grid h-6 w-6 place-items-center rounded-full transition ${on ? 'bg-arc-600 text-white' : 'ring-1 ring-inset ring-slate-300'}`}>
                      {on && <Check size={13} strokeWidth={3} />}
                    </span>
                    <p className="pr-8 text-[15px] font-semibold text-ink">{o.label}</p>
                    <p className="mt-2 font-mono text-[11.5px] text-slate-500">{o.detail}</p>
                  </button>
                )
              })}
            </div>
          </fieldset>
        ))}
      </div>
      <button
        type="button"
        onClick={() => onSubmit(choices)}
        disabled={busy}
        className="mt-6 inline-flex items-center gap-2 rounded-full bg-ink px-5 py-2.5 text-[14px] font-bold text-white transition hover:bg-black disabled:opacity-50"
      >
        {busy ? 'Drawing…' : 'Draw it'} <ArrowRight size={15} />
      </button>
    </section>
  )
}

/* ── The answer ───────────────────────────────────────────────────────────── */

function Recommendation({ r }) {
  const total = r.components.reduce((s, c) => s + c.perMonth, 0)
  return (
    <div className="mt-10 space-y-8">
      <section className="grid gap-8 lg:grid-cols-[1fr_minmax(320px,420px)] lg:items-end">
        <div>
          <p className="text-[11px] font-bold uppercase tracking-[0.2em] text-slate-400">
            {r.users ? `For ~${r.users.toLocaleString('en-IN')} users · ` : ''}{r.complexity}
          </p>
          <h2 className="mt-3 font-display text-[clamp(1.7rem,3vw,2.4rem)] font-semibold leading-[1.14] tracking-tight text-ink">
            {headline(r)}{' '}
            {r.free ? (
              <>— <span className="text-emerald-600">₹0 a month</span> while the free tier lasts.</>
            ) : (
              <>— about <span className="text-arc-600">{rupees(r.estimate.low)}–{rupees(r.estimate.high)}</span> a month.</>
            )}
          </h2>
        </div>
        <BudgetGauge r={r} />
      </section>

      <Blueprint components={r.components} users={r.users} />

      <div className="grid gap-6 lg:grid-cols-[1.15fr_0.85fr]">
        <section className="rounded-3xl border border-slate-200/70 bg-white p-6 shadow-[0_1px_2px_rgb(15_23_42/0.04),0_20px_44px_-34px_rgb(23_23_60/0.45)]">
          <p className="text-[11px] font-bold uppercase tracking-[0.2em] text-slate-400">What you’ll pay for</p>
          <ul className="mt-4 space-y-5">
            {r.components.map((c) => {
              const s = svc(c.service)
              const Icon = s.icon
              return (
                <li key={c.service}>
                  <div className="flex items-start gap-3">
                    <span className="grid h-10 w-10 shrink-0 place-items-center rounded-2xl text-white" style={{ background: s.color }}>
                      <Icon size={18} strokeWidth={2.2} />
                    </span>
                    <div className="min-w-0 flex-1">
                      <div className="flex items-baseline justify-between gap-3">
                        <p className="text-[15px] font-bold text-ink">{c.service} <span className="font-mono text-[11.5px] font-medium text-slate-400">{c.size}</span></p>
                        <p className="shrink-0 text-right font-display text-[1.2rem] font-semibold tabular-nums text-ink">
                          {c.perMonth ? rupees(c.perMonth) : 'Free'}
                          {!c.perMonth && c.fullPrice > 0 && <span className="block font-sans text-[10.5px] font-semibold text-slate-400">{rupees(c.fullPrice)} after free tier</span>}
                        </p>
                      </div>
                      <p className="mt-0.5 text-[13.5px] text-slate-600">
                        {c.role}
                        {c.where === 'external' && <span className="ml-2 rounded-full bg-emerald-50 px-2 py-0.5 text-[10.5px] font-bold text-emerald-700">outside AWS</span>}
                      </p>
                      <p className="mt-0.5 text-[12.5px] text-slate-400">{c.explainer}</p>
                      <div className="mt-2.5 h-1.5 overflow-hidden rounded-full bg-slate-100">
                        <div className="h-full rounded-full" style={{ width: `${total ? Math.max(2, (c.perMonth / total) * 100) : 0}%`, background: s.color }} />
                      </div>
                    </div>
                  </div>
                </li>
              )
            })}
          </ul>
          <div className="mt-6 flex items-baseline justify-between border-t border-dashed border-slate-200 pt-4">
            <span className="text-[13px] font-semibold text-slate-500">{r.free ? 'Monthly now · after the free tier' : 'Monthly, before traffic'}</span>
            <span className="font-display text-[1.6rem] font-semibold tabular-nums text-ink">
              {rupees(total)}
              {r.free && r.afterFreeTier != null && <span className="text-slate-400"> · {rupees(r.afterFreeTier)}</span>}
            </span>
          </div>
        </section>

        <section className="rounded-3xl border border-slate-200/70 bg-white p-6 shadow-[0_1px_2px_rgb(15_23_42/0.04),0_20px_44px_-34px_rgb(23_23_60/0.45)]">
          <p className="text-[11px] font-bold uppercase tracking-[0.2em] text-slate-400">Left out on purpose</p>
          <p className="mt-1 text-[12.5px] text-slate-500">Complexity has to be earned by something you said you need.</p>
          <ul className="mt-4 space-y-4">
            {r.whyNot.map((w) => (
              <li key={w.option} className="flex gap-3">
                <span className="mt-0.5 grid h-6 w-6 shrink-0 place-items-center rounded-full bg-coral-50 text-coral-500 ring-1 ring-inset ring-coral-100">
                  <X size={13} strokeWidth={3} />
                </span>
                <div>
                  <p className="font-display text-[1.1rem] font-semibold text-slate-400 line-through decoration-coral-400/70 decoration-2">{w.option}</p>
                  <p className="mt-0.5 text-[13px] leading-relaxed text-slate-600">{w.because}</p>
                </div>
              </li>
            ))}
          </ul>
        </section>
      </div>

      <p className="text-[12px] text-slate-400">{r.note}</p>
    </div>
  )
}

function headline(r) {
  const names = r.components.map((c) => c.service)
  if (!names.includes('EC2')) return 'No server at all — just storage and a CDN'
  const db = names.find((n) => ['RDS', 'DocumentDB', 'MongoDB Atlas'].includes(n))
  const server = r.components[0].size === 't3.micro' ? 'One small server' : `One ${r.components[0].size} server`
  if (db === 'MongoDB Atlas') return `${server} and a free MongoDB Atlas cluster`
  if (db) return `${server} and a managed database`
  if (r.components[0].role?.includes('MongoDB')) return `${server} running your app and MongoDB`
  return server
}

function Understood({ items }) {
  return (
    <p className="mt-4 flex flex-wrap items-center gap-1.5 text-[12.5px] text-slate-500">
      <span className="mr-1 font-semibold">Ward read:</span>
      {items.map((t) => (
        <span key={t} className="rounded-full bg-white px-2.5 py-0.5 font-semibold text-slate-700 ring-1 ring-inset ring-slate-200">{t}</span>
      ))}
    </p>
  )
}

// The estimate as a band on a track that starts at ₹0, the budget as a marker on the same scale. Labels
// sit under (range) and over (budget) the exact point they describe, and never run off the ends.
function BudgetGauge({ r }) {
  if (r.free) return <FreeTierCard r={r} />
  const max = Math.max(r.budget || 0, r.estimate.high) * 1.15
  const at = (n) => (n / max) * 100
  const fits = r.withinBudget
  const gap = r.budget ? Math.abs(r.estimate.high - r.budget) : 0
  const tone = fits == null ? 'text-ink' : fits ? 'text-emerald-600' : 'text-coral-600'
  const place = (pct) => ({ left: `${pct}%`, transform: `translateX(${pct < 12 ? '0' : pct > 88 ? '-100%' : '-50%'})` })

  return (
    <div className="rounded-3xl border border-slate-200/70 bg-white p-5 shadow-[0_1px_2px_rgb(15_23_42/0.04),0_20px_44px_-34px_rgb(23_23_60/0.45)]">
      <p className="text-[10.5px] font-bold uppercase tracking-[0.16em] text-slate-400">Against your budget</p>

      <div className="mt-3 flex items-end justify-between gap-4">
        <div>
          <p className={`font-display text-[1.9rem] font-semibold leading-none tabular-nums ${tone}`}>
            {r.budget ? (fits ? `${rupees(gap)} spare` : `${rupees(gap)} over`) : rupees(r.estimate.high)}
          </p>
          <p className="mt-1.5 text-[12px] text-slate-500">
            {r.budget ? `at the high estimate, on a ${rupees(r.budget)} budget` : 'high estimate — no budget given'}
          </p>
        </div>
        {fits != null && (
          <span className={`shrink-0 rounded-full px-2.5 py-1 text-[11px] font-bold ${fits ? 'bg-emerald-50 text-emerald-700' : 'bg-coral-50 text-coral-600'}`}>
            {fits ? 'Fits' : 'Over budget'}
          </span>
        )}
      </div>

      {/* the scale: budget label above its marker, range labels below the band */}
      <div className="relative mt-9 mb-8">
        {r.budget > 0 && (
          <span className={`absolute bottom-full mb-2 whitespace-nowrap text-[11px] font-bold ${fits ? 'text-emerald-700' : 'text-coral-600'}`} style={place(at(r.budget))}>
            Budget {rupees(r.budget)}
          </span>
        )}
        <div className="relative h-2.5 rounded-full bg-slate-100">
          <div className="absolute inset-y-0 rounded-full bg-gradient-to-r from-arc-400 to-arc-600" style={{ left: `${at(r.estimate.low)}%`, width: `${at(r.estimate.high) - at(r.estimate.low)}%` }} />
          {r.budget > 0 && (
            <span className={`absolute -top-1.5 h-5.5 w-1 -translate-x-1/2 rounded-full ring-2 ring-white ${fits ? 'bg-emerald-500' : 'bg-coral-500'}`} style={{ left: `${at(r.budget)}%` }} />
          )}
        </div>
        <span className="absolute top-full mt-2 whitespace-nowrap text-[11px] tabular-nums text-slate-400" style={place(0)}>₹0</span>
        <span className="absolute top-full mt-2 whitespace-nowrap text-[11px] font-semibold tabular-nums text-arc-700" style={place(at(r.estimate.low))}>
          {rupees(r.estimate.low)}
        </span>
        <span className="absolute top-full mt-2 whitespace-nowrap text-[11px] font-semibold tabular-nums text-arc-700" style={place(at(r.estimate.high))}>
          {rupees(r.estimate.high)}
        </span>
      </div>
    </div>
  )
}

// "Keep it free": ₹0 now, and — just as important — what it becomes when the free tier ends.
function FreeTierCard({ r }) {
  const paid = r.components.filter((c) => c.perMonth > 0)
  return (
    <div className="rounded-3xl border border-slate-200/70 bg-white p-5 shadow-[0_1px_2px_rgb(15_23_42/0.04),0_20px_44px_-34px_rgb(23_23_60/0.45)]">
      <div className="flex items-center justify-between gap-3">
        <p className="text-[10.5px] font-bold uppercase tracking-[0.16em] text-slate-400">Free tier</p>
        <span className={`rounded-full px-2.5 py-1 text-[11px] font-bold ${r.withinBudget ? 'bg-emerald-50 text-emerald-700' : 'bg-amber-50 text-amber-700'}`}>
          {r.withinBudget ? 'Fits' : `${paid.length} paid item${paid.length === 1 ? '' : 's'}`}
        </span>
      </div>
      <div className="mt-4 grid grid-cols-2 gap-4">
        <div>
          <p className="font-display text-[2rem] font-semibold leading-none tabular-nums text-emerald-600">{rupees(r.estimate.high)}</p>
          <p className="mt-1.5 text-[12px] text-slate-500">a month, now</p>
        </div>
        <div className="border-l border-slate-100 pl-4">
          <p className="font-display text-[2rem] font-semibold leading-none tabular-nums text-ink">{rupees(r.afterFreeTier ?? 0)}</p>
          <p className="mt-1.5 text-[12px] text-slate-500">a month, once it ends</p>
        </div>
      </div>
      <p className="mt-4 text-[11.5px] leading-relaxed text-slate-400">Set a guardrail to warn you before that day — Ward watches the bill either way.</p>
    </div>
  )
}

/* ── The blueprint ────────────────────────────────────────────────────────── */

// Users at the top, the main service beneath, everything it talks to on the row below — inside a
// dashed region frame, on grid paper. The ghost version is the preview drawn before any answer.
function Blueprint({ components, users, ghost }) {
  // The disk and the public address belong to the server: tags on it, not boxes of their own.
  const [main, ...others] = components.filter((c) => !c.attachedTo)
  const rest = others
  const attached = components.filter((c) => c.attachedTo)
  return (
    <section
      className={`relative overflow-hidden rounded-[30px] border px-6 py-8 md:px-10 ${ghost ? 'border-dashed border-arc-200 bg-arc-50/40' : 'border-arc-100 bg-[#f6f7ff] shadow-[0_24px_50px_-36px_rgb(49_57_251/0.5)]'}`}
      style={{
        backgroundImage:
          'linear-gradient(rgb(49 57 251 / 0.06) 1px, transparent 1px), linear-gradient(90deg, rgb(49 57 251 / 0.06) 1px, transparent 1px)',
        backgroundSize: '24px 24px',
      }}
    >
      <div className="mb-6 flex items-center justify-between">
        <p className="font-mono text-[11px] font-semibold uppercase tracking-[0.16em] text-arc-600/70">{ghost ? 'Your blueprint will appear here' : 'Blueprint'}</p>
        {!ghost && <p className="font-mono text-[11px] text-arc-600/60">1 region · 1 server · on-demand prices</p>}
      </div>

      <div className={`flex flex-col items-center ${ghost ? 'opacity-45' : ''}`}>
        <Node icon={Users} title="Your users" sub={users ? `~${users.toLocaleString('en-IN')}` : 'people'} muted />
        <Wire />
        <div className="relative w-full rounded-3xl border-2 border-dashed border-arc-200 px-4 pb-6 pt-8">
          <span className="absolute -top-3 left-6 rounded-full bg-[#f6f7ff] px-2 font-mono text-[11px] font-semibold text-arc-600">ap-south-1 · Mumbai</span>
          <div className="flex flex-col items-center">
            <Node service={main} strong />
            {attached.length > 0 && (
              <div className="mt-2 flex flex-wrap justify-center gap-1.5">
                {attached.map((c) => (
                  <span key={c.service} className="rounded-full bg-white px-2.5 py-0.5 font-mono text-[10.5px] text-slate-500 ring-1 ring-inset ring-arc-100">
                    + {c.service} · {c.size} · {c.perMonth ? `${rupees(c.perMonth)}/mo` : 'free tier'}
                  </span>
                ))}
              </div>
            )}
            {rest.length > 0 && (
              <>
                <Wire />
                <div className="relative grid w-full gap-4" style={{ gridTemplateColumns: `repeat(${rest.length}, minmax(0, 1fr))` }}>
                  {rest.length > 1 && (
                    <span className="absolute top-0 h-0.5 bg-arc-300" style={{ left: `${50 / rest.length}%`, right: `${50 / rest.length}%` }} />
                  )}
                  {rest.map((c) => (
                    <div key={c.service} className="flex flex-col items-center">
                      <span className="h-5 w-0.5 bg-arc-300" />
                      <Node service={c} />
                    </div>
                  ))}
                </div>
              </>
            )}
          </div>
        </div>
      </div>
    </section>
  )
}

const Wire = () => <span className="h-8 w-0.5 bg-gradient-to-b from-arc-300 to-arc-400" />

function Node({ service, icon, title, sub, muted, strong }) {
  const s = service ? svc(service.service) : null
  const Icon = icon ?? s.icon
  return (
    <div
      className={`flex min-w-[180px] items-center gap-3 rounded-2xl border bg-white px-4 py-3 ${
        muted ? 'border-dashed border-slate-300' : strong ? 'border-arc-200 shadow-[0_16px_34px_-20px_rgb(49_57_251/0.6)]' : 'border-slate-200 shadow-[0_10px_24px_-18px_rgb(23_23_60/0.5)]'
      }`}
    >
      <span className="grid h-10 w-10 shrink-0 place-items-center rounded-xl text-white" style={{ background: muted ? '#cbd5e1' : s.color }}>
        <Icon size={18} strokeWidth={2.2} />
      </span>
      <div className="min-w-0 leading-tight">
        <p className="text-[14px] font-bold text-ink">{title ?? service.service}</p>
        <p className="truncate font-mono text-[11px] text-slate-500">{sub ?? service.size}</p>
        {service?.where === 'external' && <p className="text-[10px] font-bold uppercase tracking-wider text-emerald-600">outside AWS</p>}
      </div>
      {service?.perMonth != null && (
        <span className="ml-auto pl-2 text-right font-display text-[1rem] font-semibold tabular-nums text-ink">
          {service.perMonth ? rupees(service.perMonth) : service.fullPrice ? '₹0' : 'Free'}
          <span className="block font-sans text-[9.5px] font-bold uppercase tracking-wider text-slate-400">a month</span>
        </span>
      )}
    </div>
  )
}
