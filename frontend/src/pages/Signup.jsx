import { useState } from 'react'
import { Link, Navigate, useNavigate, useSearchParams } from 'react-router-dom'
import AuthShell, { Blank, FormError, Parsed, Sentence, Submit } from '../components/AuthShell.jsx'
import { useAuthStatus, useMe, useSignUp } from '../auth.jsx'
import { EMAIL_OK, safeNext } from './Login.jsx'

// The same rules the backend enforces (app/auth.py: password_problem), shown as you type.
const RULES = [
  ['At least 8 characters', (p) => p.length >= 8],
  ['Letters and a number or symbol', (p) => /[a-z]/i.test(p) && /[^a-z]/i.test(p)],
]

export default function Signup() {
  const [params] = useSearchParams()
  const next = safeNext(params.get('next'))
  const navigate = useNavigate()
  const me = useMe()
  const status = useAuthStatus()
  const signUp = useSignUp()
  const [name, setName] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')

  if (me.data) return <Navigate to={next} replace />

  const met = RULES.map(([, test]) => test(password))
  const closed = status.data && !status.data.signupOpen

  const submit = (e) => {
    e.preventDefault()
    signUp.mutate({ name, email, password }, { onSuccess: () => navigate(next, { replace: true }) })
  }

  if (closed) {
    return (
      <AuthShell title="Sign-up is closed." subtitle="This Ward only lets an administrator add people. Ask yours for an account."
                 footer={<>Already have one? <Link to="/login" className="font-bold text-arc-700 hover:underline">Sign in</Link></>} />
    )
  }

  return (
    <AuthShell
      mode="signup"
      title="Create your account"
    >
      <form onSubmit={submit} noValidate>
        <Sentence>
          Hi, I’m
          <Blank label="Your name" value={name} onChange={(e) => setName(e.target.value)} placeholder="your name"
                 autoComplete="name" autoFocus valid={name.trim().length > 1} />
          . Reach me at
          <Blank label="Email" type="email" value={email} onChange={(e) => setEmail(e.target.value)} placeholder="you@company.com"
                 autoComplete="email" valid={EMAIL_OK(email)} />
          , and I’ll keep it safe with
          <Blank label="Password" type="password" value={password} onChange={(e) => setPassword(e.target.value)} placeholder="a password"
                 autoComplete="new-password" valid={met.every(Boolean)} peek />
          .
        </Sentence>
        <Parsed
          ready={name.trim().length > 1 && EMAIL_OK(email) && met.every(Boolean)}
          waitingFor={name.trim().length < 2 ? 'your name' : !EMAIL_OK(email) ? 'your email' : 'a stronger password'}
          items={[
            ['name', name.trim() || '—', name.trim().length > 1],
            ['email', EMAIL_OK(email) ? email.trim().toLowerCase() : '—', EMAIL_OK(email)],
            ...RULES.map(([label], i) => [met[i] ? '✓' : '·', label.toLowerCase(), met[i]]),
          ]}
        />
        <div className="mt-6 space-y-4">
          <FormError>{signUp.error?.message}</FormError>
          <Submit busy={signUp.isPending}>{signUp.isPending ? 'Creating your account…' : 'Create account'}</Submit>
        </div>
      </form>
    </AuthShell>
  )
}
