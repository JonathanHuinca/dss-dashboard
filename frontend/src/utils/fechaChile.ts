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

function parsearIsoUtc(isoDate: string): number {
  const parts = isoDate.slice(0, 10).split('-')
  if (parts.length !== 3) return Number.NaN
  const y = Number(parts[0])
  const m = Number(parts[1])
  const d = Number(parts[2])
  if (!Number.isFinite(y) || !Number.isFinite(m) || !Number.isFinite(d)) return Number.NaN
  return Date.UTC(y, m - 1, d)
}

export function sumarDiasIso(isoDate: string, dias: number): string {
  const ms = parsearIsoUtc(isoDate)
  if (Number.isNaN(ms)) return isoDate
  const dt = new Date(ms + dias * 86400000)
  return dt.toISOString().slice(0, 10)
}

export function diferenciaDiasIso(inicioIso: string, finIso: string): number {
  const msIni = parsearIsoUtc(inicioIso)
  const msFin = parsearIsoUtc(finIso)
  if (Number.isNaN(msIni) || Number.isNaN(msFin)) return Number.NaN
  return Math.round((msFin - msIni) / 86400000)
}

export function ultimoDiaMesIso(year: number, monthNum: number): number {
  return new Date(Date.UTC(year, monthNum, 0)).getUTCDate()
}
