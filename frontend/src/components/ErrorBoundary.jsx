import { Component } from 'react'
import { ErrorState } from './ui.jsx'

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
    return <ErrorState error={this.state.error} onRetry={() => this.setState({ error: null })} />
  }
}
