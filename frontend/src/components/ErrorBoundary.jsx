import { Component } from 'react'
import { AlertTriangle } from 'lucide-react'

// A crash in one page shows a recoverable message instead of a blank screen.
export default class ErrorBoundary extends Component {
  state = { error: null }

  static getDerivedStateFromError(error) {
    return { error }
  }

  componentDidUpdate(prev) {
    if (prev.resetKey !== this.props.resetKey && this.state.error) this.setState({ error: null })
  }

  render() {
    if (!this.state.error) return this.props.children
    return (
      <div className="mx-auto max-w-lg rounded-xl border border-rose-200 bg-rose-50/50 p-6 text-center">
        <AlertTriangle className="mx-auto text-rose-600" size={28} />
        <p className="mt-3 font-medium text-rose-950">This page hit an error</p>
        <p className="mt-1 break-words font-mono text-xs text-rose-800">{String(this.state.error.message ?? this.state.error)}</p>
        <button
          onClick={() => this.setState({ error: null })}
          className="mt-4 rounded-lg border border-rose-300 bg-white px-3 py-1.5 text-sm text-rose-800 hover:bg-rose-50"
        >
          Try again
        </button>
      </div>
    )
  }
}
