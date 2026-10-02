import { Activity } from 'lucide-react'

interface Props { lastUpdated?: string }

export function LiveBadge({ lastUpdated }: Props) {
  return (
    <span className="inline-flex items-center gap-1.5 px-2.5 py-1 bg-uct-success/10 text-uct-success text-xs font-semibold rounded-full border border-uct-success/20">
      <span className="relative flex h-2 w-2">
        <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-uct-success opacity-75" />
        <span className="relative inline-flex rounded-full h-2 w-2 bg-uct-success" />
      </span>
      EN VIVO
      {lastUpdated && <span className="text-uct-text-muted font-normal ml-0.5">{lastUpdated}</span>}
    </span>
  )
}
