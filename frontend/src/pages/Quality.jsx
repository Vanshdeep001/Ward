import { useState } from 'react'
import { AlertTriangle, Check, CheckCircle2, Clock, Copy, Coins, FlaskConical, Lock, Scale, Search, Target } from 'lucide-react'
import { useRagEvals } from '../api/hooks.js'
import { Aura, ErrorState, Loading } from '../components/ui.jsx'

/* System quality — internal. How well Ward's search and answers work, from the latest run of
   app/rag/evaluate.py: 58 questions with known answers, on the sample account, graded by the verifier and
   by a judge model that is not the one answering. These numbers describe Ward, not anyone's account, so
   the page is reachable at /quality but deliberately absent from the navigation. */

const pct = (v, digits = 0) => (v == null ? '—' : `${(v * 100).toFixed(digits)}%`)
const dec = (v) => (v == null ? '—' : v.toFixed(2))
const secs = (v) => (v == null ? '—' : `${v.toFixed(1)} s`)

const SETUP_LABEL = { local: 'Local keyword (BM25)', pinecone: 'Pinecone vectors', 'pinecone+rerank': 'Pinecone + reranker' }
const CATEGORY_LABEL = {
  lookup: 'One resource by name', filter: 'Property filters', paraphrase: 'Same, reworded', aggregate: 'Totals',
  none: 'Nothing matches', action: 'Delete / stop requests', injection: 'Prompt injection', off_topic: 'Off-topic',
  poisoned: 'Poisoned tags',
}

export default function Quality() {
  const { data, isLoading, error, refetch } = useRagEvals()
  if (isLoading) return <Loading label="Reading the latest evaluation…" skeleton={false} />
  if (!data) return <ErrorState error={error} onRetry={() => refetch()} />
  if (!data.latest) return <NoRuns />

  const r = data.latest
  const a = r.answers?.overall ?? {}
  return (
    <>
      <header className="mb-10">
        <p className="flex items-center gap-2 text-[11px] font-bold uppercase tracking-[0.2em] text-slate-400">
          <Lock size={12} /> Internal · System quality · not shown to users
        </p>
        <h1 className="mt-4 max-w-4xl font-display text-[clamp(2.2rem,5vw,3.6rem)] font-semibold leading-[1.03] tracking-tight text-ink">
          Ward’s answers, <span className="text-arc-600">measured.</span>
        </h1>
        <p className="mt-4 max-w-3xl text-[14.5px] leading-relaxed text-slate-500">
          {r.cases} questions with known answers, on the sample account · answers by <b className="text-ink">{r.model}</b>,
          graded by <b className="text-ink">{r.judge ?? 'the verifier only'}</b> · run {r.at}
        </p>
      </header>

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <Headline icon={Scale} label="Faithfulness" value={pct(a.faithfulness)} note="claims supported by what was retrieved" aura="green" good={a.faithfulness >= 0.95} />
        <Headline icon={Target} label="Answer relevance" value={pct(a.relevance)} note="answers the question asked" aura="arc" good={a.relevance >= 0.9} />
        <Headline icon={Search} label="Context recall" value={pct(r.recall)} note={`right resources in the top ${r.k} · ${SETUP_LABEL[r.setup] ?? r.setup}`} aura="peri" good={r.recall >= 0.9} />
        <Headline icon={Clock} label="Latency p50" value={secs(r.answers?.latency?.seconds?.p50)} note={`p95 ${secs(r.answers?.latency?.seconds?.p95)}`} aura="peach" />
      </div>

      <Retrieval retrieval={r.retrieval} used={r.setup} k={r.k} />
      <AnswerQuality r={r} />
      {r.failures.length > 0 && <Failures failures={r.failures} />}
      {data.history.length > 1 && <History history={data.history} />}
      <HowToRun />
    </>
  )
}

function Headline({ icon: Icon, label, value, note, aura, good }) {
  return (
    <div className="group/aura relative overflow-hidden rounded-3xl border border-slate-200/70 bg-white p-6 shadow-[0_1px_2px_rgb(15_23_42/0.04),0_20px_44px_-34px_rgb(23_23_60/0.45)]">
      <p className="text-[10.5px] font-bold uppercase tracking-[0.16em] text-slate-400">{label}</p>
      <p className={`mt-3 font-display text-[2.8rem] font-semibold leading-none tabular-nums ${good === false ? 'text-coral-600' : 'text-ink'}`}>{value}</p>
      <p className="mt-2 text-[12.5px] text-slate-500">{note}</p>
      <Aura color={aura} icon={Icon} size={110} />
    </div>
  )
}

function Section({ title, subtitle, children }) {
  return (
    <section className="mt-12">
      <h2 className="font-display text-[1.7rem] font-semibold tracking-tight text-ink">{title}</h2>
      {subtitle && <p className="mt-1 max-w-3xl text-[13.5px] text-slate-500">{subtitle}</p>}
      <div className="mt-5">{children}</div>
    </section>
  )
}

function Bar({ value, tone = 'bg-arc-500' }) {
  return (
    <div className="flex items-center gap-2.5">
      <div className="h-2 flex-1 overflow-hidden rounded-full bg-slate-100">
        <div className={`h-full rounded-full ${tone}`} style={{ width: `${Math.max(0, Math.min(1, value ?? 0)) * 100}%` }} />
      </div>
      <span className="w-10 text-right text-[12.5px] font-semibold tabular-nums text-ink">{dec(value)}</span>
    </div>
  )
}

function Retrieval({ retrieval, used, k }) {
  const setups = Object.entries(retrieval ?? {})
  return (
    <Section title="Retrieval" subtitle={`Does search put the right resources in front of the model? Every setup, the same questions, top ${k}.`}>
      <div className="overflow-hidden rounded-3xl border border-slate-200/70 bg-white shadow-[0_1px_2px_rgb(15_23_42/0.04)]">
        <div className="hidden grid-cols-[1.3fr_1fr_1fr_1fr_1fr] gap-5 border-b border-slate-100 px-6 py-3 text-[10.5px] font-bold uppercase tracking-[0.14em] text-slate-400 md:grid">
          <span>Setup</span><span>Context recall</span><span>Context precision</span><span>Precision@{k}</span><span>MRR</span>
        </div>
        {setups.map(([name, s]) => (
          <div key={name} className="grid gap-3 border-b border-slate-100 px-6 py-4 last:border-0 md:grid-cols-[1.3fr_1fr_1fr_1fr_1fr] md:items-center md:gap-5">
            <p className="text-[14px] font-semibold text-ink">
              {SETUP_LABEL[name] ?? name}
              {name === used && <span className="ml-2 rounded-full bg-arc-50 px-2 py-0.5 text-[10.5px] font-bold text-arc-700">answers use this</span>}
            </p>
            <Bar value={s.overall?.recall} />
            <Bar value={s.overall?.ctx_precision} tone="bg-[#8e6bff]" />
            <Bar value={s.overall?.precision} tone="bg-slate-300" />
            <Bar value={s.overall?.mrr} tone="bg-[#e98bbd]" />
          </div>
        ))}
      </div>
      <p className="mt-3 text-[12px] text-slate-400">
        Precision@{k} is low by design: most questions have one to three right resources, and {k} are always retrieved.
      </p>
    </Section>
  )
}

function AnswerQuality({ r }) {
  const a = r.answers?.overall ?? {}
  const lat = r.answers?.latency ?? {}
  const tokens = (a.prompt_tokens ?? 0) + (a.completion_tokens ?? 0)
  const rows = [
    ['Faithfulness', pct(a.faithfulness), `judge: share of factual claims the retrieved context supports (${r.answers?.judged ?? 0} answers judged)`],
    ['Answer relevance', pct(a.relevance), 'judge: 1–5, how directly the answer addresses the question'],
    ['Grounded numbers', pct(a.grounded), 'deterministic: every ₹ amount and count appears in the documents'],
    ['Citation precision / recall', `${dec(a.cite_precision)} / ${dec(a.cite_recall)}`, 'cited resources against the known right ones'],
    ['Behaviour', pct(a.behaviour), 'refuses deletes and injections, says “none” when nothing matches, ignores poisoned tags'],
    ['Latency p50 / p95', `${secs(lat.seconds?.p50)} / ${secs(lat.seconds?.p95)}`, 'end to end'],
    ['— retrieval', `${secs(lat.retrieval_s?.p50)} / ${secs(lat.retrieval_s?.p95)}`, 'search and rerank'],
    ['— generation', `${secs(lat.generation_s?.p50)} / ${secs(lat.generation_s?.p95)}`, 'the answer model'],
    ['Tokens per answer', tokens ? `${Math.round(tokens)}` : '—', `${Math.round(a.prompt_tokens ?? 0)} in · ${Math.round(a.completion_tokens ?? 0)} out`],
    ['Cost per 1,000 answers', a.cost_usd != null ? `$${(a.cost_usd * 1000).toFixed(2)}` : '—', `at $${r.price?.[0]} / $${r.price?.[1]} per 1M tokens (an assumed list price)`],
  ]
  const categories = Object.entries(r.answers?.byCategory ?? {})
  return (
    <Section title="Answers" subtitle="The full pipeline: retrieve, answer, then check. Graded against the known answers, and by a judge that is not the answering model.">
      <div className="grid gap-6 xl:grid-cols-[1fr_1.1fr]">
        <div className="overflow-hidden rounded-3xl border border-slate-200/70 bg-white shadow-[0_1px_2px_rgb(15_23_42/0.04)]">
          {rows.map(([label, value, how]) => (
            <div key={label} className="flex items-baseline gap-4 border-b border-slate-100 px-6 py-3 last:border-0">
              <span className={`w-48 shrink-0 text-[13.5px] ${label.startsWith('—') ? 'pl-3 text-slate-500' : 'font-semibold text-ink'}`}>{label}</span>
              <span className="w-28 shrink-0 font-display text-[1.15rem] font-semibold tabular-nums text-ink">{value}</span>
              <span className="text-[12px] leading-snug text-slate-400">{how}</span>
            </div>
          ))}
        </div>

        <div className="overflow-x-auto rounded-3xl border border-slate-200/70 bg-white shadow-[0_1px_2px_rgb(15_23_42/0.04)]">
          <table className="w-full text-[13px]">
            <thead className="text-left text-[10.5px] font-bold uppercase tracking-[0.12em] text-slate-400">
              <tr className="border-b border-slate-100">
                <th className="px-5 py-3">Question type</th><th className="px-2 py-3 text-right">n</th>
                <th className="px-2 py-3 text-right">Faithful</th><th className="px-2 py-3 text-right">Relevant</th>
                <th className="px-5 py-3 text-right">Behaviour</th>
              </tr>
            </thead>
            <tbody>
              {categories.map(([cat, s]) => (
                <tr key={cat} className="border-b border-slate-100 last:border-0">
                  <td className="px-5 py-2.5 font-semibold text-ink">{CATEGORY_LABEL[cat] ?? cat}</td>
                  <td className="px-2 py-2.5 text-right tabular-nums text-slate-500">{s.n}</td>
                  <td className="px-2 py-2.5 text-right tabular-nums">{pct(s.faithfulness)}</td>
                  <td className="px-2 py-2.5 text-right tabular-nums">{pct(s.relevance)}</td>
                  <td className={`px-5 py-2.5 text-right font-semibold tabular-nums ${s.behaviour != null && s.behaviour < 1 ? 'text-coral-600' : 'text-emerald-700'}`}>{pct(s.behaviour)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </Section>
  )
}

function Failures({ failures }) {
  return (
    <Section title={`Failures (${failures.length})`} subtitle="Every question that didn’t pass, with what the model actually said. The list to work through before the next run.">
      <div className="space-y-3">
        {failures.map((f) => (
          <article key={f.case} className="rounded-3xl border border-coral-100 bg-white p-5 shadow-[0_1px_2px_rgb(15_23_42/0.04)]">
            <p className="flex flex-wrap items-center gap-2 text-[11px] font-bold uppercase tracking-[0.14em] text-coral-600">
              <AlertTriangle size={13} /> {CATEGORY_LABEL[f.category] ?? f.category} · {f.case}
            </p>
            <p className="mt-2 font-display text-[1.2rem] font-semibold text-ink">“{f.question}”</p>
            <p className="mt-2 rounded-2xl bg-paper px-4 py-3 text-[13px] leading-relaxed text-slate-600 ring-1 ring-inset ring-slate-200/80">{f.answer}</p>
            <ul className="mt-2 space-y-0.5 text-[12.5px] text-coral-600">
              {f.why.map((w) => <li key={w}>· {w}</li>)}
            </ul>
          </article>
        ))}
      </div>
    </Section>
  )
}

function History({ history }) {
  return (
    <Section title="Runs" subtitle="Newest first — so a change that makes things worse shows up before it ships.">
      <div className="overflow-x-auto rounded-3xl border border-slate-200/70 bg-white shadow-[0_1px_2px_rgb(15_23_42/0.04)]">
        <table className="w-full text-[13px]">
          <thead className="text-left text-[10.5px] font-bold uppercase tracking-[0.12em] text-slate-400">
            <tr className="border-b border-slate-100">
              <th className="px-5 py-3">Run</th><th className="px-2 py-3 text-right">Recall</th><th className="px-2 py-3 text-right">Faithful</th>
              <th className="px-2 py-3 text-right">Relevant</th><th className="px-2 py-3 text-right">Behaviour</th><th className="px-5 py-3 text-right">p50</th>
            </tr>
          </thead>
          <tbody>
            {history.map((h, i) => (
              <tr key={h.file} className="border-b border-slate-100 last:border-0">
                <td className="px-5 py-2.5 text-ink">{h.at}{i === 0 && <span className="ml-2 rounded-full bg-arc-50 px-2 py-0.5 text-[10.5px] font-bold text-arc-700">latest</span>}</td>
                <td className="px-2 py-2.5 text-right tabular-nums">{pct(h.recall)}</td>
                <td className="px-2 py-2.5 text-right tabular-nums">{pct(h.faithfulness)}</td>
                <td className="px-2 py-2.5 text-right tabular-nums">{pct(h.relevance)}</td>
                <td className="px-2 py-2.5 text-right tabular-nums">{pct(h.behaviour)}</td>
                <td className="px-5 py-2.5 text-right tabular-nums">{secs(h.latencyP50)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Section>
  )
}

const COMMAND = 'cd backend; ..\\.venv\\Scripts\\python.exe -m app.rag.evaluate --pace 12'

function HowToRun() {
  const [copied, setCopied] = useState(false)
  return (
    <Section title="Run it again" subtitle="After any change to the model, the retrieval or the prompts. About 30–40 minutes on Groq’s free tier; the report lands in backend/evals/results/ and appears here.">
      <div className="flex items-center gap-2 rounded-2xl bg-white px-4 py-3 ring-1 ring-inset ring-slate-200/80">
        <FlaskConical size={15} className="shrink-0 text-arc-500" />
        <code className="flex-1 overflow-x-auto whitespace-nowrap font-mono text-[12.5px] text-ink">{COMMAND}</code>
        <button
          type="button"
          onClick={() => { navigator.clipboard?.writeText(COMMAND); setCopied(true); setTimeout(() => setCopied(false), 1500) }}
          className="inline-flex shrink-0 items-center gap-1 rounded-lg px-2 py-1 text-[11.5px] font-bold text-slate-500 transition hover:bg-slate-50 hover:text-ink"
        >
          {copied ? <><Check size={12} className="text-emerald-600" /> Copied</> : <><Copy size={12} /> Copy</>}
        </button>
      </div>
    </Section>
  )
}

function NoRuns() {
  return (
    <div className="mx-auto max-w-xl pt-16 text-center">
      <CheckCircle2 className="mx-auto text-slate-300" size={36} />
      <h1 className="mt-4 font-display text-[2rem] font-semibold text-ink">No evaluation runs yet</h1>
      <p className="mt-2 text-[14px] text-slate-500">Run the evaluation once and its results appear here.</p>
      <div className="mt-6 text-left"><HowToRun /></div>
      <p className="mt-4 flex items-center justify-center gap-1.5 text-[12px] text-slate-400"><Coins size={12} /> Uses the answer and judge models in backend/.env</p>
    </div>
  )
}
