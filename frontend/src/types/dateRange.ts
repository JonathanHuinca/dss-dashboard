export interface DateRange {
  label: string
  inicio?: string
  fin?: string
  isCustom?: boolean
}

export const MONTH_NAMES_ES = [
  'Enero', 'Febrero', 'Marzo', 'Abril', 'Mayo', 'Junio',
  'Julio', 'Agosto', 'Septiembre', 'Octubre', 'Noviembre', 'Diciembre',
]

/**
 * Genera automáticamente los meses para el año del dataset con fechas exactas
 */
export function generateMonthPresets(year: number = 2026): DateRange[] {
  // Meses activos en los registros UCT (Marzo a Octubre)
  const activeMonths = [2, 3, 4, 5, 6, 7, 8, 9] // 0-indexed: Marzo=2 ... Octubre=9
  return activeMonths.map(mIndex => {
    const monthNum = mIndex + 1
    const mm = String(monthNum).padStart(2, '0')
    const lastDay = new Date(year, monthNum, 0).getDate()
    return {
      label: `Mes de ${MONTH_NAMES_ES[mIndex]} ${year}`,
      inicio: `${year}-${mm}-01`,
      fin: `${year}-${mm}-${String(lastDay).padStart(2, '0')}`,
    }
  })
}

export const MONTH_PRESETS_2026 = generateMonthPresets(2026)

export function buildLatestWeekPreset(maxDateStr: string = '2026-10-14'): DateRange {
  const dMax = new Date(maxDateStr + 'T00:00:00')
  const d7Ago = new Date(dMax.getTime() - 6 * 24 * 60 * 60 * 1000)
  const iso7Ago = d7Ago.toISOString().substring(0, 10)
  return {
    label: `Última semana registrada (${formatShortDate(iso7Ago)} - ${formatShortDate(maxDateStr)})`,
    inicio: iso7Ago,
    fin: maxDateStr,
  }
}

export const SPECIAL_PRESETS: DateRange[] = [
  buildLatestWeekPreset('2026-10-14'),
  { label: 'Semana de Exámenes (Jul 06 - Jul 13)', inicio: '2026-07-06', fin: '2026-07-13' },
  { label: 'Inicio Semestre (Mar 16 - Mar 31)', inicio: '2026-03-16', fin: '2026-03-31' },
  { label: 'Historial Semestre Completo (Mar - Oct)', inicio: '2026-03-01', fin: '2026-10-31' },
]

export const DATE_PRESETS: DateRange[] = [
  SPECIAL_PRESETS[0],
  SPECIAL_PRESETS[1],
  ...MONTH_PRESETS_2026,
  SPECIAL_PRESETS[2],
  SPECIAL_PRESETS[3],
]

export function formatShortDate(dateStr?: string): string {
  if (!dateStr) return ''
  const parts = dateStr.split('-')
  if (parts.length !== 3) return dateStr
  const [yyyy, mm, dd] = parts
  const mIndex = parseInt(mm, 10) - 1
  const mName = MONTH_NAMES_ES[mIndex]?.substring(0, 3) || mm
  return `${dd} ${mName} ${yyyy}`
}

export function formatMonthYearSpanish(mesStr?: string): string {
  if (!mesStr) return ''
  // Si viene en formato 'yyyy-MM' o 'yyyy-MM-dd'
  const parts = mesStr.split('-')
  if (parts.length >= 2) {
    const yyyy = parts[0]
    const mIndex = parseInt(parts[1], 10) - 1
    if (mIndex >= 0 && mIndex < 12) {
      return `${MONTH_NAMES_ES[mIndex]} ${yyyy}`
    }
  }
  return mesStr
}

export function formatDayMonthSpanish(fechaStr?: string): string {
  if (!fechaStr) return ''
  const parts = fechaStr.split('-')
  if (parts.length >= 3) {
    const mm = parts[1]
    const dd = parts[2].substring(0, 2)
    const mIndex = parseInt(mm, 10) - 1
    const mName = MONTH_NAMES_ES[mIndex]?.substring(0, 3) || mm
    return `${parseInt(dd, 10)} ${mName}`
  }
  return fechaStr
}

export function calculateDaysDifference(startStr?: string, endStr?: string): number {
  if (!startStr || !endStr) return 0
  const d1 = new Date(startStr)
  const d2 = new Date(endStr)
  const diffTime = d2.getTime() - d1.getTime()
  if (isNaN(diffTime) || diffTime < 0) return 0
  return Math.round(diffTime / (1000 * 60 * 60 * 24)) + 1
}
