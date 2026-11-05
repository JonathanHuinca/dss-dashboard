import React from 'react'

export interface ItemMetricaSeccion {
  label: string
  valor: React.ReactNode
  subtexto?: string
  icono?: React.ElementType
  color?: 'primary' | 'gold' | 'success' | 'warning' | 'danger' | 'neutral'
  badge?: string
}

interface MetricasSeccionProps {
  items: ItemMetricaSeccion[]
  cargando?: boolean
  className?: string
}

const colorStyles = {
  primary: {
    bg: 'bg-gradient-to-br from-blue-50/80 to-slate-50',
    border: 'border-blue-200/80 dark:border-blue-900/40',
    iconBg: 'bg-[#003865]/10 text-[#003865] dark:text-sky-400',
    textVal: 'text-[#003865] dark:text-sky-300',
  },
  gold: {
    bg: 'bg-gradient-to-br from-amber-50/80 to-slate-50',
    border: 'border-amber-200/80 dark:border-amber-900/40',
    iconBg: 'bg-[#C59B27]/15 text-[#C59B27] dark:text-amber-400',
    textVal: 'text-[#B45309] dark:text-amber-300',
  },
  success: {
    bg: 'bg-gradient-to-br from-emerald-50/80 to-slate-50',
    border: 'border-emerald-200/80 dark:border-emerald-900/40',
    iconBg: 'bg-emerald-500/10 text-emerald-600 dark:text-emerald-400',
    textVal: 'text-emerald-700 dark:text-emerald-300',
  },
  warning: {
    bg: 'bg-gradient-to-br from-orange-50/80 to-slate-50',
    border: 'border-orange-200/80 dark:border-orange-900/40',
    iconBg: 'bg-orange-500/10 text-orange-600 dark:text-orange-400',
    textVal: 'text-orange-700 dark:text-orange-300',
  },
  danger: {
    bg: 'bg-gradient-to-br from-rose-50/80 to-slate-50',
    border: 'border-rose-200/80 dark:border-rose-900/40',
    iconBg: 'bg-rose-500/10 text-rose-600 dark:text-rose-400',
    textVal: 'text-rose-700 dark:text-rose-300',
  },
  neutral: {
    bg: 'bg-gradient-to-br from-slate-50 to-white',
    border: 'border-slate-200/80 dark:border-slate-800',
    iconBg: 'bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-300',
    textVal: 'text-slate-800 dark:text-slate-100',
  },
}

export const MetricasSeccion: React.FC<MetricasSeccionProps> = ({
  items,
  cargando = false,
  className = '',
}) => {
  if (!items || items.length === 0) return null

  return (
    <div className={`grid grid-cols-2 md:grid-cols-4 gap-3 ${className}`}>
      {items.map((item, idx) => {
        const estilo = colorStyles[item.color || 'primary']
        const Icono = item.icono

        return (
          <div
            key={idx}
            className={`p-3 rounded-xl border shadow-2xs transition-all ${estilo.bg} ${estilo.border}`}
          >
            <div className="flex items-center justify-between gap-1.5 mb-1">
              <span className="text-[11px] font-semibold text-slate-500 dark:text-slate-400 truncate">
                {item.label}
              </span>
              {Icono && (
                <div className={`p-1 rounded-md shrink-0 ${estilo.iconBg}`}>
                  <Icono size={13} />
                </div>
              )}
            </div>

            <div className="flex items-baseline gap-1.5">
              {cargando ? (
                <div className="h-6 w-16 bg-slate-200 dark:bg-slate-700 animate-pulse rounded-md" />
              ) : (
                <span className={`text-lg font-bold tracking-tight font-mono ${estilo.textVal}`}>
                  {item.valor ?? '—'}
                </span>
              )}
              {item.badge && (
                <span className="text-[10px] font-bold px-1.5 py-0.2 rounded-full bg-slate-200/80 dark:bg-slate-700 text-slate-700 dark:text-slate-300">
                  {item.badge}
                </span>
              )}
            </div>

            {item.subtexto && (
              <p className="text-[10px] text-slate-500 dark:text-slate-400 mt-0.5 truncate">
                {item.subtexto}
              </p>
            )}
          </div>
        )
      })}
    </div>
  )
}

