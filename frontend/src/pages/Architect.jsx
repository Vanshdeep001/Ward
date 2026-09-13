import { useEffect, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { Blocks, CheckCircle2, XCircle } from 'lucide-react'
import { api } from '../api/client.js'
import { rupees } from '../lib/format.js'
import { Button, Card, CardHeader, PageHeader, Pill } from '../components/ui.jsx'
import Clarifier from '../components/Clarifier.jsx'

const DEFAULT = 'I want to deploy my MERN attendance application for 500 students and keep it under ₹1,500/month.'

export default function Architect() {
  const [params] = useSearchParams()
  const [prompt, setPrompt] = useState(params.get('q') ?? DEFAULT)
  const [result, setResult] = useState(null)
  const [busy, setBusy] = useState(false)

  async function run(answers) {
    setBusy(true)
    try {
      setResult(await api.architect(prompt, answers))
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
      <PageHeader title="Architect" subtitle="Describe what you want to build. Ward recommends the simplest AWS setup that fits — and tells you what you don’t need." />

      <form
        onSubmit={(e) => {
          e.preventDefault()
          if (prompt.trim()) run()
        }}
        className="rounded-3xl bg-gradient-to-br from-arc-200 via-coral-100 to-amber-100 p-[1.5px] shadow-[0_18px_50px_-20px_rgb(49_57_251/0.45)]"
      >
        <div className="rounded-[calc(1.5rem-1.5px)] bg-white p-2 pl-5">
          <label htmlFor="arch" className="block pt-2 text-xs font-semibold text-slate-500">What are you building, for how many people, on what budget?</label>
          <div className="flex flex-col gap-2 sm:flex-row sm:items-end">
            <textarea
              id="arch"
              rows={3}
              value={prompt}
              onChange={(e) => setPrompt(e.target.value)}
              className="w-full flex-1 resize-none bg-transparent py-1 font-display text-2xl leading-snug text-ink outline-none placeholder:text-slate-300"
            />
            <Button type="submit" disabled={!prompt.trim() || busy} className="shrink-0 rounded-2xl px-5 py-3 text-base">
              <Blocks size={17} /> {busy ? 'Thinking…' : 'Recommend'}
            </Button>
          </div>
        </div>
      </form>

      {result?.status === 'needs-clarification' && (
        <div className="mt-4">
          <Clarifier key={prompt} questions={result.questions} onSubmit={run} submitLabel="Recommend" busy={busy} />
        </div>
      )}

      {result?.status === 'recommended' && <Recommendation r={result} />}
    </>
  )
}

function Recommendation({ r }) {
  return (
    <div className="mt-6 space-y-6">
      <div className="grid gap-4 sm:grid-cols-3">
        <Card className="p-5">
          <p className="text-xs text-slate-500">Estimated cost</p>
          <p className="mt-1 font-display text-3xl font-semibold tabular-nums text-ink">{rupees(r.estimate.low)}–{rupees(r.estimate.high)}</p>
          <p className="text-xs text-slate-500">per month</p>
        </Card>
        <Card className="p-5">
          <p className="text-xs text-slate-500">Your budget</p>
          <p className="mt-1 font-display text-3xl font-semibold tabular-nums text-ink">{r.budget ? rupees(r.budget) : '—'}</p>
          {r.withinBudget != null && (
            <p className={`flex items-center gap-1 text-xs ${r.withinBudget ? 'text-emerald-700' : 'text-rose-600'}`}>
              {r.withinBudget ? <><CheckCircle2 size={12} /> fits, even at the high estimate</> : <><XCircle size={12} /> over budget at the high estimate</>}
            </p>
          )}
        </Card>
        <Card className="p-5">
          <p className="text-xs text-slate-500">Complexity</p>
          <p className="mt-1 font-display text-3xl font-semibold text-ink">{r.complexity}</p>
          <p className="font-mono text-xs text-slate-500">{r.pattern}</p>
        </Card>
      </div>

      <Card>
        <CardHeader title="Recommended architecture" subtitle={`For ~${r.users.toLocaleString('en-IN')} users`} />
        <div className="px-5 py-6">
          <Diagram components={r.components} />
        </div>
      </Card>

      <div className="grid gap-6 lg:grid-cols-2">
        <Card>
          <CardHeader title="Why these services" />
          <ul className="divide-y divide-slate-100">
            {r.components.map((c) => (
              <li key={c.service} className="px-5 py-3">
                <div className="flex items-center justify-between gap-2">
                  <span className="font-medium text-slate-900">{c.service} <span className="font-normal text-slate-500">· {c.size}</span></span>
                  <span className="text-sm tabular-nums text-slate-600">{c.perMonth ? `${rupees(c.perMonth)}/mo` : 'free tier'}</span>
                </div>
                <p className="mt-0.5 text-sm text-emerald-800">{c.explainer}</p>
                <p className="mt-0.5 text-sm text-slate-600">{c.role}</p>
              </li>
            ))}
          </ul>
        </Card>

        <Card>
          <CardHeader title="What you don’t need" subtitle="Complexity has to be justified by a requirement you stated" />
          <ul className="divide-y divide-slate-100">
            {r.whyNot.map((w) => (
              <li key={w.option} className="px-5 py-3">
                <p className="flex items-center gap-2 font-medium text-slate-900"><XCircle size={14} className="text-slate-400" /> {w.option}</p>
                <p className="mt-0.5 text-sm text-slate-600">{w.because}</p>
              </li>
            ))}
          </ul>
        </Card>
      </div>

      <p className="text-xs text-slate-500">ⓘ {r.note}</p>
    </div>
  )
}

function Diagram({ components }) {
  const [compute, ...rest] = components
  return (
    <div className="flex flex-col items-center gap-3 text-sm">
      <Node label="Users" muted />
      <Arrow />
      <Node label={compute.service} sub={compute.size} />
      {rest.length > 0 && (
        <>
          <Arrow />
          <div className="flex flex-wrap justify-center gap-4">
            {rest.map((c) => <Node key={c.service} label={c.service} sub={c.size} />)}
          </div>
        </>
      )}
      <div className="mt-2"><Pill tone="green">single region · ap-south-1</Pill></div>
    </div>
  )
}

const Node = ({ label, sub, muted }) => (
  <div className={`min-w-32 rounded-lg border px-4 py-2 text-center ${muted ? 'border-dashed border-slate-300 text-slate-500' : 'border-arc-200 bg-arc-50'}`}>
    <p className="font-medium text-slate-900">{label}</p>
    {sub && <p className="text-xs text-slate-500">{sub}</p>}
  </div>
)

const Arrow = () => <span className="text-slate-300">↓</span>
