import { mock } from './mock/engine.js'

// Mock engine by default. Set VITE_USE_MOCKS=false to talk to the FastAPI backend via the /api proxy.
export const USE_MOCKS = import.meta.env.VITE_USE_MOCKS !== 'false'
const BASE = import.meta.env.VITE_API_URL ?? '/api'

// The access token lives 15 minutes; the refresh token a week. When a request comes back 401 the access
// token has most likely just expired: swap the refresh token for a new pair (POST /auth/refresh) and try
// again, once. Requests that fail together share one refresh — rotating the refresh token twice at once
// would look like a stolen token and end the sign-in.
let refreshing = null
function refreshSession() {
  refreshing ??= fetch(`${BASE}/auth/refresh`, { method: 'POST', credentials: 'include' })
    .then((r) => r.ok)
    .catch(() => false)
    .finally(() => setTimeout(() => { refreshing = null }, 0))
  return refreshing
}

const NO_RETRY = ['/auth/login', '/auth/signup', '/auth/refresh', '/auth/logout']

async function http(method, path, body, retried = false) {
  const res = await fetch(`${BASE}${path}`, {
    method,
    headers: body ? { 'Content-Type': 'application/json' } : undefined,
    body: body ? JSON.stringify(body) : undefined,
    credentials: 'include', // the access and refresh cookies (HttpOnly — this code never sees them)
  })
  if (res.status === 401 && !retried && !NO_RETRY.includes(path)) {
    if (await refreshSession()) return http(method, path, body, true)
    // The week is up, or this sign-in was ended: tell the app, so it can go to the sign-in page.
    // /auth calls report their own errors on the form instead.
    if (!path.startsWith('/auth/')) window.dispatchEvent(new Event('ward:signed-out'))
  }
  if (!res.ok) {
    const body = await res.text().catch(() => '')
    // With the backend down, Vite's dev proxy answers for it: an empty 500. A real backend error always has
    // a body, so an empty one means nothing answered — say that, so the page can say "start the server".
    if (res.status >= 500 && !body.trim()) {
      throw Object.assign(new Error(`Ward’s server is not reachable (${method} ${path} got no response)`), { status: res.status, unreachable: true })
    }
    // FastAPI puts the reason in `detail`; surface it so the UI can show why, not just that it failed.
    let detail = null
    try {
      detail = JSON.parse(body)
    } catch {
      detail = null
    }
    const reason = describe(detail?.detail) ?? `${method} ${path} → ${res.status}`
    throw Object.assign(new Error(reason), { status: res.status, detail: detail?.detail })
  }
  return res.status === 204 ? null : res.json()
}

// FastAPI's `detail` is a string for errors we raise, and a list of field errors for validation
// failures (422). Turn the list into a sentence naming the field, e.g. "budget_inr: must be greater than 0".
function describe(detail) {
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail) && detail.length) {
    return detail
      .map((e) => `${(e.loc ?? []).filter((p) => p !== 'body').join('.') || 'request'}: ${String(e.msg ?? '').replace(/^Input should be /, 'must be ')}`)
      .join('; ')
  }
  if (detail && typeof detail.message === 'string') return detail.message
  return null
}

const pick = (mockCall, method, path, body) => (USE_MOCKS ? mockCall() : http(method, path, body))

// The mock engine has no people; in mock mode everyone is a demo admin.
const DEMO_USER = { id: 'demo', email: 'demo@ward.local', name: 'Demo', role: 'admin' }

export const api = {
  // Sign-in. No mocks beyond "signed in as the demo user": there is nothing to check without a backend.
  me: () => (USE_MOCKS ? Promise.resolve(DEMO_USER) : http('GET', '/auth/me')),
  authStatus: () => (USE_MOCKS ? Promise.resolve({ hasUsers: true, signupOpen: true }) : http('GET', '/auth/status')),
  login: (email, password) => (USE_MOCKS ? Promise.resolve(DEMO_USER) : http('POST', '/auth/login', { email, password })),
  signup: (name, email, password) => (USE_MOCKS ? Promise.resolve(DEMO_USER) : http('POST', '/auth/signup', { name, email, password })),
  logout: () => (USE_MOCKS ? Promise.resolve(null) : http('POST', '/auth/logout')),

  // Accounts have no mock: connecting is only meaningful against the real backend.
  accounts: () => (USE_MOCKS ? Promise.resolve({ items: [] }) : http('GET', '/accounts')),
  setupStatus: () => http('GET', '/accounts/setup'),
  createAccount: (body) => http('POST', '/accounts', body),
  onboarding: (id) => http('GET', `/accounts/${id}/onboarding`),
  connectAccount: (id, roleArn) => http('POST', `/accounts/${id}/connect`, { role_arn: roleArn }),
  disconnectAccount: (id) => http('DELETE', `/accounts/${id}`),

  health: () => pick(() => mock.health(), 'GET', '/health'),
  resources: () => pick(() => mock.resources(), 'GET', '/resources'),
  alerts: () => pick(() => mock.alerts(), 'GET', '/alerts'),
  snoozeAlert: (id, hours) => pick(() => mock.snoozeAlert(id, hours), 'POST', `/alerts/${id}/snooze`, { hours }),
  rules: () => pick(() => mock.rules(), 'GET', '/rules'),
  compileRule: (english, opts) => pick(() => mock.compileRule(english, opts), 'POST', '/rules/compile', { english, ...opts }),
  whatIf: (kind, param, values) => pick(() => mock.whatIf(kind, param, values), 'POST', '/rules/whatif', { kind, param, values }),
  activateRule: (english) => pick(() => mock.activateRule(english), 'POST', '/rules', { english }),
  costs: () => pick(() => mock.costs(), 'GET', '/costs'),
  predictions: () => pick(() => mock.predictions(), 'GET', '/costs/predictions'),
  investigate: () => pick(() => mock.investigate(), 'GET', '/costs/investigate?window=7d'),
  findings: () => pick(() => mock.findings(), 'GET', '/guardian/findings'),
  conflicts: () => pick(() => mock.conflicts(), 'GET', '/rules/conflicts'),
  architect: (prompt, answers) => pick(() => mock.architect(prompt, answers), 'POST', '/architect', { prompt, answers }),
  chat: (message, state, scope = []) => pick(() => mock.chat(message, state), 'POST', '/chat', { message, state, scope }),
  // Internal: the RAG evaluation reports (System quality page). No mock — there is nothing to fake.
  ragEvals: () => (USE_MOCKS ? Promise.resolve({ latest: null, history: [] }) : http('GET', '/evals/rag')),
  searchStatus: () => pick(() => Promise.resolve({ retriever: 'local', generator: 'extractive', indexed: {} }), 'GET', '/search/status'),
}
