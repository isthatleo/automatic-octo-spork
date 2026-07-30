'use client'

import React from 'react'
import { AlertTriangle, RefreshCw } from 'lucide-react'

/* One crashing panel must never blank the whole control room. React only
 * offers componentDidCatch on class components, so this is the one class
 * component in the codebase -- everything else stays hooks. Mount it with
 * key={panel} (see page.tsx's WorkspaceLayout) so navigating to a
 * different panel automatically resets the boundary instead of trapping
 * the user on a stale error card. */

interface Props {
  children: React.ReactNode
  /** Shown in the error card so the user knows WHICH panel died. */
  panelName?: string
}

interface State {
  error: Error | null
}

export class PanelErrorBoundary extends React.Component<Props, State> {
  state: State = { error: null }

  static getDerivedStateFromError(error: Error): State {
    return { error }
  }

  componentDidCatch(error: Error, info: React.ErrorInfo) {
    // Real console trail for debugging -- the card below intentionally
    // shows only the message, not a stack.
    console.error(`[panel-error] ${this.props.panelName ?? 'panel'} crashed:`, error, info.componentStack)
  }

  private reset = () => this.setState({ error: null })

  render() {
    if (!this.state.error) return this.props.children
    return (
      <div className="flex h-full min-h-[240px] w-full items-center justify-center p-6">
        <div className="flex max-w-md flex-col items-center gap-3 rounded-xl border border-destructive/40 bg-card/70 px-6 py-8 text-center">
          <AlertTriangle className="h-6 w-6 text-destructive" />
          <p className="text-sm font-medium text-foreground">
            {this.props.panelName ? `The ${this.props.panelName} panel hit an error` : 'This panel hit an error'}
          </p>
          <p className="max-w-full break-words font-mono text-[0.65rem] text-muted-foreground">
            {this.state.error.message || String(this.state.error)}
          </p>
          <p className="text-[0.65rem] text-muted-foreground">
            The rest of the dashboard is unaffected.
          </p>
          <button
            type="button"
            onClick={this.reset}
            className="mt-1 flex items-center gap-1.5 rounded-lg border border-border px-3 py-1.5 text-[0.7rem] text-foreground transition-colors hover:border-primary/60"
          >
            <RefreshCw className="h-3 w-3" /> Try again
          </button>
        </div>
      </div>
    )
  }
}
