import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, Legend,
} from 'recharts'
import { format } from 'date-fns'

interface Props {
  data: { bucket: string; ingresos?: number; entradas?: number; salidas: number }[]
}

export function HourlyBarChart({ data }: Props) {
  const chartData = data.map(d => ({
    hora: d.bucket ? format(new Date(d.bucket), 'HH:mm') : '',
    Ingresos: d.ingresos ?? d.entradas ?? 0,
    Salidas: d.salidas,
  }))

  return (
    <ResponsiveContainer width="100%" height={240}>
      <BarChart data={chartData} margin={{ top: 5, right: 10, left: -10, bottom: 0 }} barGap={2}>
        <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
        <XAxis dataKey="hora" tick={{ fontSize: 10, fill: '#64748B' }} interval="preserveStartEnd" />
        <YAxis tick={{ fontSize: 10, fill: '#64748B' }} />
        <Tooltip contentStyle={{ fontSize: 11, borderRadius: 8, border: '1px solid #e2e8f0' }} />
        <Legend />
        <Bar dataKey="Ingresos" fill="#002B49" radius={[3, 3, 0, 0]} maxBarSize={14} />
        <Bar dataKey="Salidas"  fill="#C59B27" radius={[3, 3, 0, 0]} maxBarSize={14} />
      </BarChart>
    </ResponsiveContainer>
  )
}
