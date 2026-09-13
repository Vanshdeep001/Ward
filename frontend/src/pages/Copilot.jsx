import { useEffect, useRef, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { ArrowRight, Copy, ExternalLink, Send, ShieldCheck } from 'lucide-react'
import { api } from '../api/client.js'
import { ago, rupees } from '../lib/format.js'
import { Button, Pill } from '../components/ui.jsx'

const STARTERS = [
  'What is currently costing me the most?',
  'Show me my running servers',
  'Why did my bill go up?',
  'I need a database for my college project under ₹500/month',
]

const intentTone = { QUERY: 'blue', EXPLAIN: 'violet', ADVISE: 'green', ACT: 'amber', REFUSE: 'red', OUT_OF_SCOPE: 'slate' }

export default function Copilot() {
  const [messages, setMessages] = useState([])
  const [state, setState] = useState({})
  const [input, setInput] = useState('')
  const [busy, setBusy] = useState(false)
  const bottom = useRef(null)
  const [params, setParams] = useSearchParams()
  const asked = useRef(false)

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
    setMessages((m) => [...m, { id: crypto.randomUUID(), role: 'user', text: msg }])
    setBusy(true)
    try {
      const res = await api.chat(msg, state)
      setMessages((m) => [...m, res.message])
      setState(res.state)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="flex h-[calc(100vh-9rem)] flex-col md:h-[calc(100vh-6rem)]">
      <div className="mb-4">
        <h1 className="font-display text-4xl font-semibold leading-tight text-ink">Ask Ward</h1>
        <p className="mt-1 text-[15px] text-slate-600">Ask about your AWS account in plain English. Ward has read-only access — it never changes your resources.</p>
      </div>

      <div className="scroll-quiet flex-1 space-y-5 overflow-y-auto rounded-2xl border border-slate-200/80 bg-white p-4 md:p-6">
        {messages.length === 0 && (
          <div className="grid h-full place-items-center">
            <div className="max-w-lg text-center">
              <ShieldCheck className="mx-auto text-arc-600" size={32} />
              <p className="mt-3 text-sm text-slate-600">Try one of these:</p>
              <div className="mt-3 flex flex-wrap justify-center gap-2">
                {STARTERS.map((s) => (
                  <button key={s} onClick={() => send(s)} className="rounded-full border border-slate-200 px-3 py-1.5 text-sm text-slate-700 hover:border-arc-300 hover:text-arc-700">
                    {s}
                  </button>
                ))}
              </div>
            </div>
          </div>
        )}

        {messages.map((m) => (m.role === 'user' ? <UserBubble key={m.id} text={m.text} /> : <WardMessage key={m.id} m={m} onSend={send} />))}
        {busy && <p className="text-sm text-slate-400">Ward is looking…</p>}
        <div ref={bottom} />
      </div>

      <form
        className="mt-3 flex gap-2"
        onSubmit={(e) => {
          e.preventDefault()
          send(input)
        }}
      >
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Ask Ward anything about your AWS costs…"
          className="flex-1 rounded-xl border border-slate-200 bg-white px-4 py-3 text-sm shadow-[0_1px_2px_rgb(15_23_42/0.05)] outline-none focus:border-arc-500 focus:ring-4 focus:ring-arc-500/15"
        />
        <Button type="submit" disabled={!input.trim() || busy}><Send size={16} /></Button>
      </form>
    </div>
  )
}

function UserBubble({ text }) {
  return (
    <div className="flex justify-end">
      <p className="max-w-[80%] rounded-3xl rounded-br-md bg-arc-100 px-4 py-2.5 text-sm text-arc-900">{text}</p>
    </div>
  )
}

function WardMessage({ m, onSend }) {
  return (
    <div className="max-w-[90%] space-y-3">
      <div className="flex items-center gap-2">
        <span className="text-xs font-semibold text-slate-900">Ward</span>
        {m.intent && <Pill tone={intentTone[m.intent]}>{m.intent.replace('_', ' ').toLowerCase()}</Pill>}
      </div>
      <p className="text-sm leading-relaxed text-slate-800">{m.text}</p>

      {m.rows && (
        <div className="overflow-x-auto rounded-lg border border-slate-200">
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
          <div className="flex items-center gap-2 rounded-lg bg-slate-900 px-3 py-2">
            <code className="flex-1 overflow-x-auto whitespace-nowrap font-mono text-xs text-slate-100">{m.command}</code>
            <button onClick={() => navigator.clipboard?.writeText(m.command)} className="text-slate-400 hover:text-white" title="Copy">
              <Copy size={14} />
            </button>
          </div>
          <a href={m.consoleUrl} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 text-xs text-arc-700 hover:underline">
            Open in AWS console <ExternalLink size={12} />
          </a>
        </div>
      )}

      {m.draftRule && (
        <div className="rounded-lg border border-amber-200 bg-amber-50/50 p-3">
          <p className="text-xs text-slate-500">Drafted rule</p>
          <p className="mt-0.5 font-medium text-slate-900">“{m.draftRule}”</p>
          <Link to={`/rules?draft=${encodeURIComponent(m.draftRule)}`} className="mt-2 inline-flex items-center gap-1 text-sm text-arc-700 hover:underline">
            Edit, simulate and activate <ArrowRight size={14} />
          </Link>
        </div>
      )}

      {m.link && (
        <Link to={m.link.to} className="inline-flex items-center gap-1 text-sm text-arc-700 hover:underline">
          {m.link.label} <ArrowRight size={14} />
        </Link>
      )}

      {m.suggestions && (
        <div className="flex flex-wrap gap-1.5">
          {m.suggestions.map((s) => (
            <button key={s} onClick={() => onSend(s)} className="rounded-full border border-slate-200 px-2.5 py-1 text-xs text-slate-600 hover:border-arc-300 hover:text-arc-700">
              {s}
            </button>
          ))}
        </div>
      )}
    </div>
  )
}
