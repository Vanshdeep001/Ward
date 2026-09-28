import { mock } from './mock/engine.js'

// Mock engine by default. Set VITE_USE_MOCKS=false to talk to the FastAPI backend via the /api proxy.
export const USE_MOCKS = import.meta.env.VITE_USE_MOCKS !== 'false'
const BASE = import.meta.env.VITE_API_URL ?? '/api'

async function http(method, path, body) {
  const res = await fetch(`${BASE}${path}`, {
    method,
    headers: body ? { 'Content-Type': 'application/json' } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  })
  if (!res.ok) {
    // FastAPI puts the reason in `detail`; surface it so the UI can show why, not just that it failed.
    const detail = await res.json().catch(() => null)
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

export const api = {
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
  searchStatus: () => pick(() => Promise.resolve({ retriever: 'local', generator: 'extractive', indexed: {} }), 'GET', '/search/status'),
}
