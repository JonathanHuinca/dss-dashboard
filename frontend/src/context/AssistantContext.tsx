import React, { createContext, useContext, useState } from 'react'

interface AssistantContextType {
  isOpen: boolean
  contextoGrafico?: string
  openAssistant: (contexto?: string) => void
  closeAssistant: () => void
  clearContexto: () => void
}

const AssistantContext = createContext<AssistantContextType | undefined>(undefined)

export const AssistantProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [isOpen, setIsOpen] = useState(false)
  const [contextoGrafico, setContextoGrafico] = useState<string | undefined>(undefined)

  const openAssistant = (contexto?: string) => {
    setContextoGrafico(contexto)
    setIsOpen(true)
  }

  const closeAssistant = () => {
    setIsOpen(false)
  }

  const clearContexto = () => {
    setContextoGrafico(undefined)
  }

  return (
    <AssistantContext.Provider
      value={{
        isOpen,
        contextoGrafico,
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
      contextoGrafico: undefined,
      openAssistant: () => {},
      closeAssistant: () => {},
      clearContexto: () => {},
    }
  }
  return context
}
