import { PieChart, Pie, Cell, Tooltip, Legend, ResponsiveContainer } from 'recharts'
import { FleetItem } from '../../api/client'

interface Props { data: FleetItem[]; nameKey: 'tipo' | 'marca' }

const PALETTE = ['#002B49', '#003865', '#C59B27', '#E0B648', '#64748B', '#0F172A', '#16A34A', '#D97706', '#DC2626', '#7C3AED']

export function FleetDonutChart({ data, nameKey }: Props) {
  const chartData = data.map(d => ({
    name: (nameKey === 'tipo' ? d.tipo : d.marca) ?? 'Desconocido',
    value: d.total,
    pct: d.pct,
  }))

  return (
    <ResponsiveContainer width="100%" height={240}>
      <PieChart>
        <Pie
          data={chartData}
          cx="50%" cy="50%"
          innerRadius={55} outerRadius={90}
          paddingAngle={3}
          dataKey="value"
          label={({ name, pct }) => `${pct}%`}
          labelLine={false}
        >
          {chartData.map((_, i) => (
            <Cell key={i} fill={PALETTE[i % PALETTE.length]} />
          ))}
        </Pie>
        <Tooltip
          contentStyle={{ fontSize: 11, borderRadius: 8, border: '1px solid #e2e8f0' }}
          formatter={(v: number, name: string) => [`${v} veh.`, name]}
        />
        <Legend iconType="circle" iconSize={8} wrapperStyle={{ fontSize: 11 }} />
      </PieChart>
    </ResponsiveContainer>
  )
}
