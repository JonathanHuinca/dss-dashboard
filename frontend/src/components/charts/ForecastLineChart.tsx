import {
  ComposedChart, Line, Area, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, Legend,
} from 'recharts'
import { ForecastPoint } from '../../api/client'
import { format } from 'date-fns'

interface Props {
  actual: { bucket: string; ingresos?: number; entradas?: number }[]
  forecast: ForecastPoint[]
}

export function ForecastLineChart({ actual, forecast }: Props) {
  const actualMap = new Map(actual.map(d => [d.bucket.substring(0, 13), d.ingresos ?? d.entradas ?? 0]))

  const combined = forecast.slice(0, 72).map(f => {
    const key = f.ds.substring(0, 13)
    return {
      hora: format(new Date(f.ds), 'dd/MM HH:mm'),
      real: actualMap.get(key) ?? null,
      yhat: Math.max(0, Math.round(f.yhat)),
      lower: Math.max(0, Math.round(f.yhat_lower)),
      upper: Math.max(0, Math.round(f.yhat_upper)),
    }
  })

  return (
    <ResponsiveContainer width="100%" height={260}>
      <ComposedChart data={combined} margin={{ top: 10, right: 10, left: -10, bottom: 0 }}>
        <defs>
          <linearGradient id="gradBand" x1="0" y1="0" x2="0" y2="1">
            <stop offset="5%"  stopColor="#D97706" stopOpacity={0.25} />
            <stop offset="95%" stopColor="#D97706" stopOpacity={0.05} />
          </linearGradient>
        </defs>
        <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
        <XAxis dataKey="hora" tick={{ fontSize: 9, fill: '#64748B' }} interval={6} />
        <YAxis tick={{ fontSize: 10, fill: '#64748B' }} />
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
          formatter={(v: any, name: any) => [
            v !== null && v !== undefined ? `${v}` : '—',
            name === 'yhat' ? 'Pronóstico Prophet' : name === 'real' ? 'Dato Real' : name,
          ]}
        />
        <Legend
          payload={[
            { value: 'Pronóstico Prophet', type: 'line', id: 'yhat', color: '#D97706' },
            { value: 'Dato Real', type: 'line', id: 'real', color: '#003865' },
          ]}
        />
        <Area
          type="monotone"
          dataKey="upper"
          stroke="#D97706"
          strokeWidth={1}
          strokeDasharray="2 2"
          fill="url(#gradBand)"
          dot={false}
          legendType="none"
        />
        <Area
          type="monotone"
          dataKey="lower"
          stroke="transparent"
          fill="#ffffff"
          dot={false}
          legendType="none"
        />
        <Line
          type="monotone"
          dataKey="yhat"
          stroke="#D97706"
          strokeWidth={3}
          dot={false}
          name="yhat"
        />
        <Line
          type="monotone"
          dataKey="real"
          stroke="#003865"
          strokeWidth={2}
          dot={false}
          strokeDasharray="4 2"
          name="real"
        />
      </ComposedChart>
    </ResponsiveContainer>
  )
}
