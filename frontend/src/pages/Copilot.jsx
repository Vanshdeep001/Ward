import { useEffect, useRef, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import {
  AlertTriangle, ArrowRight, ArrowUp, Check, ChevronDown, Copy, Cpu, Database, ExternalLink, Filter, HardDrive,
  Layers, Network, Search, Server, ShieldAlert, ShieldCheck, Sparkles, TrendingUp, UserX, Wallet,
} from 'lucide-react'
import { api } from '../api/client.js'
import { rupees } from '../lib/format.js'
import { Aura, WardMark } from '../components/ui.jsx'

/* Ask Ward. A question goes through a pipeline — screened, searched, answered, its figures checked —
   and the page shows that pipeline instead of hiding it: while Ward works, the steps light up in turn;
   under every answer, the same steps say what actually happened. Resources the answer relies on are
   shown as cards; what else matched waits behind a toggle. */

const STARTERS = [
  { q: 'What is currently costing me the most?', label: 'Spend', icon: Wallet, aura: 'arc' },
  { q: 'Which resources have no owner?', label: 'Ownership', icon: UserX, aura: 'coral' },
  { q: 'Is anything open to the internet?', label: 'Exposure', icon: ShieldAlert, aura: 'peach' },
  { q: 'Are any disks sitting unused?', label: 'Waste', icon: HardDrive, aura: 'lilac' },
  { q: 'Why did my bill go up?', label: 'Bill', icon: TrendingUp, aura: 'pink' },
  { q: 'Tell me about my most expensive server', label: 'Deep dive', icon: Server, aura: 'peri' },
]

const KIND = {
  ec2: { icon: Server, label: 'Instance', color: '#3139fb' },
  rds: { icon: Database, label: 'Database', color: '#b79bff' },
  ebs: { icon: HardDrive, label: 'Volume', color: '#8e96ff' },
  nat: { icon: Network, label: 'NAT gateway', color: '#ffb48f' },
  sg: { icon: ShieldCheck, label: 'Security group', color: '#f7827d' },
}

const INTENT = {
  SEARCH: { label: 'Search', aura: 'arc' },
  ANSWER: { label: 'Answer', aura: 'peri' },
  ACT: { label: 'Draft rule', aura: 'amber' },
  REFUSE: { label: 'Read-only', aura: 'lilac' },
}

const THINKING = ['Checking the question', 'Searching your inventory', 'Ranking what matched', 'Writing the answer', 'Checking every figure']

export default function Copilot() {
  const [messages, setMessages] = useState([])
  const [state, setState] = useState({})
  const [busy, setBusy] = useState(false)
  const bottom = useRef(null)
  const [params, setParams] = useSearchParams()
  const asked = useRef(false)
  const status = useQuery({ queryKey: ['search-status'], queryFn: api.searchStatus, staleTime: 60_000 })

  // A question typed into the sidebar's "Ask Ward" bar arrives as ?q=.
  useEffect(() => {
    const q = params.get('q')
    if (!q || asked.current) return
    asked.current = true
    setParams({}, { replace: true })
    send(q)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [params])

  useEffect(() => {
    // Braces matter: scrollIntoView returns a Promise in current Chrome, and React would treat it as a cleanup function.
    bottom.current?.scrollIntoView({ behavior: 'smooth', block: 'end' })
  }, [messages, busy])

  async function send(text) {
    const msg = text.trim()
    if (!msg || busy) return
    setMessages((m) => [...m, { id: crypto.randomUUID(), role: 'user', text: msg }])
    setBusy(true)
    try {
      const res = await api.chat(msg, state)
      setMessages((m) => [...m, res.message])
      setState(res.state)
    } catch (e) {
      setMessages((m) => [...m, { id: crypto.randomUUID(), role: 'ward', intent: 'ANSWER', text: `Something went wrong: ${e.message}`, failed: true }])
    } finally {
      setBusy(false)
    }
  }

  const empty = messages.length === 0

  return (
    <div className="flex h-[calc(100vh-9rem)] flex-col md:h-[calc(100vh-6rem)]">
      <Header compact={!empty} status={status.data} />

      <div className="scroll-quiet -mx-2 flex-1 overflow-y-auto px-2 pb-6">
        {empty ? (
          <Starters onPick={send} />
        ) : (
          <div className="mx-auto max-w-4xl space-y-7 pt-2">
            {messages.map((m) => (m.role === 'user' ? <UserBubble key={m.id} text={m.text} /> : <WardMessage key={m.id} m={m} onSend={send} />))}
            {busy && <Thinking status={status.data} />}
            <div ref={bottom} />
          </div>
        )}
      </div>

      <Composer onSend={send} busy={busy} />
    </div>
  )
}

/* ── Header ───────────────────────────────────────────────────────────────── */

function Header({ compact, status }) {
  return (
    <header className={`flex flex-wrap items-end justify-between gap-x-8 gap-y-4 transition-all duration-500 ${compact ? 'mb-4' : 'mb-8'}`}>
      <div>
        <p className="text-[11px] font-bold uppercase tracking-[0.2em] text-slate-400">Ask Ward · read-only, grounded in your account</p>
        <h1 className={`mt-3 font-display font-semibold leading-[1.02] tracking-tight text-ink transition-all duration-500 ${compact ? 'text-[2rem]' : 'text-[clamp(2.4rem,5vw,3.6rem)]'}`}>
          Ask your account <span className="bg-gradient-to-r from-arc-600 via-[#8e6bff] to-coral-500 bg-clip-text text-transparent">anything.</span>
        </h1>
      </div>
      {status && <Engine status={status} />}
    </header>
  )
}

// What will answer: the retriever, the model, how much is indexed. A live dot, not a spinner.
function Engine({ status }) {
  const docs = Object.values(status.indexed ?? {}).reduce((s, n) => s + n, 0)
  const vector = status.retriever === 'pinecone'
  const model = status.generator !== 'extractive'
  return (
    <div className="group/aura relative flex items-center gap-4 overflow-hidden rounded-2xl border border-slate-200/70 bg-white px-4 py-3 shadow-[0_1px_2px_rgb(15_23_42/0.04),0_14px_30px_-22px_rgb(23_23_60/0.5)]">
      <span className="relative flex h-2.5 w-2.5">
        <span className="absolute inset-0 animate-ping rounded-full bg-emerald-400/60 [animation-duration:2.4s]" />
        <span className="relative h-2.5 w-2.5 rounded-full bg-emerald-500" />
      </span>
      <EngineStat label="Search" value={vector ? 'Pinecone' : 'Local index'} />
      <span className="h-7 w-px bg-slate-200" />
      <EngineStat label="Answers" value={model ? status.generator.split('/').pop() : 'Matches only'} />
      {docs > 0 && (
        <>
          <span className="h-7 w-px bg-slate-200" />
          <EngineStat label="Indexed" value={`${docs} docs`} />
        </>
      )}
      <Aura color="arc" />
    </div>
  )
}

function EngineStat({ label, value }) {
  return (
    <div className="leading-tight">
      <p className="text-[9.5px] font-bold uppercase tracking-[0.16em] text-slate-400">{label}</p>
      <p className="mt-0.5 text-[13px] font-semibold text-ink">{value}</p>
    </div>
  )
}

/* ── Empty state ──────────────────────────────────────────────────────────── */

function Starters({ onPick }) {
  return (
    <div className="pt-2">
      <p className="mb-4 text-[13px] text-slate-500">Start with one of these, or type your own below.</p>
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
        {STARTERS.map((s, i) => {
          const Icon = s.icon
          return (
            <button
              key={s.q}
              type="button"
              onClick={() => onPick(s.q)}
              className="animate-rise group/aura relative flex min-h-[132px] flex-col justify-between overflow-hidden rounded-3xl border border-slate-200/70 bg-white p-5 text-left shadow-[0_1px_2px_rgb(15_23_42/0.04),0_20px_44px_-34px_rgb(23_23_60/0.45)] transition duration-300 hover:-translate-y-1 hover:shadow-[0_1px_2px_rgb(15_23_42/0.04),0_26px_50px_-28px_rgb(23_23_60/0.5)]"
              style={{ animationDelay: `${i * 60}ms` }}
            >
              <span className="text-[10.5px] font-bold uppercase tracking-[0.16em] text-slate-400">{s.label}</span>
              <span className="mt-3 max-w-[85%] font-display text-[1.3rem] font-semibold leading-snug tracking-tight text-ink">{s.q}</span>
              <span className="mt-3 inline-flex items-center gap-1 text-[12px] font-bold text-arc-600 opacity-0 transition duration-300 group-hover/aura:translate-x-0.5 group-hover/aura:opacity-100">
                Ask <ArrowRight size={13} />
              </span>
              <Aura color={s.aura} icon={Icon} />
            </button>
          )
        })}
      </div>
    </div>
  )
}

/* ── The conversation ─────────────────────────────────────────────────────── */

function UserBubble({ text }) {
  return (
    <div className="animate-rise flex justify-end">
      <p className="max-w-[78%] rounded-[26px] rounded-br-lg bg-gradient-to-br from-arc-500 to-arc-700 px-5 py-3 text-[15px] font-medium leading-relaxed text-white shadow-[0_14px_30px_-16px_rgb(49_57_251/0.7)]">
        {text}
      </p>
    </div>
  )
}

function WardMessage({ m, onSend }) {
  const intent = INTENT[m.intent] ?? INTENT.ANSWER
  const sources = m.sources ?? tableSources(m.table)
  const cited = m.sources ? sources.filter((s) => s.cited) : sources
  const others = m.sources ? sources.filter((s) => !s.cited) : []
  const blocked = m.checks?.blocked

  return (
    <div className="animate-rise flex gap-3.5">
      <div className="shrink-0 pt-1"><WardMark size={34} /></div>

      <article className="group/aura relative min-w-0 flex-1 overflow-hidden rounded-[28px] border border-slate-200/70 bg-white p-5 shadow-[0_1px_2px_rgb(15_23_42/0.04),0_22px_48px_-34px_rgb(23_23_60/0.5)] md:p-6">
        <header className="mb-3 flex items-center gap-2">
          <span className="text-[13px] font-bold text-ink">Ward</span>
          <span className={`rounded-full px-2 py-0.5 text-[10.5px] font-bold uppercase tracking-[0.12em] ${blocked ? 'bg-violet-50 text-violet-700' : m.failed ? 'bg-coral-50 text-coral-600' : 'bg-arc-50 text-arc-700'}`}>
            {blocked ? 'Guardrail' : intent.label}
          </span>
        </header>

        <div className="whitespace-pre-line text-[15.5px] leading-[1.7] text-slate-800">
          {m.sources ? <Cited text={m.text} sources={sources} /> : <Bold text={m.text} />}
        </div>

        {cited.length > 0 && <SourceGrid sources={cited} />}
        {others.length > 0 && cited.length > 0 && <AlsoMatched sources={others} />}

        {m.command && <Command command={m.command} consoleUrl={m.consoleUrl} />}
        {(m.draft || m.draftRule || m.suggestedRule) && <RuleCard m={m} />}
        {m.link && (
          <Link to={m.link.to} className="mt-4 inline-flex items-center gap-1 text-[13px] font-bold text-arc-700 hover:underline">
            {m.link.label} <ArrowRight size={14} />
          </Link>
        )}

        {m.notice && (
          <p className="mt-4 flex items-start gap-2 rounded-2xl bg-amber-50/80 px-3.5 py-2.5 text-[12.5px] leading-relaxed text-amber-800 ring-1 ring-inset ring-amber-200/80">
            <AlertTriangle size={14} className="mt-0.5 shrink-0" /> {m.notice}
          </p>
        )}

        {(m.retriever || blocked) && <Trace m={m} cited={cited.length} />}

        {m.suggestions && (
          <div className="mt-4 flex flex-wrap gap-1.5">
            {m.suggestions.map((s) => (
              <button key={s} type="button" onClick={() => onSend(s)} className="rounded-full border border-slate-200 bg-white px-3 py-1 text-[12px] font-semibold text-slate-600 transition hover:border-arc-200 hover:bg-arc-50 hover:text-arc-700">
                {s}
              </button>
            ))}
          </div>
        )}
        <Aura color={blocked ? 'lilac' : m.failed ? 'coral' : intent.aura} />
      </article>
    </div>
  )
}

// The computed answers (spend, the bill) send a table of {id, name, costPerDay}; show them as sources too.
function tableSources(table) {
  return (table ?? []).map((r) => ({ id: r.id, name: r.name, costPerDay: r.costPerDay, type: r.id?.startsWith('i-') ? 'ec2' : r.id?.startsWith('vol-') ? 'ebs' : r.id?.startsWith('sg-') ? 'sg' : r.id?.startsWith('nat-') ? 'nat' : 'rds', owner: true }))
}

// The model cites resources as [id]; each becomes a chip naming the resource.
function Cited({ text, sources }) {
  const byId = Object.fromEntries(sources.map((s) => [s.id, s]))
  return text.split(/(\[[^\]\s]+\])/g).map((part, i) => {
    const s = byId[part.slice(1, -1)]
    if (!part.startsWith('[') || !s) return <Bold key={i} text={part} />
    return (
      <span key={i} className="mx-0.5 inline-flex translate-y-[-1px] items-center gap-1.5 rounded-lg bg-white px-2 py-0.5 align-middle font-mono text-[11.5px] font-semibold text-ink shadow-[0_1px_2px_rgb(15_23_42/0.06)] ring-1 ring-inset ring-slate-200">
        <span className="h-2 w-2 rounded-full" style={{ background: KIND[s.type]?.color ?? '#94a3b8' }} />
        {s.name ?? s.id}
      </span>
    )
  })
}

// Models write **bold**; show it as bold rather than asterisks.
function Bold({ text }) {
  return String(text ?? '').split(/(\*\*[^*]+\*\*)/g).map((p, i) =>
    p.startsWith('**') && p.endsWith('**') && p.length > 4 ? <strong key={i} className="font-semibold text-ink">{p.slice(2, -2)}</strong> : p,
  )
}

function SourceGrid({ sources }) {
  const [all, setAll] = useState(false)
  const shown = all ? sources : sources.slice(0, 6)
  return (
    <div className="mt-5">
      <p className="mb-2.5 text-[10.5px] font-bold uppercase tracking-[0.16em] text-slate-400">Resources in this answer</p>
      <div className="grid gap-2.5 sm:grid-cols-2 xl:grid-cols-3">
        {shown.map((s, i) => <SourceCard key={s.id} s={s} delay={i * 50} />)}
      </div>
      {sources.length > 6 && (
        <button type="button" onClick={() => setAll((v) => !v)} className="mt-2.5 inline-flex items-center gap-1 text-[12px] font-bold text-arc-700 hover:underline">
          {all ? 'Show fewer' : `Show all ${sources.length}`} <ChevronDown size={13} className={all ? 'rotate-180' : ''} />
        </button>
      )}
    </div>
  )
}

function SourceCard({ s, delay = 0 }) {
  const kind = KIND[s.type] ?? { icon: Layers, label: s.type, color: '#94a3b8' }
  const Icon = kind.icon
  return (
    <div
      className="animate-rise group/aura relative flex items-center gap-3 overflow-hidden rounded-2xl border border-slate-200/80 bg-paper/60 p-3 transition duration-300 hover:-translate-y-0.5 hover:bg-white hover:shadow-[0_14px_30px_-20px_rgb(23_23_60/0.5)]"
      style={{ animationDelay: `${delay}ms` }}
    >
      <span className="grid h-10 w-10 shrink-0 place-items-center rounded-xl text-white shadow-[0_8px_18px_-10px_rgb(23_23_60/0.6)]" style={{ background: kind.color }}>
        <Icon size={17} strokeWidth={2.2} />
      </span>
      <div className="min-w-0 flex-1">
        <p className="truncate text-[14px] font-semibold text-ink">{s.name ?? s.id}</p>
        <p className="truncate font-mono text-[10.5px] text-slate-400">{s.detail ?? kind.label}{s.region ? ` · ${s.region}` : ''}</p>
      </div>
      <div className="shrink-0 text-right leading-tight">
        <p className={`text-[13px] font-bold tabular-nums ${s.costPerDay ? 'text-ink' : 'text-slate-300'}`}>{s.costPerDay ? rupees(s.costPerDay) : '₹0'}</p>
        <p className="text-[9.5px] font-bold uppercase tracking-wider text-slate-400">a day</p>
        {!s.owner && <p className="mt-0.5 text-[10px] font-bold text-coral-600">no owner</p>}
      </div>
    </div>
  )
}

function AlsoMatched({ sources }) {
  const [open, setOpen] = useState(false)
  return (
    <div className="mt-3">
      <button type="button" onClick={() => setOpen((v) => !v)} className="inline-flex items-center gap-1 text-[12px] font-semibold text-slate-500 hover:text-ink">
        <Filter size={12} /> {open ? 'Hide' : 'Also matched'} ({sources.length}) <ChevronDown size={13} className={`transition ${open ? 'rotate-180' : ''}`} />
      </button>
      {open && (
        <div className="mt-2 flex flex-wrap gap-1.5">
          {sources.map((s) => (
            <span key={s.id} className="inline-flex items-center gap-1.5 rounded-full border border-slate-200 bg-white px-2.5 py-1 text-[11.5px] text-slate-600">
              <span className="h-1.5 w-1.5 rounded-full" style={{ background: KIND[s.type]?.color ?? '#94a3b8' }} />
              {s.name ?? s.id}
            </span>
          ))}
        </div>
      )}
    </div>
  )
}

// What actually happened, as the same steps the thinking state shows.
function Trace({ m, cited }) {
  const blocked = m.checks?.blocked
  if (blocked) {
    const why = { action: 'Ward is read-only', injection: 'looked like an attempt to change Ward’s instructions', 'off-topic': 'not about your AWS account' }[blocked]
    return (
      <div className="mt-5 flex flex-wrap items-center gap-1.5 border-t border-slate-100 pt-4">
        <Step ok icon={ShieldCheck} tone="violet">Stopped by a guardrail — {why}</Step>
      </div>
    )
  }
  const unsupported = m.checks?.unsupported ?? []
  const checked = m.checks?.numbersChecked ?? 0
  const model = m.generator && m.generator !== 'extractive'
  return (
    <div className="mt-5 flex flex-wrap items-center gap-1.5 border-t border-slate-100 pt-4">
      <Step ok icon={ShieldCheck}>Screened</Step>
      <Chevron />
      <Step ok icon={Search}>{m.retriever === 'pinecone' ? 'Pinecone' : 'Local index'}{m.sources ? ` · ${m.sources.length} found` : ''}</Step>
      <Chevron />
      <Step ok icon={model ? Sparkles : Layers}>{model ? m.generator.split('/').pop() : 'Matches shown'}{cited ? ` · ${cited} cited` : ''}</Step>
      {model && (
        <>
          <Chevron />
          {unsupported.length ? (
            <Step icon={AlertTriangle} tone="amber">{unsupported.length} figure{unsupported.length === 1 ? '' : 's'} unverified</Step>
          ) : (
            <Step ok icon={Check} tone="green">{checked ? `${checked} figure${checked === 1 ? '' : 's'} verified` : 'Nothing to verify'}</Step>
          )}
        </>
      )}
    </div>
  )
}

function Step({ icon: Icon, tone = 'slate', children }) {
  const tones = {
    slate: 'bg-slate-50 text-slate-600 ring-slate-200/80',
    green: 'bg-emerald-50 text-emerald-700 ring-emerald-200/80',
    amber: 'bg-amber-50 text-amber-800 ring-amber-200/80',
    violet: 'bg-violet-50 text-violet-700 ring-violet-200/80',
  }
  return (
    <span className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-[11.5px] font-semibold ring-1 ring-inset ${tones[tone]}`}>
      <Icon size={12} /> {children}
    </span>
  )
}

const Chevron = () => <span className="text-[11px] text-slate-300">→</span>

function Command({ command, consoleUrl }) {
  const [copied, setCopied] = useState(false)
  return (
    <div className="mt-4 space-y-2">
      <div className="flex items-center gap-2 rounded-2xl bg-paper px-3.5 py-2.5 ring-1 ring-inset ring-slate-200">
        <code className="flex-1 overflow-x-auto whitespace-nowrap font-mono text-[12px] text-ink">{command}</code>
        <button
          type="button"
          onClick={() => { navigator.clipboard?.writeText(command); setCopied(true); setTimeout(() => setCopied(false), 1500) }}
          className="rounded-lg p-1 text-slate-400 transition hover:bg-white hover:text-ink"
          title="Copy"
        >
          {copied ? <Check size={14} className="text-emerald-600" /> : <Copy size={14} />}
        </button>
      </div>
      {consoleUrl && (
        <a href={consoleUrl} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 text-[12px] font-bold text-arc-700 hover:underline">
          Open in AWS console <ExternalLink size={12} />
        </a>
      )}
    </div>
  )
}

function RuleCard({ m }) {
  const english = m.draft?.english ?? m.draftRule ?? m.suggestedRule?.english
  const note = m.draft ? `Verified · matches ${m.draft.matched} resource${m.draft.matched === 1 ? '' : 's'} now` : m.suggestedRule?.because
  return (
    <div className="mt-4 rounded-2xl bg-gradient-to-br from-amber-50 to-[#fff4ec] p-4 ring-1 ring-inset ring-amber-200/80">
      <p className="text-[10.5px] font-bold uppercase tracking-[0.16em] text-amber-700">Suggested guardrail</p>
      <p className="mt-1.5 font-display text-[1.15rem] font-semibold leading-snug text-ink">“{english}”</p>
      {note && <p className="mt-1 text-[12px] text-slate-500">{note}</p>}
      <Link to={`/rules?draft=${encodeURIComponent(english)}`} className="mt-3 inline-flex items-center gap-1 rounded-full bg-ink px-3.5 py-1.5 text-[12px] font-bold text-white transition hover:bg-black">
        Simulate and activate <ArrowRight size={13} />
      </Link>
    </div>
  )
}

/* ── While Ward works ─────────────────────────────────────────────────────── */

// The pipeline's steps, lit in turn. Timed, not reported — the request is one call — so it stops at the
// last step and waits there rather than claiming to be done.
function Thinking({ status }) {
  const [step, setStep] = useState(0)
  useEffect(() => {
    const timers = [350, 1100, 2000, 3600].map((ms, i) => setTimeout(() => setStep(i + 1), ms))
    return () => timers.forEach(clearTimeout)
  }, [])
  const steps = THINKING.map((s, i) => (i === 1 && status?.retriever === 'pinecone' ? 'Searching Pinecone' : s))
  return (
    <div className="animate-rise flex gap-3.5">
      <div className="shrink-0 pt-1"><WardMark size={34} /></div>
      <div className="group/aura relative flex-1 overflow-hidden rounded-[28px] border border-slate-200/70 bg-white p-5 shadow-[0_22px_48px_-34px_rgb(23_23_60/0.5)] md:p-6">
        <ol className="space-y-2.5">
          {steps.map((s, i) => (
            <li key={s} className={`flex items-center gap-3 text-[13.5px] transition-all duration-500 ${i > step ? 'opacity-30' : 'opacity-100'}`}>
              <span className={`grid h-5 w-5 shrink-0 place-items-center rounded-full transition-colors duration-500 ${i < step ? 'bg-emerald-500 text-white' : i === step ? 'bg-arc-600 text-white' : 'bg-slate-100'}`}>
                {i < step ? <Check size={11} strokeWidth={3} /> : i === step ? <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-white" /> : null}
              </span>
              <span className={i === step ? 'font-semibold text-ink' : 'text-slate-500'}>{s}</span>
            </li>
          ))}
        </ol>
        <Aura color="arc" icon={Cpu} size={100} />
      </div>
    </div>
  )
}

/* ── Composer ─────────────────────────────────────────────────────────────── */

function Composer({ onSend, busy }) {
  const [input, setInput] = useState('')
  const ready = input.trim() && !busy
  return (
    <form
      className="mx-auto w-full max-w-4xl pt-2"
      onSubmit={(e) => {
        e.preventDefault()
        if (!ready) return
        onSend(input)
        setInput('')
      }}
    >
      {/* A gradient hairline around a white field: the aurora, drawn as a border. */}
      <div className="rounded-[26px] bg-gradient-to-r from-arc-300 via-[#f5a3c7] to-[#ffb48f] p-[1.5px] shadow-[0_20px_44px_-26px_rgb(49_57_251/0.55)] transition focus-within:from-arc-500 focus-within:via-[#e98bbd] focus-within:to-coral-400">
        <div className="flex items-center gap-2 rounded-[24.5px] bg-white py-2 pl-5 pr-2">
          <Sparkles size={17} className="shrink-0 text-arc-500" />
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Ask about costs, owners, exposure, a resource by name…"
            className="min-w-0 flex-1 bg-transparent py-2 text-[15px] text-ink outline-none placeholder:text-slate-400"
          />
          <button
            type="submit"
            disabled={!ready}
            aria-label="Send"
            className="grid h-11 w-11 shrink-0 place-items-center rounded-full bg-gradient-to-br from-arc-500 to-arc-700 text-white shadow-[0_10px_22px_-10px_rgb(49_57_251/0.8)] transition hover:scale-105 active:scale-95 disabled:scale-100 disabled:from-slate-200 disabled:to-slate-300 disabled:shadow-none"
          >
            <ArrowUp size={18} strokeWidth={2.5} />
          </button>
        </div>
      </div>
      <p className="mt-2 text-center text-[11px] text-slate-400">Answers come only from your account’s data, and cite the resources they use. Ward never changes anything.</p>
    </form>
  )
}
