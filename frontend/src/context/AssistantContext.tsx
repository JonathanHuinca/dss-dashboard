import React, { createContext, useContext, useState, useEffect, useLayoutEffect, useCallback, useRef } from 'react'
import { useQuery } from '@tanstack/react-query'
import { api } from '../api/clienteBase'
import { useAuth } from './AuthContext'

export interface AssistantPeriodo {
  startDate?: string
  endDate?: string
  inicio?: string
  fin?: string
  label?: string
}

interface AssistantContextType {
  isOpen: boolean
  isAiEnabled: boolean
  canUseAssistant: boolean
  contextoGrafico?: string
  periodo?: AssistantPeriodo
  filtros?: Record<string, any>
  openAssistant: (contexto?: string, periodo?: AssistantPeriodo, filtros?: Record<string, any>) => void
  setFiltrosActivos: (filtros: Record<string, any>) => void
  setPeriodoActivo: (periodo: AssistantPeriodo) => void
  closeAssistant: () => void
  clearContexto: () => void
}

const AssistantContext = createContext<AssistantContextType | undefined>(undefined)

export const AssistantProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const { isAuthenticated, userId, userEmail, canUseAi, userRole, roles, hasDatasetAccess, canAccessAdmin } = useAuth()
  const [isOpen, setIsOpen] = useState(false)
  const [contextoGrafico, setContextoGrafico] = useState<string | undefined>(undefined)
  const [periodo, setPeriodo] = useState<AssistantPeriodo | undefined>(undefined)
  const [filtros, setFiltros] = useState<Record<string, any> | undefined>(undefined)
  const prevSessionRef = useRef<string | null>(null)

  // Limpia estado previo del asistente antes de que efectos hijos sincronicen la nueva sesión
  useLayoutEffect(() => {
    const currentSession = isAuthenticated
      ? (userId !== null && userId !== undefined ? `u${userId}` : (userEmail || 'auth'))
      : null
    if (prevSessionRef.current !== currentSession) {
      setIsOpen(false)
      setContextoGrafico(undefined)
      setPeriodo(undefined)
      setFiltros(undefined)
      prevSessionRef.current = currentSession
    }
  }, [isAuthenticated, userId, userEmail])

  const { data: statusData } = useQuery<{ ia_asistente_activo: boolean }>({
    queryKey: ['ia-status'],
    queryFn: async () => {
      try {
        const res = await api.get('/config/ia-status')
        return res.data
      } catch {
        return { ia_asistente_activo: true }
      }
    },
    refetchInterval: 15_000,
    staleTime: 10_000,
    enabled: isAuthenticated,
  })

  const isAiEnabled = statusData ? Boolean(statusData.ia_asistente_activo) : true
  const esSoloConsultor =
    (userRole === 'Consultor_Reporte' || (roles || []).includes('Consultor_Reporte')) &&
    !hasDatasetAccess('biblioteca') &&
    !hasDatasetAccess('estacionamiento') &&
    !canAccessAdmin
  const canUseAssistant = isAiEnabled && canUseAi && !esSoloConsultor

  useEffect(() => {
    if (!canUseAssistant && isOpen) {
      setIsOpen(false)
    }
  }, [canUseAssistant, isOpen])

  const openAssistant = useCallback((
    contexto?: string,
    periodoParam?: AssistantPeriodo,
    filtrosParam?: Record<string, any>
  ) => {
    if (!canUseAssistant) return
    if (contexto !== undefined) setContextoGrafico(contexto)
    if (periodoParam !== undefined) setPeriodo(periodoParam)
    if (filtrosParam !== undefined) setFiltros(filtrosParam)
    setIsOpen(true)
  }, [canUseAssistant])

  const setFiltrosActivos = useCallback((nuevosFiltros: Record<string, any>) => {
    setFiltros(nuevosFiltros)
  }, [])

  const setPeriodoActivo = useCallback((nuevoPeriodo: AssistantPeriodo) => {
    setPeriodo(nuevoPeriodo)
  }, [])

  const closeAssistant = useCallback(() => {
    setIsOpen(false)
  }, [])

  const clearContexto = useCallback(() => {
    setContextoGrafico(undefined)
  }, [])

  return (
    <AssistantContext.Provider
      value={{
        isOpen,
        isAiEnabled,
        canUseAssistant,
        contextoGrafico,
        periodo,
        filtros,
        openAssistant,
        setFiltrosActivos,
        setPeriodoActivo,
        closeAssistant,
        clearContexto,
      }}
    >
      {children}
    </AssistantContext.Provider>
  )
}

export const useAssistant = (): AssistantContextType => {
  const context = useContext(AssistantContext)
  if (!context) {
    return {
      isOpen: false,
      isAiEnabled: true,
      canUseAssistant: false,
      contextoGrafico: undefined,
      periodo: undefined,
      filtros: undefined,
      openAssistant: () => {},
      setFiltrosActivos: () => {},
      setPeriodoActivo: () => {},
      closeAssistant: () => {},
      clearContexto: () => {},
    }
  }
  return context
}
