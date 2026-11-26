import { useCallback, useEffect, useRef } from 'react'

/**
 * Programa temporizadores que se cancelan automáticamente al desmontar el componente.
 */
export function useTemporizadorSeguro() {
  const timersRef = useRef<number[]>([])

  const limpiarTodos = useCallback(() => {
    timersRef.current.forEach((id) => window.clearTimeout(id))
    timersRef.current = []
  }, [])

  useEffect(() => limpiarTodos, [limpiarTodos])

  const programar = useCallback((fn: () => void, ms: number) => {
    const id = window.setTimeout(() => {
      timersRef.current = timersRef.current.filter((item) => item !== id)
      fn()
    }, ms)
    timersRef.current.push(id)
    return id
  }, [])

  return { programar, limpiarTodos }
}
