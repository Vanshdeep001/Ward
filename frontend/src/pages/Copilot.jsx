import { Fragment, useEffect, useRef, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { ArrowRight, ArrowUp, Check, ChevronDown, Copy, Crosshair, Database, ExternalLink, HardDrive, Info, Network, Search, Server, ShieldCheck, X } from 'lucide-react'
import { api } from '../api/client.js'
import { useResources } from '../api/hooks.js'
import { ago, rupees } from '../lib/format.js'

/* Ask Ward, set like an interview. The page leads with what Ward can see, in numbers. Before the first
   question, the questions people ask are an index to pick from. After it, every exchange is a spread:
   the question as a serif headline marked Q., the answer beneath it marked A., with the resources it
   used and how it was found. No bubbles, no avatars — the type carries it. */

const STARTERS = [
  'What is currently costing me the most?',
  'Show me my running servers',
  'Why did my bill go up?',
  'Which resources have no owner?',
  'Is anything open to the internet?',
]

export default function Copilot() {
  const [messages, setMessages] = useState([])
  const [state, setState] = useState({})
  const [input, setInput] = useState('')
  const [busy, setBusy] = useState(false)
  const [focus, setFocus] = useState(null) // one resource to ask about, or null for the whole account
  const bottom = useRef(null)
  const [params, setParams] = useSearchParams()
  const asked = useRef(false)
  const { data: inventory } = useResources()

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
    bottom.current?.scrollIntoView({ behavior: 'smooth', block: 'nearest' })
  }, [messages, busy])

  async function send(text) {
    const msg = text.trim()
    if (!msg || busy) return
    setInput('')
    setMessages((m) => [...m, { id: crypto.randomUUID(), role: 'user', text: msg, focus }])
    setBusy(true)
    try {
      const res = await api.chat(msg, state, focus ? [focus.id] : [])
      setMessages((m) => [...m, res.message])
      setState(res.state)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="flex h-[calc(100vh-9rem)] flex-col md:h-[calc(100vh-6rem)]">
      <Hero items={inventory?.items ?? []} focus={focus} />

      {messages.length === 0 ? (
        <Stickers onPick={send} />
      ) : (
        <div className="scroll-quiet relative flex-1 overflow-y-auto rounded-4xl border border-slate-200/70 bg-white shadow-[0_1px_2px_rgb(15_23_42/0.04),0_30px_60px_-44px_rgb(23_23_60/0.5)]">
          <div className="mx-auto max-w-3xl px-6 py-8 md:px-10">
            {messages.map((m, i) => (
              <Fragment key={m.id}>
                {m.role === 'user' && i > 0 && <hr className="my-9 border-slate-100" />}
                {m.role === 'user' ? <Question m={m} /> : <Answer m={m} onSend={send} />}
              </Fragment>
            ))}
            {busy && <Thinking focus={focus} />}
            <div ref={bottom} />
          </div>
        </div>
      )}

      <form
        className="mt-4"
        onSubmit={(e) => {
          e.preventDefault()
          send(input)
        }}
      >
        <div className="flex items-center gap-2 rounded-[28px] border border-slate-200/80 bg-white p-2 shadow-[0_1px_2px_rgb(15_23_42/0.04),0_20px_44px_-28px_rgb(23_23_60/0.5)] transition focus-within:border-arc-300 focus-within:shadow-[0_0_0_5px_rgb(49_57_251/0.08),0_20px_44px_-28px_rgb(49_57_251/0.5)]">
          <ResourceToggle value={focus} onChange={setFocus} />
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder={focus ? `Ask about ${focus.name}…` : 'Ask anything…'}
            className="min-w-0 flex-1 bg-transparent px-3 py-2 font-display text-[1.3rem] font-medium tracking-tight text-ink outline-none placeholder:text-slate-300"
          />
          <button
            type="submit"
            disabled={!input.trim() || busy}
            aria-label="Send"
            className="grid h-13 w-13 shrink-0 place-items-center rounded-full bg-arc-600 text-white shadow-[inset_0_1px_0_rgb(255_255_255/0.2),0_12px_24px_-10px_rgb(49_57_251/0.8)] transition hover:bg-arc-700 active:scale-95 disabled:bg-slate-200 disabled:shadow-none"
          >
            <ArrowUp size={20} strokeWidth={2.5} />
          </button>
        </div>
      </form>
    </div>
  )
}

/* ── The headline ─────────────────────────────────────────────────────────── */

function Hero({ items, focus }) {
  return (
    <header className="mb-6">
      <h1 className="max-w-3xl font-display text-[clamp(2.1rem,4.4vw,3.3rem)] font-semibold leading-[1.03] tracking-tight text-ink">
        {focus ? (
          <>Asking about <span className="text-arc-600">{focus.name}</span>.</>
        ) : (
          <>Ask anything about your <span className="text-arc-600">{items.length || '—'}</span> resources.</>
        )}
      </h1>
    </header>
  )
}

/* ── Before the first question ───────────────────────────────────────────── */

// The questions people ask, as speech-bubble stickers on the page itself: pastel, a little tilted, like
// notes stuck to a board. Each straightens and lifts when pointed at.
const STICKERS = [
  { bg: '#eef0ff', ring: '#c6c9ff', tilt: -2.2 },
  { bg: '#fdeef5', ring: '#f5c6dc', tilt: 1.6 },
  { bg: '#fff1e8', ring: '#ffd2bd', tilt: -1.2 },
  { bg: '#f3edff', ring: '#d9c9ff', tilt: 2.0 },
  { bg: '#eaf8f2', ring: '#bfe8d5', tilt: -1.6 },
]

function Stickers({ onPick }) {
  return (
    <div className="flex flex-1 flex-col items-center justify-center pb-6">
      <p className="animate-rise text-[12px] font-semibold text-slate-400">Start with one of these —</p>
      <div className="mt-6 flex max-w-4xl flex-wrap items-center justify-center gap-x-5 gap-y-6 px-4">
        {STARTERS.map((q, i) => {
          const s = STICKERS[i % STICKERS.length]
          return (
            <button
              key={q}
              type="button"
              onClick={() => onPick(q)}
              className="animate-rise group relative"
              style={{ animationDelay: `${80 + i * 70}ms` }}
            >
              <span
                className="relative block rounded-[26px] px-6 py-3.5 font-display text-[clamp(1.15rem,2vw,1.45rem)] font-semibold tracking-tight text-ink shadow-[0_14px_30px_-20px_rgb(23_23_60/0.45)] ring-1 ring-inset rotate-(--tilt) transition duration-300 ease-[cubic-bezier(0.32,0.72,0,1)] group-hover:-translate-y-1.5 group-hover:rotate-0 group-hover:shadow-[0_24px_44px_-22px_rgb(23_23_60/0.5)]"
                style={{ background: s.bg, '--tw-ring-color': s.ring, '--tilt': `${s.tilt}deg` }}
              >
                {q}
                {/* the bubble's tail */}
                <span
                  aria-hidden
                  className="absolute -bottom-1.5 h-4 w-4 rotate-45 rounded-[3px]"
                  style={{ background: s.bg, left: i % 2 ? 'auto' : 28, right: i % 2 ? 28 : 'auto', boxShadow: `inset -1px -1px 0 ${s.ring}` }}
                />
              </span>
            </button>
          )
        })}
      </div>
      <p className="animate-rise mt-8 text-[13px] text-slate-500 [animation-delay:500ms]">
        Or pick one resource in the bar below, and every answer will be about that resource alone.
      </p>
    </div>
  )
}

function Thinking({ focus }) {
  return (
    <div className="animate-rise mt-9 flex gap-4">
      <Mark tone="text-arc-600">A.</Mark>
      <p className="flex items-center gap-2 pt-2 text-[14px] text-slate-500">
        {[0, 1, 2].map((i) => (
          <span key={i} className="h-1.5 w-1.5 animate-pulse rounded-full bg-arc-500" style={{ animationDelay: `${i * 180}ms` }} />
        ))}
        <span className="ml-1">{focus ? `Reading ${focus.name}…` : 'Reading your inventory…'}</span>
      </p>
    </div>
  )
}

const Mark = ({ tone, children }) => (
  <span className={`w-9 shrink-0 font-display text-[1.7rem] font-semibold leading-[1.15] ${tone}`}>{children}</span>
)

/* ── Choosing one resource to ask about ──────────────────────────────────── */

const KIND = {
  ec2: { icon: Server, label: 'Instance', color: '#3139fb' },
  rds: { icon: Database, label: 'Database', color: '#b79bff' },
  ebs: { icon: HardDrive, label: 'Volume', color: '#8e96ff' },
  nat: { icon: Network, label: 'NAT gateway', color: '#ffb48f' },
  sg: { icon: ShieldCheck, label: 'Security group', color: '#f7827d' },
}

// "All resources" by default; pick one and every question is answered about that resource only.
function ResourceToggle({ value, onChange }) {
  const [open, setOpen] = useState(false)
  const [q, setQ] = useState('')
  const box = useRef(null)
  const { data } = useResources()

  useEffect(() => {
    if (!open) return undefined
    const away = (e) => box.current && !box.current.contains(e.target) && setOpen(false)
    document.addEventListener('mousedown', away)
    return () => document.removeEventListener('mousedown', away)
  }, [open])

  const needle = q.trim().toLowerCase()
  const items = (data?.items ?? []).filter((r) => KIND[r.type] && (!needle || `${r.name} ${r.id} ${r.type}`.toLowerCase().includes(needle)))

  return (
    <div ref={box} className="relative">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className={`flex h-12 max-w-55 items-center gap-2 rounded-full px-4 text-[13.5px] transition ${
          value ? 'bg-arc-50 text-arc-700 ring-1 ring-inset ring-arc-200' : 'bg-slate-50 text-slate-600 hover:bg-slate-100 hover:text-ink'
        }`}
      >
        {value ? (
          <span className="h-2 w-2 shrink-0 rounded-full" style={{ background: KIND[value.type]?.color }} />
        ) : (
          <Crosshair size={15} className="shrink-0" />
        )}
        <span className="truncate font-medium">{value ? value.name : 'All resources'}</span>
        {value ? (
          <X
            size={14}
            className="shrink-0 opacity-60 hover:opacity-100"
            onClick={(e) => {
              e.stopPropagation()
              onChange(null)
            }}
          />
        ) : (
          <ChevronDown size={14} className="shrink-0 opacity-60" />
        )}
      </button>

      {open && (
        <div className="animate-rise absolute bottom-full left-0 z-30 mb-3 w-80 overflow-hidden rounded-3xl border border-slate-200/80 bg-white shadow-[0_28px_60px_-24px_rgb(23_23_60/0.45)]">
          <p className="px-4 pb-1 pt-3.5 text-[10.5px] font-bold uppercase tracking-[0.16em] text-slate-400">Ask about</p>
          <div className="border-b border-slate-100 px-3 pb-3 pt-1.5">
            <input autoFocus value={q} onChange={(e) => setQ(e.target.value)} placeholder="Find a resource…" className="w-full rounded-xl bg-slate-50 px-3.5 py-2 text-sm outline-none ring-1 ring-inset ring-slate-200/80 focus:bg-white focus:ring-arc-300" />
          </div>
          <ul className="scroll-quiet max-h-72 overflow-y-auto p-1.5">
            <li>
              <Option active={!value} onClick={() => { onChange(null); setOpen(false) }}>
                <Crosshair size={14} className="text-slate-400" /> <span className="flex-1">All resources</span>
              </Option>
            </li>
            {items.map((r) => (
              <li key={r.id}>
                <Option active={value?.id === r.id} onClick={() => { onChange(r); setOpen(false); setQ('') }}>
                  <span className="grid h-7 w-7 shrink-0 place-items-center rounded-lg text-white" style={{ background: KIND[r.type].color }}>
                    {(() => { const Icon = KIND[r.type].icon; return <Icon size={13} strokeWidth={2.4} /> })()}
                  </span>
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-ink">{r.name}</span>
                    <span className="block truncate font-mono text-[10.5px] text-slate-400">{r.id}</span>
                  </span>
                  <span className="shrink-0 text-[11px] text-slate-400">{KIND[r.type].label}</span>
                </Option>
              </li>
            ))}
            {!items.length && <li className="px-3 py-4 text-center text-xs text-slate-400">No match</li>}
          </ul>
        </div>
      )}
    </div>
  )
}

function Option({ active, onClick, children }) {
  return (
    <button type="button" onClick={onClick} className={`flex w-full items-center gap-2.5 rounded-xl px-2.5 py-2 text-left text-sm transition ${active ? 'bg-arc-50' : 'hover:bg-slate-50'}`}>
      {children}
      {active && <Check size={14} className="shrink-0 text-arc-600" />}
    </button>
  )
}

/* ── An exchange ──────────────────────────────────────────────────────────── */

function Question({ m }) {
  return (
    <div className="animate-rise flex gap-4">
      <Mark tone="text-coral-500">Q.</Mark>
      <div className="min-w-0">
        <h2 className="font-display text-[1.7rem] font-semibold leading-[1.15] tracking-tight text-ink">{m.text}</h2>
        {m.focus && (
          <p className="mt-2 inline-flex items-center gap-1.5 rounded-full bg-arc-50 px-2.5 py-1 text-[11.5px] font-semibold text-arc-700">
            <Crosshair size={11} /> about {m.focus.name}
          </p>
        )}
      </div>
    </div>
  )
}

function Answer({ m, onSend }) {
  // Only the resources the answer actually uses get cards; a greeting shouldn't come with four.
  const cited = (m.sources ?? []).filter((s) => s.cited)
  return (
    <div className="animate-rise mt-6 flex gap-4">
      <Mark tone="text-arc-600">A.</Mark>
      <div className="min-w-0 flex-1 space-y-4 pt-1">
        <p className="whitespace-pre-line text-[15.5px] leading-[1.75] text-slate-700">
          {m.sources ? <Cited text={m.text} sources={m.sources} /> : m.text}
        </p>
        {cited.length > 0 && <Sources sources={cited} />}

        {m.rows && (
          <div className="overflow-x-auto rounded-2xl border border-slate-200">
            <table className="w-full text-sm">
              <thead className="bg-slate-50 text-left text-xs text-slate-500">
                <tr>{m.columns.map((c) => <th key={c.key} className="px-3 py-2 font-medium">{c.label}</th>)}</tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {m.rows.map((r) => (
                  <tr key={r.id}>
                    {m.columns.map((c) => (
                      <td key={c.key} className={`px-3 py-2 ${c.key === 'id' ? 'font-mono text-xs text-slate-500' : ''} ${c.key === 'perDay' ? 'tabular-nums' : ''}`}>
                        {c.key === 'perDay' ? rupees(r[c.key]) : r[c.key]}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {m.asOf && <p className="text-xs text-slate-400">Inventory as of {ago(m.asOf)}</p>}

        {m.command && (
          <div className="space-y-2">
            <div className="flex items-center gap-2 rounded-2xl bg-paper px-3.5 py-2.5 ring-1 ring-inset ring-slate-200">
              <code className="flex-1 overflow-x-auto whitespace-nowrap font-mono text-[12px] text-ink">{m.command}</code>
              <button type="button" onClick={() => navigator.clipboard?.writeText(m.command)} className="text-slate-400 hover:text-ink" title="Copy">
                <Copy size={14} />
              </button>
            </div>
            {m.consoleUrl && (
              <a href={m.consoleUrl} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 text-xs font-semibold text-arc-700 hover:underline">
                Open in AWS console <ExternalLink size={12} />
              </a>
            )}
          </div>
        )}

        {m.draftRule && (
          <div className="rounded-2xl border border-amber-200 bg-amber-50/50 p-4">
            <p className="text-xs text-slate-500">Drafted rule</p>
            <p className="mt-0.5 font-display text-[1.1rem] font-semibold text-ink">“{m.draftRule}”</p>
            <Link to={`/rules?draft=${encodeURIComponent(m.draftRule)}`} className="mt-2 inline-flex items-center gap-1 text-sm font-semibold text-arc-700 hover:underline">
              Edit, simulate and activate <ArrowRight size={14} />
            </Link>
          </div>
        )}

        {m.link && (
          <Link to={m.link.to} className="inline-flex items-center gap-1 text-sm font-semibold text-arc-700 hover:underline">
            {m.link.label} <ArrowRight size={14} />
          </Link>
        )}

        {m.suggestions && (
          <div className="flex flex-wrap gap-1.5">
            {m.suggestions.map((s) => (
              <button key={s} type="button" onClick={() => onSend(s)} className="rounded-full border border-slate-200 px-3 py-1 text-xs font-semibold text-slate-600 hover:border-arc-300 hover:text-arc-700">
                {s}
              </button>
            ))}
          </div>
        )}

        {(m.retriever || m.checks?.blocked) && <Provenance m={m} />}
      </div>
    </div>
  )
}

/* ── Search answers ───────────────────────────────────────────────────────── */

// The model cites resources as [id]; each becomes a small chip naming the resource.
function Cited({ text, sources }) {
  const byId = Object.fromEntries(sources.map((s) => [s.id, s]))
  return text.split(/(\[[^\]\s]+\])/g).map((part, i) => {
    const s = byId[part.slice(1, -1)]
    if (!part.startsWith('[') || !s) return <Bold key={i} text={part} />
    return (
      <span key={i} className="mx-0.5 inline-flex items-center gap-1 rounded-md bg-arc-50 px-1.5 py-px align-baseline font-mono text-[11px] font-semibold text-arc-700 ring-1 ring-inset ring-arc-100">
        <span className="h-1.5 w-1.5 rounded-full" style={{ background: KIND[s.type]?.color ?? '#94a3b8' }} />
        {s.name ?? s.id}
      </span>
    )
  })
}

// Models write **bold**; show it as bold rather than asterisks.
function Bold({ text }) {
  return text.split(/(\*\*[^*]+\*\*)/g).map((p, i) =>
    p.startsWith('**') && p.endsWith('**') && p.length > 4 ? <strong key={i} className="font-semibold text-ink">{p.slice(2, -2)}</strong> : p,
  )
}

// The resources the answer used.
function Sources({ sources }) {
  const [all, setAll] = useState(false)
  const shown = all ? sources : sources.slice(0, 4)
  return (
    <div>
      <p className="mb-2 text-[10.5px] font-bold uppercase tracking-[0.16em] text-slate-400">Found in your inventory</p>
      <div className="grid gap-2 sm:grid-cols-2">
        {shown.map((s) => {
          const kind = KIND[s.type] ?? { icon: Search, label: s.type, color: '#94a3b8' }
          const Icon = kind.icon
          return (
            <div key={s.id} className="flex items-center gap-3 rounded-2xl border border-slate-200/80 bg-white p-3">
              <span className="grid h-9 w-9 shrink-0 place-items-center rounded-xl text-white" style={{ background: kind.color }}>
                <Icon size={16} strokeWidth={2.2} />
              </span>
              <div className="min-w-0 flex-1">
                <p className="truncate text-[13.5px] font-semibold text-ink">{s.name ?? s.id}</p>
                <p className="truncate font-mono text-[10.5px] text-slate-400">
                  {s.id}{s.detail ? ` · ${s.detail}` : ''}{s.region ? ` · ${s.region}` : ''}
                </p>
              </div>
              <div className="shrink-0 text-right">
                <p className={`text-[12.5px] font-semibold tabular-nums ${s.costPerDay ? 'text-ink' : 'text-slate-400'}`}>
                  {s.costPerDay ? `${rupees(s.costPerDay)}/d` : 'free'}
                </p>
                {!s.owner && <p className="text-[10px] font-bold text-coral-600">no owner</p>}
              </div>
            </div>
          )
        })}
      </div>
      {sources.length > 4 && (
        <button type="button" onClick={() => setAll((v) => !v)} className="mt-2 text-[12px] font-semibold text-arc-700 hover:underline">
          {all ? 'Show fewer' : `Show ${sources.length - 4} more`}
        </button>
      )}
    </div>
  )
}

const BLOCKED = {
  action: 'Stopped by a guardrail — Ward is read-only',
  injection: 'Stopped by a guardrail — that looked like an attempt to change Ward’s instructions',
  'off-topic': 'Stopped by a guardrail — not about your AWS account',
}

function Provenance({ m }) {
  if (m.checks?.blocked) {
    return (
      <p className="flex items-center gap-1.5 text-[11px] font-semibold text-violet-700">
        <ShieldCheck size={12} /> {BLOCKED[m.checks.blocked] ?? 'Stopped by a guardrail'}
      </p>
    )
  }
  const retriever = m.retriever === 'focus' ? `only ${m.focus === 1 ? 'the chosen resource' : `the ${m.focus} chosen resources`}` : m.retriever === 'pinecone' ? 'Pinecone vector search' : 'local keyword search'
  const generator = m.generator === 'extractive' ? 'no model — matches shown as found' : `answered by ${m.generator}`
  return (
    <div className="space-y-1.5">
      <p className="flex items-center gap-1.5 text-[11px] text-slate-400">
        <Search size={11} /> Retrieved with {retriever} · {generator}
      </p>
      {m.notice && (
        <p className="flex items-start gap-1.5 rounded-xl bg-amber-50 px-3 py-2 text-[11.5px] text-amber-800 ring-1 ring-inset ring-amber-200">
          <Info size={12} className="mt-0.5 shrink-0" /> {m.notice}
        </p>
      )}
    </div>
  )
}
