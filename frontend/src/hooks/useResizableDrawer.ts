import { useCallback, useEffect, useRef, useState } from 'react'

interface UseResizableDrawerOptions {
  storageKey: string
  defaultWidth: number
  minWidth?: number
}

/**
 * Hook para redimensionar horizontalmente paneles laterales arrastrando el borde izquierdo
 * o alternar pantalla completa, persistiendo el ancho elegido y notificando a gráficos Plotly.
 */
export function useResizableDrawer({
  storageKey,
  defaultWidth,
  minWidth = 420,
}: UseResizableDrawerOptions) {
  const [width, setWidth] = useState<number>(() => {
    if (typeof window === 'undefined') return defaultWidth
    try {
      const saved = Number(localStorage.getItem(storageKey))
      if (Number.isFinite(saved) && saved >= minWidth) {
        return Math.min(saved, Math.max(minWidth, window.innerWidth))
      }
    } catch {
      // Ignorar errores de almacenamiento
    }
    return defaultWidth
  })
  const [isMaximized, setIsMaximized] = useState(false)
  const [isResizing, setIsResizing] = useState(false)
  const [isMobile, setIsMobile] = useState<boolean>(() =>
    typeof window !== 'undefined' ? window.innerWidth < 768 : false
  )
  const widthRef = useRef(width)
  widthRef.current = width
  const dragCleanupRef = useRef<(() => void) | null>(null)
  const maximizeTimerRef = useRef<number | null>(null)

  useEffect(() => {
    return () => {
      dragCleanupRef.current?.()
      if (maximizeTimerRef.current !== null) {
        window.clearTimeout(maximizeTimerRef.current)
        maximizeTimerRef.current = null
      }
    }
  }, [])

  useEffect(() => {
    const onResize = () => {
      const mobile = window.innerWidth < 768
      setIsMobile(mobile)
      if (!mobile && widthRef.current > window.innerWidth) {
        setWidth(Math.max(minWidth, window.innerWidth))
      }
    }
    window.addEventListener('resize', onResize)
    return () => window.removeEventListener('resize', onResize)
  }, [minWidth])

  const triggerChartResize = useCallback(() => {
    if (typeof window === 'undefined') return
    requestAnimationFrame(() => window.dispatchEvent(new Event('resize')))
  }, [])

  const handlePointerDown = useCallback(
    (e: React.PointerEvent<HTMLDivElement>) => {
      if (typeof window === 'undefined' || window.innerWidth < 768) return
      e.preventDefault()
      setIsResizing(true)
      if (isMaximized) setIsMaximized(false)

      const prevUserSelect = document.body.style.userSelect
      const prevCursor = document.body.style.cursor
      document.body.style.userSelect = 'none'
      document.body.style.cursor = 'ew-resize'

      const onPointerMove = (ev: PointerEvent) => {
        const nextWidth = Math.max(minWidth, Math.min(window.innerWidth, window.innerWidth - ev.clientX))
        widthRef.current = nextWidth
        setWidth(nextWidth)
      }

      const onPointerUp = () => {
        setIsResizing(false)
        document.body.style.userSelect = prevUserSelect
        document.body.style.cursor = prevCursor
        window.removeEventListener('pointermove', onPointerMove)
        window.removeEventListener('pointerup', onPointerUp)
        window.removeEventListener('pointercancel', onPointerUp)
        dragCleanupRef.current = null
        try {
          localStorage.setItem(storageKey, String(Math.round(widthRef.current)))
        } catch {
          // Ignorar errores de almacenamiento
        }
        triggerChartResize()
      }

      dragCleanupRef.current = () => {
        setIsResizing(false)
        document.body.style.userSelect = prevUserSelect
        document.body.style.cursor = prevCursor
        window.removeEventListener('pointermove', onPointerMove)
        window.removeEventListener('pointerup', onPointerUp)
        window.removeEventListener('pointercancel', onPointerUp)
      }

      window.addEventListener('pointermove', onPointerMove)
      window.addEventListener('pointerup', onPointerUp)
      window.addEventListener('pointercancel', onPointerUp)
    },
    [isMaximized, minWidth, storageKey, triggerChartResize]
  )

  const toggleMaximize = useCallback(() => {
    setIsMaximized((prev) => !prev)
    if (maximizeTimerRef.current !== null) {
      window.clearTimeout(maximizeTimerRef.current)
    }
    maximizeTimerRef.current = window.setTimeout(() => {
      maximizeTimerRef.current = null
      triggerChartResize()
    }, 60)
  }, [triggerChartResize])

  const drawerWidth = isMobile || isMaximized ? '100%' : `${Math.min(width, typeof window !== 'undefined' ? window.innerWidth : width)}px`

  return {
    drawerWidth,
    isMaximized,
    isResizing,
    isMobile,
    handlePointerDown,
    toggleMaximize,
  }
}
