import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ReporteCompartidoView } from '../ReporteCompartidoView'
import * as apiClient from '../../../api/client'
import { useAuth } from '../../../context/AuthContext'

vi.mock('../../../context/AuthContext', () => ({
  useAuth: vi.fn(),
}))

vi.mock('../../../context/AssistantContext', () => ({
  useAssistant: () => ({ isAiEnabled: false }),
}))

vi.mock('../../../api/reportesCompartidos', () => ({
  registrarEventoReportePublico: vi.fn().mockResolvedValue(undefined),
}))

vi.mock('../../reports/AsistenteIAReporteDrawer', () => ({
  AsistenteIAReporteDrawer: () => <div data-testid="ai-drawer-mock" />,
}))

vi.mock('../../../api/client', async (importOriginal) => {
  const orig = await importOriginal<typeof import('../../../api/client')>()
  return {
    ...orig,
    fetchReportePublicoPorToken: vi.fn(),
    fetchPortalDestinatarioPorToken: vi.fn(),
    fetchMisReportesConsultor: vi.fn(),
  }
})

describe('ReporteCompartidoView', () => {
  const loginWithCredentialsMock = vi.fn()

  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(useAuth).mockReturnValue({
      isAuthenticated: false,
      logout: vi.fn(),
      loginWithCredentials: loginWithCredentialsMock,
    } as any)
  })

  it('muestra pantalla de login confidencial cuando requiere_login=true y envía credenciales', async () => {
    vi.mocked(apiClient.fetchReportePublicoPorToken).mockResolvedValue({
      requiere_login: true,
      reporte: {
        titulo_reporte: 'Reporte Ejecutivo Biblioteca',
        codigo_corto: 'RPT-2026-001',
        espacio_id: 1,
        modulo_nombre: 'Biblioteca CSF',
        destinatario: { email: 'dest@uct.cl' },
      },
    } as any)
    loginWithCredentialsMock.mockResolvedValue(false)

    render(<ReporteCompartidoView modoRuta="reporte" token="tok-abc" />)

    await screen.findByText(/Identificación Requerida/i)
    expect(screen.getByText(/Reporte Ejecutivo Biblioteca/i)).toBeInTheDocument()

    const passInput = document.querySelector('input[type="password"]') as HTMLInputElement
    fireEvent.change(passInput, { target: { value: 'clave-incorrecta' } })
    fireEvent.submit(passInput.closest('form')!)

    await waitFor(() => {
      expect(loginWithCredentialsMock).toHaveBeenCalledWith('dest@uct.cl', 'clave-incorrecta')
      expect(screen.getByText(/Credenciales institucionales incorrectas/i)).toBeInTheDocument()
    })
  })

  it('renderiza reporte ejecutivo cuando el usuario está autenticado', async () => {
    vi.mocked(useAuth).mockReturnValue({
      isAuthenticated: true,
      logout: vi.fn(),
      loginWithCredentials: loginWithCredentialsMock,
    } as any)

    vi.mocked(apiClient.fetchReportePublicoPorToken).mockResolvedValue({
      requiere_login: false,
      reporte: {
        titulo_reporte: 'Informe Mensual CSF',
        codigo_corto: 'RPT-2026-002',
        espacio_id: 1,
        espacio_nombre: 'Biblioteca CSF',
        fecha_inicio: '2026-10-01',
        fecha_fin: '2026-10-31',
        finalidad_reporte: 'Seguimiento mensual de aforo',
        nota_general: 'Nota oficial',
        destinatario: {
          nombre_completo: 'Decano UCT',
          email: 'decano@uct.cl',
          cargo: 'Decano',
          unidad_academica: 'Ingeniería',
        },
        creador: {
          nombre_completo: 'Directora Biblioteca',
          rol: 'Director_Recinto',
          email: 'dir@uct.cl',
        },
        notas_items: [],
      },
      datos: {
        indicadores_ejecutivos: { afluencia_total: 1200 },
        indicadores_visibles: ['afluencia_total'],
        graficos_visibles: [],
        graficos: {},
      },
    } as any)

    render(<ReporteCompartidoView modoRuta="reporte" token="tok-valid" />)

    await screen.findByText('Informe Mensual CSF')
    expect(screen.getByText('Nota oficial')).toBeInTheDocument()
  })
})
