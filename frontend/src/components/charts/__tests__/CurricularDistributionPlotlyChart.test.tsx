import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { CurricularDistributionPlotlyChart } from '../CurricularDistributionPlotlyChart'
import type { CurricularDistributionResponse } from '../../../api/client'

vi.mock('../../ui/InteractiveChart', () => ({
  InteractiveChart: ({ filename, data }: { filename?: string; data: unknown[] }) => (
    <div data-testid={`plotly-mock-${filename ?? 'chart'}`} data-traces={String(data?.length ?? 0)} />
  ),
}))

const DATA_MOCK: CurricularDistributionResponse = {
  espacio_id: 1,
  total_estudiantes_catalogados: 500,
  total_estudiantes_asistentes: 180,
  total_eventos_asistencia: 450,
  total_registros_sin_identificar: 10,
  cobertura_identificacion_pct: 95,
  carreras: [
    {
      carrera: 'Ingeniería Civil Informática',
      facultad: 'Ingeniería',
      total_estudiantes: 120,
      estudiantes_asistentes: 90,
      eventos_asistencia: 250,
      porcentaje: 50,
      porcentaje_asistentes: 50,
      porcentaje_eventos: 55.5,
    },
    {
      carrera: 'Derecho',
      facultad: 'Ciencias Jurídicas',
      total_estudiantes: 100,
      estudiantes_asistentes: 90,
      eventos_asistencia: 200,
      porcentaje: 50,
      porcentaje_asistentes: 50,
      porcentaje_eventos: 44.5,
    },
  ],
  facultades: [
    {
      facultad: 'Ingeniería',
      total_estudiantes: 120,
      estudiantes_asistentes: 90,
      eventos_asistencia: 250,
      porcentaje: 55,
      porcentaje_asistentes: 50,
      porcentaje_eventos: 55.5,
    },
  ],
  cohortes: [
    {
      cohorte: 2024,
      etiqueta: 'Cohorte 2024',
      total_estudiantes: 80,
      estudiantes_asistentes: 60,
      eventos_asistencia: 190,
      porcentaje: 40,
      porcentaje_asistentes: 33,
      porcentaje_eventos: 42,
    },
  ],
}

describe('CurricularDistributionPlotlyChart', () => {
  it('renderiza estado vacío seguro sin violar Rules of Hooks cuando data es undefined', () => {
    render(<CurricularDistributionPlotlyChart data={undefined} />)
    expect(screen.getByText(/Sin datos curriculares disponibles/i)).toBeInTheDocument()
  })

  it('alterna agrupaciones y métricas manteniendo render consistente', () => {
    render(<CurricularDistributionPlotlyChart data={DATA_MOCK} />)
    expect(screen.getByTestId('plotly-mock-distribucion_carreras_visitas_uct')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: /Por Facultad/i }))
    expect(screen.getByTestId('plotly-mock-distribucion_facultades_visitas_uct')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: /Por Cantidad de Alumnos/i }))
    expect(screen.getByTestId('plotly-mock-distribucion_facultades_alumnos_uct')).toBeInTheDocument()
  })
})
