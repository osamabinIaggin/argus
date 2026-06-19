import { Card } from '../ui/Card'

interface SummaryCardProps {
  summary: string
}

export function SummaryCard({ summary }: SummaryCardProps) {
  return (
    <Card>
      <h3 className="text-xs font-semibold text-text-3 uppercase tracking-wider mb-2">Summary</h3>
      <p className="text-sm text-text-1 leading-relaxed">{summary}</p>
    </Card>
  )
}
