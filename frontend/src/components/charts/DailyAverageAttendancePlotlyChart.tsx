import React, { useState } from 'react'
import { InteractiveChart } from '../ui/InteractiveChart'
import { DailyAverageResponse } from '../../api/client'
import { Data, Layout } from 'plotly.js-dist-min'
import { Calendar, TrendingUp, Users, Award, Info, BarChart3, Layers } from 'lucide-react'

interface Props {
  data?: DailyAverageResponse
}

type VistaModo = 'desglose_salas' | 'total' | 'ocupacion_relativa'

export function DailyAverageAttendancePlotlyChart({ data }: Props) {
  const [vista, setVista] = useState<VistaModo>('desglose_salas')

  const dias = data?.dias && data.dias.length > 0
    ? data.dias
    : [
      { dia_num: 1, dia_nombre: 'Lunes', dia_corto: 'Lun', dias_muestreados: 0, promedio_entradas_total: 0, promedio_entradas_sala1: 0, promedio_entradas_sala2: 0, total_entradas_acumuladas: 0, ocupacion_relativa_sala1_pct: 0, ocupacion_relativa_sala2_pct: 0 },
      { dia_num: 2, dia_nombre: 'Martes', dia_corto: 'Mar', dias_muestreados: 0, promedio_entradas_total: 0, promedio_entradas_sala1: 0, promedio_entradas_sala2: 0, total_entradas_acumuladas: 0, ocupacion_relativa_sala1_pct: 0, ocupacion_relativa_sala2_pct: 0 },
      { dia_num: 3, dia_nombre: 'Miércoles', dia_corto: 'Mié', dias_muestreados: 0, promedio_entradas_total: 0, promedio_entradas_sala1: 0, promedio_entradas_sala2: 0, total_entradas_acumuladas: 0, ocupacion_relativa_sala1_pct: 0, ocupacion_relativa_sala2_pct: 0 },
      { dia_num: 4, dia_nombre: 'Jueves', dia_corto: 'Jue', dias_muestreados: 0, promedio_entradas_total: 0, promedio_entradas_sala1: 0, promedio_entradas_sala2: 0, total_entradas_acumuladas: 0, ocupacion_relativa_sala1_pct: 0, ocupacion_relativa_sala2_pct: 0 },
      { dia_num: 5, dia_nombre: 'Viernes', dia_corto: 'Vie', dias_muestreados: 0, promedio_entradas_total: 0, promedio_entradas_sala1: 0, promedio_entradas_sala2: 0, total_entradas_acumuladas: 0, ocupacion_relativa_sala1_pct: 0, ocupacion_relativa_sala2_pct: 0 },
      { dia_num: 6, dia_nombre: 'Sábado', dia_corto: 'Sáb', dias_muestreados: 0, promedio_entradas_total: 0, promedio_entradas_sala1: 0, promedio_entradas_sala2: 0, total_entradas_acumuladas: 0, ocupacion_relativa_sala1_pct: 0, ocupacion_relativa_sala2_pct: 0 },
    ]

  const resumen = data?.resumen || {
    dia_mayor_afluencia: 'N/A',
    pico_promedio_diario: 0,
    sala1_capacidad: 124,
    sala2_capacidad: 226,
    total_dias_evaluados: 0,
  }

  // Filtrar domingos si no hubo actividad registrada
  const diasFiltrados = dias.filter(d => d.dias_muestreados > 0 || d.promedio_entradas_total > 0 || d.dia_num <= 6)

  const etiquetasX = diasFiltrados.map(d => `${d.dia_nombre}<br><span style="font-size:9px;color:#94A3B8">(${d.dias_muestreados} días)</span>`)

  // Construcción de trazas según la vista
  let plotData: Data[] = []

  if (vista === 'desglose_salas') {
    plotData = [
      {
        x: etiquetasX,
        y: diasFiltrados.map(d => d.promedio_entradas_sala1),
        name: 'Sala 1 (CSF02 — 124 asientos)',
        type: 'bar',
        marker: {
          color: '#002B49',
          line: { color: '#001A2C', width: 1 },
        },
        text: diasFiltrados.map(d => `${d.promedio_entradas_sala1.toFixed(0)}`),
        textposition: 'auto',
        textfont: { color: '#FFFFFF', size: 10, family: 'Inter, sans-serif' },
        hovertemplate:
          '<b>%{x}</b><br>' +
          'Promedio Sala 1: <b>%{y:.1f} ingresos/día</b><br>' +
          'Capacidad física: 124 asientos<extra></extra>',
      },
      {
        x: etiquetasX,
        y: diasFiltrados.map(d => d.promedio_entradas_sala2),
        name: 'Sala 2 (CSF04 Pecera — 226 asientos)',
        type: 'bar',
        marker: {
          color: '#C59B27',
          line: { color: '#9A781D', width: 1 },
        },
        text: diasFiltrados.map(d => `${d.promedio_entradas_sala2.toFixed(0)}`),
        textposition: 'auto',
        textfont: { color: '#FFFFFF', size: 10, family: 'Inter, sans-serif' },
        hovertemplate:
          '<b>%{x}</b><br>' +
          'Promedio Sala 2: <b>%{y:.1f} ingresos/día</b><br>' +
          'Capacidad física: 226 asientos<extra></extra>',
      },
      {
        x: etiquetasX,
        y: diasFiltrados.map(d => d.promedio_entradas_total),
        name: 'Promedio Total Diario',
        type: 'scatter',
        mode: 'text+lines+markers',
        line: { color: '#0284C7', width: 2.5, dash: 'solid', shape: 'spline' },
        marker: { size: 7, color: '#0284C7', symbol: 'diamond' },
        text: diasFiltrados.map(d => `${d.promedio_entradas_total.toFixed(0)}`),
        textposition: 'top center',
        textfont: { color: '#0369A1', size: 11, family: 'Inter, sans-serif' },
        hovertemplate:
          '<b>%{x}</b><br>' +
          'Promedio Total Biblioteca: <b>%{y:.1f} ingresos/día</b><extra></extra>',
      },
    ]
  } else if (vista === 'total') {
    plotData = [
      {
        x: etiquetasX,
        y: diasFiltrados.map(d => d.promedio_entradas_total),
        name: 'Promedio Ingresos Totales',
        type: 'bar',
        marker: {
          color: diasFiltrados.map(d =>
            d.dia_nombre === resumen.dia_mayor_afluencia ? '#002B49' : '#38BDF8'
          ),
          line: { color: '#0369A1', width: 1.5 },
        },
        text: diasFiltrados.map(d => `${d.promedio_entradas_total.toFixed(1)} ing/d`),
        textposition: 'outside',
        textfont: { color: '#0F172A', size: 11, family: 'Inter, sans-serif' },
        hovertemplate:
          '<b>%{x}</b><br>' +
          'Promedio Ingresos: <b>%{y:.1f} personas/día</b><br>' +
          'Muestreo: %{text}<extra></extra>',
      },
    ]
  } else {
    // ocupacion_relativa
    plotData = [
      {
        x: etiquetasX,
        y: diasFiltrados.map(d => d.ocupacion_relativa_sala1_pct),
        name: 'Sala 1 — Rotación Diaria (% sobre 124 asientos)',
        type: 'bar',
        marker: { color: '#002B49' },
        text: diasFiltrados.map(d => `${d.ocupacion_relativa_sala1_pct.toFixed(0)}%`),
        textposition: 'auto',
        textfont: { color: '#FFFFFF', size: 10 },
        hovertemplate:
          '<b>%{x}</b><br>' +
          'Rotación Sala 1: <b>%{y:.1f}%</b> de la capacidad física<br>' +
          'Base: 124 asientos<extra></extra>',
      },
      {
        x: etiquetasX,
        y: diasFiltrados.map(d => d.ocupacion_relativa_sala2_pct),
        name: 'Sala 2 — Rotación Diaria (% sobre 226 asientos)',
        type: 'bar',
        marker: { color: '#C59B27' },
        text: diasFiltrados.map(d => `${d.ocupacion_relativa_sala2_pct.toFixed(0)}%`),
        textposition: 'auto',
        textfont: { color: '#FFFFFF', size: 10 },
        hovertemplate:
          '<b>%{x}</b><br>' +
          'Rotación Sala 2: <b>%{y:.1f}%</b> de la capacidad física<br>' +
          'Base: 226 asientos<extra></extra>',
      },
    ]
  }

  const layout: Partial<Layout> = {
    autosize: true,
    barmode: vista === 'desglose_salas' ? 'group' : 'group',
    margin: { t: 25, r: 20, b: 50, l: 45 },
    xaxis: {
      automargin: true,
      tickfont: { size: 11, color: '#334155' },
      gridcolor: '#F8FAFC',
    },
    yaxis: {
      title: {
        text: vista === 'ocupacion_relativa' ? 'Rotación sobre Capacidad (%)' : 'Ingresos Promedio / Día',
        font: { size: 11, color: '#475569' },
      },
      automargin: true,
      tickfont: { size: 10, color: '#64748B' },
      gridcolor: '#F1F5F9',
    },
    legend: {
      orientation: 'h',
      x: 0.5,
      xanchor: 'center',
      y: -0.22,
      font: { size: 10, color: '#334155' },
    },
    paper_bgcolor: 'transparent',
    plot_bgcolor: 'transparent',
  }

  return (
    <div className="w-full h-full flex flex-col space-y-3.5">
      {/* Barra Superior con KPIs Resumen y Selector de Modo */}
      <div className="flex flex-wrap items-center justify-between gap-3 bg-slate-50/80 p-2.5 rounded-xl border border-slate-200/80">
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-2 bg-white px-3 py-1.5 rounded-lg border border-slate-200 shadow-2xs">
            <Award className="w-4 h-4 text-amber-500" />
            <span className="text-xs text-slate-500">Día Pico Promedio:</span>
            <span className="text-xs font-bold text-slate-800">
              {resumen.dia_mayor_afluencia} ({resumen.pico_promedio_diario.toFixed(1)} ing/d)
            </span>
          </div>
          <div className="hidden sm:flex items-center gap-2 bg-white px-3 py-1.5 rounded-lg border border-slate-200 shadow-2xs">
            <Calendar className="w-4 h-4 text-sky-600" />
            <span className="text-xs text-slate-500">Días muestreados:</span>
            <span className="text-xs font-bold text-slate-800">{resumen.total_dias_evaluados} fechas</span>
          </div>
        </div>

        {/* Selector de Vista */}
        <div className="flex items-center gap-1 bg-slate-200/70 p-0.5 rounded-lg text-xs">
          <button
            onClick={() => setVista('desglose_salas')}
            className={`px-2.5 py-1 rounded-md font-medium transition-all ${
              vista === 'desglose_salas'
                ? 'bg-white text-slate-900 shadow-2xs'
                : 'text-slate-600 hover:text-slate-900'
            }`}
          >
            Salas 1 y 2
          </button>
          <button
            onClick={() => setVista('total')}
            className={`px-2.5 py-1 rounded-md font-medium transition-all ${
              vista === 'total'
                ? 'bg-white text-slate-900 shadow-2xs'
                : 'text-slate-600 hover:text-slate-900'
            }`}
          >
            Total Biblioteca
          </button>
          <button
            onClick={() => setVista('ocupacion_relativa')}
            className={`px-2.5 py-1 rounded-md font-medium transition-all ${
              vista === 'ocupacion_relativa'
                ? 'bg-white text-slate-900 shadow-2xs'
                : 'text-slate-600 hover:text-slate-900'
            }`}
          >
            % Capacidad
          </button>
        </div>
      </div>

      {/* Gráfico Principal Plotly */}
      <div className="w-full flex-1 min-h-[320px]">
        <InteractiveChart
          data={plotData}
          layout={layout}
          className="w-full h-full min-h-[320px]"
          config={{
            responsive: true,
            displayModeBar: false,
          }}
        />
      </div>

      {/* Pie descriptivo con información metodológica de cálculo */}
      <div className="flex items-start gap-2 text-[11px] text-slate-500 bg-slate-50/60 p-2 rounded-lg border border-slate-100">
        <Info className="w-3.5 h-3.5 text-slate-400 mt-0.5 shrink-0" />
        <p>
          <strong>Metodología de Cálculo:</strong> El promedio diario por día de semana se calcula dividiendo el total
          de entradas registradas en cada día entre el conteo exacto de fechas únicas transcurridas en el período y
          filtros activos (<code className="text-slate-600">COUNT(DISTINCT fecha)</code>), evitando sesgos por semanas
          incompletas o feriados.
        </p>
      </div>
    </div>
  )
}
export default DailyAverageAttendancePlotlyChart
