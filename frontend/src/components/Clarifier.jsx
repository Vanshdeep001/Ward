import { useState } from 'react'
import { HelpCircle } from 'lucide-react'
import { Button, Card } from './ui.jsx'

// SRS §20 — one targeted question per ambiguous term, each option with its live consequence.
export default function Clarifier({ questions, onSubmit, submitLabel = 'Build the rule', busy }) {
  const [choices, setChoices] = useState(() =>
    Object.fromEntries(questions.map((q) => [q.term, q.options[q.defaultIndex].value])),
  )

  return (
    <Card className="border-amber-200 bg-amber-50/40 p-5">
      <div className="mb-4 flex items-center gap-2 text-sm font-medium text-amber-900">
        <HelpCircle size={16} />
        Before Ward builds this, {questions.length === 1 ? 'one thing needs' : `${questions.length} things need`} pinning down
      </div>
      <div className="space-y-5">
        {questions.map((q) => (
          <fieldset key={q.term}>
            <legend className="mb-2 text-sm font-medium text-slate-800">{q.question}</legend>
            <div className="space-y-1.5">
              {q.options.map((o) => (
                <label
                  key={o.value}
                  className={`flex cursor-pointer items-center justify-between gap-3 rounded-lg border px-3 py-2 text-sm transition ${
                    choices[q.term] === o.value ? 'border-arc-500 bg-white ring-1 ring-arc-500' : 'border-slate-200 bg-white hover:border-slate-300'
                  }`}
                >
                  <span className="flex items-center gap-2">
                    <input
                      type="radio"
                      name={q.term}
                      className="accent-arc-600"
                      checked={choices[q.term] === o.value}
                      onChange={() => setChoices((c) => ({ ...c, [q.term]: o.value }))}
                    />
                    {o.label}
                  </span>
                  <span className="text-xs text-slate-500">
                    {o.matches != null ? `${o.matches} of your resources` : o.detail}
                  </span>
                </label>
              ))}
            </div>
          </fieldset>
        ))}
      </div>
      <Button className="mt-5" onClick={() => onSubmit(choices)} disabled={busy}>
        {busy ? 'Working…' : submitLabel}
      </Button>
    </Card>
  )
}
