import { ReactNode } from 'react'
import { Sparkles } from 'lucide-react'
import { useAssistant } from '../../context/AssistantContext'

interface Props {
  title: string
  children: ReactNode
  action?: ReactNode
  contextoGrafico?: string
  graficoContexto?: string
  onAskIA?: (contexto: string) => void
  hideAskIA?: boolean
}

export function ChartCard({
  title,
  children,
  action,
  contextoGrafico,
  graficoContexto,
  onAskIA,
  hideAskIA = false,
}: Props) {
  const { openAssistant } = useAssistant()

  const resolvedContext =
    contextoGrafico ||
    graficoContexto ||
    title
      .toLowerCase()
      .normalize('NFD')
      .replace(/[\u0300-\u036f]/g, '')
      .replace(/[^a-z0-9]+/g, '_')
      .replace(/^_+|_+$/g, '')

  const handleAskClick = () => {
    if (onAskIA) {
      onAskIA(resolvedContext)
    }
    openAssistant(resolvedContext)
  }

  return (
    <div className="card">
      <div className="flex items-center justify-between mb-4 gap-2">
        <h3 className="text-sm font-semibold text-uct-text-primary">{title}</h3>
        <div className="flex items-center gap-2">
          {action}
          {!hideAskIA && (
            <button
              onClick={handleAskClick}
              title={`Consultar con el asistente IA sobre este gráfico (${resolvedContext})`}
              className="flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-xs font-semibold bg-gradient-to-r from-amber-500/10 to-uct-gold/20 hover:from-amber-500/20 hover:to-uct-gold/30 text-amber-700 hover:text-amber-900 border border-uct-gold/30 hover:border-uct-gold/60 transition-all cursor-pointer shadow-2xs group"
            >
              <Sparkles size={13} className="text-amber-500 group-hover:rotate-12 transition-transform animate-pulse" />
              <span className="text-[11px] font-bold">Preguntar a IA</span>
            </button>
          )}
        </div>
      </div>
      {children}
    </div>
  )
}
