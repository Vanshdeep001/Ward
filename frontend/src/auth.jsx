import { useEffect } from 'react'
import { Link, Navigate, Outlet, useLocation, useNavigate } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ArrowRight, Lock } from 'lucide-react'
import { api } from './api/client.js'
import { ErrorState, isUnreachable, WardMark } from './components/ui.jsx'

/* Who is signed in, and the gates in front of the app.

   The session lives in an HttpOnly cookie this code can't read; the backend is the only judge. `useMe`
   asks it (GET /auth/me). A 401 anywhere — the session expired, or was ended elsewhere — fires
   'ward:signed-out' from the API client, and the gate sends the person to sign in, remembering where
   they were so they come straight back. */

export const useMe = () =>
  useQuery({ queryKey: ['me'], queryFn: api.me, retry: false, staleTime: 5 * 60_000 })

export const useAuthStatus = () => useQuery({ queryKey: ['auth-status'], queryFn: api.authStatus, staleTime: 60_000 })

function useSignedIn() {
  const qc = useQueryClient()
  return (user) => {
    qc.removeQueries({ predicate: (q) => q.queryKey[0] !== 'me' }) // nothing cached from a previous person
    qc.setQueryData(['me'], user)
  }
}

export function useSignIn() {
  const done = useSignedIn()
  return useMutation({ mutationFn: ({ email, password }) => api.login(email, password), onSuccess: done })
}

export function useSignUp() {
  const done = useSignedIn()
  return useMutation({ mutationFn: ({ name, email, password }) => api.signup(name, email, password), onSuccess: done })
}

export function useSignOut() {
  const qc = useQueryClient()
  const navigate = useNavigate()
  return useMutation({
    mutationFn: api.logout,
    onSettled: () => {
      qc.clear()
      qc.setQueryData(['me'], null)
      navigate('/login', { replace: true })
    },
  })
}

const initials = (name = '') => name.trim().split(/\s+/).slice(0, 2).map((w) => w[0]?.toUpperCase() ?? '').join('') || '?'
export { initials }

// Every app page sits behind this. Signed out → the sign-in page, then back here.
export function RequireAuth() {
  const me = useMe()
  const location = useLocation()
  const navigate = useNavigate()
  const qc = useQueryClient()
  const next = encodeURIComponent(location.pathname + location.search)

  useEffect(() => {
    const signedOut = () => {
      qc.setQueryData(['me'], null)
      navigate(`/login?next=${next}&expired=1`, { replace: true })
    }
    window.addEventListener('ward:signed-out', signedOut)
    return () => window.removeEventListener('ward:signed-out', signedOut)
  }, [qc, navigate, next])

  if (me.isLoading) return <Gate />
  if (me.error && isUnreachable(me.error)) {
    return <div className="min-h-screen bg-paper px-4"><ErrorState error={me.error} onRetry={() => me.refetch()} /></div>
  }
  if (!me.data) return <Navigate to={`/login?next=${next}`} replace />
  return <Outlet />
}

// Internal pages: admins only. The backend refuses the data regardless (403); this just explains it.
export function RequireAdmin() {
  const { data: user } = useMe()
  if (user?.role === 'admin') return <Outlet />
  return (
    <div className="mx-auto max-w-lg pt-20 text-center">
      <span className="mx-auto grid h-16 w-16 place-items-center rounded-full bg-white text-slate-400 shadow-[0_16px_32px_-14px_rgb(23_23_60/0.4)]">
        <Lock size={24} />
      </span>
      <h1 className="mt-6 font-display text-[2rem] font-semibold tracking-tight text-ink">For administrators</h1>
      <p className="mt-2 text-[14.5px] text-slate-500">This page shows how Ward itself performs. Ask an administrator if you need it.</p>
      <Link to="/app" className="mt-6 inline-flex items-center gap-1.5 rounded-full bg-ink px-4 py-2 text-[13.5px] font-bold text-white hover:bg-black">
        Back to your account <ArrowRight size={14} />
      </Link>
    </div>
  )
}

// While Ward checks who you are: the shield, nothing else — it's a fraction of a second.
function Gate() {
  return (
    <div className="grid min-h-screen place-items-center bg-paper">
      <span className="animate-pulse"><WardMark size={40} /></span>
    </div>
  )
}
