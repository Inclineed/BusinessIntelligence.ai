import React, { Component, ErrorInfo, ReactNode } from "react"
import { AlertTriangle, RefreshCw } from "lucide-react"

interface Props {
  children: ReactNode
  fallback?: ReactNode
}

interface State {
  hasError: boolean
  error: Error | null
  errorInfo: ErrorInfo | null
}

export class ErrorBoundary extends Component<Props, State> {
  public state: State = {
    hasError: false,
    error: null,
    errorInfo: null,
  }

  public static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error, errorInfo: null }
  }

  public componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    console.error("ErrorBoundary caught an error:", error, errorInfo)
    this.setState({ error, errorInfo })
  }

  public handleReset = () => {
    this.setState({ hasError: false, error: null, errorInfo: null })
    window.location.reload()
  }

  public render() {
    if (this.state.hasError) {
      if (this.props.fallback) {
        return this.props.fallback
      }

      return (
        <div className="min-h-screen bg-[#08090C] text-white flex items-center justify-center p-6 font-sans">
          <div className="max-w-xl w-full bg-[#12131D] border border-red-500/30 rounded-3xl p-8 space-y-5 shadow-2xl">
            <div className="flex items-center gap-3 text-red-400">
              <div className="w-10 h-10 rounded-xl bg-red-500/10 border border-red-500/30 flex items-center justify-center">
                <AlertTriangle className="w-5 h-5 text-red-400" />
              </div>
              <div>
                <h2 className="text-lg font-bold text-white">Rendering Error Intercepted</h2>
                <p className="text-xs text-neutral-400">A component encountered an unexpected exception while rendering.</p>
              </div>
            </div>

            {this.state.error && (
              <div className="p-4 rounded-xl bg-black/60 border border-white/[0.06] space-y-2 text-xs font-mono">
                <div className="text-red-400 font-bold">{this.state.error.name}: {this.state.error.message}</div>
                {this.state.errorInfo?.componentStack && (
                  <pre className="text-[11px] text-neutral-500 overflow-x-auto max-h-40 leading-tight whitespace-pre-wrap">
                    {this.state.errorInfo.componentStack}
                  </pre>
                )}
              </div>
            )}

            <div className="flex gap-3">
              <button
                onClick={this.handleReset}
                className="px-4 py-2 rounded-xl bg-emerald-500 hover:bg-emerald-400 text-black font-bold text-xs flex items-center gap-2 transition-all cursor-pointer"
              >
                <RefreshCw className="w-3.5 h-3.5" />
                <span>Reload Application</span>
              </button>
            </div>
          </div>
        </div>
      )
    }

    return this.props.children
  }
}
