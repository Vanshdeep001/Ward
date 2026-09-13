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
  if (!res.ok) throw new Error(`${method} ${path} → ${res.status}`)
  return res.json()
}

const pick = (mockCall, method, path, body) => (USE_MOCKS ? mockCall() : http(method, path, body))

export const api = {
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
  chat: (message, state) => pick(() => mock.chat(message, state), 'POST', '/chat', { message, state }),
}
