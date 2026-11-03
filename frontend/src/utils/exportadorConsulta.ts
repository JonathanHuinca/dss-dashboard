import { api } from '../api/clienteBase'
import {
  exportarGraficoExcelNativo,
  GraficoNativoPayload,
  SerieGraficoNativo,
} from '../api/administracion'
import { extraerPayloadGraficoNativo, descargarBlob } from './excelExport'

export interface OpcionesExportacionConsulta {
  pregunta: string
  respuesta: string
  payload?: any
  tableData?: Record<string, any>[]
  elementoId?: string
  espacioId?: number
  titulo?: string
  component?: string
  figData?: { data: any[]; layout: any }
}

/**
 * Captura un elemento del DOM (gráfico o tabla) en una imagen PNG base64 de alta resolución.
 */
export async function capturarElementoGrafico(elementoId: string): Promise<string | null> {
  const el = document.getElementById(elementoId)
  if (!el) return null
  try {
    const html2canvas = (await import('html2canvas')).default
    const canvas = await html2canvas(el, {
      scale: 2,
      backgroundColor: '#FFFFFF',
      logging: false,
      useCORS: true,
    })
    return canvas.toDataURL('image/png')
  } catch (err) {
    console.warn('No se pudo capturar el gráfico en imagen:', err)
    return null
  }
}

/**
 * Extrae filas tabulares normalizadas desde el payload o tableData de la consulta.
 */
function normalizarFilasTabulares(payload?: any, tableData?: Record<string, any>[]): Record<string, any>[] {
  if (Array.isArray(tableData) && tableData.length > 0 && typeof tableData[0] === 'object') {
    return tableData
  }
  if (Array.isArray(payload) && payload.length > 0 && typeof payload[0] === 'object') {
    return payload
  }
  if (payload && typeof payload === 'object') {
    if (Array.isArray(payload.forecast)) return payload.forecast
    if (Array.isArray(payload.pronostico_7d)) return payload.pronostico_7d
    if (Array.isArray(payload.predicciones)) return payload.predicciones
    if (Array.isArray(payload.puntos)) return payload.puntos
  }
  return []
}

/**
 * Construye un payload nativo de gráfico para Excel OpenXML a partir de datos structured
 * (figData de Plotly o registros tabulares de la consulta).
 */
function construirPayloadGraficoDesdeDatos(opciones: OpcionesExportacionConsulta): GraficoNativoPayload | null {
  const chartId = `chat_chart_${Date.now()}`
  const chartTitle = opciones.titulo || opciones.pregunta || 'Consulta Analítica DSS UCT'
  const categoria = opciones.espacioId === 2 ? 'Estacionamiento CSF' : 'Biblioteca CSF'

  // Caso 1: Estructura Plotly figData
  if (opciones.figData && Array.isArray(opciones.figData.data) && opciones.figData.data.length > 0) {
    const traces = opciones.figData.data
    const xSet = new Set<string>()
    traces.forEach((t: any) => {
      const rawX = Array.isArray(t.x) ? t.x : []
      rawX.forEach((x: any) => {
        if (x !== undefined && x !== null) {
          xSet.add(String(x).replace(/<[^>]*>/g, '').trim())
        }
      })
    })

    const categorias_x = Array.from(xSet)
    if (categorias_x.length > 0) {
      const series: SerieGraficoNativo[] = traces.map((t: any, idx: number) => {
        const rawX = Array.isArray(t.x) ? t.x : []
        const rawY = Array.isArray(t.y) ? t.y : []
        const mapVal = new Map<string, number | null>()
        for (let i = 0; i < rawX.length; i++) {
          const k = String(rawX[i]).replace(/<[^>]*>/g, '').trim()
          const v = rawY[i]
          mapVal.set(k, v !== null && v !== undefined && !isNaN(Number(v)) ? Number(v) : null)
        }

        let color = typeof t.marker?.color === 'string' ? t.marker.color : undefined
        if (!color && typeof t.line?.color === 'string') color = t.line.color

        return {
          nombre: (t.name || `Serie ${idx + 1}`).replace(/<[^>]*>/g, '').trim(),
          valores: categorias_x.map(cat => mapVal.get(cat) ?? null),
          color: color?.startsWith('#') ? color : undefined,
          dash_type: t.line?.dash === 'dash' ? 'dash' : (t.line?.dash === 'dot' ? 'dot' : undefined),
        }
      })

      const primerTipo = traces[0]?.type
      let tipoGrafico = 'column'
      if (primerTipo === 'scatter') {
        tipoGrafico = traces[0]?.fill && traces[0]?.fill !== 'none' ? 'area' : 'line'
      } else if (primerTipo === 'bar') {
        tipoGrafico = traces[0]?.orientation === 'h' ? 'bar' : 'column'
      } else if (primerTipo === 'pie') {
        tipoGrafico = 'doughnut'
      }

      return {
        id: chartId,
        titulo: chartTitle,
        categoria,
        tipo_grafico: tipoGrafico,
        eje_x_nombre: opciones.figData.layout?.xaxis?.title?.text || 'Categoría / Período',
        eje_y_nombre: opciones.figData.layout?.yaxis?.title?.text || 'Cantidad / Aforo',
        categorias_x,
        series,
        subtitulo: opciones.pregunta,
      }
    }
  }

  // Caso 2: Filas tabulares (payload o tableData)
  const filas = normalizarFilasTabulares(opciones.payload, opciones.tableData)
  if (filas.length > 0) {
    const columnKeys = Object.keys(filas[0])
    const candidatosX = ['bucket', 'fecha', 'dia', 'semana', 'mes', 'hora', 'label', 'carrera', 'sector', 'nombre', 'camara', 'puerta']
    let xKey = columnKeys.find(k => candidatosX.includes(k.toLowerCase()))
    if (!xKey) {
      xKey = columnKeys.find(k => typeof filas[0][k] === 'string') || columnKeys[0]
    }

    const categorias_x = filas.map(f => String(f[xKey] ?? ''))
    const numericKeys = columnKeys.filter(k => k !== xKey && filas.some(f => {
      const v = f[k]
      return typeof v === 'number' || (typeof v === 'string' && /^-?\d+(\.\d+)?$/.test(v.trim()))
    }))

    if (numericKeys.length > 0 && categorias_x.length > 0) {
      const series: SerieGraficoNativo[] = numericKeys.map(k => ({
        nombre: k.replace(/_/g, ' ').toUpperCase(),
        valores: filas.map(f => {
          const v = f[k]
          if (typeof v === 'number') return v
          if (typeof v === 'string' && !isNaN(Number(v))) return Number(v)
          return null
        }),
      }))

      let tipoGrafico = 'column'
      if (opciones.component === 'OccupancyAreaChart') tipoGrafico = 'area'
      else if (opciones.component === 'ForecastLineChart') tipoGrafico = 'line'
      else if (opciones.component === 'FleetDonutChart') tipoGrafico = 'doughnut'

      return {
        id: chartId,
        titulo: chartTitle,
        categoria,
        tipo_grafico: tipoGrafico,
        eje_x_nombre: xKey.replace(/_/g, ' ').toUpperCase(),
        eje_y_nombre: 'Cantidad / Aforo',
        categorias_x,
        series,
        subtitulo: opciones.pregunta,
      }
    }
  }

  return null
}

/**
 * Exporta el informe ejecutivo en formato PDF con la consulta, respuesta y gráfico incrustado.
 */
export async function exportarConsultaPdf(opciones: OpcionesExportacionConsulta): Promise<void> {
  const { pregunta, respuesta, elementoId, espacioId = 1, titulo } = opciones
  const filas = normalizarFilasTabulares(opciones.payload, opciones.tableData)

  let graficoB64: string | null = null
  if (elementoId) {
    graficoB64 = await capturarElementoGrafico(elementoId)
  }

  const payloadReq: Record<string, any> = {
    session_id: `consulta-${Date.now()}`,
    espacio_id: espacioId,
    titulo: titulo || 'Informe Ejecutivo de Consulta Analítica — DSS UCT',
    consulta_texto: pregunta,
    respuesta_texto: respuesta,
    datos_tabla: filas.length > 0 ? filas.slice(0, 50) : undefined,
  }

  if (graficoB64) {
    payloadReq.graficos_b64 = { single: graficoB64 }
  }

  const res = await api.post('/chat/export-pdf', payloadReq, { responseType: 'blob' })
  const blob = new Blob([res.data], { type: 'application/pdf' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `Informe_UCT_${new Date().toISOString().slice(0, 10)}.pdf`
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  URL.revokeObjectURL(url)
}

/**
 * Exporta un libro Excel (.xlsx) con un gráfico OpenXML nativo (editable y vinculado a celdas)
 * idéntico al estándar generado por las tarjetas del dashboard (ChartCard).
 */
export async function exportarConsultaExcel(opciones: OpcionesExportacionConsulta): Promise<void> {
  const { pregunta, respuesta, elementoId, espacioId = 1, titulo } = opciones
  const categoria = espacioId === 2 ? 'Estacionamiento CSF' : 'Biblioteca CSF'
  const chartTitle = titulo || pregunta || 'Consulta Analítica DSS UCT'
  const chartId = `chat_grafico_${Date.now()}`

  // 1. Intentar extracción desde el elemento visual en pantalla (Plotly o tabla)
  let payloadNativo: GraficoNativoPayload | null = null
  if (elementoId) {
    const el = document.getElementById(elementoId)
    if (el) {
      payloadNativo = extraerPayloadGraficoNativo(el, chartId, chartTitle, categoria)
    }
  }

  // 2. Si no se extrajo del DOM, construirlo desde la estructura de datos
  if (!payloadNativo || payloadNativo.series.length === 0 || payloadNativo.categorias_x.length === 0) {
    payloadNativo = construirPayloadGraficoDesdeDatos(opciones)
  }

  // 3. Si se dispone de estructura para gráfico nativo, delegar a la API oficial de Excel OpenXML
  if (payloadNativo && payloadNativo.series.length > 0 && payloadNativo.categorias_x.length > 0) {
    try {
      const blob = await exportarGraficoExcelNativo(payloadNativo)
      const nombreSaneado = chartTitle
        .replace(/[^a-zA-Z0-9_-]/g, '_')
        .replace(/^_+|_+$/g, '')
        .slice(0, 35) || 'Consulta_Analitica'

      descargarBlob(blob, `Reporte_UCT_${nombreSaneado}_nativo_${new Date().toISOString().slice(0, 10)}.xlsx`)
      return
    } catch (apiErr) {
      console.warn('Error en servicio de gráfico nativo OpenXML backend, recurriendo a generador alternativo:', apiErr)
    }
  }

  // 4. Respaldo dinámico mediante exceljs para consultas sin series numéricas
  const filas = normalizarFilasTabulares(opciones.payload, opciones.tableData)
  const ExcelJS = (await import('exceljs')).default
  const workbook = new ExcelJS.Workbook()
  workbook.creator = 'Sistema DSS UCT Campus San Francisco'
  workbook.created = new Date()

  const sheetResumen = workbook.addWorksheet('Resumen Analítico')
  sheetResumen.views = [{ showGridLines: true }]

  sheetResumen.mergeCells('A1:G1')
  const titleCell = sheetResumen.getCell('A1')
  titleCell.value = 'UNIVERSIDAD CATÓLICA DE TEMUCO — SISTEMA DSS'
  titleCell.font = { name: 'Calibri', size: 14, bold: true, color: { argb: 'FFFFFFFF' } }
  titleCell.fill = { type: 'pattern', pattern: 'solid', fgColor: { argb: 'FF002B49' } }
  titleCell.alignment = { horizontal: 'center', vertical: 'middle' }
  sheetResumen.getRow(1).height = 32

  sheetResumen.mergeCells('A2:G2')
  const subCell = sheetResumen.getCell('A2')
  subCell.value = 'Reporte Analítico Oficial — Plataforma de Toma de Decisiones (Ley N° 21.719)'
  subCell.font = { name: 'Calibri', size: 9, italic: true, color: { argb: 'FF64748B' } }
  subCell.alignment = { horizontal: 'center', vertical: 'middle' }

  sheetResumen.getCell('A4').value = 'Fecha de Emisión:'
  sheetResumen.getCell('A4').font = { bold: true }
  sheetResumen.getCell('B4').value = new Date().toLocaleString('es-CL')

  sheetResumen.getCell('A5').value = 'Módulo Institucional:'
  sheetResumen.getCell('A5').font = { bold: true }
  sheetResumen.getCell('B5').value = categoria

  sheetResumen.getCell('A7').value = 'Consulta Realizada:'
  sheetResumen.getCell('A7').font = { bold: true, color: { argb: 'FF003865' } }
  sheetResumen.mergeCells('A8:G8')
  const qCell = sheetResumen.getCell('A8')
  qCell.value = pregunta
  qCell.font = { bold: true, size: 10 }
  qCell.fill = { type: 'pattern', pattern: 'solid', fgColor: { argb: 'FFF1F5F9' } }
  sheetResumen.getRow(8).height = 24

  sheetResumen.getCell('A10').value = 'Interpretación Analítica Institucional:'
  sheetResumen.getCell('A10').font = { bold: true, color: { argb: 'FF003865' } }
  sheetResumen.mergeCells('A11:G15')
  const descCell = sheetResumen.getCell('A11')
  descCell.value = respuesta
  descCell.alignment = { wrapText: true, vertical: 'top' }
  descCell.font = { size: 9.5 }

  if (filas.length > 0) {
    const sheetDatos = workbook.addWorksheet('Datos_Modificables')
    sheetDatos.views = [{ showGridLines: true }]
    const columnKeys = Object.keys(filas[0])
    sheetDatos.columns = columnKeys.map(k => ({
      header: k.replace(/_/g, ' ').toUpperCase(),
      key: k,
      width: Math.max(16, k.length + 4),
    }))

    const headerRow = sheetDatos.getRow(1)
    headerRow.height = 26
    headerRow.eachCell(cell => {
      cell.fill = { type: 'pattern', pattern: 'solid', fgColor: { argb: 'FF002B49' } }
      cell.font = { name: 'Calibri', size: 10, bold: true, color: { argb: 'FFFFFFFF' } }
      cell.alignment = { horizontal: 'center', vertical: 'middle' }
    })

    filas.forEach(f => {
      const rowData: Record<string, any> = {}
      columnKeys.forEach(k => {
        const val = f[k]
        rowData[k] = typeof val === 'number' ? val : (val ?? '')
      })
      sheetDatos.addRow(rowData)
    })
  }

  const buffer = await workbook.xlsx.writeBuffer()
  const blob = new Blob([buffer], { type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' })
  descargarBlob(blob, `Datos_UCT_${new Date().toISOString().slice(0, 10)}.xlsx`)
}
