/**
 * Descarga un Blob en el navegador garantizando la liberación diferida del ObjectURL.
 */
export function descargarBlobSeguro(blob: Blob, nombreArchivo: string): void {
  if (typeof window === 'undefined' || typeof document === 'undefined') return
  const url = window.URL.createObjectURL(blob)
  const enlace = document.createElement('a')
  try {
    enlace.href = url
    enlace.download = nombreArchivo
    enlace.style.display = 'none'
    document.body.appendChild(enlace)
    enlace.click()
  } finally {
    if (enlace.parentNode) {
      enlace.parentNode.removeChild(enlace)
    }
    window.setTimeout(() => {
      window.URL.revokeObjectURL(url)
    }, 1000)
  }
}
