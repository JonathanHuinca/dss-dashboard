import { HeatmapPoint } from '../../api/client'

interface Props { data: HeatmapPoint[] }

const DIAS = ['Lun', 'Mar', 'Mié', 'Jue', 'Vie', 'Sáb', 'Dom']
const HORAS = Array.from({ length: 16 }, (_, i) => i + 6) // 06-21

function lerp(a: number, b: number, t: number) { return a + (b - a) * t }
function colorForValue(v: number, max: number): string {
  const t = max > 0 ? Math.min(v / max, 1) : 0
  if (t < 0.5) {
    const r = Math.round(lerp(240, 251, t * 2))
    const g = Math.round(lerp(253, 191, t * 2))
    const b = Math.round(lerp(244, 36,  t * 2))
    return `rgb(${r},${g},${b})`
  }
  const r = Math.round(lerp(251, 127, (t - 0.5) * 2))
  const g = Math.round(lerp(191, 29,  (t - 0.5) * 2))
  const b = Math.round(lerp(36,  12,  (t - 0.5) * 2))
  return `rgb(${r},${g},${b})`
}

export function HeatmapChart({ data }: Props) {
  const lookup = new Map(data.map(d => [`${d.dia_semana}-${d.hora}`, d.ingresos_promedio]))
  const max = Math.max(...data.map(d => d.ingresos_promedio), 1)

  return (
    <div className="overflow-x-auto">
      <div className="inline-grid min-w-full" style={{ gridTemplateColumns: `48px repeat(${HORAS.length}, 1fr)` }}>
        {/* Header row */}
        <div />
        {HORAS.map(h => (
          <div key={h} className="text-center text-[9px] text-uct-text-muted pb-1 font-medium">
            {String(h).padStart(2, '0')}h
          </div>
        ))}
        {/* Data rows */}
        {DIAS.map((dia, di) => (
          <>
            <div key={`label-${di}`} className="text-[10px] text-uct-text-muted flex items-center pr-2 font-medium">{dia}</div>
            {HORAS.map(h => {
              const v = lookup.get(`${di}-${h}`) ?? 0
              return (
                <div
                  key={`${di}-${h}`}
                  title={`${dia} ${h}:00 — ${v.toFixed(1)} ingresos/h`}
                  className="aspect-square rounded-sm m-px cursor-default transition-transform hover:scale-110"
                  style={{ backgroundColor: colorForValue(v, max) }}
                />
              )
            })}
          </>
        ))}
      </div>
      {/* Legend */}
      <div className="flex items-center gap-2 mt-3">
        <span className="text-[10px] text-uct-text-muted">Bajo</span>
        <div className="h-2 flex-1 rounded-full" style={{
          background: 'linear-gradient(to right, rgb(240,253,244), rgb(251,191,36), rgb(127,29,12))'
        }} />
        <span className="text-[10px] text-uct-text-muted">Alto</span>
      </div>
    </div>
  )
}
