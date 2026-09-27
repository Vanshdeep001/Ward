import { useState } from 'react'
import { AlertTriangle, Check, Copy, Download, ExternalLink, Lock, ShieldCheck, Terminal } from 'lucide-react'
import { useConnection, useConnectAccount, useCreateAccount, useDisconnectAccount, useSetupStatus } from '../api/hooks.js'
import { api } from '../api/client.js'
import { Button, Loading, PageHeader, Panel } from '../components/ui.jsx'

/* Connecting an account, in the three steps the backend actually has:
   name it → deploy a role → hand back the ARN. Ward issues the ExternalId and bakes it into the
   template, so nothing secret is ever typed, and the only thing the user copies is a public ARN. */

export default function Connect() {
  const { connected, accounts, isLoading, usingMocks } = useConnection()
  const setup = useSetupStatus()
  const [pending, setPending] = useState(null) // { account, onboarding }
  const create = useCreateAccount()
  const connect = useConnectAccount()
  const disconnect = useDisconnectAccount()
  const [roleArn, setRoleArn] = useState('')

  if (usingMocks) return <MocksNotice />
  if (isLoading) return <Loading label="Checking your connection…" />
  if (connected) return <ConnectedState account={connected} onDisconnect={() => disconnect.mutate(connected.id)} busy={disconnect.isPending} />

  async function startOnboarding(form) {
    const account = await create.mutateAsync(form)
    const onboarding = await api.onboarding(account.id)
    setPending({ account, onboarding })
  }

  return (
    <>
      <PageHeader
        title="Connect your AWS account"
        subtitle="Ward reads your account through a role you create — it never asks for access keys, and it is never granted permission to change anything."
      />

      <WardReadiness setup={setup} />

      <ol className="space-y-4">
        <Step n={1} title="Tell Ward about the account" done={!!pending}>
          {pending ? (
            <p className="text-sm text-slate-600">
              <span className="font-semibold text-ink">{pending.account.label}</span> · {pending.account.region} ·
              budget {Number(pending.account.budgetInr).toLocaleString('en-IN')}
            </p>
          ) : (
            <AccountForm onSubmit={startOnboarding} busy={create.isPending} error={create.error} />
          )}
        </Step>

        <Step n={2} title="Create the read-only role" disabled={!pending}>
          {pending && <TemplateStep onboarding={pending.onboarding} />}
        </Step>

        <Step n={3} title="Hand the role back to Ward" disabled={!pending}>
          {pending && (
            <form
              className="space-y-3"
              onSubmit={(e) => {
                e.preventDefault()
                connect.mutate({ id: pending.account.id, roleArn: roleArn.trim() })
              }}
            >
              <label className="block text-sm text-slate-600">
                Paste the <span className="font-mono text-[12px] text-ink">RoleArn</span> from the stack’s Outputs tab.
              </label>
              <div className="flex flex-wrap gap-2">
                <input
                  value={roleArn}
                  onChange={(e) => setRoleArn(e.target.value)}
                  placeholder="arn:aws:iam::123456789012:role/WardReadOnly"
                  className="min-w-0 flex-1 rounded-xl border border-slate-200 px-3 py-2.5 font-mono text-[12.5px] outline-none focus:border-arc-500"
                />
                <Button type="submit" disabled={!roleArn.trim() || connect.isPending} className="rounded-xl px-4 py-2.5">
                  {connect.isPending ? 'Verifying…' : 'Verify and connect'}
                </Button>
              </div>
              {connect.error && (
                <p className="flex items-start gap-2 rounded-xl bg-coral-50 p-3 text-[13px] text-coral-600">
                  <AlertTriangle size={15} className="mt-px shrink-0" />
                  {connect.error.message}
                </p>
              )}
              <p className="text-[12px] text-slate-500">
                Ward assumes the role once to check it works, and records which account it landed in. A role it
                cannot assume is rejected rather than saved.
              </p>
            </form>
          )}
        </Step>
      </ol>

      {accounts.length > 0 && !connected && (
        <p className="mt-6 text-[12.5px] text-slate-500">
          {accounts.length} account{accounts.length > 1 ? 's' : ''} pending. Ward keeps running on demo data until one connects.
        </p>
      )}
    </>
  )
}

function AccountForm({ onSubmit, busy, error }) {
  const [label, setLabel] = useState('')
  const [region, setRegion] = useState('ap-south-1')
  const [budget, setBudget] = useState('30000')
  const [invalid, setInvalid] = useState(null)

  return (
    <form
      className="grid gap-3 sm:grid-cols-[1.4fr_1fr_1fr_auto]"
      onSubmit={(e) => {
        e.preventDefault()
        // Blank means "use Ward's default"; only a number that is actually zero or negative is wrong.
        const amount = budget.trim() === '' ? undefined : Number(budget)
        if (amount !== undefined && !(amount > 0)) {
          setInvalid('Budget must be more than ₹0 — or leave it blank to use the default.')
          return
        }
        if (!region.trim()) {
          setInvalid('Region is required, e.g. ap-south-1.')
          return
        }
        setInvalid(null)
        onSubmit({ label: label.trim() || 'My AWS account', region: region.trim(), budget_inr: amount })
      }}
    >
      <Field label="Name">
        <input value={label} onChange={(e) => setLabel(e.target.value)} placeholder="Lab account" className={inputClass} />
      </Field>
      <Field label="Region">
        <input value={region} onChange={(e) => setRegion(e.target.value)} className={`${inputClass} font-mono text-[12.5px]`} />
      </Field>
      <Field label="Monthly budget (₹)">
        <input type="number" min="1" inputMode="numeric" placeholder="30000 (default)" value={budget} onChange={(e) => setBudget(e.target.value)} className={`${inputClass} tabular-nums`} />
      </Field>
      <div className="flex items-end">
        <Button type="submit" disabled={busy} className="w-full rounded-xl px-4 py-2.5">
          {busy ? 'Starting…' : 'Continue'}
        </Button>
      </div>
      {(invalid || error) && <p className="text-[13px] text-coral-600 sm:col-span-4">{invalid ?? error.message}</p>}
    </form>
  )
}

function TemplateStep({ onboarding }) {
  const [route, setRoute] = useState('console')

  return (
    <div className="space-y-4">
      {!onboarding.ready && (
        <p className="flex items-start gap-2 rounded-xl bg-amber-50 p-3 text-[13px] text-amber-800">
          <AlertTriangle size={15} className="mt-px shrink-0" />
          Ward has no identity for this template to trust yet, so the WardPrincipal field is blank. Fix the check
          at the top of this page first — deploying now would fail.
        </p>
      )}

      <p className="text-sm leading-relaxed text-slate-600">
        Deploy this CloudFormation stack in the account you want watched. It creates a single role called{' '}
        <span className="font-mono text-[12.5px] text-ink">WardReadOnly</span>. Both parameters are already filled
        in, so you don’t have to type anything.
      </p>

      <div className="flex flex-wrap gap-2">
        <Button variant="brand" className="rounded-xl px-4 py-2.5" onClick={() => download(onboarding.template, `${onboarding.stack_name}.yaml`)}>
          <Download size={14} /> Download {onboarding.stack_name}.yaml
        </Button>
        {onboarding.quick_create_url && (
          <a href={onboarding.quick_create_url} target="_blank" rel="noreferrer">
            <Button variant="secondary" className="rounded-xl px-4 py-2.5">
              Open in the AWS console <ExternalLink size={14} />
            </Button>
          </a>
        )}
        <CopyButton text={onboarding.template} label="Copy the template" />
      </div>

      {/* Two routes to the same RoleArn. The console needs no tools; the CLI is two commands. */}
      <div className="rounded-2xl border border-slate-200 bg-white">
        <div className="flex gap-1 border-b border-slate-100 p-1.5">
          {[['console', 'In the AWS console'], ['cli', 'With the AWS CLI']].map(([key, label]) => (
            <button
              key={key}
              type="button"
              onClick={() => setRoute(key)}
              className={`flex-1 rounded-xl px-3 py-2 text-[12.5px] font-bold transition ${
                route === key ? 'bg-ink text-white' : 'text-slate-500 hover:bg-slate-50 hover:text-ink'
              }`}
            >
              {label}
            </button>
          ))}
        </div>

        {route === 'console' ? (
          <ol className="space-y-3 p-4 text-[13px] leading-relaxed text-slate-600">
            <Guide n={1}>
              Sign in to the account you want watched, and open{' '}
              <a className="font-semibold text-arc-700 underline-offset-2 hover:underline" href="https://console.aws.amazon.com/cloudformation/home#/stacks/create" target="_blank" rel="noreferrer">
                CloudFormation → Create stack
              </a>.
            </Guide>
            <Guide n={2}>
              Choose <b>Choose an existing template</b> → <b>Upload a template file</b>, pick the{' '}
              <span className="font-mono text-[12px]">{onboarding.stack_name}.yaml</span> you just downloaded, then <b>Next</b>.
            </Guide>
            <Guide n={3}>
              Stack name: <span className="font-mono text-[12px]">{onboarding.stack_name}</span>. Leave both parameters as they
              are — they already hold your ExternalId and Ward’s principal. <b>Next</b>, then <b>Next</b> again.
            </Guide>
            <Guide n={4}>
              At the bottom, tick <b>“I acknowledge that AWS CloudFormation might create IAM resources with custom names”</b>
              — the role has a fixed name, WardReadOnly. Then <b>Submit</b>.
            </Guide>
            <Guide n={5}>
              Wait about a minute, until the status reads <span className="font-mono text-[12px] text-emerald-700">CREATE_COMPLETE</span>.
            </Guide>
            <Guide n={6}>
              Open the <b>Outputs</b> tab. Copy the value next to <span className="font-mono text-[12px]">RoleArn</span> — it looks like{' '}
              <span className="font-mono text-[12px] text-ink">arn:aws:iam::123456789012:role/WardReadOnly</span> — and paste it in step 3.
            </Guide>
          </ol>
        ) : (
          <div className="space-y-3 p-4 text-[13px] leading-relaxed text-slate-600">
            <p>From the folder you saved <span className="font-mono text-[12px]">{onboarding.stack_name}.yaml</span> in, signed in to the account you want watched:</p>
            {onboarding.cli.map((line, i) => (
              <div key={line} className="flex items-start gap-2">
                <span className="mt-2.5 text-[11px] font-bold text-slate-400">{i + 1}</span>
                <pre className="scroll-quiet min-w-0 flex-1 overflow-x-auto rounded-xl bg-ink p-3 font-mono text-[11.5px] text-white/85">{line}</pre>
                <CopyIcon text={line} />
              </div>
            ))}
            <p className="flex items-start gap-2 text-[12px] text-slate-500">
              <Terminal size={13} className="mt-px shrink-0" />
              The second command prints the RoleArn directly. <span className="font-mono">CAPABILITY_NAMED_IAM</span> is the CLI’s
              version of the console’s acknowledgement tick.
            </p>
          </div>
        )}
      </div>

      <details className="group rounded-2xl border border-slate-200 bg-white">
        <summary className="cursor-pointer list-none px-4 py-3 text-[13px] font-semibold text-slate-700 group-open:border-b group-open:border-slate-100">
          What this grants — {onboarding.permissions.length} read-only permissions
        </summary>
        <div className="space-y-3 p-4">
          <ul className="flex flex-wrap gap-1.5">
            {onboarding.permissions.map((p) => (
              <li key={p} className="rounded-lg bg-slate-100 px-2 py-1 font-mono text-[11px] text-slate-600">{p}</li>
            ))}
          </ul>
          <p className="flex items-start gap-2 rounded-xl bg-emerald-50 p-3 text-[12.5px] text-emerald-800">
            <ShieldCheck size={15} className="mt-px shrink-0" />
            No Delete, no Terminate, no iam:*. Ward cannot change anything in your account, by design.
          </p>
          <pre className="scroll-quiet max-h-64 overflow-auto rounded-xl bg-ink p-4 font-mono text-[11px] leading-relaxed text-white/85">
            {onboarding.template}
          </pre>
        </div>
      </details>

      <p className="flex items-start gap-2 text-[12px] text-slate-500">
        <Lock size={13} className="mt-px shrink-0" />
        The template carries an ExternalId Ward generated for this account. It is what stops anyone else from
        pointing Ward at an account you did not agree to watch.
      </p>
    </div>
  )
}

function ConnectedState({ account, onDisconnect, busy }) {
  return (
    <>
      <PageHeader title="Your AWS account" subtitle="Ward is reading this account through an assumed role. Credentials are temporary and never stored." />
      <Panel eyebrow="Connected" title={account.label}>
        <dl className="divide-y divide-slate-100">
          <Row label="AWS account" value={<span className="font-mono text-[12.5px]">{account.awsAccountId}</span>} />
          <Row label="Role" value={<span className="font-mono text-[11.5px] break-all">{account.roleArn}</span>} />
          <Row label="Region" value={account.region} />
          <Row label="Budget" value={`₹${Number(account.budgetInr).toLocaleString('en-IN')}/month`} />
          <Row label="Connected" value={new Date(account.connectedAt).toLocaleString('en-IN')} />
          <Row label="Last sweep" value={account.lastSweepAt ? new Date(account.lastSweepAt).toLocaleString('en-IN') : 'waiting for the next one'} />
        </dl>
        <div className="flex items-center justify-between gap-4 border-t border-slate-100 bg-slate-50/60 px-5 py-3.5">
          <p className="text-[12px] text-slate-500">Disconnecting stops the sweeps and deletes the stored role. Your AWS role stays until you delete the stack.</p>
          <Button variant="secondary" onClick={onDisconnect} disabled={busy} className="shrink-0 rounded-xl">
            {busy ? 'Disconnecting…' : 'Disconnect'}
          </Button>
        </div>
      </Panel>
    </>
  )
}

function MocksNotice() {
  return (
    <>
      <PageHeader title="Connect your AWS account" subtitle="The frontend is running on mock data, so there is no backend to connect to." />
      <Panel eyebrow="Configuration" title="Point the app at the API first">
        <div className="space-y-3 p-5 text-sm leading-relaxed text-slate-600">
          <p>Create <span className="font-mono text-[12.5px] text-ink">frontend/.env.local</span> with:</p>
          <pre className="rounded-xl bg-ink p-4 font-mono text-[12px] text-white/85">VITE_USE_MOCKS=false</pre>
          <p>Then restart the dev server. Vite proxies <span className="font-mono text-[12.5px]">/api</span> to the backend on port 8000.</p>
        </div>
      </Panel>
    </>
  )
}

/* Step zero: Ward's own side. The customer's role trusts Ward's identity, so Ward must *have* one —
   AWS credentials on the machine running the backend. Checked first, because every later step fails
   without it and the failure would otherwise surface at step 3, far from its cause. */
function WardReadiness({ setup }) {
  if (setup.isLoading) {
    return <p className="mb-4 text-[12.5px] text-slate-400">Checking Ward’s own AWS credentials…</p>
  }
  const s = setup.data
  if (s?.ready) {
    return (
      <div className="mb-4 flex flex-wrap items-center gap-3 rounded-2xl border border-emerald-100 bg-emerald-50/60 px-4 py-3">
        <span className="grid h-7 w-7 shrink-0 place-items-center rounded-full bg-emerald-500 text-white"><Check size={14} strokeWidth={3} /></span>
        <p className="min-w-0 flex-1 text-[13px] text-emerald-900">
          <span className="font-semibold">Ward is ready.</span> Your role will trust{' '}
          <span className="break-all font-mono text-[11.5px]">{s.principal}</span>
          <span className="text-emerald-700/70"> ({s.principalSource === 'detected' ? 'detected from Ward’s credentials' : 'set by WARD_PRINCIPAL'})</span>
        </p>
      </div>
    )
  }

  return (
    <div className="mb-4 rounded-3xl border border-amber-200 bg-amber-50/50 p-5">
      <div className="mb-3 flex items-center gap-3">
        <span className="grid h-7 w-7 shrink-0 place-items-center rounded-full bg-amber-400 text-white"><AlertTriangle size={14} /></span>
        <h2 className="font-display text-[1.15rem] font-semibold text-ink">First, give Ward an AWS identity</h2>
      </div>
      <div className="space-y-3 text-[13px] leading-relaxed text-slate-700">
        <p>
          Your role is going to trust Ward, so Ward needs an AWS identity of its own — credentials on the machine running
          the backend. This is separate from the account being watched, and it needs no permissions except
          <span className="font-mono text-[12px]"> sts:AssumeRole</span>.
        </p>
        <ol className="space-y-2">
          <Guide n={1}>
            In the AWS console, go to <b>IAM → Users → Create user</b>. Call it <span className="font-mono text-[12px]">ward</span>.
            Don’t give it console access.
          </Guide>
          <Guide n={2}>
            Attach an inline policy that allows only <span className="font-mono text-[12px]">sts:AssumeRole</span> on{' '}
            <span className="font-mono text-[12px]">arn:aws:iam::*:role/WardReadOnly</span>.
          </Guide>
          <Guide n={3}>
            Under <b>Security credentials → Create access key</b>, pick <b>Application running outside AWS</b>. On the
            backend machine, run <span className="font-mono text-[12px]">aws configure</span> and paste the key in.
          </Guide>
          <Guide n={4}>
            Restart the backend and reload this page. Ward detects the new identity by itself — no setting needed.
          </Guide>
        </ol>
        <p className="text-[12px] text-slate-500">
          These keys belong to Ward, on your own machine, and can do nothing except assume WardReadOnly. The account being
          watched still never hands over keys of any kind.
        </p>
        {s?.error && <p className="rounded-xl bg-white/70 p-3 font-mono text-[11.5px] text-amber-900">{s.error}</p>}
        {setup.isError && <p className="rounded-xl bg-white/70 p-3 text-[12px] text-amber-900">{setup.error.message}</p>}
      </div>
    </div>
  )
}

/* ── pieces ─────────────────────────────────────────────────────────────── */

function Guide({ n, children }) {
  return (
    <li className="flex gap-3">
      <span className="grid h-5 w-5 shrink-0 place-items-center rounded-full bg-slate-100 text-[10.5px] font-bold text-slate-500">{n}</span>
      <span className="min-w-0">{children}</span>
    </li>
  )
}

function CopyIcon({ text }) {
  const [copied, setCopied] = useState(false)
  return (
    <button
      type="button"
      aria-label="Copy command"
      onClick={async () => {
        await navigator.clipboard.writeText(text)
        setCopied(true)
        setTimeout(() => setCopied(false), 1500)
      }}
      className="mt-1.5 grid h-8 w-8 shrink-0 place-items-center rounded-lg border border-slate-200 text-slate-500 transition hover:border-arc-200 hover:text-arc-700"
    >
      {copied ? <Check size={13} /> : <Copy size={13} />}
    </button>
  )
}

// Save the template as a file, so the console's "Upload a template file" has something to pick.
function download(text, filename) {
  const url = URL.createObjectURL(new Blob([text], { type: 'text/yaml' }))
  const a = Object.assign(document.createElement('a'), { href: url, download: filename })
  document.body.appendChild(a)
  a.click()
  a.remove()
  URL.revokeObjectURL(url)
}

const inputClass = 'w-full rounded-xl border border-slate-200 px-3 py-2.5 text-sm outline-none focus:border-arc-500'

function Field({ label, children }) {
  return (
    <label className="block">
      <span className="mb-1.5 block text-[11px] font-bold uppercase tracking-[0.12em] text-slate-400">{label}</span>
      {children}
    </label>
  )
}

function Step({ n, title, children, done, disabled }) {
  return (
    <li className={`rounded-3xl border bg-white p-5 transition ${disabled ? 'border-slate-200/70 opacity-55' : 'border-slate-200'}`}>
      <div className="mb-4 flex items-center gap-3">
        <span className={`grid h-7 w-7 shrink-0 place-items-center rounded-full text-[12px] font-bold ${
          done ? 'bg-emerald-500 text-white' : disabled ? 'bg-slate-100 text-slate-400' : 'bg-ink text-white'
        }`}>
          {done ? <Check size={14} strokeWidth={3} /> : n}
        </span>
        <h2 className="font-display text-[1.15rem] font-semibold text-ink">{title}</h2>
      </div>
      {children}
    </li>
  )
}

function Row({ label, value }) {
  return (
    <div className="flex flex-wrap items-baseline justify-between gap-3 px-5 py-3 text-sm">
      <dt className="text-slate-500">{label}</dt>
      <dd className="text-right text-ink">{value}</dd>
    </div>
  )
}

function CopyButton({ text, label }) {
  const [copied, setCopied] = useState(false)
  return (
    <Button
      variant="secondary"
      className="rounded-xl px-4 py-2.5"
      onClick={async () => {
        await navigator.clipboard.writeText(text)
        setCopied(true)
        setTimeout(() => setCopied(false), 1800)
      }}
    >
      {copied ? <><Check size={14} /> Copied</> : <><Copy size={14} /> {label}</>}
    </Button>
  )
}

