import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { AlertCircle, Check, CheckCircle2, Eye, EyeOff, Lock, ShieldCheck } from 'lucide-react'
import MicroSlats from './MicroSlats.jsx'
import { WardMark } from './ui.jsx'

/* The frame both sign-in pages share.

   Left: the product, working. Over Ward's moving indigo slats, a glass card types a rule in plain
   English, assembles the Cloud Custodian policy under it line by line, then stamps it verified with what
   it would catch — three rules in turn. The page shows what Ward does before anyone has an account.

   Right: the form, in a white card with an aurora edge, under a Sign in / Create account switch.
   On a phone the left side folds away and the form stands alone. */
export default function AuthShell({ mode, title, subtitle, children, footer }) {
  return (
    <div className="grid min-h-screen bg-paper lg:h-screen lg:grid-cols-[1.08fr_1fr] lg:overflow-hidden">
      <aside className="grain relative hidden overflow-hidden bg-arc-600 text-white lg:block">
        <MicroSlats
          className="absolute! inset-0"
          preset="tide"
          color="#4048fd"
          glintColor="#8c93ff"
          backgroundColor="#3139fb"
          slatWidth={8}
          slatHeight={20}
          gap={4}
          speed={0.4}
          cursorStrength={0.8}
        />
        <span aria-hidden className="pointer-events-none absolute -right-40 -top-40 z-[1] h-[34rem] w-[34rem] rounded-full bg-[radial-gradient(circle,rgb(245_163_199/0.3),transparent_65%)] blur-2xl" />

        <div className="relative z-10 flex h-full flex-col px-12 py-8">
          <Link to="/" className="flex items-center gap-2.5 self-start">
            <WardMark size={34} />
            <span className="font-display text-[1.5rem] font-semibold tracking-tight">Ward</span>
          </Link>

          <div className="my-auto max-w-xl">
            <h2 className="font-display text-[clamp(2.2rem,3.1vw,3rem)] font-semibold leading-[1.03] tracking-tight [text-shadow:0_2px_24px_rgb(20_22_140/0.45)]">
              Say the rule.<br />Ward writes the policy.
            </h2>
            <LiveCompile />
          </div>

          <div className="flex flex-wrap gap-x-6 gap-y-2 text-[12.5px] font-semibold text-white/80">
            {['Read-only by design', 'Verified before it’s trusted', 'Your role, your control'].map((t) => (
              <span key={t} className="flex items-center gap-1.5"><ShieldCheck size={14} className="text-white/60" /> {t}</span>
            ))}
          </div>
        </div>
      </aside>

      <main className="relative flex items-center justify-center overflow-hidden px-5 py-8 sm:px-10">
        <span aria-hidden className="pointer-events-none absolute -right-32 top-10 h-80 w-80 rounded-full bg-[radial-gradient(circle,rgb(142_150_255/0.22),transparent_70%)] blur-2xl" />
        <span aria-hidden className="pointer-events-none absolute -left-24 bottom-0 h-72 w-72 rounded-full bg-[radial-gradient(circle,rgb(255_180_143/0.2),transparent_70%)] blur-2xl" />

        <div className="animate-rise relative w-full max-w-[440px]">
          <Link to="/" className="mb-8 flex items-center gap-2 lg:hidden">
            <WardMark size={30} />
            <span className="font-display text-[1.35rem] font-semibold tracking-tight text-ink">Ward</span>
          </Link>

          {mode && <ModeSwitch mode={mode} />}

          <h1 className="mt-9 text-[11.5px] font-bold uppercase tracking-[0.22em] text-slate-400">{title}</h1>
          {subtitle && <p className="mt-1 text-[13.5px] text-slate-400">{subtitle}</p>}
          {children && <div className="mt-4">{children}</div>}
          {footer && <p className="mt-6 text-center text-[13.5px] text-slate-500">{footer}</p>}
        </div>
      </main>
    </div>
  )
}

// Sign in ⇄ Create account, as one control with a pill that slides between them.
function ModeSwitch({ mode }) {
  const signup = mode === 'signup'
  return (
    <div className="relative grid w-full grid-cols-2 rounded-2xl border border-slate-200/80 bg-white p-1 shadow-[0_1px_2px_rgb(15_23_42/0.04)]">
      <span
        aria-hidden
        className="absolute inset-y-1 left-1 w-[calc(50%-0.25rem)] rounded-xl bg-ink shadow-[0_8px_18px_-8px_rgb(0_0_0/0.5)] transition-transform duration-500 ease-[cubic-bezier(0.32,0.72,0,1)]"
        style={{ transform: signup ? 'translateX(100%)' : 'none' }}
      />
      {[['login', 'Sign in', '/login'], ['signup', 'Create account', '/signup']].map(([key, label, to]) => (
        <Link key={key} to={to} replace aria-current={mode === key ? 'page' : undefined}
              className={`relative z-10 py-2.5 text-center text-[13.5px] font-bold transition-colors duration-300 ${mode === key ? 'text-white' : 'text-slate-500 hover:text-ink'}`}>
          {label}
        </Link>
      ))}
    </div>
  )
}

/* ── The live compile ──────────────────────────────────────────────────────── */

const DEMOS = [
  {
    rule: 'No GPU instance may run for more than 6 hours',
    yaml: ['policies:', '  - name: gpu-max-runtime-6h', '    resource: aws.ec2', '    filters:', '      - State.Name: running',
           '      - InstanceType: ^(p|g|inf)[0-9].*', '      - instance-age > 6h'],
    caught: 'Would flag 2 GPU boxes · ₹4,012/day',
  },
  {
    rule: 'Every volume needs an Owner tag',
    yaml: ['policies:', '  - name: require-owner-tag', '    resource: aws.ebs', '    filters:', '      - "tag:Owner": absent'],
    caught: 'Would flag 3 volumes nobody owns',
  },
  {
    rule: 'SSH must never be open to the internet',
    yaml: ['policies:', '  - name: no-public-port-22', '    resource: aws.security-group', '    filters:',
           '      - type: ingress', '        Ports: [22]', '        Cidr: 0.0.0.0/0'],
    caught: 'Would flag launch-wizard-1',
  },
]

// Phases: type the rule → assemble the YAML → stamp it verified → hold → next rule.
function LiveCompile() {
  const reduced = typeof window !== 'undefined' && window.matchMedia?.('(prefers-reduced-motion: reduce)').matches
  const [index, setIndex] = useState(0)
  const [typed, setTyped] = useState(0)
  const [lines, setLines] = useState(0)
  const [verified, setVerified] = useState(false)
  const demo = DEMOS[index]

  useEffect(() => {
    if (reduced) {
      setTyped(demo.rule.length)
      setLines(demo.yaml.length)
      setVerified(true)
      return undefined
    }
    setTyped(0)
    setLines(0)
    setVerified(false)
    const timers = []
    let t = 400
    for (let i = 1; i <= demo.rule.length; i++) {
      timers.push(setTimeout(() => setTyped(i), t))
      t += 38
    }
    t += 350
    for (let i = 1; i <= demo.yaml.length; i++) {
      timers.push(setTimeout(() => setLines(i), t))
      t += 170
    }
    t += 300
    timers.push(setTimeout(() => setVerified(true), t))
    timers.push(setTimeout(() => setIndex((n) => (n + 1) % DEMOS.length), t + 3200))
    return () => timers.forEach(clearTimeout)
  }, [index, reduced, demo])

  return (
    <div className="mt-7 overflow-hidden rounded-[26px] bg-white/[0.09] shadow-[0_30px_60px_-30px_rgb(10_8_60/0.7)] ring-1 ring-inset ring-white/20 backdrop-blur-md">
      <div className="flex items-center justify-between border-b border-white/10 px-5 py-3">
        <span className="text-[10.5px] font-bold uppercase tracking-[0.18em] text-white/60">Your rule</span>
        <span className="flex gap-1.5">
          {DEMOS.map((_, i) => (
            <span key={i} className={`h-1.5 rounded-full transition-all duration-500 ${i === index ? 'w-5 bg-white' : 'w-1.5 bg-white/30'}`} />
          ))}
        </span>
      </div>

      <p className="min-h-[4.2rem] px-5 pt-4 font-display text-[1.45rem] font-semibold leading-snug">
        “{demo.rule.slice(0, typed)}
        {typed < demo.rule.length && <span className="caret ml-0.5 inline-block h-[1.1em] w-[2px] translate-y-[3px] bg-white" />}
        {typed >= demo.rule.length && '”'}
      </p>

      <pre className="mx-5 mt-3 min-h-[8.8rem] overflow-hidden rounded-2xl bg-[#1f25c9]/60 px-4 py-3 font-mono text-[11.5px] leading-[1.6] text-white/85 ring-1 ring-inset ring-white/10">
        {demo.yaml.slice(0, lines).map((line, i) => (
          <span key={`${index}-${i}`} className="animate-rise block">{line}</span>
        ))}
      </pre>

      <div className="flex min-h-[3.6rem] items-center gap-3 px-5 py-3.5">
        <span
          className={`inline-flex items-center gap-1.5 rounded-full bg-emerald-400 px-3 py-1 text-[12px] font-bold text-emerald-950 transition-all duration-500 ${
            verified ? 'scale-100 opacity-100' : 'scale-75 opacity-0'
          }`}
        >
          <CheckCircle2 size={14} /> Verified · 5/5 tests
        </span>
        <span className={`text-[12.5px] font-semibold text-white/80 transition-opacity delay-150 duration-500 ${verified ? 'opacity-100' : 'opacity-0'}`}>
          {demo.caught}
        </span>
      </div>
    </div>
  )
}

/* ── Form pieces ───────────────────────────────────────────────────────────── */

/* Sign in, written as a sentence. Ward turns plain-English sentences into policies, so its own door is one
   too: the blanks sit inside the sentence in the same serif, grow as you type, and underline themselves —
   dashed while empty, a glowing indigo line while you're in them, green once what's there is valid.

   Under it, Ward "reads" the sentence back in mono, the way it reads a rule — what it understood, and
   whether it has enough to go on. */

export function Sentence({ children }) {
  return (
    <p className="font-display text-[clamp(1.7rem,2.6vw,2.15rem)] font-medium leading-[1.75] tracking-tight text-slate-400">
      {children}
    </p>
  )
}

export function Blank({ value, onChange, placeholder, type = 'text', valid, label, autoFocus, autoComplete, peek }) {
  const [focused, setFocused] = useState(false)
  const [shown, setShown] = useState(false)
  const secret = type === 'password' && !shown
  // The width follows the text: an invisible copy of it sizes the grid cell the input fills.
  const mirror = value ? (secret ? '•'.repeat(value.length) : value) : placeholder
  const line = valid ? 'bg-emerald-500' : focused ? 'bg-gradient-to-r from-arc-600 via-[#8e6bff] to-[#e98bbd] shadow-[0_2px_10px_rgb(49_57_251/0.45)]' : ''
  return (
    <span className="relative mx-1 inline-grid max-w-full align-baseline">
      <span aria-hidden className="invisible col-start-1 row-start-1 whitespace-pre pr-1 text-ink">{mirror}</span>
      <input
        aria-label={label}
        type={secret ? 'password' : type === 'password' ? 'text' : type}
        value={value}
        onChange={onChange}
        onFocus={() => setFocused(true)}
        onBlur={() => setFocused(false)}
        placeholder={placeholder}
        autoFocus={autoFocus}
        autoComplete={autoComplete}
        spellCheck={false}
        required
        className="auth-input col-start-1 row-start-1 w-full min-w-[3ch] bg-transparent font-display text-ink caret-arc-600 outline-none placeholder:text-slate-300"
      />
      {/* the underline: dashed when empty and idle; a live line otherwise */}
      <span aria-hidden className={`absolute -bottom-0.5 left-0 right-0 h-[2.5px] rounded-full transition-all duration-300 ${line || 'bg-[length:10px_2.5px] bg-repeat-x bg-[linear-gradient(90deg,rgb(148_163_184/0.7)_55%,transparent_55%)]'}`} />
      {valid && (
        <span aria-hidden className="animate-rise absolute -right-2.5 -top-1.5 grid h-5 w-5 place-items-center rounded-full bg-emerald-500 text-white shadow-[0_4px_10px_-3px_rgb(16_185_129/0.7)]">
          <Check size={11} strokeWidth={3.5} />
        </span>
      )}
      {peek && value && (
        <button type="button" onClick={() => setShown((v) => !v)} aria-label={shown ? 'Hide password' : 'Show password'}
                className="absolute -bottom-7 right-0 flex items-center gap-1 font-sans text-[11px] font-bold tracking-normal text-slate-400 transition hover:text-arc-600">
          {shown ? <EyeOff size={12} /> : <Eye size={12} />} {shown ? 'hide' : 'show'}
        </button>
      )}
    </span>
  )
}

// What Ward understood from the sentence, in its own voice: mono, like a policy.
export function Parsed({ items, ready, waitingFor }) {
  return (
    <div className="mt-7 flex flex-wrap items-center gap-x-2 gap-y-2 rounded-2xl bg-white/70 px-4 py-3 font-mono text-[11.5px] text-slate-500 ring-1 ring-inset ring-slate-200/80 backdrop-blur">
      <span className="text-arc-500">→</span>
      {items.map(([key, value, ok]) => (
        <span key={key} className="flex items-center gap-1.5">
          <span className="text-slate-400">{key}</span>
          <span className={ok ? 'text-ink' : 'text-slate-300'}>{value}</span>
        </span>
      ))}
      <span className={`ml-auto rounded-full px-2 py-0.5 font-sans text-[10.5px] font-bold transition-colors duration-300 ${ready ? 'bg-emerald-50 text-emerald-700' : 'bg-slate-100 text-slate-400'}`}>
        {ready ? 'ready' : `waiting for ${waitingFor}`}
      </span>
    </div>
  )
}

export function FormError({ children }) {
  if (!children) return null
  return (
    <p role="alert" className="animate-rise flex items-start gap-2 rounded-2xl bg-coral-50 px-4 py-3 text-[13px] leading-relaxed text-coral-600 ring-1 ring-inset ring-coral-100">
      <AlertCircle size={15} className="mt-0.5 shrink-0" /> {children}
    </p>
  )
}

export function Submit({ busy, children }) {
  return (
    <div className="pt-2">
      <button
        type="submit"
        disabled={busy}
        className="group relative flex w-full items-center justify-center gap-2.5 overflow-hidden rounded-2xl bg-arc-600 py-1.5 pl-6 pr-1.5 text-[15px] font-bold text-white shadow-[inset_0_1px_0_rgb(255_255_255/0.22),0_18px_36px_-14px_rgb(49_57_251/0.85)] transition hover:bg-arc-700 disabled:cursor-wait disabled:opacity-75"
      >
        <span className="flex-1 text-left">{children}</span>
        <span className="grid h-10 w-10 place-items-center rounded-xl bg-white/20 transition duration-300 group-hover:translate-x-0.5">
          <span aria-hidden className="text-[17px]">→</span>
        </span>
      </button>
      <p className="mt-4 flex items-center justify-center gap-1.5 text-[11.5px] text-slate-400">
        <Lock size={11} /> Encrypted session · Ward only ever reads your account
      </p>
    </div>
  )
}
