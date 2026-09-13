// Rewrites a vague rule into the precise sentence the user picked (choices: { [term]: value }).
// The rewritten sentence is shown to the user before compiling, so nothing is resolved silently.
export function applyClarifications(choices) {
  const duration = choices['too long'] ?? 'more than 6 hours'
  if (choices.expensive === 'GPU') return `No GPU instance runs ${duration}`
  return `Flag anything ${choices.expensive ?? 'costing more than ₹50/day'} running ${duration}`
}
