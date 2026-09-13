import { Pill } from './ui.jsx'

const tones = {
  discovered: ['blue', 'Discovered'],
  watched: ['green', 'Watched'],
  warning: ['amber', 'Warning'],
  alert: ['red', 'Alert'],
  snoozed: ['violet', 'Snoozed'],
  resolved: ['slate', 'Resolved'],
}

export default function StateBadge({ state }) {
  const [tone, label] = tones[state] ?? ['slate', state]
  return <Pill tone={tone}>{label}</Pill>
}
