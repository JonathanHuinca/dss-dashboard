import { ReactNode, useRef, useState, useEffect } from 'react'
import { Sparkles, Download, Maximize2, Minimize2, X, ArrowLeftRight, FileSpreadsheet, Loader2, Table, Check, Layers } from 'lucide-react'
import { useAssistant } from '../../context/AssistantContext'
import { useDownloadProgress } from '../../context/DownloadProgressContext'
import {
  exportarGraficoAExcel,
  detectarSubgraficosEnElemento,
  exportarSubgraficosCombinadosAExcel,
  SubgraficoDetectado,
} from '../../utils/excelExport'

interface Props {
  title: string
  children: ReactNode
  action?: ReactNode
  contextoGrafico?: string
  graficoContexto?: string
  onAskIA?: (contexto: string) => void
  hideAskIA?: boolean
  layout?: 'half' | 'third' | 'two-thirds' | 'full'
  className?: string
  minHeight?: number | string
  maxHeight?: number | string
}

export function ChartCard({
  title,
  children,
  action,
  contextoGrafico,
  graficoContexto,
  onAskIA,
  hideAskIA = false,
  layout = 'half',
  className = '',
  minHeight,
  maxHeight,
}: Props) {
  const { openAssistant, isAiEnabled } = useAssistant()
  const { ejecutarDescarga } = useDownloadProgress()
  const [isMaximized, setIsMaximized] = useState(false)
  const [isFullWidth, setIsFullWidth] = useState(false)
  const [customHeight, setCustomHeight] = useState<number | null>(null)
  const [isExportingImg, setIsExportingImg] = useState(false)
  const [isExportingCsv, setIsExportingCsv] = useState(false)
  const [isExportingExcel, setIsExportingExcel] = useState(false)

  const resolvedContext =
    contextoGrafico ||
    graficoContexto ||
    title
      .toLowerCase()
      .normalize('NFD')
      .replace(/[\u0300-\u036f]/g, '')
      .replace(/[^a-z0-9]+/g, '_')
      .replace(/^_+|_+$/g, '')

  const chartRef = useRef<HTMLDivElement>(null)
  const cardRef = useRef<HTMLDivElement>(null)

  // Cerrar ventana maximizada con Escape
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && isMaximized) {
        setIsMaximized(false)
      }
    }
    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [isMaximized])

  // Despachar resize de Plotly cuando cambia maximizado, altura o ancho
  useEffect(() => {
    const t1 = setTimeout(() => window.dispatchEvent(new Event('resize')), 50)
    const t2 = setTimeout(() => window.dispatchEvent(new Event('resize')), 180)
    const t3 = setTimeout(() => window.dispatchEvent(new Event('resize')), 350)
    return () => {
      clearTimeout(t1)
      clearTimeout(t2)
      clearTimeout(t3)
    }
  }, [isMaximized, customHeight, isFullWidth])

  // Escuchar redimensionamiento bidireccional mediante ResizeObserver en el card
  useEffect(() => {
    if (!cardRef.current) return
    let animId: number
    const observer = new ResizeObserver(() => {
      cancelAnimationFrame(animId)
      animId = requestAnimationFrame(() => {
        window.dispatchEvent(new Event('resize'))
      })
    })
    observer.observe(cardRef.current)
    return () => {
      observer.disconnect()
      cancelAnimationFrame(animId)
    }
  }, [])

  // Escuchar evento global de restablecimiento de gráficos
  useEffect(() => {
    const handleResetLayout = () => {
      setIsFullWidth(false)
      setCustomHeight(null)
      if (cardRef.current) {
        cardRef.current.style.width = ''
        cardRef.current.style.height = ''
      }
    }
    window.addEventListener('uct:reset-charts-layout', handleResetLayout)
    return () => window.removeEventListener('uct:reset-charts-layout', handleResetLayout)
  }, [])

  const handleAskClick = () => {
    if (onAskIA) {
      onAskIA(resolvedContext)
    }
    openAssistant(resolvedContext)
  }


  // Estado para el modal de selección de subgráficos cuando hay 2 o más
  const [modalSubgraficos, setModalSubgraficos] = useState<{
    tipo: 'excel' | 'csv' | 'imagen'
    subgraficos: SubgraficoDetectado[]
  } | null>(null)
  const [opcionSeleccionada, setOpcionSeleccionada] = useState<'ambos' | 'sub1' | 'sub2'>('ambos')

  const downloadCsvBlob = (csvContent: string, filename: string) => {
    const blob = new Blob(['\uFEFF' + csvContent], { type: 'text/csv;charset=utf-8;' })
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.setAttribute('download', `${filename}.csv`)
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
    URL.revokeObjectURL(url)
  }

  const generarCsvStringDesdePlotly = (plotEl: any): string | null => {
    const traces = plotEl?.data
    if (!Array.isArray(traces) || traces.length === 0) return null

    // Caso 1: Gráficos de torta o dona (pie)
    if (traces[0].type === 'pie' || traces[0].labels) {
      const trace = traces[0]
      const labels = trace.labels || []
      const values = trace.values || []
      const rows = [['Categoría', 'Valor', 'Porcentaje']]
      const total = values.reduce((acc: number, val: any) => acc + (Number(val) || 0), 0)
      for (let i = 0; i < Math.max(labels.length, values.length); i++) {
        const cat = labels[i] !== undefined ? `"${String(labels[i]).replace(/"/g, '""')}"` : ''
        const val = values[i] !== undefined ? values[i] : ''
        const pct = total > 0 && values[i] !== undefined ? ((Number(values[i]) / total) * 100).toFixed(2) + '%' : ''
        rows.push([cat, String(val), pct])
      }
      return rows.map((r) => r.join(';')).join('\r\n')
    }

    // Caso 2: Gráficos de barras horizontales (orientation === 'h')
    if (traces[0].type === 'bar' && traces[0].orientation === 'h') {
      const yValues = traces[0].y || []
      const xValues = traces[0].x || []
      const pairs: { cat: string; val: any }[] = []
      for (let i = 0; i < yValues.length; i++) {
        pairs.push({ cat: String(yValues[i] ?? ''), val: xValues[i] })
      }
      // Ordenar de mayor a menor
      pairs.sort((a, b) => (Number(b.val) || 0) - (Number(a.val) || 0))
      const headers = ['Categoría', ...traces.map((t: any, i: number) => `"${(t.name || `Serie_${i + 1}`).replace(/"/g, '""')}"`)]
      const rows = [headers]
      pairs.forEach((p) => {
        rows.push([`"${p.cat.replace(/"/g, '""')}"`, p.val !== undefined && p.val !== null ? String(p.val) : ''])
      })
      return rows.map((r) => r.join(';')).join('\r\n')
    }

    // Caso 3: Gráficos cartesianos estándar (líneas, columnas verticales, etc.)
    const xValuesSet = new Set<string | number>()
    traces.forEach((trace) => {
      if (Array.isArray(trace.x)) {
        trace.x.forEach((val: any) => xValuesSet.add(val))
      }
    })

    if (xValuesSet.size === 0) {
      const maxLen = Math.max(...traces.map((t) => (Array.isArray(t.y) ? t.y.length : 0)))
      if (maxLen === 0) return null
      const headers = ['Índice', ...traces.map((t, i) => `"${(t.name || `Serie_${i + 1}`).replace(/"/g, '""')}"`)]
      const rows = [headers]
      for (let i = 0; i < maxLen; i++) {
        const row = [String(i + 1)]
        traces.forEach((t) => {
          row.push(t.y && t.y[i] !== undefined ? String(t.y[i]) : '')
        })
        rows.push(row)
      }
      return rows.map((r) => r.join(';')).join('\r\n')
    }

    const sortedX = Array.from(xValuesSet)
    const headers = ['Eje_X', ...traces.map((t, i) => `"${(t.name || `Serie_${i + 1}`).replace(/"/g, '""')}"`)]
    const rows = [headers]

    const traceMaps = traces.map((trace) => {
      const map = new Map<string | number, any>()
      if (Array.isArray(trace.x) && Array.isArray(trace.y)) {
        for (let i = 0; i < trace.x.length; i++) {
          map.set(trace.x[i], trace.y[i])
        }
      }
      return map
    })

    sortedX.forEach((x) => {
      const xStr = `"${String(x).replace(/"/g, '""')}"`
      const row = [xStr]
      traceMaps.forEach((map) => {
        const val = map.get(x)
        row.push(val !== undefined && val !== null ? String(val) : '')
      })
      rows.push(row)
    })

    return rows.map((r) => r.join(';')).join('\r\n')
  }

  const exportTableToCsv = (tableEl: HTMLTableElement, filename: string): boolean => {
    const rows: string[][] = []
    const trElements = tableEl.querySelectorAll('tr')
    if (trElements.length === 0) return false

    trElements.forEach((tr) => {
      const cells = tr.querySelectorAll('th, td')
      if (cells.length > 0) {
        const rowData: string[] = []
        cells.forEach((cell) => {
          const text = (cell.textContent || '').trim().replace(/"/g, '""')
          rowData.push(`"${text}"`)
        })
        rows.push(rowData)
      }
    })

    if (rows.length === 0) return false
    downloadCsvBlob(rows.map((r) => r.join(';')).join('\r\n'), filename)
    return true
  }

  // Ejecutores concretos de descarga
  const ejecutarDescargaExcel = async (
    opcion: 'ambos' | 'sub1' | 'sub2',
    subgraficos: SubgraficoDetectado[]
  ) => {
    if (isExportingExcel) return
    const targetElement = isMaximized
      ? document.getElementById(`maximized-chart-${resolvedContext}`)
      : chartRef.current
    if (!targetElement) return

    const filename = `${resolvedContext}_datos_${new Date().toISOString().slice(0, 10)}`
    setIsExportingExcel(true)

    try {
      if (opcion === 'ambos' && subgraficos.length > 1) {
        await ejecutarDescarga({
          titulo: 'Exportación Consolidada a Excel (.xlsx)',
          subtitulo: `${title} • 2 gráficos integrados`,
          tipo: 'excel',
          nombreArchivo: `${filename}_completo.xlsx`,
          tarea: async ({ setProgreso }) => {
            await exportarSubgraficosCombinadosAExcel(
              subgraficos,
              `${filename}_completo`,
              title,
              setProgreso
            )
          },
        })
      } else {
        const subIndex = opcion === 'sub2' && subgraficos.length > 1 ? 1 : 0
        const elExportar = subgraficos.length > 0 ? subgraficos[subIndex].plotEl : targetElement
        const tituloGrafico = subgraficos.length > 0 ? subgraficos[subIndex].titulo : title
        const sufijo = subgraficos.length > 0 ? `_${subgraficos[subIndex].id}` : ''

        await ejecutarDescarga({
          titulo: 'Exportación a Excel (.xlsx)',
          subtitulo: tituloGrafico,
          tipo: 'excel',
          nombreArchivo: `${filename}${sufijo}.xlsx`,
          tarea: async ({ setProgreso }) => {
            setProgreso(20, 'Extrayendo series y coordenadas del gráfico...')
            await new Promise((r) => setTimeout(r, 200))
            setProgreso(60, 'Generando libro Excel OpenXML con formatos nativos...')

            const ok = await exportarGraficoAExcel(elExportar, `${filename}${sufijo}`, tituloGrafico, setProgreso)
            if (!ok) {
              setProgreso(80, 'Detectando estructura alternativa de respaldo...')
              const plotEl = elExportar.querySelector ? elExportar.querySelector('.js-plotly-plot') : elExportar
              const tableEl = elExportar.querySelector ? elExportar.querySelector('table') : null
              let csvOk = false
              if (plotEl && plotEl.data) {
                const csv = generarCsvStringDesdePlotly(plotEl)
                if (csv) {
                  downloadCsvBlob(csv, `${filename}${sufijo}`)
                  csvOk = true
                }
              } else if (tableEl) {
                csvOk = exportTableToCsv(tableEl, `${filename}${sufijo}`)
              }
              if (!csvOk) {
                throw new Error('No se encontraron datos tabulares o visuales en este gráfico para exportar.')
              }
            }
            setProgreso(95, 'Descarga del archivo generada exitosamente...')
            await new Promise((r) => setTimeout(r, 300))
          },
        })
      }
    } catch (err) {
      console.error('Error exportando datos a Excel', err)
    } finally {
      setIsExportingExcel(false)
    }
  }

  const ejecutarDescargaCsv = async (
    opcion: 'ambos' | 'sub1' | 'sub2',
    subgraficos: SubgraficoDetectado[]
  ) => {
    if (isExportingCsv) return
    const targetElement = isMaximized
      ? document.getElementById(`maximized-chart-${resolvedContext}`)
      : chartRef.current
    if (!targetElement) return

    const filename = `${resolvedContext}_datos_${new Date().toISOString().slice(0, 10)}`
    setIsExportingCsv(true)

    try {
      if (opcion === 'ambos' && subgraficos.length > 1) {
        await ejecutarDescarga({
          titulo: 'Exportación Consolidada a CSV',
          subtitulo: `${title} • 2 tablas integradas`,
          tipo: 'csv',
          nombreArchivo: `${filename}_completo.csv`,
          tarea: async ({ setProgreso }) => {
            setProgreso(25, 'Extrayendo valores de ambos gráficos...')
            await new Promise((r) => setTimeout(r, 200))
            const csv1 = generarCsvStringDesdePlotly(subgraficos[0].plotEl)
            const csv2 = generarCsvStringDesdePlotly(subgraficos[1].plotEl)
            if (!csv1 && !csv2) throw new Error('No se encontraron datos estructurados para exportar.')

            setProgreso(75, 'Estructurando archivo CSV consolidado con encabezados UCT...')
            const encabezado = `# SISTEMA DE APOYO A LA TOMA DE DECISIONES (DSS) — UNIVERSIDAD CATÓLICA DE TEMUCO\r\n# REPORTE: ${title}\r\n# FECHA DE EXPORTACIÓN: ${new Date().toLocaleString('es-CL')}\r\n\r\n# ============================================================\r\n# 1. ${subgraficos[0].titulo.toUpperCase()}\r\n# ============================================================\r\n${csv1 || '# Sin datos'}\r\n\r\n# ============================================================\r\n# 2. ${subgraficos[1].titulo.toUpperCase()}\r\n# ============================================================\r\n${csv2 || '# Sin datos'}`

            downloadCsvBlob(encabezado, `${filename}_completo`)
            setProgreso(95, 'Descarga del archivo CSV finalizada...')
            await new Promise((r) => setTimeout(r, 200))
          },
        })
      } else {
        const subIndex = opcion === 'sub2' && subgraficos.length > 1 ? 1 : 0
        const elPlot = subgraficos.length > 0 ? subgraficos[subIndex].plotEl : targetElement.querySelector('.js-plotly-plot')
        const tituloGrafico = subgraficos.length > 0 ? subgraficos[subIndex].titulo : title
        const sufijo = subgraficos.length > 0 ? `_${subgraficos[subIndex].id}` : ''

        await ejecutarDescarga({
          titulo: 'Exportación a CSV',
          subtitulo: tituloGrafico,
          tipo: 'csv',
          nombreArchivo: `${filename}${sufijo}.csv`,
          tarea: async ({ setProgreso }) => {
            setProgreso(30, 'Extrayendo valores y series del gráfico...')
            await new Promise((r) => setTimeout(r, 200))
            setProgreso(70, 'Estructurando archivo CSV delimitado por punto y coma...')

            let ok = false
            if (elPlot && elPlot.data) {
              const csv = generarCsvStringDesdePlotly(elPlot)
              if (csv) {
                downloadCsvBlob(csv, `${filename}${sufijo}`)
                ok = true
              }
            }

            if (!ok) {
              const tableEl = targetElement.querySelector<HTMLTableElement>('table')
              if (tableEl) {
                ok = exportTableToCsv(tableEl, `${filename}${sufijo}`)
              }
            }

            if (!ok) {
              throw new Error('No se encontraron datos estructurados en este gráfico para exportar.')
            }

            setProgreso(95, 'Descargando archivo CSV...')
            await new Promise((r) => setTimeout(r, 200))
          },
        })
      }
    } catch (err) {
      console.error('Error exportando datos a CSV', err)
    } finally {
      setIsExportingCsv(false)
    }
  }

  const ejecutarDescargaImagen = async (
    opcion: 'ambos' | 'sub1' | 'sub2',
    subgraficos: SubgraficoDetectado[]
  ) => {
    if (isExportingImg) return
    const targetElement = isMaximized
      ? document.getElementById(`maximized-chart-${resolvedContext}`)
      : chartRef.current
    if (!targetElement) return

    const filename = `${resolvedContext}_grafico_${new Date().toISOString().slice(0, 10)}`
    setIsExportingImg(true)

    try {
      if (opcion === 'ambos' || subgraficos.length <= 1) {
        await ejecutarDescarga({
          titulo: 'Exportación de Imagen en Alta Resolución',
          subtitulo: title,
          tipo: 'imagen',
          nombreArchivo: `${filename}.png`,
          tarea: async ({ setProgreso }) => {
            setProgreso(20, 'Preparando lienzo panorámico y ocultando controles...')
            const modebars = targetElement.querySelectorAll<HTMLElement>('.modebar, .modebar-container, .js-plotly-plot .modebar')
            modebars.forEach((el) => {
              el.style.display = 'none'
            })

            setProgreso(50, 'Renderizando lienzo de alta resolución (x2)...')
            const html2canvas = (await import('html2canvas')).default
            const canvas = await html2canvas(targetElement, {
              backgroundColor: '#ffffff',
              scale: 2,
              ignoreElements: (element) => {
                return (
                  element.classList?.contains('modebar') ||
                  element.classList?.contains('modebar-container') ||
                  element.closest?.('.modebar') !== null ||
                  element.closest?.('.modebar-container') !== null
                )
              },
            })

            modebars.forEach((el) => {
              el.style.display = ''
            })

            setProgreso(80, 'Estampando firma institucional UCT...')
            const ctx = canvas.getContext('2d')
            if (ctx) {
              ctx.font = '14px Inter, sans-serif'
              ctx.fillStyle = 'rgba(100, 116, 139, 0.7)'
              const watermark = `Exportado: ${new Date().toLocaleString()} - DSS UCT`
              ctx.fillText(watermark, canvas.width - ctx.measureText(watermark).width - 15, canvas.height - 15)
            }

            const imgData = canvas.toDataURL('image/png')
            const link = document.createElement('a')
            link.href = imgData
            link.download = `${filename}.png`
            link.click()
            setProgreso(95, 'Descargando archivo PNG...')
          },
        })
      } else {
        const subIndex = opcion === 'sub2' ? 1 : 0
        const subPlot = subgraficos[subIndex].plotEl
        const subTitulo = subgraficos[subIndex].titulo
        const sufijo = `_${subgraficos[subIndex].id}`

        await ejecutarDescarga({
          titulo: 'Exportación de Imagen en Alta Resolución',
          subtitulo: subTitulo,
          tipo: 'imagen',
          nombreArchivo: `${filename}${sufijo}.png`,
          tarea: async ({ setProgreso }) => {
            setProgreso(30, 'Renderizando gráfico individual en alta resolución...')
            const Plotly = (window as any).Plotly
            if (subPlot && Plotly?.downloadImage) {
              await Plotly.downloadImage(subPlot, {
                format: 'png',
                height: Math.max(750, subPlot.clientHeight || 750),
                width: Math.max(1200, subPlot.clientWidth || 1200),
                filename: `${filename}${sufijo}`,
              })
            } else {
              const html2canvas = (await import('html2canvas')).default
              const canvas = await html2canvas(subPlot, { backgroundColor: '#ffffff', scale: 2 })
              const imgData = canvas.toDataURL('image/png')
              const link = document.createElement('a')
              link.href = imgData
              link.download = `${filename}${sufijo}.png`
              link.click()
            }
            setProgreso(95, 'Descarga finalizada...')
          },
        })
      }
    } catch (err) {
      console.error('Error exportando gráfico como imagen', err)
    } finally {
      setIsExportingImg(false)
    }
  }

  // Handlers disparados desde la barra de botones
  const handleDownloadImage = () => {
    if (isExportingImg) return
    const targetElement = isMaximized
      ? document.getElementById(`maximized-chart-${resolvedContext}`)
      : chartRef.current
    if (!targetElement) return

    const subgraficos = detectarSubgraficosEnElemento(targetElement, resolvedContext, title)
    if (subgraficos.length > 1) {
      setModalSubgraficos({ tipo: 'imagen', subgraficos })
      setOpcionSeleccionada('ambos')
      return
    }
    ejecutarDescargaImagen('ambos', subgraficos)
  }

  const handleExportCsv = () => {
    if (isExportingCsv) return
    const targetElement = isMaximized
      ? document.getElementById(`maximized-chart-${resolvedContext}`)
      : chartRef.current
    if (!targetElement) return

    const subgraficos = detectarSubgraficosEnElemento(targetElement, resolvedContext, title)
    if (subgraficos.length > 1) {
      setModalSubgraficos({ tipo: 'csv', subgraficos })
      setOpcionSeleccionada('ambos')
      return
    }
    ejecutarDescargaCsv('ambos', subgraficos)
  }

  const handleExportExcel = () => {
    if (isExportingExcel) return
    const targetElement = isMaximized
      ? document.getElementById(`maximized-chart-${resolvedContext}`)
      : chartRef.current
    if (!targetElement) return

    const subgraficos = detectarSubgraficosEnElemento(targetElement, resolvedContext, title)
    if (subgraficos.length > 1) {
      setModalSubgraficos({ tipo: 'excel', subgraficos })
      setOpcionSeleccionada('ambos')
      return
    }
    ejecutarDescargaExcel('ambos', subgraficos)
  }

  const handleConfirmarDescargaMultiple = () => {
    if (!modalSubgraficos) return
    const { tipo, subgraficos } = modalSubgraficos
    const opcion = opcionSeleccionada
    setModalSubgraficos(null)

    if (tipo === 'excel') {
      ejecutarDescargaExcel(opcion, subgraficos)
    } else if (tipo === 'csv') {
      ejecutarDescargaCsv(opcion, subgraficos)
    } else if (tipo === 'imagen') {
      ejecutarDescargaImagen(opcion, subgraficos)
    }
  }

  const adjustHeight = (delta: number) => {
    setCustomHeight((prev) => {
      const current = prev ?? 320
      const next = Math.max(220, Math.min(800, current + delta))
      return next
    })
  }

  const getLayoutClass = () => {
    switch (layout) {
      case 'third':
        return 'w-full md:w-[calc(50%-0.5rem)] xl:w-[calc(33.333%-0.7rem)]'
      case 'two-thirds':
        return 'w-full lg:w-[calc(66.666%-0.5rem)]'
      case 'full':
        return 'w-full'
      case 'half':
      default:
        return 'w-full lg:w-[calc(50%-0.5rem)]'
    }
  }

  return (
    <>
      <div
        ref={cardRef}
        data-chart-card="true"
        data-chart-id={resolvedContext}
        data-chart-title={title}
        className={`card chart-resizable-card flex flex-col w-full min-w-0 max-w-full relative transition-[box-shadow,border-color] duration-150 ${getLayoutClass()} ${isFullWidth ? '!w-full !max-w-full shadow-md ring-1 ring-uct-blue-primary/30' : ''
          } ${className}`}
        style={{
          overflow: 'hidden',
          minHeight: customHeight
            ? `${customHeight}px`
            : minHeight
              ? typeof minHeight === 'number'
                ? `${minHeight}px`
                : minHeight
              : '360px',
          maxHeight: customHeight
            ? `${customHeight}px`
            : maxHeight
              ? typeof maxHeight === 'number'
                ? `${maxHeight}px`
                : maxHeight
              : layout === 'full'
                ? 'none'
                : '920px',
          height: customHeight ? `${customHeight}px` : undefined,
          width: isFullWidth ? '100%' : undefined,
        }}
      >
        <div className="flex flex-wrap items-center justify-between mb-3 gap-2 shrink-0">
          <h3 className="text-sm font-semibold text-uct-text-primary">{title}</h3>

          <div className="flex items-center gap-1.5 shrink-0">
            {action}

            {/* Botón Expandir Ancho a fila completa sin solapamiento (solo para tarjetas no completas) */}
            {layout !== 'full' && (
              <button
                type="button"
                onClick={() => setIsFullWidth(!isFullWidth)}
                title={isFullWidth ? 'Restaurar ancho normal' : 'Expandir a ancho completo (100% de la fila)'}
                className={`hidden sm:flex items-center gap-1 px-2 py-1 rounded-lg text-xs font-semibold border transition cursor-pointer shadow-2xs ${isFullWidth
                    ? 'bg-blue-50 text-uct-blue-primary border-blue-300 font-bold'
                    : 'bg-slate-100 hover:bg-slate-200 text-slate-600 border-slate-200'
                  }`}
              >
                <ArrowLeftRight size={12} />
                <span className="text-[10.5px]">{isFullWidth ? 'Restaurar' : 'Expandir Ancho'}</span>
              </button>
            )}

            {!hideAskIA && isAiEnabled && (
              <button
                type="button"
                onClick={handleAskClick}
                title={`Consultar con el asistente IA sobre este gráfico (${resolvedContext})`}
                className="flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-xs font-semibold bg-gradient-to-r from-amber-500/10 to-uct-gold/20 hover:from-amber-500/20 hover:to-uct-gold/30 text-amber-700 hover:text-amber-900 border border-uct-gold/30 hover:border-uct-gold/60 transition-all cursor-pointer shadow-2xs group"
              >
                <Sparkles size={13} className="text-amber-500 group-hover:rotate-12 transition-transform animate-pulse" />
                <span className="text-[11px] font-bold">Preguntar a IA</span>
              </button>
            )}

            {/* Botón Exportar Imagen PNG con indicador */}
            <button
              type="button"
              onClick={handleDownloadImage}
              disabled={isExportingImg}
              title="Exportar Gráfico como PNG"
              className={`flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-xs font-semibold transition-colors border shadow-2xs cursor-pointer ${
                isExportingImg
                  ? 'bg-blue-50 text-uct-blue-primary border-blue-200 cursor-wait'
                  : 'bg-slate-100 hover:bg-slate-200 text-slate-600 border-slate-200'
              }`}
            >
              {isExportingImg ? (
                <>
                  <Loader2 size={13} className="animate-spin text-uct-blue-primary" />
                  <span className="text-[11px] font-medium text-uct-blue-primary">Exportando...</span>
                </>
              ) : (
                <>
                  <Download size={13} />
                  <span className="hidden md:inline text-[11px]">Exportar</span>
                </>
              )}
            </button>

            {/* Botón Exportar Datos Excel (.xlsx) */}
            <button
              type="button"
              onClick={handleExportExcel}
              disabled={isExportingExcel}
              title="Exportar datos del gráfico a Excel (.xlsx)"
              className={`flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-xs font-semibold transition-colors border shadow-2xs cursor-pointer ${
                isExportingExcel
                  ? 'bg-emerald-50 text-emerald-800 border-emerald-300 cursor-wait'
                  : 'bg-emerald-50/70 hover:bg-emerald-100 text-emerald-800 border-emerald-200 hover:border-emerald-300'
              }`}
            >
              {isExportingExcel ? (
                <>
                  <Loader2 size={13} className="animate-spin text-emerald-700" />
                  <span className="text-[11px] font-medium text-emerald-800">Generando...</span>
                </>
              ) : (
                <>
                  <FileSpreadsheet size={13} className="text-emerald-700" />
                  <span className="text-[11px] font-bold">Excel</span>
                </>
              )}
            </button>

            {/* Botón Exportar Datos CSV */}
            <button
              type="button"
              onClick={handleExportCsv}
              disabled={isExportingCsv}
              title="Exportar datos del gráfico a CSV"
              className={`flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-xs font-semibold transition-colors border shadow-2xs cursor-pointer ${
                isExportingCsv
                  ? 'bg-slate-100 text-slate-700 border-slate-300 cursor-wait'
                  : 'bg-slate-100 hover:bg-slate-200 text-slate-600 border-slate-200 hover:text-slate-900'
              }`}
            >
              {isExportingCsv ? (
                <>
                  <Loader2 size={13} className="animate-spin text-slate-600" />
                  <span className="text-[11px] font-medium text-slate-700">Generando...</span>
                </>
              ) : (
                <>
                  <Table size={13} className="text-slate-500" />
                  <span className="text-[11px]">CSV</span>
                </>
              )}
            </button>

            {/* Botón Maximizar a Pantalla Completa */}
            <button
              type="button"
              onClick={() => setIsMaximized(true)}
              title="Abrir en ventana grande completa (Pantalla completa)"
              className="p-1.5 rounded-lg text-slate-600 bg-slate-100 hover:bg-blue-50 hover:text-uct-blue-primary hover:border-blue-200 border border-slate-200 transition cursor-pointer shadow-2xs"
            >
              <Maximize2 size={13} />
            </button>
          </div>
        </div>

        {/* Contenedor del gráfico: ocupa todo el alto y ancho dinámico del card con soporte de scroll vertical */}
        <div className="flex-1 w-full min-h-[240px] min-w-0 flex flex-col overflow-hidden relative">
          <div
            ref={chartRef}
            id={`chart-container-${resolvedContext}`}
            className="w-full h-full min-w-0 flex-1 flex flex-col overflow-y-auto overflow-x-hidden"
            style={{
              scrollbarWidth: 'thin',
              scrollbarColor: '#CBD5E1 transparent',
            }}
          >
            {children}
          </div>
        </div>
      </div>

      {/* Ventana Modal Maximizada a Pantalla Completa */}
      {isMaximized && (
        <div className="fixed inset-0 z-50 bg-slate-950/80 backdrop-blur-sm p-3 sm:p-6 flex items-center justify-center animate-in fade-in duration-150">
          <div className="bg-white rounded-2xl border border-slate-200 shadow-2xl w-full h-full max-w-[96vw] max-h-[94vh] flex flex-col overflow-hidden animate-in zoom-in-95 duration-150">
            {/* Cabecera del Modal */}
            <div className="p-4 sm:px-6 sm:py-3.5 border-b border-slate-200 flex items-center justify-between gap-3 bg-slate-50/70 shrink-0">
              <div className="flex items-center gap-2.5 min-w-0">
                <span className="p-1.5 bg-blue-100 text-uct-blue-primary rounded-lg shrink-0">
                  <Maximize2 size={16} />
                </span>
                <div className="min-w-0">
                  <h2 className="text-base font-bold text-slate-900 truncate">{title}</h2>
                  <p className="text-[11px] text-slate-500">Vista ampliada en alta resolución • Presione Escape o Clic en Cerrar</p>
                </div>
              </div>

              <div className="flex items-center gap-2 shrink-0">
                {!hideAskIA && isAiEnabled && (
                  <button
                    type="button"
                    onClick={handleAskClick}
                    className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-xs font-semibold bg-gradient-to-r from-amber-500/10 to-uct-gold/20 text-amber-800 border border-uct-gold/40 hover:bg-amber-100 transition cursor-pointer"
                  >
                    <Sparkles size={14} className="text-amber-500" />
                    <span>Preguntar a IA</span>
                  </button>
                )}

                <button
                  type="button"
                  onClick={handleDownloadImage}
                  disabled={isExportingImg}
                  className="flex items-center gap-1.5 px-3 py-1.5 bg-white border border-slate-200 rounded-xl text-xs font-semibold text-slate-700 hover:bg-slate-100 transition cursor-pointer shadow-xs disabled:opacity-75"
                >
                  {isExportingImg ? (
                    <>
                      <Loader2 size={14} className="animate-spin text-uct-blue-primary" />
                      <span>Exportando PNG...</span>
                    </>
                  ) : (
                    <>
                      <Download size={14} />
                      <span>Exportar PNG</span>
                    </>
                  )}
                </button>

                <button
                  type="button"
                  onClick={handleExportExcel}
                  disabled={isExportingExcel}
                  className="flex items-center gap-1.5 px-3 py-1.5 bg-emerald-50 hover:bg-emerald-100 text-emerald-800 border border-emerald-300 rounded-xl text-xs font-bold transition cursor-pointer shadow-xs disabled:opacity-75"
                >
                  {isExportingExcel ? (
                    <>
                      <Loader2 size={14} className="animate-spin text-emerald-700" />
                      <span>Generando Excel...</span>
                    </>
                  ) : (
                    <>
                      <FileSpreadsheet size={14} className="text-emerald-700" />
                      <span>Exportar Excel</span>
                    </>
                  )}
                </button>

                <button
                  type="button"
                  onClick={handleExportCsv}
                  disabled={isExportingCsv}
                  className="flex items-center gap-1.5 px-3 py-1.5 bg-white border border-slate-200 rounded-xl text-xs font-semibold text-slate-700 hover:bg-slate-100 hover:text-slate-900 transition cursor-pointer shadow-xs disabled:opacity-75"
                >
                  {isExportingCsv ? (
                    <>
                      <Loader2 size={14} className="animate-spin text-slate-600" />
                      <span className="text-slate-700">Generando CSV...</span>
                    </>
                  ) : (
                    <>
                      <Table size={14} className="text-slate-600" />
                      <span>Exportar CSV</span>
                    </>
                  )}
                </button>

                <button
                  type="button"
                  onClick={() => setIsMaximized(false)}
                  className="flex items-center gap-1 px-3 py-1.5 bg-slate-200 hover:bg-slate-300 text-slate-800 rounded-xl text-xs font-bold transition cursor-pointer"
                  title="Cerrar vista grande (Escape)"
                >
                  <X size={15} />
                  <span>Cerrar</span>
                </button>
              </div>
            </div>

            {/* Contenedor del Gráfico en Gran Tamaño con Desplazamiento Vertical Fluido */}
            <div
              id={`maximized-chart-${resolvedContext}`}
              className="flex-1 w-full p-4 sm:p-6 pb-16 overflow-y-auto overflow-x-hidden bg-white min-h-0 uct-maximized-chart-wrapper"
              style={{
                scrollbarWidth: 'thin',
                scrollbarColor: '#94A3B8 #F1F5F9',
                scrollbarGutter: 'stable',
              }}
            >
              <style>{`
                .uct-maximized-chart-wrapper {
                  overflow-y: auto !important;
                  overflow-x: hidden !important;
                  scroll-behavior: smooth;
                  scrollbar-gutter: stable;
                }
                .uct-maximized-chart-wrapper::-webkit-scrollbar {
                  width: 10px;
                }
                .uct-maximized-chart-wrapper::-webkit-scrollbar-track {
                  background: #F1F5F9;
                  border-radius: 8px;
                }
                .uct-maximized-chart-wrapper::-webkit-scrollbar-thumb {
                  background: #94A3B8;
                  border-radius: 8px;
                  border: 2px solid #F1F5F9;
                }
                .uct-maximized-chart-wrapper::-webkit-scrollbar-thumb:hover {
                  background: #475569;
                }
                .uct-maximized-chart-wrapper .js-plotly-plot {
                  width: 100% !important;
                }
                .uct-maximized-chart-wrapper .plot-container {
                  width: 100% !important;
                }
                .uct-maximized-chart-wrapper > div:only-child > .js-plotly-plot {
                  min-height: calc(85vh - 120px) !important;
                }
              `}</style>
              <div className="w-full min-h-0 flex flex-col space-y-4 pb-8">
                {children}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Modal Institucional de Selección cuando la Tarjeta Contiene 2 o más Gráficos */}
      {modalSubgraficos && modalSubgraficos.subgraficos.length > 1 && (
        <div className="fixed inset-0 z-50 bg-slate-950/70 backdrop-blur-xs flex items-center justify-center p-4 animate-in fade-in duration-150">
          <div className="bg-white rounded-2xl border border-slate-200 shadow-2xl max-w-lg w-full overflow-hidden animate-in zoom-in-95 duration-150">
            {/* Cabecera */}
            <div className="p-4 sm:p-5 border-b border-slate-200 bg-slate-50/80 flex items-start justify-between gap-3">
              <div className="flex items-center gap-3">
                <div
                  className={`p-2.5 rounded-xl ${
                    modalSubgraficos.tipo === 'excel'
                      ? 'bg-emerald-100 text-emerald-800'
                      : modalSubgraficos.tipo === 'csv'
                      ? 'bg-slate-200 text-slate-800'
                      : 'bg-blue-100 text-uct-blue-primary'
                  }`}
                >
                  {modalSubgraficos.tipo === 'excel' && <FileSpreadsheet size={20} />}
                  {modalSubgraficos.tipo === 'csv' && <Table size={20} />}
                  {modalSubgraficos.tipo === 'imagen' && <Download size={20} />}
                </div>
                <div>
                  <h3 className="text-sm font-bold text-slate-900">
                    Opciones de Exportación ({modalSubgraficos.tipo === 'excel' ? 'Excel .xlsx' : modalSubgraficos.tipo === 'csv' ? 'CSV' : 'Imagen PNG'})
                  </h3>
                  <p className="text-xs text-slate-500 line-clamp-1">{title}</p>
                </div>
              </div>
              <button
                type="button"
                onClick={() => setModalSubgraficos(null)}
                className="p-1 rounded-lg text-slate-400 hover:text-slate-600 hover:bg-slate-100 transition cursor-pointer"
              >
                <X size={18} />
              </button>
            </div>

            {/* Contenido / Opciones */}
            <div className="p-4 sm:p-5 space-y-3">
              <p className="text-xs text-slate-600">
                Esta sección integra <strong>2 gráficos independientes</strong>. Selecciona qué componentes deseas exportar:
              </p>

              <div className="space-y-2.5">
                {/* Opción Ambos */}
                <div
                  onClick={() => setOpcionSeleccionada('ambos')}
                  className={`p-3.5 rounded-xl border-2 transition-all cursor-pointer flex items-start gap-3 ${
                    opcionSeleccionada === 'ambos'
                      ? 'border-uct-blue-primary bg-blue-50/60 shadow-xs'
                      : 'border-slate-200 hover:border-slate-300 bg-white'
                  }`}
                >
                  <div
                    className={`w-5 h-5 rounded-full border-2 mt-0.5 flex items-center justify-center shrink-0 ${
                      opcionSeleccionada === 'ambos'
                        ? 'border-uct-blue-primary bg-uct-blue-primary text-white'
                        : 'border-slate-300 bg-white'
                    }`}
                  >
                    {opcionSeleccionada === 'ambos' && <Check size={12} strokeWidth={3} />}
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <span className="text-xs font-bold text-slate-900">Ambos Gráficos (Completo)</span>
                      <span className="text-[10px] font-bold px-2 py-0.5 rounded-md bg-emerald-100 text-emerald-800">
                        Recomendado
                      </span>
                    </div>
                    <p className="text-[11px] text-slate-500 mt-0.5">
                      {modalSubgraficos.tipo === 'excel'
                        ? 'Genera un archivo Excel (.xlsx) con 2 pestañas independientes y sus gráficos nativos OpenXML.'
                        : modalSubgraficos.tipo === 'csv'
                        ? 'Genera un archivo CSV consolidado con ambas tablas de datos y encabezados institucionales.'
                        : 'Captura la vista panorámica completa que incluye los 2 gráficos juntos en alta definición.'}
                    </p>
                  </div>
                </div>

                {/* Opción Subgráfico 1 */}
                <div
                  onClick={() => setOpcionSeleccionada('sub1')}
                  className={`p-3.5 rounded-xl border-2 transition-all cursor-pointer flex items-start gap-3 ${
                    opcionSeleccionada === 'sub1'
                      ? 'border-uct-blue-primary bg-blue-50/60 shadow-xs'
                      : 'border-slate-200 hover:border-slate-300 bg-white'
                  }`}
                >
                  <div
                    className={`w-5 h-5 rounded-full border-2 mt-0.5 flex items-center justify-center shrink-0 ${
                      opcionSeleccionada === 'sub1'
                        ? 'border-uct-blue-primary bg-uct-blue-primary text-white'
                        : 'border-slate-300 bg-white'
                    }`}
                  >
                    {opcionSeleccionada === 'sub1' && <Check size={12} strokeWidth={3} />}
                  </div>
                  <div className="flex-1 min-w-0">
                    <span className="text-xs font-bold text-slate-900">
                      Solo Gráfico 1: {modalSubgraficos.subgraficos[0].titulo}
                    </span>
                    <p className="text-[11px] text-slate-500 mt-0.5">
                      Exporta exclusivamente la visualización y datos tabulares del primer gráfico.
                    </p>
                  </div>
                </div>

                {/* Opción Subgráfico 2 */}
                <div
                  onClick={() => setOpcionSeleccionada('sub2')}
                  className={`p-3.5 rounded-xl border-2 transition-all cursor-pointer flex items-start gap-3 ${
                    opcionSeleccionada === 'sub2'
                      ? 'border-uct-blue-primary bg-blue-50/60 shadow-xs'
                      : 'border-slate-200 hover:border-slate-300 bg-white'
                  }`}
                >
                  <div
                    className={`w-5 h-5 rounded-full border-2 mt-0.5 flex items-center justify-center shrink-0 ${
                      opcionSeleccionada === 'sub2'
                        ? 'border-uct-blue-primary bg-uct-blue-primary text-white'
                        : 'border-slate-300 bg-white'
                    }`}
                  >
                    {opcionSeleccionada === 'sub2' && <Check size={12} strokeWidth={3} />}
                  </div>
                  <div className="flex-1 min-w-0">
                    <span className="text-xs font-bold text-slate-900">
                      Solo Gráfico 2: {modalSubgraficos.subgraficos[1].titulo}
                    </span>
                    <p className="text-[11px] text-slate-500 mt-0.5">
                      Exporta exclusivamente la visualización y datos tabulares del segundo gráfico.
                    </p>
                  </div>
                </div>
              </div>
            </div>

            {/* Pie / Acciones */}
            <div className="p-4 sm:px-5 sm:py-3.5 bg-slate-50 border-t border-slate-200 flex items-center justify-end gap-2.5">
              <button
                type="button"
                onClick={() => setModalSubgraficos(null)}
                className="px-3.5 py-2 rounded-xl text-xs font-medium text-slate-600 hover:bg-slate-200/70 transition cursor-pointer"
              >
                Cancelar
              </button>
              <button
                type="button"
                onClick={handleConfirmarDescargaMultiple}
                className={`flex items-center gap-1.5 px-4 py-2 rounded-xl text-xs font-bold text-white transition shadow-xs cursor-pointer ${
                  modalSubgraficos.tipo === 'excel'
                    ? 'bg-emerald-700 hover:bg-emerald-800'
                    : modalSubgraficos.tipo === 'csv'
                    ? 'bg-slate-700 hover:bg-slate-800'
                    : 'bg-uct-blue-primary hover:bg-blue-900'
                }`}
              >
                <Download size={14} />
                <span>
                  Descargar {opcionSeleccionada === 'ambos' ? 'Ambos Gráficos' : 'Selección'}
                </span>
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  )
}

