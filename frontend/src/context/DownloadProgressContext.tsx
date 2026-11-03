import React, { createContext, useContext, useState, useCallback } from 'react'

export type DownloadFileType = 'excel' | 'csv' | 'pdf' | 'imagen'
export type DownloadState = 'inactivo' | 'procesando' | 'completado' | 'error'

export interface DownloadProgressInfo {
  titulo: string
  subtitulo?: string
  tipo: DownloadFileType
  estado: DownloadState
  progreso: number // 0 a 100
  etapaActual: string
  mensajeError?: string
  nombreArchivo?: string
}

interface EjecutarDescargaParams {
  titulo: string
  subtitulo?: string
  tipo: DownloadFileType
  nombreArchivo?: string
  tarea: (helpers: {
    setProgreso: (porcentaje: number, etapa?: string) => void
    setEtapa: (etapa: string) => void
  }) => Promise<void>
}

interface DownloadProgressContextValue {
  descargaActual: DownloadProgressInfo | null
  estaAbierto: boolean
  ejecutarDescarga: (params: EjecutarDescargaParams) => Promise<boolean>
  cerrarModal: () => void
  cancelarDescarga: () => void
}

const DownloadProgressContext = createContext<DownloadProgressContextValue | null>(null)

export const DownloadProgressProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [descargaActual, setDescargaActual] = useState<DownloadProgressInfo | null>(null)
  const [estaAbierto, setEstaAbierto] = useState(false)

  const cerrarModal = useCallback(() => {
    setEstaAbierto(false)
    setTimeout(() => {
      setDescargaActual(null)
    }, 300)
  }, [])

  const cancelarDescarga = useCallback(() => {
    cerrarModal()
  }, [cerrarModal])

  const ejecutarDescarga = useCallback(
    async ({ titulo, subtitulo, tipo, nombreArchivo, tarea }: EjecutarDescargaParams): Promise<boolean> => {
      setDescargaActual({
        titulo,
        subtitulo,
        tipo,
        estado: 'procesando',
        progreso: 10,
        etapaActual: 'Iniciando recopilación de datos...',
        nombreArchivo,
      })
      setEstaAbierto(true)

      const helpers = {
        setProgreso: (porcentaje: number, etapa?: string) => {
          setDescargaActual(prev =>
            prev
              ? {
                  ...prev,
                  progreso: Math.min(100, Math.max(0, porcentaje)),
                  ...(etapa ? { etapaActual: etapa } : {}),
                }
              : null
          )
        },
        setEtapa: (etapa: string) => {
          setDescargaActual(prev => (prev ? { ...prev, etapaActual: etapa } : null))
        },
      }

      try {
        await tarea(helpers)

        setDescargaActual(prev =>
          prev
            ? {
                ...prev,
                estado: 'completado',
                progreso: 100,
                etapaActual: '¡Descarga completada con éxito!',
              }
            : null
        )

        // Cierre automático suave después de 2.2 segundos
        setTimeout(() => {
          setEstaAbierto(false)
          setTimeout(() => setDescargaActual(null), 300)
        }, 2200)

        return true
      } catch (err: any) {
        console.error('Error durante la descarga:', err)
        const errorMsg =
          err?.message ||
          (typeof err === 'string' ? err : 'Ocurrió un error inesperado al generar el archivo.')

        setDescargaActual(prev =>
          prev
            ? {
                ...prev,
                estado: 'error',
                progreso: 100,
                etapaActual: 'Error en la generación del archivo',
                mensajeError: errorMsg,
              }
            : null
        )

        return false
      }
    },
    []
  )

  return (
    <DownloadProgressContext.Provider
      value={{
        descargaActual,
        estaAbierto,
        ejecutarDescarga,
        cerrarModal,
        cancelarDescarga,
      }}
    >
      {children}
    </DownloadProgressContext.Provider>
  )
}

export function useDownloadProgress() {
  const context = useContext(DownloadProgressContext)
  if (!context) {
    throw new Error('useDownloadProgress debe usarse dentro de un DownloadProgressProvider')
  }
  return context
}
