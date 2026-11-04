import React, { createContext, useContext, useState, useEffect } from 'react'
import { useQuery } from '@tanstack/react-query'
import { api } from '../api/clienteBase'

export interface AssistantPeriodo {
  startDate?: string
  endDate?: string
  label?: string
}

interface AssistantContextType {
  isOpen: boolean
  isAiEnabled: boolean
  contextoGrafico?: string
  periodo?: AssistantPeriodo
  filtros?: Record<string, any>
  openAssistant: (contexto?: string, periodo?: AssistantPeriodo, filtros?: Record<string, any>) => void
  closeAssistant: () => void
  clearContexto: () => void
}

const AssistantContext = createContext<AssistantContextType | undefined>(undefined)

export const AssistantProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [isOpen, setIsOpen] = useState(false)
  const [contextoGrafico, setContextoGrafico] = useState<string | undefined>(undefined)
  const [periodo, setPeriodo] = useState<AssistantPeriodo | undefined>(undefined)
  const [filtros, setFiltros] = useState<Record<string, any> | undefined>(undefined)

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
  })

  const isAiEnabled = statusData ? Boolean(statusData.ia_asistente_activo) : true

  useEffect(() => {
    if (!isAiEnabled && isOpen) {
      setIsOpen(false)
    }
  }, [isAiEnabled, isOpen])

  const openAssistant = (
    contexto?: string,
    periodoParam?: AssistantPeriodo,
    filtrosParam?: Record<string, any>
  ) => {
    if (!isAiEnabled) return
    if (contexto !== undefined) setContextoGrafico(contexto)
    if (periodoParam !== undefined) setPeriodo(periodoParam)
    if (filtrosParam !== undefined) setFiltros(filtrosParam)
    setIsOpen(true)
  }

  const closeAssistant = () => {
    setIsOpen(false)
  }

  const clearContexto = () => {
    setContextoGrafico(undefined)
    setPeriodo(undefined)
    setFiltros(undefined)
  }

  return (
    <AssistantContext.Provider
      value={{
        isOpen,
        isAiEnabled,
        contextoGrafico,
        periodo,
        filtros,
        openAssistant,
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
      contextoGrafico: undefined,
      periodo: undefined,
      filtros: undefined,
      openAssistant: () => {},
      closeAssistant: () => {},
      clearContexto: () => {},
    }
  }
  return context
}
