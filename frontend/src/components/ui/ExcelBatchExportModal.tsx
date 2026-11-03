import React, { useState } from 'react'
import {
  FileSpreadsheet,
  CheckSquare,
  Square,
  X,
  Download,
  Loader2,
  Layers,
  Sparkles,
  CheckCircle2,
  AlertCircle,
} from 'lucide-react'
import {
  exportarMultiplesGraficosAExcel,
  GraficoParaExportar,
  exportarPlantillaOficialSalasEstudio,
} from '../../utils/excelExport'

import { useDownloadProgress } from '../../context/DownloadProgressContext'

export interface ChartExportItem {
  id: string
  label: string
  category: string
  description?: string
}

interface Props {
  charts: ChartExportItem[]
  dateRangeLabel?: string
  activeFiltersDesc?: Record<string, string>
  moduloNombre?: string
}

export const ExcelBatchExportModal: React.FC<Props> = ({
  charts,
  dateRangeLabel = 'Período Completo',
  activeFiltersDesc = {},
  moduloNombre = 'Biblioteca Campus San Francisco',
}) => {
  const { ejecutarDescarga } = useDownloadProgress()
  const [isOpen, setIsOpen] = useState(false)
  const [selectedIds, setSelectedIds] = useState<Record<string, boolean>>(() =>
    charts.reduce<Record<string, boolean>>((acc, c) => ({ ...acc, [c.id]: true }), {})
  )
  const [isExporting, setIsExporting] = useState(false)
  const [statusMsg, setStatusMsg] = useState<{ tipo: 'exito' | 'error'; texto: string } | null>(null)

  const handleToggle = (id: string) => {
    setSelectedIds(prev => ({ ...prev, [id]: !prev[id] }))
  }

  const handleSelectAll = () => {
    const next: Record<string, boolean> = {}
    charts.forEach(c => {
      next[c.id] = true
    })
    setSelectedIds(next)
  }

  const handleDeselectAll = () => {
    const next: Record<string, boolean> = {}
    charts.forEach(c => {
      next[c.id] = false
    })
    setSelectedIds(next)
  }

  const selectedCount = charts.filter(c => selectedIds[c.id]).length

  // Agrupar gráficos por categoría
  const groupedCharts = charts.reduce<Record<string, ChartExportItem[]>>((acc, chart) => {
    if (!acc[chart.category]) acc[chart.category] = []
    acc[chart.category].push(chart)
    return acc
  }, {})

  const handleExportConsolidado = async () => {
    if (selectedCount === 0 || isExporting) return
    setIsExporting(true)
    setStatusMsg(null)

    const filename = `Reporte_Consolidado_${moduloNombre.replace(/[^a-zA-Z0-9]/g, '_')}_${new Date().toISOString().slice(0, 10)}`

    try {
      const ok = await ejecutarDescarga({
        titulo: 'Exportación Consolidada a Excel (.xlsx)',
        subtitulo: `${moduloNombre} • ${selectedCount} gráficos seleccionados`,
        tipo: 'excel',
        nombreArchivo: `${filename}.xlsx`,
        tarea: async ({ setProgreso }) => {
          setProgreso(15, 'Identificando gráficos y visualizaciones en pantalla...')

          // Recopilar elementos DOM de los gráficos seleccionados
          const itemsParaExportar: GraficoParaExportar[] = []

          for (const chart of charts) {
            if (!selectedIds[chart.id]) continue

            let el: HTMLElement | null = document.querySelector(
              `[data-chart-id="${chart.id}"]`
            )

            if (!el) {
              el = document.querySelector(
                `#chart-container-${chart.id}`
              )
            }

            if (!el) {
              const cards = Array.from(document.querySelectorAll<HTMLElement>('[data-chart-card="true"]'))
              el = cards.find(c => {
                const t = (c.getAttribute('data-chart-title') || '').toLowerCase()
                return t.includes(chart.label.toLowerCase()) || chart.label.toLowerCase().includes(t)
              }) || null
            }

            itemsParaExportar.push({
              id: chart.id,
              titulo: chart.label,
              categoria: chart.category,
              element: el,
            })
          }

          const metadatos: Record<string, string> = {
            'Recinto / Módulo': moduloNombre,
            'Período Evaluado': dateRangeLabel,
            'Fecha de Generación': new Date().toLocaleString('es-CL'),
            ...activeFiltersDesc,
          }

          const resultado = await exportarMultiplesGraficosAExcel(
            itemsParaExportar,
            filename,
            metadatos,
            (actual, total, titulo) => {
              const pct = Math.min(80, Math.round(20 + ((actual - 1) / total) * 60))
              setProgreso(pct, `Extrayendo datos (${actual}/${total}): ${titulo}`)
            }
          )

          setProgreso(85, 'Compilando libro Excel nativo OpenXML con hojas dinámicas...')

          if (resultado.exitosos === 0) {
            throw new Error(
              resultado.errorMsg ||
              'No se encontraron datos estructurados en los gráficos seleccionados. Verifique que los gráficos estén cargados.'
            )
          }

          setProgreso(96, `¡Libro generado con éxito (${resultado.exitosos} hojas)! Iniciando descarga...`)
          await new Promise(r => setTimeout(r, 400))
        },
      })

      if (ok) {
        setStatusMsg({
          tipo: 'exito',
          texto: `Libro Excel generado y descargado exitosamente.`,
        })
        setTimeout(() => {
          setIsOpen(false)
          setStatusMsg(null)
        }, 1500)
      } else {
        setStatusMsg({
          tipo: 'error',
          texto: 'No se pudo completar la generación del archivo Excel consolidado.',
        })
      }
    } catch (err: any) {
      console.error('Error generando reporte consolidado Excel', err)
      setStatusMsg({
        tipo: 'error',
        texto: err?.message || 'Ocurrió un error al compilar el archivo Excel consolidado.',
      })
    } finally {
      setIsExporting(false)
    }
  }

  return (
    <>
      {/* Botón Disparador del Modal */}
      <button
        type="button"
        onClick={() => setIsOpen(true)}
        className="flex items-center gap-2 px-3 py-2 rounded-xl text-xs font-semibold bg-emerald-50 hover:bg-emerald-100/90 text-emerald-800 border border-emerald-200 shadow-2xs transition-all cursor-pointer"
        title="Exportar todos o varios gráficos en un solo libro Excel (.xlsx)"
      >
        <FileSpreadsheet size={15} className="text-emerald-700 shrink-0" />
        <span className="font-bold">Exportar Gráficos a Excel</span>
      </button>

      {/* Modal Interactivo de Exportación Consolidada */}
      {isOpen && (
        <div className="fixed inset-0 z-50 bg-slate-950/70 backdrop-blur-xs flex items-center justify-center p-4 animate-in fade-in duration-150">
          <div className="bg-white rounded-2xl border border-slate-200 shadow-2xl w-full max-w-2xl max-h-[90vh] flex flex-col overflow-hidden animate-in zoom-in-95 duration-150">
            {/* Cabecera del Modal */}
            <div className="p-4 sm:px-6 sm:py-4 border-b border-slate-200 flex items-center justify-between gap-3 bg-gradient-to-r from-emerald-50/60 to-slate-50">
              <div className="flex items-center gap-2.5">
                <div className="p-2 bg-emerald-100 text-emerald-800 rounded-xl">
                  <FileSpreadsheet size={20} />
                </div>
                <div>
                  <h2 className="text-base font-bold text-slate-900">
                    Exportación Consolidada a Excel (.xlsx)
                  </h2>
                  <p className="text-xs text-slate-500">
                    {moduloNombre} • {dateRangeLabel}
                  </p>
                </div>
              </div>

              <button
                type="button"
                onClick={() => setIsOpen(false)}
                className="p-1.5 text-slate-400 hover:text-slate-700 hover:bg-slate-100 rounded-lg transition"
              >
                <X size={18} />
              </button>
            </div>

            {/* Banner Destacado: Plantilla Oficial Institucional (Salas de Estudio) */}
            {moduloNombre.includes('Biblioteca') && (
              <div className="mx-6 mt-3 p-3 bg-gradient-to-r from-amber-50 to-amber-100/60 rounded-xl border border-amber-300/80 flex flex-wrap items-center justify-between gap-3 shadow-2xs">
                <div className="flex items-center gap-2.5 min-w-0">
                  <div className="w-8 h-8 rounded-lg bg-amber-500/20 text-amber-900 flex items-center justify-center shrink-0">
                    <FileSpreadsheet size={16} />
                  </div>
                  <div>
                    <h4 className="text-xs font-bold text-amber-950">Plantilla Informe Oficial (Salas de Estudio)</h4>
                    <p className="text-[11px] text-amber-800">
                      Genera el reporte ejecutivo de 4 tablas maestras y 5 gráficos nativos oscuros vinculados.
                    </p>
                  </div>
                </div>
                <button
                  type="button"
                  onClick={async () => {
                    const nombreArchivo = `Informe_Oficial_Salas_Estudio_Biblioteca_${new Date().toISOString().slice(0, 10)}.xlsx`
                    await ejecutarDescarga({
                      titulo: 'Plantilla Informe Oficial (Salas de Estudio)',
                      subtitulo: 'Biblioteca CSF • Tablas maestras y gráficos nativos vinculados',
                      tipo: 'excel',
                      nombreArchivo,
                      tarea: async ({ setProgreso }) => {
                        setProgreso(20, 'Extrayendo métricas de aforo, permanencia y carreras...')
                        await new Promise(r => setTimeout(r, 400))
                        setProgreso(55, 'Generando libro OpenXML con 4 tablas maestras y 5 gráficos oscuros...')
                        const exito = await exportarPlantillaOficialSalasEstudio({
                          espacio_id: 1,
                          periodo_label: dateRangeLabel,
                        })
                        if (!exito) {
                          throw new Error('El servidor no pudo generar la plantilla oficial en este momento.')
                        }
                        setProgreso(95, 'Finalizando ensamblado y descargando libro Excel...')
                        await new Promise(r => setTimeout(r, 400))
                      },
                    })
                    setIsOpen(false)
                  }}
                  className="shrink-0 px-3 py-1.5 bg-amber-500 hover:bg-amber-600 text-white font-bold text-xs rounded-lg shadow-2xs transition cursor-pointer"
                >
                  Descargar Plantilla Oficial
                </button>
              </div>
            )}

            {/* Barra de Acciones Rápidas */}
            <div className="px-6 py-2.5 bg-slate-50 border-b border-slate-200 flex items-center justify-between text-xs text-slate-600">
              <div className="flex items-center gap-2 font-medium">
                <span>Seleccionados:</span>
                <span className="px-2 py-0.5 bg-emerald-100 text-emerald-800 font-bold rounded-md">
                  {selectedCount} de {charts.length} gráficos
                </span>
              </div>

              <div className="flex items-center gap-2">
                <button
                  type="button"
                  onClick={handleSelectAll}
                  className="px-2.5 py-1 text-slate-600 hover:text-slate-900 hover:bg-slate-200/60 rounded-md transition font-medium"
                >
                  Seleccionar todos
                </button>
                <span className="text-slate-300">|</span>
                <button
                  type="button"
                  onClick={handleDeselectAll}
                  className="px-2.5 py-1 text-slate-600 hover:text-slate-900 hover:bg-slate-200/60 rounded-md transition font-medium"
                >
                  Deseleccionar todos
                </button>
              </div>
            </div>

            {/* Contenido Scrolleable con la lista de gráficos agrupados */}
            <div className="p-4 sm:p-6 overflow-y-auto space-y-5 flex-1 min-h-0 text-slate-700 text-xs">
              {Object.entries(groupedCharts).map(([category, items]) => (
                <div key={category} className="space-y-2">
                  <div className="flex items-center gap-2 pb-1 border-b border-slate-100">
                    <Layers size={13} className="text-slate-400" />
                    <h3 className="font-bold text-slate-700 text-[11.5px] uppercase tracking-wider">
                      {category}
                    </h3>
                  </div>

                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                    {items.map(item => {
                      const isChecked = !!selectedIds[item.id]
                      return (
                        <div
                          key={item.id}
                          onClick={() => handleToggle(item.id)}
                          className={`p-2.5 rounded-xl border transition-all cursor-pointer flex items-start gap-2.5 select-none ${
                            isChecked
                              ? 'bg-emerald-50/50 border-emerald-300 shadow-2xs'
                              : 'bg-white border-slate-200 hover:border-slate-300 text-slate-400'
                          }`}
                        >
                          <div className="mt-0.5 shrink-0 text-emerald-700">
                            {isChecked ? <CheckSquare size={16} /> : <Square size={16} className="text-slate-300" />}
                          </div>
                          <div className="min-w-0">
                            <p className={`font-semibold text-xs leading-tight ${isChecked ? 'text-slate-900' : 'text-slate-500'}`}>
                              {item.label}
                            </p>
                            {item.description && (
                              <p className="text-[10.5px] text-slate-400 mt-0.5 line-clamp-1 leading-tight">
                                {item.description}
                              </p>
                            )}
                          </div>
                        </div>
                      )
                    })}
                  </div>
                </div>
              ))}

              {/* Mensaje de estado */}
              {statusMsg && (
                <div
                  className={`p-3 rounded-xl border flex items-center gap-2.5 text-xs ${
                    statusMsg.tipo === 'exito'
                      ? 'bg-emerald-50 border-emerald-200 text-emerald-800'
                      : 'bg-red-50 border-red-200 text-red-800'
                  }`}
                >
                  {statusMsg.tipo === 'exito' ? (
                    <CheckCircle2 size={16} className="text-emerald-600 shrink-0" />
                  ) : (
                    <AlertCircle size={16} className="text-red-600 shrink-0" />
                  )}
                  <span>{statusMsg.texto}</span>
                </div>
              )}
            </div>

            {/* Pie del Modal */}
            <div className="p-4 sm:px-6 border-t border-slate-200 bg-slate-50 flex items-center justify-between gap-3">
              <span className="text-[11px] text-slate-500 hidden sm:inline">
                Cada gráfico seleccionado creará una pestaña separada con sus datos tabulares y metadatos.
              </span>

              <div className="flex items-center gap-2 ml-auto">
                <button
                  type="button"
                  onClick={() => setIsOpen(false)}
                  disabled={isExporting}
                  className="px-3.5 py-2 text-xs font-semibold text-slate-700 hover:bg-slate-200 rounded-xl transition cursor-pointer"
                >
                  Cancelar
                </button>

                <button
                  type="button"
                  onClick={handleExportConsolidado}
                  disabled={isExporting || selectedCount === 0}
                  className="flex items-center gap-2 px-4 py-2 bg-emerald-600 hover:bg-emerald-700 text-white rounded-xl text-xs font-bold transition shadow-sm cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  {isExporting ? (
                    <>
                      <Loader2 size={15} className="animate-spin" />
                      <span>Generando Excel...</span>
                    </>
                  ) : (
                    <>
                      <Download size={15} />
                      <span>Descargar Libro Excel ({selectedCount})</span>
                    </>
                  )}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </>
  )
}
export default ExcelBatchExportModal
