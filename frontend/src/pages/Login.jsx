import { useState } from 'react'
import { Navigate, useNavigate, useSearchParams } from 'react-router-dom'
import { Info } from 'lucide-react'
import AuthShell, { Blank, FormError, Parsed, Sentence, Submit } from '../components/AuthShell.jsx'
import { useMe, useSignIn } from '../auth.jsx'

// Only paths inside the app — never an address someone slipped into ?next= to bounce people off-site.
export const EMAIL_OK = (v) => /^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(v.trim())

export const safeNext = (value) => (value && value.startsWith('/') && !value.startsWith('//') ? value : '/app')

export default function Login() {
  const [params] = useSearchParams()
  const next = safeNext(params.get('next'))
  const navigate = useNavigate()
  const me = useMe()
  const signIn = useSignIn()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')

  if (me.data) return <Navigate to={next} replace />

  const submit = (e) => {
    e.preventDefault()
    signIn.mutate({ email, password }, { onSuccess: () => navigate(next, { replace: true }) })
  }

  return (
    <AuthShell mode="login" title="Welcome back">
      {params.get('expired') && (
        <p className="mb-5 flex items-start gap-2 rounded-2xl bg-arc-50 px-4 py-3 text-[13px] text-arc-800 ring-1 ring-inset ring-arc-100">
          <Info size={15} className="mt-0.5 shrink-0" /> Your session ended. Sign in again to carry on where you were.
        </p>
      )}

      <form onSubmit={submit} noValidate>
        <Sentence>
          I’m
          <Blank label="Email" type="email" value={email} onChange={(e) => setEmail(e.target.value)} placeholder="you@company.com"
                 autoComplete="email" autoFocus valid={EMAIL_OK(email)} />
          , and my password is
          <Blank label="Password" type="password" value={password} onChange={(e) => setPassword(e.target.value)} placeholder="········"
                 autoComplete="current-password" peek />
          .
        </Sentence>
        <Parsed
          ready={EMAIL_OK(email) && password.length > 0}
          waitingFor={!EMAIL_OK(email) ? 'your email' : 'your password'}
          items={[
            ['identity', EMAIL_OK(email) ? email.trim().toLowerCase() : '—', EMAIL_OK(email)],
            ['secret', password ? `${password.length} characters` : '—', password.length > 0],
          ]}
        />
        <div className="mt-6 space-y-4">
          <FormError>{signIn.error?.message}</FormError>
          <Submit busy={signIn.isPending}>{signIn.isPending ? 'Signing in…' : 'Sign in'}</Submit>
        </div>
      </form>
    </AuthShell>
  )
}
