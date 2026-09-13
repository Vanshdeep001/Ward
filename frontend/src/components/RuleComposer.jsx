import { useEffect, useRef, useState } from 'react'
import { Sparkles, XCircle } from 'lucide-react'
import { api } from '../api/client.js'
import { useActivateRule } from '../api/hooks.js'
import { applyClarifications } from '../lib/clarify.js'
import { Button, Card } from './ui.jsx'
import Clarifier from './Clarifier.jsx'
import GuardrailCard from './GuardrailCard.jsx'

const EXAMPLES = [
  'Never let a GPU instance run more than 6 hours',
  'Flag EBS volumes unattached for more than 7 days',
  "Don't let anything expensive run too long",
  'No resources outside ap-south-1',
]

// English → (clarify) → compile → verify → simulate → approve.
export default function RuleComposer({ initialText = '', suggestions = EXAMPLES, onPick }) {
  const [text, setText] = useState(initialText)
  const [result, setResult] = useState(null)
  const [busy, setBusy] = useState(false)
  const activate = useActivateRule()
  const latest = useRef(0)

  useEffect(() => {
    if (!initialText) return
    setText(initialText)
    compile(initialText)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [initialText])

  async function compile(english, opts) {
    const request = ++latest.current // only the most recent compile may update the screen
    setBusy(true)
    activate.reset()
    try {
      const res = await api.compileRule(english, opts)
      if (request === latest.current) setResult(res)
    } finally {
      if (request === latest.current) setBusy(false)
    }
  }

  function onClarified(choices) {
    const precise = applyClarifications(choices)
    setText(precise)
    compile(precise, { skipClarify: true })
  }

  return (
    <div className="space-y-5">
      {/* The prompt is the hero, like arc.net's "Try Dia" moment. */}
      <form
        onSubmit={(e) => {
          e.preventDefault()
          if (text.trim()) compile(text.trim())
        }}
        className="rounded-3xl bg-gradient-to-br from-arc-200 via-coral-100 to-amber-100 p-[1.5px] shadow-[0_18px_50px_-20px_rgb(49_57_251/0.45)]"
      >
        <div className="rounded-[calc(1.5rem-1.5px)] bg-white p-2 pl-5">
          <label htmlFor="rule" className="block pt-2 text-xs font-semibold text-slate-500">Write a guardrail in plain English</label>
          <div className="flex flex-col gap-2 sm:flex-row sm:items-end">
            <textarea
              id="rule"
              rows={2}
              value={text}
              onChange={(e) => setText(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && !e.shiftKey && text.trim()) {
                  e.preventDefault()
                  compile(text.trim())
                }
              }}
              placeholder="Never let a GPU instance run more than 6 hours"
              className="min-h-16 w-full flex-1 resize-none bg-transparent py-1 font-display text-2xl leading-snug text-ink outline-none placeholder:text-slate-300"
            />
            <Button type="submit" disabled={!text.trim() || busy} className="shrink-0 rounded-2xl px-5 py-3 text-base">
              <Sparkles size={17} /> {busy ? 'Verifying…' : 'Compile'}
            </Button>
          </div>
        </div>
      </form>

      {suggestions.length > 0 && (
        <div className="flex flex-wrap gap-2">
          {suggestions.map((sug) => (
            <button
              key={sug}
              type="button"
              onClick={() => (onPick ? onPick(sug) : setText(sug))}
              className={`rounded-full border px-3 py-1.5 text-xs font-medium transition hover:-translate-y-px hover:border-arc-300 hover:text-arc-700 ${
                sug === text ? 'border-arc-500 bg-arc-50 text-arc-700' : 'border-slate-200 bg-white text-slate-600'
              }`}
            >
              {sug}
            </button>
          ))}
        </div>
      )}

      {result?.status === 'needs-clarification' && (
        <Clarifier key={result.english} questions={result.questions} onSubmit={onClarified} busy={busy} />
      )}

      {result?.status === 'failed' && (
        <Card className="border-coral-100 bg-coral-50 p-5 text-sm text-coral-600">
          <p className="flex items-center gap-2 font-medium"><XCircle size={16} /> Ward couldn’t build a verified policy for this rule</p>
          <p className="mt-1 text-slate-700">{result.verifier.error}</p>
          <p className="mt-2 text-slate-600">Try naming the resource type and a number — e.g. “No RDS instance larger than db.t3.small”.</p>
        </Card>
      )}

      {result?.status === 'compiled' && (
        <GuardrailCard
          key={result.english}
          result={result}
          onActivate={() => activate.mutate(result.english)}
          activating={activate.isPending}
          activated={activate.isSuccess}
        />
      )}
    </div>
  )
}
