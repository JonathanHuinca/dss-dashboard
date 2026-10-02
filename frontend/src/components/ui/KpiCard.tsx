import { LucideIcon } from 'lucide-react'
import { ReactNode } from 'react'

interface Props {
  title: string
  value: ReactNode
  subtitle?: string
  icon: LucideIcon
  iconColor?: string
  trend?: 'up' | 'down' | 'neutral'
  alert?: 'normal' | 'preventivo' | 'critico' | 'saturacion'
}

const ALERT_STYLES: Record<string, string> = {
  normal:     'border-l-4 border-uct-success',
  preventivo: 'border-l-4 border-uct-warning',
  critico:    'border-l-4 border-uct-danger animate-pulse',
  saturacion: 'border-l-4 border-uct-danger animate-pulse',
}

export function KpiCard({ title, value, subtitle, icon: Icon, iconColor = '#C59B27', alert }: Props) {
  const alertClass = alert ? ALERT_STYLES[alert] : ''
  return (
    <div className={`kpi-card ${alertClass}`}>
      <div className="flex items-start justify-between">
        <p className="text-xs font-medium text-uct-text-muted uppercase tracking-wider">{title}</p>
        <div className="p-2 rounded-lg bg-slate-50">
          <Icon size={16} color={iconColor} />
        </div>
      </div>
      <p className="text-2xl font-bold text-uct-text-primary mt-1">{value}</p>
      {subtitle && <p className="text-xs text-uct-text-muted mt-0.5">{subtitle}</p>}
    </div>
  )
}
