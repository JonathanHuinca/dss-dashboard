import {
  GraficoNativoPayload,
  SerieGraficoNativo,
  SolicitudExportacionExcel,
  exportarGraficoExcelNativo,
  exportarConsolidadoExcelNativo,
  descargarPlantillaSalasEstudioExcel,
} from '../api/client'

export interface GraficoParaExportar {
  id: string
  titulo: string
  categoria?: string
  element: HTMLElement | null
}

export interface ResultadoExportacionMultiple {
  exitosos: number
  total: number
  errorMsg?: string
  titulosExitosos: string[]
}

/**
 * Descarga en el navegador un Blob binario con el nombre de archivo especificado.
 */
export function descargarBlob(blob: Blob, nombreArchivo: string, extensionPorDefecto = '.xlsx') {
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  const tieneExtension = /\.[a-zA-Z0-9]+$/.test(nombreArchivo)
  link.download = tieneExtension ? nombreArchivo : `${nombreArchivo}${extensionPorDefecto}`
  document.body.appendChild(link)
  link.click()
  document.body.removeChild(link)
  URL.revokeObjectURL(url)
}

/**
 * Normaliza cualquier iterable o TypedArray a un array estándar de JavaScript.
 */
function toArray<T = any>(val: any): T[] {
  if (!val) return []
  if (Array.isArray(val)) return val as T[]
  if (typeof val.length === 'number') {
    try {
      return Array.from(val) as T[]
    } catch {
      return []
    }
  }
  return []
}

/**
 * Localiza de forma exhaustiva y tolerante el elemento DOM que contiene la instancia activa de Plotly
 * inspeccionando propiedades directas (.data, ._fullData), selectores CSS y nodos hijos.
 */
export function encontrarElementoPlotly(root: HTMLElement | null, chartId?: string): any {
  if (!root && chartId) {
    // Intento de búsqueda global por identificadores conocidos
    root =
      document.querySelector<HTMLElement>(`[data-chart-id="${chartId}"]`) ||
      document.querySelector<HTMLElement>(`#chart-container-${chartId}`) ||
      null
  }

  if (!root) return null

  // 1. Verificación directa en el nodo raíz
  const rootAny = root as any
  if (toArray(rootAny.data).length > 0) return root
  if (toArray(rootAny._fullData).length > 0) return root

  // 2. Selectores CSS prioritarios de Plotly
  const selectores = [
    '.js-plotly-plot',
    '[data-plotly="true"]',
    '.plot-container',
    '.plotly',
    '.main-svg',
  ]

  for (const sel of selectores) {
    const el = root.querySelector<any>(sel)
    if (el) {
      if (toArray(el.data).length > 0) return el
      if (toArray(el._fullData).length > 0) return el
      const parent = el.closest?.('.js-plotly-plot') || el.closest?.('.plot-container')
      if (parent && (toArray(parent.data).length > 0 || toArray(parent._fullData).length > 0)) {
        return parent
      }
    }
  }

  // 3. Exploración de todos los divs internos buscando propiedades .data o ._fullData
  const todosDivs = root.getElementsByTagName('div')
  for (let i = 0; i < todosDivs.length; i++) {
    const d = todosDivs[i] as any
    if (toArray(d.data).length > 0 || toArray(d._fullData).length > 0) {
      return d
    }
  }

  return null
}

export interface SubgraficoDetectado {
  id: string
  titulo: string
  plotEl: any
  categoria?: string
}

/**
 * Detecta si una tarjeta visual contiene 2 o más subgráficos Plotly independientes
 * (ejemplo: Comparativa de Salas o Población Académica / Distribución Curricular).
 */
export function detectarSubgraficosEnElemento(
  element: HTMLElement | null,
  chartId: string,
  tituloBase: string,
  categoria = 'General'
): SubgraficoDetectado[] {
  if (!element) return []
  const plots = Array.from(element.querySelectorAll<any>('.js-plotly-plot')).filter(
    (el) => (el.data && el.data.length > 0) || (el._fullData && el._fullData.length > 0)
  )

  if (plots.length <= 1) return []

  return plots.map((p, idx) => {
    let t = p.layout?.title?.text || ''
    if (typeof t === 'string') {
      t = t.replace(/<[^>]*>/g, '').trim()
    }
    const cleanTitle = t || `${tituloBase} (Gráfico ${idx + 1})`
    return {
      id: `${chartId}_parte_${idx + 1}`,
      titulo: cleanTitle,
      plotEl: p,
      categoria,
    }
  })
}

/**
 * Extrae la especificación nativa de un gráfico Plotly o tabla HTML para que
 * el backend genere un objeto OpenXML nativo de Excel vinculado a celdas.
 */
export function extraerPayloadGraficoNativo(
  element: HTMLElement | null,
  chartId: string,
  chartTitle: string,
  categoria = 'General'
): GraficoNativoPayload | null {
  // 1. Extraer desde instancia Plotly
  const plotEl = encontrarElementoPlotly(element, chartId)

  if (plotEl) {
    const rawData = toArray<any>(plotEl.data)
    const rawFullData = toArray<any>(plotEl._fullData)
    const traces: any[] = rawData.length > 0 ? rawData : rawFullData
    const layout = plotEl.layout || plotEl._fullLayout || {}

    if (traces.length > 0) {
      // A. Gráficos de torta o dona (pie / doughnut)
      if (traces[0].type === 'pie' || traces[0].labels || traces[0]._labels) {
        const trace = traces[0]
        const labels: any[] = toArray(trace.labels || trace._labels || trace.x)
        const values: any[] = toArray(trace.values || trace._values || trace.y)

        const categorias_x: string[] = labels.map(l =>
          String(l ?? '').replace(/<[^>]*>/g, '').trim()
        )
        const valoresNumericos: (number | null)[] = values.map(v =>
          v !== undefined && v !== null && !isNaN(Number(v)) ? Number(v) : null
        )

        if (categorias_x.length > 0 && valoresNumericos.length > 0) {
          return {
            id: chartId,
            titulo: chartTitle,
            categoria,
            tipo_grafico: trace.hole && trace.hole > 0 ? 'doughnut' : 'pie',
            eje_x_nombre: 'Categoría',
            eje_y_nombre: 'Cantidad / Participación',
            categorias_x,
            series: [
              {
                nombre: trace.name || 'Distribución',
                valores: valoresNumericos,
              },
            ],
          }
        }
      }

      // B. Mapas de calor (Heatmap)
      if (traces[0].type === 'heatmap' && (traces[0].z || traces[0]._z)) {
        const trace = traces[0]
        const xLabels: any[] = toArray(trace.x || trace._x)
        const yLabels: any[] = toArray(trace.y || trace._y)
        const zMatrix: any[][] = trace.z || trace._z || []

        const categorias_x: string[] = yLabels.map(y =>
          String(y ?? '').replace(/<[^>]*>/g, '').trim()
        )
        const series: SerieGraficoNativo[] = []

        for (let c = 0; c < xLabels.length; c++) {
          const colName = String(xLabels[c] ?? '').replace(/<[^>]*>/g, '').trim()
          const colVals: (number | null)[] = []
          for (let r = 0; r < zMatrix.length; r++) {
            const val = zMatrix[r] ? zMatrix[r][c] : null
            colVals.push(val !== undefined && val !== null && !isNaN(Number(val)) ? Number(val) : 0)
          }
          series.push({
            nombre: colName.includes(':') ? colName : `${colName} hrs`,
            valores: colVals,
          })
        }

        if (categorias_x.length > 0 && series.length > 0) {
          return {
            id: chartId,
            titulo: chartTitle,
            categoria,
            tipo_grafico: 'column',
            eje_x_nombre: 'Día de la Semana',
            eje_y_nombre: 'Ocupación Promedio',
            categorias_x,
            series,
          }
        }
      }

      // C. Gráficos cartesianos (barras, líneas, áreas, dispersión)
      let tipoGraficoGeneral = 'column'
      const primerTipo = traces[0].type
      const esHorizontal = primerTipo === 'bar' && traces[0].orientation === 'h'

      if (esHorizontal) {
        // En gráficos de barras horizontales (Plotly 'h'):
        // - trace.y contiene los nombres de las categorías (ej: nombres de carreras).
        // - trace.x contiene los valores numéricos correspondientes.
        // Construimos pares y ordenamos de mayor a menor valor para generar el ranking Top.
        const rawY = toArray(traces[0].y || traces[0]._y)
        const rawX = toArray(traces[0].x || traces[0]._x)

        const itemsPares: { cat: string; val: number | null }[] = []
        for (let i = 0; i < rawY.length; i++) {
          const itemY = rawY[i]
          const cat = typeof itemY === 'string'
            ? itemY.replace(/<[^>]*>/g, ' ').trim()
            : String(itemY ?? '')
          const valNum = rawX[i] !== undefined && rawX[i] !== null && !isNaN(Number(rawX[i])) ? Number(rawX[i]) : null
          if (cat) {
            itemsPares.push({ cat, val: valNum })
          }
        }

        // Ordenar descendentemente de mayor a menor según el valor numérico
        itemsPares.sort((a, b) => (b.val ?? 0) - (a.val ?? 0))

        const categorias_x = itemsPares.map((p) => p.cat)

        const series: SerieGraficoNativo[] = traces.map((trace: any, idx: number) => {
          const nombreSerie = (trace.name || `Demanda / Visitas`).replace(/<[^>]*>/g, '').trim()
          const tY = toArray(trace.y || trace._y)
          const tX = toArray(trace.x || trace._x)
          const mapVal = new Map<string, number | null>()
          for (let i = 0; i < tY.length; i++) {
            const k = typeof tY[i] === 'string' ? tY[i].replace(/<[^>]*>/g, ' ').trim() : String(tY[i] ?? '')
            const num = tX[i] !== undefined && tX[i] !== null && !isNaN(Number(tX[i])) ? Number(tX[i]) : null
            mapVal.set(k, num)
          }

          const valoresCompletos = categorias_x.map((cat) => mapVal.get(cat) ?? null)

          let color = trace.marker?.color || trace.line?.color
          if (Array.isArray(color)) color = color[0]
          if (typeof color !== 'string' || !color.startsWith('#')) {
            color = undefined
          }

          return {
            nombre: nombreSerie,
            valores: valoresCompletos,
            color,
          }
        })

        if (categorias_x.length > 0 && series.length > 0) {
          const eje_x_nombre = layout.yaxis?.title?.text || 'Carrera / Programa Académico'
          const eje_y_nombre = layout.xaxis?.title?.text || 'Total Visitas en Período'

          return {
            id: chartId,
            titulo: chartTitle,
            categoria,
            tipo_grafico: 'bar',
            eje_x_nombre: typeof eje_x_nombre === 'string' ? eje_x_nombre.replace(/<[^>]*>/g, '').trim() : 'Carrera',
            eje_y_nombre: typeof eje_y_nombre === 'string' ? eje_y_nombre.replace(/<[^>]*>/g, '').trim() : 'Cantidad',
            categorias_x,
            series,
          }
        }
      }

      if (primerTipo === 'scatter') {
        if (traces[0].fill && traces[0].fill !== 'none') {
          tipoGraficoGeneral = 'area'
        } else {
          tipoGraficoGeneral = 'line'
        }
      } else if (primerTipo === 'bar') {
        tipoGraficoGeneral = 'column'
      } else if (primerTipo === 'line') {
        tipoGraficoGeneral = 'line'
      }

      // Recopilar conjunto unificado del eje X
      const xValuesSet = new Set<string>()
      traces.forEach((trace: any) => {
        const rawX = toArray(trace.x || trace._x)
        rawX.forEach((val: any) => {
          if (val !== undefined && val !== null) {
            const limpio = typeof val === 'string' ? val.replace(/<[^>]*>/g, ' ').trim() : String(val)
            if (limpio) xValuesSet.add(limpio)
          }
        })
      })

      let categorias_x = Array.from(xValuesSet)

      // Si no hay eje X explícito, usar índice de puntos de Y
      if (categorias_x.length === 0) {
        const maxLen = Math.max(...traces.map((t: any) => toArray(t.y || t._y).length))
        if (maxLen > 0) {
          for (let i = 1; i <= maxLen; i++) {
            categorias_x.push(`Punto ${i}`)
          }
        }
      }

      // Muestreo uniforme de protección si hay más de 1.500 categorías (ej. series continuas de meses)
      let indicesMuestreados: number[] | null = null
      if (categorias_x.length > 1500) {
        const paso = Math.ceil(categorias_x.length / 1000)
        const categoriasReducidas: string[] = []
        indicesMuestreados = []
        for (let i = 0; i < categorias_x.length; i += paso) {
          categoriasReducidas.push(categorias_x[i])
          indicesMuestreados.push(i)
        }
        categorias_x = categoriasReducidas
      }

      const series: SerieGraficoNativo[] = traces.map((trace: any, idx: number) => {
        const nombreSerie = (trace.name || `Serie ${idx + 1}`).replace(/<[^>]*>/g, '').trim()
        const rawX = toArray(trace.x || trace._x)
        const rawY = toArray(trace.y || trace._y)

        // Mapear valores por coordenada X
        const mapX = new Map<string, number | null>()
        for (let i = 0; i < rawX.length; i++) {
          const item = rawX[i]
          const k = typeof item === 'string' ? (item as string).replace(/<[^>]*>/g, ' ').trim() : String(item ?? '')
          const valNum = rawY[i] !== undefined && rawY[i] !== null && !isNaN(Number(rawY[i])) ? Number(rawY[i]) : null
          mapX.set(k, valNum)
        }

        const valoresCompletos = categorias_x.map((cat, i) => {
          if (mapX.has(cat)) {
            return mapX.get(cat) ?? null
          }
          const origIdx = indicesMuestreados ? indicesMuestreados[i] : i
          if (rawY[origIdx] !== undefined) {
            const y = rawY[origIdx]
            return y !== null && !isNaN(Number(y)) ? Number(y) : null
          }
          return null
        })

        // Color de serie
        let color = trace.marker?.color || trace.line?.color
        if (Array.isArray(color)) color = color[0]
        if (typeof color !== 'string' || !color.startsWith('#')) {
          color = undefined
        }

        let dash_type: string | undefined = undefined
        if (trace.line?.dash === 'dash') dash_type = 'dash'
        else if (trace.line?.dash === 'dot') dash_type = 'dot'

        return {
          nombre: nombreSerie,
          valores: valoresCompletos,
          color,
          dash_type,
        }
      })

      if (categorias_x.length > 0 && series.length > 0) {
        const eje_x_nombre = layout.xaxis?.title?.text || ''
        const eje_y_nombre = layout.yaxis?.title?.text || ''

        return {
          id: chartId,
          titulo: chartTitle,
          categoria,
          tipo_grafico: tipoGraficoGeneral,
          eje_x_nombre: typeof eje_x_nombre === 'string' ? eje_x_nombre.replace(/<[^>]*>/g, '').trim() : '',
          eje_y_nombre: typeof eje_y_nombre === 'string' ? eje_y_nombre.replace(/<[^>]*>/g, '').trim() : '',
          categorias_x,
          series,
        }
      }
    }
  }

  // 2. Extraer desde Tabla HTML alternativa
  const rootElement = element || (chartId ? document.querySelector<HTMLElement>(`[data-chart-id="${chartId}"]`) : null)
  if (rootElement) {
    const tableEl = rootElement.querySelector<HTMLTableElement>('table')
    if (tableEl) {
      const trElements = Array.from(tableEl.querySelectorAll('tr'))
      if (trElements.length > 0) {
        const thElements = Array.from(tableEl.querySelectorAll('thead th, tr:first-child th'))
        const headers = thElements.map(th => (th.textContent || '').trim())

        const categorias_x: string[] = []
        const seriesColMap: number[][] = []

        trElements.forEach(tr => {
          const tds = Array.from(tr.querySelectorAll('td'))
          if (tds.length > 1) {
            categorias_x.push((tds[0].textContent || '').trim())
            for (let c = 1; c < tds.length; c++) {
              if (!seriesColMap[c - 1]) seriesColMap[c - 1] = []
              const txt = (tds[c].textContent || '').trim()
              const num = Number(txt.replace(/\./g, '').replace(',', '.'))
              seriesColMap[c - 1].push(!isNaN(num) ? num : 0)
            }
          }
        })

        if (categorias_x.length > 0 && seriesColMap.length > 0) {
          const series: SerieGraficoNativo[] = seriesColMap.map((vals, i) => ({
            nombre: headers[i + 1] || `Columna ${i + 2}`,
            valores: vals,
          }))

          return {
            id: chartId,
            titulo: chartTitle,
            categoria,
            tipo_grafico: 'column',
            eje_x_nombre: headers[0] || 'Ítem',
            eje_y_nombre: 'Valor',
            categorias_x,
            series,
          }
        }
      }
    }
  }

  return null
}

/**
 * Exporta un único gráfico como archivo Excel (.xlsx) conteniendo un objeto OpenXML
 * nativo (editable, vinculado a celdas y ampliable) generado por el backend.
 */
export async function exportarGraficoAExcel(
  element: HTMLElement | null,
  filename: string,
  chartTitle: string,
  onProgreso?: (porcentaje: number, etapa?: string) => void
): Promise<boolean> {
  if (onProgreso) onProgreso(20, 'Extrayendo datos de la visualización...')

  const payload = extraerPayloadGraficoNativo(element, filename, chartTitle)
  if (!payload || payload.series.length === 0 || payload.categorias_x.length === 0) {
    console.warn('No fue posible extraer la estructura tabular para el gráfico nativo:', chartTitle)
    return false
  }

  if (onProgreso) onProgreso(60, 'Generando gráfico OpenXML nativo en servidor...')

  try {
    const blob = await exportarGraficoExcelNativo(payload)
    if (onProgreso) onProgreso(90, 'Descargando archivo Excel...')
    descargarBlob(blob, `${filename}_nativo.xlsx`)
    if (onProgreso) onProgreso(100, '¡Descarga completada!')
    return true
  } catch (err) {
    console.error('Error al generar gráfico nativo en backend:', err)
    return false
  }
}

/**
 * Exporta los subgráficos de una tarjeta específica a un libro Excel consolidado (.xlsx)
 * con una pestaña independiente para cada visualización.
 */
export async function exportarSubgraficosCombinadosAExcel(
  subgraficos: SubgraficoDetectado[],
  filename: string,
  tituloTarjeta: string,
  onProgreso?: (porcentaje: number, etapa?: string) => void
): Promise<boolean> {
  const listaPayloads: GraficoNativoPayload[] = []
  const total = subgraficos.length

  for (let i = 0; i < total; i++) {
    const sub = subgraficos[i]
    if (onProgreso) {
      onProgreso(20 + Math.round((i / total) * 40), `Extrayendo datos de: ${sub.titulo}`)
    }
    const p = extraerPayloadGraficoNativo(sub.plotEl, sub.id, sub.titulo, sub.categoria || 'General')
    if (p && p.series.length > 0 && p.categorias_x.length > 0) {
      listaPayloads.push(p)
    }
  }

  if (listaPayloads.length === 0) {
    throw new Error('No se encontraron datos estructurados en los gráficos seleccionados.')
  }

  if (onProgreso) {
    onProgreso(75, 'Compilando libro Excel institucional con múltiples pestañas...')
  }

  const solicitud: SolicitudExportacionExcel = {
    modulo_nombre: 'Dashboard DSS Campus San Francisco - UCT',
    periodo_label: tituloTarjeta,
    filtros: { 'Tarjeta': tituloTarjeta, 'Visualizaciones': `${listaPayloads.length} gráficos integrados` },
    graficos: listaPayloads,
  }

  const blob = await exportarConsolidadoExcelNativo(solicitud)
  if (onProgreso) {
    onProgreso(95, 'Descargando archivo Excel...')
  }
  descargarBlob(blob, `${filename}.xlsx`)
  return true
}

/**
 * Exporta múltiples gráficos seleccionados a un único libro Excel (.xlsx)
 * con objetos OpenXML nativos de Excel y hoja de Resumen Ejecutivo.
 */
export async function exportarMultiplesGraficosAExcel(
  graficos: GraficoParaExportar[],
  filename = 'DSS_UCT_Reporte_Consolidado',
  metadatos?: Record<string, string>,
  onProgreso?: (actual: number, total: number, titulo: string, etapa?: string) => void
): Promise<ResultadoExportacionMultiple> {
  const listaPayloads: GraficoNativoPayload[] = []
  const titulosExitosos: string[] = []
  const total = graficos.length

  for (let i = 0; i < graficos.length; i++) {
    const item = graficos[i]
    if (onProgreso) {
      onProgreso(i + 1, total, item.titulo, `Extrayendo datos del gráfico ${i + 1} de ${total}: ${item.titulo}`)
    }

    // Detectar si el elemento contiene más de 1 gráfico integrado (ej: Comparativa Salas o Población Curricular)
    const subgraficos = detectarSubgraficosEnElemento(item.element, item.id, item.titulo, item.categoria)
    if (subgraficos.length > 1) {
      for (const sub of subgraficos) {
        const subPayload = extraerPayloadGraficoNativo(sub.plotEl, sub.id, sub.titulo, item.categoria)
        if (subPayload && subPayload.series.length > 0 && subPayload.categorias_x.length > 0) {
          listaPayloads.push(subPayload)
          titulosExitosos.push(sub.titulo)
        }
      }
    } else {
      const payload = extraerPayloadGraficoNativo(item.element, item.id, item.titulo, item.categoria)
      if (payload && payload.series.length > 0 && payload.categorias_x.length > 0) {
        listaPayloads.push(payload)
        titulosExitosos.push(item.titulo)
      }
    }
  }

  if (listaPayloads.length === 0) {
    return {
      exitosos: 0,
      total,
      titulosExitosos: [],
      errorMsg:
        'No se encontraron datos listos en pantalla en los gráficos seleccionados. Asegúrate de que las visualizaciones hayan terminado de cargar sus datos antes de exportar.',
    }
  }

  if (onProgreso) {
    onProgreso(
      listaPayloads.length,
      total,
      'Compilando Libro Excel',
      `Enviando ${listaPayloads.length} gráficos al motor OpenXML del servidor...`
    )
  }

  const solicitud: SolicitudExportacionExcel = {
    modulo_nombre: 'Dashboard DSS Campus San Francisco - UCT',
    periodo_label: metadatos?.['Período Evaluado'] || 'Período Activo',
    filtros: metadatos || {},
    graficos: listaPayloads,
  }

  try {
    const blob = await exportarConsolidadoExcelNativo(solicitud)
    if (onProgreso) {
      onProgreso(listaPayloads.length, total, 'Descargando Archivo', 'Descargando archivo Excel consolidado...')
    }
    descargarBlob(blob, `${filename}.xlsx`)
    return {
      exitosos: listaPayloads.length,
      total,
      titulosExitosos,
    }
  } catch (err: any) {
    console.error('Error generando libro consolidado nativo en backend:', err)
    let msg = err?.message || 'Error de comunicación con el servicio de exportación Excel.'
    if (err?.response?.data) {
      if (typeof err.response.data.text === 'function') {
        try {
          const raw = await err.response.data.text()
          const json = JSON.parse(raw)
          if (json.detail) msg = json.detail
        } catch {
          // Si no es json se mantiene msg
        }
      } else if (err.response.data.detail) {
        msg = err.response.data.detail
      }
    }
    return {
      exitosos: 0,
      total,
      titulosExitosos: [],
      errorMsg: `Fallo al generar el libro consolidado: ${msg}`,
    }
  }
}

/**
 * Exporta el Reporte Oficial Institucional de Salas de Estudio (Plantilla UCT)
 * directamente desde el backend mediante consultas maestras en la base de datos.
 */
export async function exportarPlantillaOficialSalasEstudio(
  params: {
    espacio_id?: number
    fecha_inicio?: string
    fecha_fin?: string
    alcance?: string
    regimen_horario?: string
    direccion?: string
    dias_semana?: string
    door?: string
    carrera?: string
    facultad?: string
    periodo_label?: string
  },
  onProgreso?: (porcentaje: number, etapa?: string) => void
): Promise<boolean> {
  if (onProgreso) onProgreso(25, 'Consultando parámetros y base de datos institucional...')

  try {
    if (onProgreso) onProgreso(60, 'Generando reporte de 4 tablas maestras y 5 gráficos oscuros...')
    const blob = await descargarPlantillaSalasEstudioExcel(params)
    const periodoSaneado = (params.periodo_label || 'Periodo')
      .replace(/[^a-zA-Z0-9]/g, '_')
      .replace(/^_+|_+$/g, '')

    if (onProgreso) onProgreso(95, 'Descargando archivo Excel en equipo local...')
    descargarBlob(blob, `Reporte_Salas_Estudios_${periodoSaneado}.xlsx`)
    if (onProgreso) onProgreso(100, '¡Descarga completada!')
    return true
  } catch (err) {
    console.error('Error descargando plantilla oficial de salas de estudio:', err)
    throw err
  }
}
