import { lazy, Suspense } from 'react'
import { Routes, Route } from 'react-router-dom'
import Layout from './components/Layout.jsx'
import { Loading } from './components/ui.jsx'

// Each page is its own chunk; Recharts only loads on the pages that draw charts.
const Dashboard = lazy(() => import('./pages/Dashboard.jsx'))
const Copilot = lazy(() => import('./pages/Copilot.jsx'))
const Rules = lazy(() => import('./pages/Rules.jsx'))
const RuleHealth = lazy(() => import('./pages/RuleHealth.jsx'))
const Resources = lazy(() => import('./pages/Resources.jsx'))
const Alerts = lazy(() => import('./pages/Alerts.jsx'))
const Detective = lazy(() => import('./pages/Detective.jsx'))
const Guardian = lazy(() => import('./pages/Guardian.jsx'))
const Architect = lazy(() => import('./pages/Architect.jsx'))
const Accuracy = lazy(() => import('./pages/Accuracy.jsx'))

const page = (Page) => (
  <Suspense fallback={<Loading />}>
    <Page />
  </Suspense>
)

export default function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route index element={page(Dashboard)} />
        <Route path="copilot" element={page(Copilot)} />
        <Route path="rules" element={page(Rules)} />
        <Route path="health" element={page(RuleHealth)} />
        <Route path="resources" element={page(Resources)} />
        <Route path="alerts" element={page(Alerts)} />
        <Route path="detective" element={page(Detective)} />
        <Route path="guardian" element={page(Guardian)} />
        <Route path="architect" element={page(Architect)} />
        <Route path="accuracy" element={page(Accuracy)} />
        <Route path="*" element={<p className="py-20 text-center text-sm text-slate-500">Page not found.</p>} />
      </Route>
    </Routes>
  )
}
