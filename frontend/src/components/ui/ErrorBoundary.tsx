import { Component, ErrorInfo, ReactNode } from 'react'

interface Props {
  children?: ReactNode
}

interface State {
  hasError: boolean
  error?: Error
}

export class ErrorBoundary extends Component<Props, State> {
  public state: State = {
    hasError: false
  }

  public static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error }
  }

  public componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    console.error('Uncaught error:', error, errorInfo)
  }

  public render() {
    if (this.state.hasError) {
      return (
        <div className="flex items-center justify-center h-full p-4 bg-red-50 text-red-800 rounded-lg border border-red-200">
          <div className="text-center">
            <h2 className="text-lg font-bold mb-2">Ocurrió un error en el chat</h2>
            <p className="text-sm">El componente no pudo ser renderizado correctamente.</p>
            <button
              className="mt-4 px-4 py-2 bg-red-600 text-white rounded hover:bg-red-700 transition-colors text-xs font-semibold"
              onClick={() => this.setState({ hasError: false })}
            >
              Intentar nuevamente
            </button>
          </div>
        </div>
      )
    }

    return this.props.children
  }
}
