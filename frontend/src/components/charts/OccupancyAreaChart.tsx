import {
  AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip,
  ReferenceLine, ResponsiveContainer, Legend,
} from 'recharts'
import { format } from 'date-fns'
import { es } from 'date-fns/locale'

interface Props {
  data: { bucket: string; ingresos?: number; entradas?: number; salidas: number; personas_unicas?: number }[]
  capacidad: number
  title?: string
  unit?: string
}

export function OccupancyAreaChart({ data, capacidad, unit = 'ocupantes' }: Props) {
  let running = 0
  const isMultiDay = data.length > 24
  const chartData = data.map(d => {
    const inCount = d.ingresos ?? d.entradas ?? 0
    let aforo = 0
    if (unit === 'vehículos') {
      running = Math.max(0, running + inCount - d.salidas)
      aforo = running
    } else {
      aforo = d.personas_unicas ?? inCount
    }
    return {
      hora: d.bucket ? format(new Date(d.bucket), isMultiDay ? 'dd/MM HH:mm' : 'HH:mm', { locale: es }) : '',
      aforo: aforo,
    }
  })

  const alerta70  = Math.round(capacidad * 0.70)
  const alerta85  = Math.round(capacidad * 0.85)

  return (
    <ResponsiveContainer width="100%" height={260}>
      <AreaChart data={chartData} margin={{ top: 10, right: 10, left: -10, bottom: 0 }}>
        <defs>
          <linearGradient id="gradAforo" x1="0" y1="0" x2="0" y2="1">
            <stop offset="5%"  stopColor="#003865" stopOpacity={0.4} />
            <stop offset="95%" stopColor="#003865" stopOpacity={0.02} />
          </linearGradient>
        </defs>
        <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
        <XAxis dataKey="hora" tick={{ fontSize: 10, fill: '#64748B' }} interval="preserveStartEnd" />
        <YAxis domain={[0, capacidad + 20]} tick={{ fontSize: 10, fill: '#64748B' }} />
        <Tooltip
          contentStyle={{
            backgroundColor: '#ffffff',
            borderColor: '#cbd5e1',
            borderRadius: 8,
            boxShadow: '0 4px 6px -1px rgb(0 0 0 / 0.1)',
            fontSize: 12,
            color: '#0f172a',
          }}
          labelStyle={{ color: '#0f172a', fontWeight: 600, marginBottom: 4 }}
          itemStyle={{ color: '#0f172a' }}
          formatter={(v: number) => [`${v} ${unit}`, 'Ocupación']}
        />
        <ReferenceLine y={capacidad} stroke="#DC2626" strokeDasharray="5 3" strokeWidth={2}
          label={{ value: `Máx ${capacidad}`, position: 'right', fontSize: 10, fill: '#DC2626' }} />
        <ReferenceLine y={alerta85} stroke="#D97706" strokeDasharray="4 3" strokeWidth={1.5}
          label={{ value: '85%', position: 'right', fontSize: 9, fill: '#D97706' }} />
        <ReferenceLine y={alerta70} stroke="#16A34A" strokeDasharray="3 3" strokeWidth={1}
          label={{ value: '70%', position: 'right', fontSize: 9, fill: '#16A34A' }} />
        <Area type="monotone" dataKey="aforo" stroke="#003865" strokeWidth={2}
          fill="url(#gradAforo)" dot={false} />
      </AreaChart>
    </ResponsiveContainer>
  )
}
