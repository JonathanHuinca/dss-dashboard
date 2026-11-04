import React, { useState, useRef, useEffect } from 'react'
import { Eye, SlidersHorizontal, CheckSquare, Square, X, ChevronDown, Check } from 'lucide-react'

export interface ChartConfigItem {
  id: string
  label: string
  category: string
  description?: string
}

interface Props {
  charts: ChartConfigItem[]
  visibleCharts: Record<string, boolean>
  onToggleChart: (id: string) => void
  onSelectAll: () => void
  onDeselectAll: () => void
  moduloName?: string
}

export const ChartVisibilitySelector: React.FC<Props> = ({
  charts,
  visibleCharts,
  onToggleChart,
  onSelectAll,
  onDeselectAll,
  moduloName = 'Dashboard',
}) => {
  const [isOpen, setIsOpen] = useState(false)
  const popoverRef = useRef<HTMLDivElement>(null)

  // Cerrar al hacer clic fuera
  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (popoverRef.current && !popoverRef.current.contains(event.target as Node)) {
        setIsOpen(false)
      }
    }
    if (isOpen) {
      document.addEventListener('mousedown', handleClickOutside)
    }
    return () => {
      document.removeEventListener('mousedown', handleClickOutside)
    }
  }, [isOpen])

  // Agrupar gráficos por categoría
  const groupedCharts = charts.reduce<Record<string, ChartConfigItem[]>>((acc, chart) => {
    if (!acc[chart.category]) acc[chart.category] = []
    acc[chart.category].push(chart)
    return acc
  }, {})

  const totalCharts = charts.length
  const activeCount = charts.filter(c => visibleCharts[c.id] !== false).length

  return (
    <div className="relative inline-block" ref={popoverRef}>
      <button
        type="button"
        onClick={() => setIsOpen(prev => !prev)}
        className={`flex items-center gap-2 px-3 py-1.5 rounded-xl text-xs font-semibold border transition-all cursor-pointer shadow-2xs ${
          isOpen || activeCount < totalCharts
            ? 'bg-uct-blue-primary text-white border-uct-blue-primary shadow-xs'
            : 'bg-white text-slate-700 border-slate-200 hover:bg-slate-50'
        }`}
        title="Personalizar qué gráficos mostrar u ocultar en este módulo"
      >
        <SlidersHorizontal size={13} className={isOpen || activeCount < totalCharts ? 'text-white' : 'text-uct-blue-primary'} />
        <span>Visibilidad de Gráficos</span>
        <span className={`px-1.5 py-0.2 text-[10px] font-bold rounded-full ${
          isOpen || activeCount < totalCharts
            ? 'bg-white text-uct-blue-primary'
            : 'bg-slate-100 text-slate-600'
        }`}>
          {activeCount}/{totalCharts}
        </span>
        <ChevronDown size={13} className={`transition-transform duration-200 ${isOpen ? 'rotate-180' : ''}`} />
      </button>

      {isOpen && (
        <div className="absolute right-0 mt-2 w-80 md:w-96 bg-white rounded-2xl border border-slate-200 shadow-xl z-50 overflow-hidden animate-in fade-in zoom-in-95 duration-150">
          {/* Encabezado del Popover */}
          <div className="p-3.5 bg-slate-50 border-b border-slate-200/90 flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Eye size={15} className="text-uct-blue-primary" />
              <div>
                <h4 className="text-xs font-bold text-slate-800">Personalizar Gráficos</h4>
                <p className="text-[10px] text-slate-500">Módulo: {moduloName}</p>
              </div>
            </div>

            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={onSelectAll}
                className="text-[10px] text-uct-blue-primary hover:underline font-semibold cursor-pointer"
              >
                Todos
              </button>
              <span className="text-slate-300 text-xs">|</span>
              <button
                type="button"
                onClick={onDeselectAll}
                className="text-[10px] text-slate-500 hover:underline font-semibold cursor-pointer"
              >
                Ninguno
              </button>
              <button
                type="button"
                onClick={() => setIsOpen(false)}
                className="p-1 rounded-lg text-slate-400 hover:text-slate-700 hover:bg-slate-200/60 transition cursor-pointer ml-1"
              >
                <X size={14} />
              </button>
            </div>
          </div>

          {/* Lista de Gráficos por Categoría */}
          <div className="p-3 max-h-[380px] overflow-y-auto space-y-3.5 text-xs">
            {Object.entries(groupedCharts).map(([category, items]) => {
              const categoryActiveCount = items.filter(i => visibleCharts[i.id] !== false).length

              return (
                <div key={category} className="space-y-1.5">
                  <div className="flex items-center justify-between text-[11px] font-bold text-slate-700 uppercase tracking-wider pb-1 border-b border-slate-100">
                    <span>{category}</span>
                    <span className="text-[10px] text-slate-400 font-normal">
                      {categoryActiveCount}/{items.length}
                    </span>
                  </div>

                  <div className="space-y-1">
                    {items.map(item => {
                      const isVisible = visibleCharts[item.id] !== false

                      return (
                        <label
                          key={item.id}
                          className={`flex items-start gap-2 p-1.5 rounded-lg cursor-pointer transition select-none ${
                            isVisible ? 'bg-blue-50/40 hover:bg-blue-50/70 text-slate-800' : 'hover:bg-slate-50 text-slate-400'
                          }`}
                        >
                          <input
                            type="checkbox"
                            checked={isVisible}
                            onChange={() => onToggleChart(item.id)}
                            className="rounded text-uct-blue-primary focus:ring-uct-blue-primary h-3.5 w-3.5 mt-0.5 border-slate-300 cursor-pointer shrink-0"
                          />
                          <div className="flex-1">
                            <span className={`block leading-tight text-xs ${isVisible ? 'font-semibold text-slate-800' : 'text-slate-400 line-through'}`}>
                              {item.label}
                            </span>
                            {item.description && (
                              <span className="text-[10px] text-slate-400 block leading-tight mt-0.5">
                                {item.description}
                              </span>
                            )}
                          </div>
                        </label>
                      )
                    })}
                  </div>
                </div>
              )
            })}
          </div>

          {/* Pie del Popover */}
          <div className="p-2.5 bg-slate-50 border-t border-slate-200 text-center text-[10px] text-slate-500">
            Los gráficos no seleccionados se ocultan inmediatamente del panel.
          </div>
        </div>
      )}
    </div>
  )
}

export default ChartVisibilitySelector
