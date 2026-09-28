import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { ArrowRight, Check, Cpu, Radar } from 'lucide-react'
import { WardMark } from '../components/ui.jsx'
import YamlBlock from '../components/YamlBlock.jsx'

/* The landing page. It sits outside the app shell but keeps its weather: the indigo tint with
   grain, paper plates that meet the tint along a cloud line, and Fraunces at poster size. */

export default function Landing() {
  return (
    <div className="shell min-h-full overflow-x-hidden pb-px">
      <Hero />
      <Problem />
      <Machines />
      <Rulebook />
      <Loop />
      <Closing />
    </div>
  )
}

/* ── Hero ──────────────────────────────────────────────────────────────── */

function Hero() {
  return (
    <section className="mx-auto max-w-6xl px-5 pb-20 pt-20 text-center md:px-8 md:pb-28 md:pt-24">
      {/* The headline is the product: the same sentence, said twice, in two typefaces. */}
      <h1 className="lift-text display-hero mx-auto flex max-w-4xl flex-col items-center gap-y-1 text-white">
        <span className="flex flex-wrap items-baseline justify-center gap-x-4">
          <span className="font-sans text-[clamp(0.95rem,2.2vw,1.35rem)] font-semibold uppercase tracking-[0.22em] text-white/55">
            You write it in
          </span>
          <span className="font-display text-[clamp(3rem,10vw,7rem)] font-extrabold">English.</span>
        </span>
        <span className="flex flex-wrap items-baseline justify-center gap-x-4">
          <span className="font-sans text-[clamp(0.95rem,2.2vw,1.35rem)] font-semibold uppercase tracking-[0.22em] text-white/55">
            Ward runs it as
          </span>
          <span className="font-mono text-[clamp(2.4rem,8vw,5.6rem)] font-medium tracking-[-0.04em] text-arc-200">YAML.</span>
        </span>
      </h1>

      <Compiler />

      <div className="mt-12 flex flex-wrap items-center justify-center gap-x-9 gap-y-5">
        {/* A serif label in a white pill, with the arrow in its own dark well. */}
        <Link
          to="/app"
          className="group inline-flex items-center gap-5 rounded-full bg-white py-2 pl-7 pr-2 text-ink shadow-[0_20px_44px_-20px_rgb(8_6_50/0.9)] transition duration-300 hover:shadow-[0_26px_56px_-22px_rgb(8_6_50/0.95)] active:translate-y-px"
        >
          <span className="font-display text-[1.05rem] font-semibold tracking-tight">Open the dashboard</span>
          <span className="grid h-10 w-10 place-items-center rounded-full bg-ink text-white transition duration-300 group-hover:bg-arc-600">
            <ArrowRight size={16} className="transition duration-300 group-hover:translate-x-0.5" />
          </span>
        </Link>

        <a href="#problem" className="group inline-flex items-center gap-3 text-[11px] font-bold uppercase tracking-[0.2em] text-white/60 transition hover:text-white">
          Why it exists
          <span aria-hidden className="h-px w-6 bg-white/35 transition-all duration-300 group-hover:w-11 group-hover:bg-white" />
        </a>
      </div>

      <div className="mx-auto mt-14 max-w-2xl">
        <div className="h-px w-full bg-gradient-to-r from-transparent via-white/25 to-transparent" />
        <ul className="lift-text mt-5 flex flex-wrap items-center justify-center gap-x-4 gap-y-2 text-[10.5px] font-bold uppercase tracking-[0.18em] text-white/55">
          {['Runs on Cloud Custodian', 'Read-only IAM', 'Sweeps every 15 minutes'].map((item, i) => (
            <li key={item} className="flex items-center gap-4">
              {i > 0 && <span aria-hidden className="h-1 w-1 rounded-full bg-white/25" />}
              {item}
            </li>
          ))}
        </ul>
      </div>
    </section>
  )
}

// Three real rules from the default rulebook, with the YAML Ward actually compiles them into.
const DEMOS = [
  {
    english: 'No GPU instance runs more than 6 hours.',
    fixtures: '5/5 fixtures · 2 match, 2 don’t, 1 edge case',
    yaml: `policies:
  - name: ec2-gpu-max-runtime-6h
    resource: aws.ec2
    filters:
      - State.Name: running
      - type: value
        key: InstanceType
        op: regex
        value: ^(p|g|inf)
      - type: instance-age
        op: greater-than
        hours: 6`,
  },
  {
    english: 'Nothing left running over a weekend.',
    fixtures: '5/5 fixtures · timezone-aware, Asia/Kolkata',
    yaml: `policies:
  - name: ec2-no-weekend-running
    resource: aws.ec2
    filters:
      - State.Name: running
      - "tag:Environment": absent
      - type: offhour
        weekends: true
        default_tz: Asia/Kolkata`,
  },
  {
    english: 'Flag any resource with no owner tag.',
    fixtures: '5/5 fixtures · edge case: tag key is case-sensitive',
    yaml: `policies:
  - name: require-owner-tag
    resource: aws.ec2
    filters:
      - "tag:Owner": absent`,
  },
]

const prefersReducedMotion = () =>
  typeof window !== 'undefined' && window.matchMedia?.('(prefers-reduced-motion: reduce)').matches

// The product in one object: a sentence typing itself on the left, the policy it compiles to
// on the right, and the verifier's receipt underneath.
function Compiler() {
  const [idx, setIdx] = useState(0)
  const [typed, setTyped] = useState(0)
  const demo = DEMOS[idx]
  const done = typed >= demo.english.length

  useEffect(() => {
    if (prefersReducedMotion()) {
      setTyped(demo.english.length)
      return
    }
    setTyped(0)
    let n = 0
    const id = setInterval(() => {
      n += 1
      setTyped(n)
      if (n >= demo.english.length) clearInterval(id)
    }, 26)
    return () => clearInterval(id)
  }, [demo.english])

  useEffect(() => {
    if (!done) return
    const id = setTimeout(() => setIdx((v) => (v + 1) % DEMOS.length), 4600)
    return () => clearTimeout(id)
  }, [done, idx])

  return (
    <div className="glass grain mx-auto mt-14 max-w-5xl rounded-4xl p-2.5 text-left shadow-[0_40px_80px_-40px_rgb(6_4_40/0.9)]">
      <div className="grid gap-2.5 lg:grid-cols-2">
        {/* What you write */}
        <div className="relative flex flex-col rounded-[1.6rem] bg-paper p-5 md:p-6">
          <div className="flex items-center justify-between gap-3">
            <p className="text-[10px] font-bold uppercase tracking-[0.16em] text-slate-400">You write</p>
            <div className="flex gap-1.5">
              {DEMOS.map((d, i) => (
                <button
                  key={d.english}
                  onClick={() => setIdx(i)}
                  aria-label={`Show rule ${i + 1}`}
                  className={`h-1.5 rounded-full transition-all ${i === idx ? 'w-5 bg-arc-500' : 'w-1.5 bg-slate-300 hover:bg-slate-400'}`}
                />
              ))}
            </div>
          </div>

          <p className="flex h-60 items-center font-display text-[clamp(1.35rem,2.8vw,1.75rem)] font-semibold leading-snug text-ink">
            <span>
              <span className="text-slate-300">“</span>
              {demo.english.slice(0, typed)}
              <span className="caret text-arc-500" />
              {done && <span className="text-slate-300">”</span>}
            </span>
          </p>

          <div className="flex items-center gap-2 border-t border-slate-200/80 pt-4 text-[11px] font-semibold text-slate-500">
            <span className="grid h-6 w-6 place-items-center rounded-lg bg-arc-50 text-arc-600"><Cpu size={12} /></span>
            Compiled by a 7B model, fine-tuned on verifier-certified output
          </div>
        </div>

        {/* What runs */}
        <div className="flex flex-col rounded-[1.6rem] bg-ink p-5 md:p-6">
          <div className="flex items-center justify-between gap-3">
            <p className="text-[10px] font-bold uppercase tracking-[0.16em] text-white/40">Ward runs</p>
            <span className="rounded-md bg-white/10 px-1.5 py-0.5 font-mono text-[10px] font-bold text-white/60">c7n</span>
          </div>

          {/* Fixed height, sized to the longest policy, so nothing reflows as rules cycle. */}
          <div className="scroll-quiet flex h-60 items-center overflow-y-auto">
            {done ? (
              <YamlBlock key={idx} code={demo.yaml} stagger className="md:text-[12.5px]" />
            ) : (
              <p className="font-mono text-[12px] text-white/35">
                compiling<span className="caret" />
              </p>
            )}
          </div>

          <div className="flex items-center gap-2 border-t border-white/10 pt-4 text-[11px] font-semibold text-emerald-300">
            <span className={`grid h-6 w-6 place-items-center rounded-lg bg-emerald-400/15 transition ${done ? 'opacity-100' : 'opacity-30'}`}>
              <Check size={12} strokeWidth={3} />
            </span>
            <span className={`transition ${done ? 'text-white/70' : 'text-white/25'}`}>verifier: {demo.fixtures}</span>
          </div>
        </div>
      </div>
    </div>
  )
}

/* ── The problem ───────────────────────────────────────────────────────── */

const PROBLEMS = [
  {
    title: 'The alerts arrive too late',
    body: 'AWS Free Tier alerts fire at 85% of the limit, or after a forecast breach. By then the money is usually gone — and the warning lands in an inbox nobody reads.',
  },
  {
    title: 'The good tools speak YAML',
    body: 'Cloud Custodian is an excellent policy engine. To use it you write a domain-specific language. Nobody learns a DSL to say “don’t let anything run overnight”.',
  },
  {
    title: 'Nothing explains the bill',
    body: 'Every tool can tell you that you spent money. None tell you why the number moved, in words a beginner understands, with a fix attached.',
  },
]

function Problem() {
  return (
    <section id="problem" className="cloud-bottom bg-paper text-ink">
      <div className="mx-auto max-w-6xl px-5 py-20 md:px-8 md:py-28">
        <p className="display-small font-display text-[13px] font-bold uppercase tracking-[0.2em] text-arc-600">The problem</p>

        <h2 className="mt-5 max-w-[18ch] font-display text-[clamp(2.1rem,5.6vw,3.9rem)] font-semibold leading-[1.02] tracking-tight text-ink">
          Cloud providers charge by the second.
          <span className="text-slate-400"> Nobody watches by the second.</span>
        </h2>

        <div className="mt-14 grid gap-x-10 gap-y-10 md:grid-cols-3">
          {PROBLEMS.map((p, i) => (
            <div key={p.title} className="border-t-2 border-ink/90 pt-5">
              <span className="font-display text-[2.4rem] font-semibold leading-none tabular-nums text-slate-300">
                {String(i + 1).padStart(2, '0')}
              </span>
              <h3 className="mt-4 font-display text-[1.35rem] font-semibold leading-tight text-ink">{p.title}</h3>
              <p className="mt-2.5 text-[14.5px] leading-relaxed text-slate-600">{p.body}</p>
            </div>
          ))}
        </div>

        <div className="mt-16 rounded-3xl bg-ink px-6 py-10 text-white md:px-12 md:py-14">
          <p className="font-display text-[clamp(1.8rem,4.4vw,3rem)] font-semibold leading-[1.05] tracking-tight">
            It’s a translation gap.
          </p>
          <p className="mt-4 max-w-2xl text-[15.5px] leading-relaxed text-white/70 md:text-[17px]">
            The rules people want are simple English sentences. The systems that enforce rules speak
            YAML. Ward is the compiler between them — and the proof that the translation was correct.
          </p>
        </div>
      </div>
    </section>
  )
}

/* ── What's inside ─────────────────────────────────────────────────────── */

const MACHINES = [
  {
    name: 'The compiler',
    lede: 'A fine-tuned 7B model turns your sentence into policy YAML — small enough to self-host, so your infrastructure config never leaves the building.',
    tag: 'english → policy.yaml',
    lift: 'lg:translate-y-0',
  },
  {
    name: 'The verifier',
    lede: 'No policy is trusted until it is graded against generated fixtures: two resources it must match, two it must not, and one edge case built from a mistake people actually make.',
    tag: '5/5 fixtures passed',
    lift: 'lg:translate-y-10',
  },
  {
    name: 'The watcher',
    lede: 'Verified policies sweep your account every 15 minutes, read-only. Ward notifies on state transitions, not on repeats — so a problem reaches you once.',
    tag: 'OK → WARNING → ALERT',
    lift: 'lg:translate-y-20',
  },
]

function Machines() {
  return (
    <section id="inside" className="mx-auto max-w-6xl px-5 py-20 md:px-8 md:py-28">
      <p className="lift-text display-small font-display text-[13px] font-bold uppercase tracking-[0.2em] text-arc-200">
        What’s inside
      </p>
      <h2 className="lift-text mt-5 max-w-[16ch] font-display text-[clamp(2.1rem,5.6vw,3.9rem)] font-semibold leading-[1.02] tracking-tight text-white">
        Three machines, one loop.
      </h2>

      <div className="mt-14 grid gap-5 lg:grid-cols-3 lg:pb-20">
        {MACHINES.map((m, i) => (
          <article
            key={m.name}
            className={`glass grain flex flex-col rounded-[1.75rem] p-6 text-white transition duration-300 hover:-translate-y-1 md:p-7 ${m.lift}`}
          >
            <span className="font-display text-[2.6rem] font-semibold leading-none tabular-nums text-white/35">
              {String(i + 1).padStart(2, '0')}
            </span>
            <h3 className="lift-text mt-5 font-display text-[1.6rem] font-semibold leading-tight">{m.name}</h3>
            <p className="lift-text mt-3 flex-1 text-[14.5px] leading-relaxed text-white/80">{m.lede}</p>
            <p className="mt-6 inline-flex w-fit rounded-lg bg-black/25 px-2.5 py-1.5 font-mono text-[11px] font-medium text-white/85">
              {m.tag}
            </p>
          </article>
        ))}
      </div>
    </section>
  )
}

/* ── The rulebook ──────────────────────────────────────────────────────── */

const RULEBOOK = [
  ['Stay inside the free tier', 'aws.ebs · Attachments: []'],
  ['Nothing runs longer than 6 hours unattended', 'type: instance-age · hours: 6'],
  ['No GPU instance without an expiry tag', '"tag:expiry": absent'],
  ['Warn before monthly spend crosses the budget', 'type: budget · threshold_percent: 85'],
  ['Nothing left running over a weekend', 'type: offhour · weekends: true'],
  ['Flag any resource with no owner tag', '"tag:Owner": absent'],
]

function Rulebook() {
  return (
    <section id="rulebook" className="cloud-bottom bg-paper text-ink">
      <div className="mx-auto max-w-6xl px-5 py-20 md:px-8 md:py-28">
        <div className="flex flex-wrap items-end justify-between gap-6">
          <h2 className="max-w-[16ch] font-display text-[clamp(2.1rem,5.6vw,3.9rem)] font-semibold leading-[1.02] tracking-tight">
            You start with a rulebook.
            <span className="text-slate-400"> Then you write your own.</span>
          </h2>
          <p className="max-w-xs text-[14.5px] leading-relaxed text-slate-600">
            Six rules ship on day one, so a new account is covered in the first five minutes. Every
            one of them is an English sentence Ward compiled and verified.
          </p>
        </div>

        <ul className="mt-14 border-t border-slate-300/70">
          {RULEBOOK.map(([english, filter]) => (
            <li key={english} className="group border-b border-slate-300/70">
              <div className="flex flex-wrap items-center gap-x-6 gap-y-2 py-5 transition-all duration-300 md:group-hover:pl-3">
                <Check size={20} strokeWidth={3} className="shrink-0 text-emerald-500/70 transition group-hover:text-emerald-500" />
                <span className="flex-1 font-display text-[clamp(1.3rem,3.3vw,2.1rem)] font-semibold leading-tight tracking-tight text-ink transition group-hover:text-arc-700">
                  {english}
                </span>
                <span className="font-mono text-[11.5px] text-slate-400 transition duration-300 md:opacity-0 md:group-hover:opacity-100">
                  {filter}
                </span>
              </div>
            </li>
          ))}
        </ul>
      </div>
    </section>
  )
}

/* ── The loop ──────────────────────────────────────────────────────────── */

const LOOP = ['You write it', 'Ward compiles it', 'The verifier grades it', 'The watcher enforces it', 'Ward explains it']

function Loop() {
  return (
    <section className="mx-auto max-w-6xl px-5 py-20 md:px-8 md:py-24">
      <h2 className="lift-text max-w-[20ch] font-display text-[clamp(1.9rem,4.8vw,3.2rem)] font-semibold leading-[1.05] tracking-tight text-white">
        English in. Enforcement out. <span className="text-arc-200">Explanations back.</span>
      </h2>

      <ol className="mt-10 flex flex-wrap items-center gap-2.5">
        {LOOP.map((step, i) => (
          <li key={step} className="flex items-center gap-2.5">
            <span className="glass lift-text flex items-center gap-2 rounded-2xl px-3.5 py-2.5 text-[13px] font-bold text-white">
              <span className="font-mono text-[10px] text-white/55">{String(i + 1).padStart(2, '0')}</span>
              {step}
            </span>
            {i < LOOP.length - 1 && <ArrowRight size={15} className="shrink-0 text-white/40" />}
          </li>
        ))}
      </ol>

      <p className="lift-text mt-6 max-w-xl text-[14.5px] leading-relaxed text-white/75">
        And the loop closes: every explanation Ward writes becomes a candidate rule you can accept
        in one click — so the rulebook learns the shape of your own account.
      </p>
    </section>
  )
}

/* ── Closing ───────────────────────────────────────────────────────────── */

function Closing() {
  return (
    <section className="cloud-top bg-paper text-ink">
      <div className="mx-auto max-w-6xl px-5 py-20 md:px-8 md:py-28">
        <h2 className="max-w-[14ch] font-display text-[clamp(2.4rem,7vw,5rem)] font-semibold leading-[0.98] tracking-tight">
          See it running.
        </h2>
        <p className="mt-5 max-w-xl text-[16px] leading-relaxed text-slate-600 md:text-[17px]">
          The dashboard opens on a demo account in ap-south-1 with 30 days of history — real
          Cloud Custodian evaluating real policies, no AWS credentials required.
        </p>

        <div className="mt-8 flex flex-wrap items-center gap-3">
          <Link
            to="/app"
            className="group inline-flex items-center gap-3 rounded-2xl bg-ink py-2 pl-2 pr-5 text-base font-semibold text-white shadow-[inset_0_1px_0_rgb(255_255_255/0.12),0_12px_30px_-12px_rgb(0_0_0/0.6)] transition hover:bg-black active:translate-y-px"
          >
            <span className="grid h-9 w-9 place-items-center rounded-xl bg-gradient-to-br from-white to-arc-100 text-arc-700">
              <Radar size={18} />
            </span>
            Open the dashboard
            <span aria-hidden className="transition group-hover:translate-x-0.5">→</span>
          </Link>
          <Link
            to="/copilot"
            className="rounded-2xl border border-slate-300 bg-white px-4 py-3 text-base font-semibold text-ink transition hover:border-slate-400 hover:bg-slate-50"
          >
            Ask Ward a question
          </Link>
        </div>

        <p className="mt-16 max-w-2xl border-l-2 border-arc-500 pl-5 font-display text-[1.15rem] font-semibold leading-relaxed text-slate-700 md:text-[1.3rem]">
          Cloud Custodian isn’t a competitor — it’s Ward’s backend. Ward doesn’t reimplement the
          rules engine. It removes the requirement to learn its language.
        </p>

        <footer className="mt-16 flex flex-wrap items-center justify-between gap-4 border-t border-slate-200 pt-7 text-[12.5px] font-semibold text-slate-500">
          <span className="flex items-center gap-2.5 text-ink">
            <WardMark size={22} />
            Ward
          </span>
          <span>Natural-language cloud cost guardrails · ap-south-1 Mumbai · demo data</span>
        </footer>
      </div>
    </section>
  )
}
