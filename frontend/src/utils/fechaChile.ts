export const ZONA_HORARIA_CHILE = 'America/Santiago'

export function formatearFechaHoraChile(
  iso?: string | null,
  opciones?: Intl.DateTimeFormatOptions,
  fallback = '—'
): string {
  if (!iso) return fallback
  const fecha = new Date(iso)
  if (Number.isNaN(fecha.getTime())) return iso
  try {
    return fecha.toLocaleString('es-CL', {
      timeZone: ZONA_HORARIA_CHILE,
      day: '2-digit',
      month: '2-digit',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
      ...opciones,
    })
  } catch {
    return fecha.toLocaleString('es-CL')
  }
}

export function obtenerFechaHoyChileIso(referencia: Date = new Date()): string {
  try {
    const formateado = new Intl.DateTimeFormat('en-CA', {
      timeZone: ZONA_HORARIA_CHILE,
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
    }).format(referencia)
    if (/^\d{4}-\d{2}-\d{2}$/.test(formateado)) {
      return formateado
    }
  } catch { }
  const y = referencia.getFullYear()
  const m = String(referencia.getMonth() + 1).padStart(2, '0')
  const d = String(referencia.getDate()).padStart(2, '0')
  return `${y}-${m}-${d}`
}
