import React from 'react'
import { act, render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { AuthProvider, useAuth } from '../AuthContext'
import { api } from '../../api/client'

function crearJwtFalso(payload: Record<string, unknown>): string {
  const encode = (obj: Record<string, unknown>) =>
    btoa(JSON.stringify(obj)).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '')
  return `${encode({ alg: 'HS256', typ: 'JWT' })}.${encode(payload)}.firma`
}

const InspectorAuth: React.FC = () => {
  const auth = useAuth()
  return (
    <div>
      <span data-testid="auth-state">{auth.isAuthenticated ? 'SI' : 'NO'}</span>
      <span data-testid="auth-role">{auth.userRole ?? 'ninguno'}</span>
      <span data-testid="auth-espacio">{String(auth.currentEspacioId)}</span>
      <span data-testid="auth-export">{String(auth.canExport)}</span>
      <button onClick={() => auth.logout()}>Salir</button>
    </div>
  )
}

describe('AuthContext', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    localStorage.clear()
    vi.spyOn(api, 'get').mockResolvedValue({ data: {} } as any)
  })

  afterEach(() => {
    vi.useRealTimers()
    vi.restoreAllMocks()
  })

  it('decodifica JWT válido, asigna permisos y limpia al recibir uct:auth-expired', () => {
    const exp = Math.floor(Date.now() / 1000) + 60
    const token = crearJwtFalso({
      user_id: 42,
      nombre_completo: 'Ana Bibliotecaria',
      email: 'ana@uct.cl',
      rol: 'Director_Recinto',
      roles: ['Director_Recinto'],
      allowed_datasets: ['estacionamiento'],
      can_use_ai: true,
      can_export: true,
      can_ingest: true,
      exp,
    })
    localStorage.setItem('uct_auth_token', token)

    const qc = new QueryClient()
    const clearSpy = vi.spyOn(qc, 'clear')

    render(
      <QueryClientProvider client={qc}>
        <AuthProvider>
          <InspectorAuth />
        </AuthProvider>
      </QueryClientProvider>
    )

    expect(screen.getByTestId('auth-state')).toHaveTextContent('SI')
    expect(screen.getByTestId('auth-role')).toHaveTextContent('Director_Recinto')
    expect(screen.getByTestId('auth-espacio')).toHaveTextContent('2')
    expect(screen.getByTestId('auth-export')).toHaveTextContent('true')

    act(() => {
      window.dispatchEvent(new Event('uct:auth-expired'))
    })

    expect(screen.getByTestId('auth-state')).toHaveTextContent('NO')
    expect(localStorage.getItem('uct_auth_token')).toBeNull()
    expect(clearSpy).toHaveBeenCalled()
  })

  it('cierra sesión automáticamente al vencer el temporizador del JWT', () => {
    const exp = Math.floor(Date.now() / 1000) + 5
    const token = crearJwtFalso({
      user_id: 99,
      nombre_completo: 'Analista',
      rol: 'Analista_Consulta',
      allowed_datasets: ['biblioteca'],
      exp,
    })
    localStorage.setItem('uct_auth_token', token)

    const qc = new QueryClient()
    render(
      <QueryClientProvider client={qc}>
        <AuthProvider>
          <InspectorAuth />
        </AuthProvider>
      </QueryClientProvider>
    )

    expect(screen.getByTestId('auth-state')).toHaveTextContent('SI')

    act(() => {
      vi.advanceTimersByTime(6000)
    })

    expect(screen.getByTestId('auth-state')).toHaveTextContent('NO')
  })
})
