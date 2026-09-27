import { useEffect, useRef, useState } from 'react'
import {
  AlertTriangle, CalendarDays, Check, Cpu, Globe2, HardDrive, HelpCircle, PiggyBank, Plus, Sparkles, Tag, Timer, Wallet,
  XCircle,
} from 'lucide-react'
import { api } from '../api/client.js'
import { useActivateRule } from '../api/hooks.js'
import { applyClarifications } from '../lib/clarify.js'
import { Card } from './ui.jsx'
import Clarifier from './Clarifier.jsx'
import GuardrailCard from './GuardrailCard.jsx'
import YamlBlock from './YamlBlock.jsx'

const EXAMPLES = [
  'Never let a GPU instance run more than 6 hours',
  'Flag EBS volumes unattached for more than 7 days',
  "Don't let anything expensive run too long",
  'No resources outside ap-south-1',
]

/* Each starter rule, with the filter it compiles down to — so picking one shows you what you
   are about to get. `vague` marks the rule that deliberately can't compile on its own: it is
   there to demonstrate the clarifier. */
const RULEBOOK = {
  'Stay inside the free tier': { icon: PiggyBank, filter: 'aws.ebs · Attachments: []' },
  'Nothing runs longer than 6 hours unattended': { icon: Timer, filter: 'type: instance-age · hours: 6' },
  'No GPU instance without an expiry tag': { icon: Cpu, filter: '"tag:expiry": absent' },
  'Warn before monthly spend crosses the budget': { icon: Wallet, filter: 'type: budget · threshold: 85%' },
  'Nothing left running over a weekend': { icon: CalendarDays, filter: 'type: offhour · weekends: true' },
  'Flag any resource with no owner tag': { icon: Tag, filter: '"tag:Owner": absent' },
  "Don't let anything expensive run too long": { icon: HelpCircle, filter: 'Ward will ask what you mean', vague: true },
  'No resources outside ap-south-1': { icon: Globe2, filter: 'type: value · Region' },
  'Never let a GPU instance run more than 6 hours': { icon: Cpu, filter: 'InstanceType ^(p|g|inf) · 6h' },
  'Flag EBS volumes unattached for more than 7 days': { icon: HardDrive, filter: 'aws.ebs · Attachments: []' },
}

// What the clarifier looks for: a resource to act on, and a limit to act at. When both are
// present Ward compiles straight through instead of stopping to ask.
const NAMES_RESOURCE = /\b(gpu|ec2|instance|instances|rds|database|databases|db|ebs|volume|volumes|s3|bucket|buckets|nat|lambda|snapshot|snapshots|resource|resources|server|servers|notebook)\b/i
const NAMES_LIMIT = /\b(\d+|free tier|budget|weekend|weekends|overnight|expiry|owner|untagged|public|publicly|outside)\b/i

// English → (clarify) → compile → verify → simulate → approve.
export default function RuleComposer({ initialText = '', suggestions = EXAMPLES, onPick }) {
  const [text, setText] = useState(initialText)
  const [result, setResult] = useState(null)
  const [busy, setBusy] = useState(false)
  const [focused, setFocused] = useState(false)
  const ghost = useGhost(EXAMPLES, !text && !focused)
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

  const named = NAMES_RESOURCE.test(text)
  const bounded = NAMES_LIMIT.test(text)

  return (
    <div className="space-y-5">
      {/* A console for English. Dark, so the one place you speak to the compiler doesn't
          read as just another form field — and so the ghost text can type itself. */}
      <form
        onSubmit={(e) => {
          e.preventDefault()
          if (text.trim()) compile(text.trim())
        }}
        className="relative overflow-hidden rounded-[1.75rem] bg-ink shadow-[0_28px_60px_-28px_rgb(10_8_60/0.75)]"
      >
        <div className="flex items-center justify-between gap-4 px-6 pt-5">
          <label htmlFor="rule" className="flex items-center gap-2 text-[10px] font-bold uppercase tracking-[0.18em] text-white/45">
            <span className={`h-1.5 w-1.5 rounded-full ${busy ? 'bg-amber-300' : 'bg-emerald-400'}`} />
            {busy ? 'Compiling…' : 'Write a guardrail in plain English'}
          </label>
          <span className="hidden font-mono text-[10px] text-white/30 sm:block">⏎ compile · ⇧⏎ new line</span>
        </div>

        <div className="relative px-6 py-5">
          <textarea
            id="rule"
            rows={2}
            value={text}
            onChange={(e) => setText(e.target.value)}
            onFocus={() => setFocused(true)}
            onBlur={() => setFocused(false)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.shiftKey && text.trim()) {
                e.preventDefault()
                compile(text.trim())
              }
            }}
            className="relative z-10 block min-h-[4.25rem] w-full resize-none bg-transparent p-0 font-display text-[clamp(1.3rem,3vw,1.85rem)] font-semibold leading-snug text-white caret-arc-300 outline-none"
          />
          {!text && (
            <p
              aria-hidden
              className="pointer-events-none absolute inset-x-6 top-5 font-display text-[clamp(1.3rem,3vw,1.85rem)] font-semibold leading-snug text-white/25"
            >
              {ghost}
              {!focused && <span className="caret text-arc-300" />}
            </p>
          )}
        </div>

        {/* Whether Ward will have to stop and ask what you meant. */}
        <div className="flex flex-wrap items-center justify-between gap-4 border-t border-white/10 px-6 py-4">
          <div className="flex flex-wrap items-center gap-x-5 gap-y-2">
            <Precision met={named} label="names a resource" />
            <Precision met={bounded} label="names a limit" />
            <span className="text-[11px] text-white/35">
              {named && bounded ? 'Specific enough to compile directly' : 'Ward may ask a clarifying question'}
            </span>
          </div>
          <button
            type="submit"
            disabled={!text.trim() || busy}
            className="group inline-flex shrink-0 items-center gap-2.5 rounded-full bg-white py-1.5 pl-5 pr-1.5 text-[15px] font-semibold text-ink transition disabled:cursor-not-allowed disabled:bg-white/25 disabled:text-white/50"
          >
            {busy ? 'Verifying…' : 'Compile'}
            <span className="grid h-9 w-9 place-items-center rounded-full bg-ink text-white transition duration-300 group-enabled:group-hover:bg-arc-600 group-disabled:bg-white/20">
              <Sparkles size={16} />
            </span>
          </button>
        </div>

        {busy && (
          <div className="absolute inset-x-0 bottom-0 h-0.5 overflow-hidden bg-white/10">
            <div className="animate-sweep h-full w-1/4 bg-gradient-to-r from-transparent via-arc-300 to-transparent" />
          </div>
        )}
      </form>

      {suggestions.length > 0 && (
        <div>
          <div className="mb-3 flex items-baseline justify-between gap-4">
            <p className="text-[10px] font-bold uppercase tracking-[0.16em] text-slate-400">Start from the rulebook</p>
            <p className="text-[10.5px] font-semibold text-slate-400">click to load · {suggestions.length} ready</p>
          </div>
          <div className="grid gap-2 sm:grid-cols-2">
            {suggestions.map((sug) => {
              const meta = RULEBOOK[sug] ?? { icon: Sparkles, filter: 'compiles to a c7n policy' }
              const Icon = meta.icon
              const picked = sug === text
              return (
                <button
                  key={sug}
                  type="button"
                  onClick={() => (onPick ? onPick(sug) : setText(sug))}
                  className={`group flex items-center gap-3 rounded-2xl border px-3 py-2.5 text-left transition duration-200 hover:-translate-y-0.5 hover:shadow-[0_12px_24px_-16px_rgb(23_23_60/0.6)] ${
                    picked ? 'border-arc-400 bg-arc-50' : 'border-slate-200 bg-white hover:border-arc-200'
                  }`}
                >
                  <span
                    className={`grid h-8 w-8 shrink-0 place-items-center rounded-xl transition ${
                      picked ? 'bg-arc-600 text-white' : meta.vague ? 'bg-amber-50 text-amber-600' : 'bg-slate-100 text-slate-500 group-hover:bg-arc-100 group-hover:text-arc-600'
                    }`}
                  >
                    <Icon size={15} strokeWidth={2.2} />
                  </span>
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-[13px] font-semibold text-ink">{sug}</span>
                    <span className={`block truncate font-mono text-[10px] ${meta.vague ? 'text-amber-600' : 'text-slate-400'}`}>
                      {meta.filter}
                    </span>
                  </span>
                  <span
                    className={`grid h-5 w-5 shrink-0 place-items-center rounded-full transition ${
                      picked ? 'bg-arc-600 text-white' : 'text-slate-300 group-hover:text-arc-500'
                    }`}
                  >
                    {picked ? <Check size={11} strokeWidth={3.5} /> : <Plus size={13} strokeWidth={2.5} />}
                  </span>
                </button>
              )
            })}
          </div>
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

      {result?.status === 'unverified' && <UnverifiedDraft key={result.english} result={result} />}
    </div>
  )
}

/* The model's policy for a sentence Ward's templates can't read. It loads as a real Custodian policy,
   but nothing independent of the model says what the sentence means, so it can't be verified — and
   the backend won't store it. What it *can* show is exactly what it would match right now, which is
   how a person decides whether the model understood them. */
function UnverifiedDraft({ result }) {
  const matched = (result.simulation?.policies ?? []).flatMap((p) => p.matched ?? [])
  return (
    <div className="overflow-hidden rounded-3xl border border-amber-200 bg-white">
      <div className="flex items-start gap-3 border-b border-amber-100 bg-amber-50/70 px-5 py-4">
        <AlertTriangle size={17} className="mt-0.5 shrink-0 text-amber-600" />
        <div className="min-w-0">
          <p className="font-display text-[1.1rem] font-semibold text-ink">Unverified draft</p>
          <p className="mt-1 text-[13px] leading-relaxed text-amber-900">{result.reason}</p>
        </div>
      </div>

      <div className="grid gap-4 p-5 md:grid-cols-[1.3fr_1fr]">
        <div className="rounded-2xl bg-ink p-4">
          <div className="mb-3 flex items-center justify-between">
            <span className="text-[10px] font-bold uppercase tracking-[0.16em] text-white/40">Drafted by the model</span>
            <span className="rounded-md bg-white/10 px-1.5 py-0.5 font-mono text-[10px] font-bold text-white/60">{result.compiler}</span>
          </div>
          <YamlBlock code={result.yaml} />
        </div>

        <div>
          <p className="text-[10px] font-bold uppercase tracking-[0.14em] text-slate-400">It would match right now</p>
          {matched.length ? (
            <ul className="mt-2 divide-y divide-slate-100 rounded-2xl border border-slate-200">
              {matched.slice(0, 8).map((m) => (
                <li key={m.id} className="flex items-baseline justify-between gap-3 px-3 py-2 text-[12.5px]">
                  <span className="min-w-0 truncate text-ink">
                    {m.name || m.id}
                    {m.detail && <span className="ml-1.5 font-mono text-[11px] text-slate-400">{m.detail}</span>}
                  </span>
                  {m.running_hours != null && <span className="shrink-0 tabular-nums text-slate-500">{m.running_hours}h</span>}
                </li>
              ))}
            </ul>
          ) : (
            <p className="mt-2 rounded-2xl border border-slate-200 px-3 py-4 text-[12.5px] text-slate-500">
              Nothing in your account right now.
            </p>
          )}
          <p className="mt-3 text-[12px] leading-relaxed text-slate-500">
            If that list isn’t what you meant, rephrase with a resource type and a number — Ward can then build
            and verify the policy itself.
          </p>
        </div>
      </div>
    </div>
  )
}

function Precision({ met, label }) {
  return (
    <span className={`flex items-center gap-1.5 text-[11px] font-semibold transition ${met ? 'text-emerald-300' : 'text-white/35'}`}>
      <span className={`grid h-4 w-4 place-items-center rounded-full transition ${met ? 'bg-emerald-400/20' : 'bg-white/10'}`}>
        <Check size={10} strokeWidth={3.5} />
      </span>
      {label}
    </span>
  )
}

// An example rule types itself in the empty field, then gives way to the next one. Stops the
// moment the field is focused, so it never competes with what the user is writing.
function useGhost(examples, active) {
  const [idx, setIdx] = useState(0)
  const [typed, setTyped] = useState(0)
  const full = examples[idx % examples.length]
  const still = typeof window !== 'undefined' && window.matchMedia?.('(prefers-reduced-motion: reduce)').matches

  useEffect(() => {
    if (!active) return
    if (still) {
      setTyped(full.length)
      return
    }
    setTyped(0)
    let n = 0
    const id = setInterval(() => {
      n += 1
      setTyped(n)
      if (n >= full.length) clearInterval(id)
    }, 34)
    return () => clearInterval(id)
  }, [full, active, still])

  useEffect(() => {
    if (!active || typed < full.length) return
    const id = setTimeout(() => setIdx((v) => v + 1), 2600)
    return () => clearTimeout(id)
  }, [active, typed, full.length])

  return active ? full.slice(0, typed) : ''
}
