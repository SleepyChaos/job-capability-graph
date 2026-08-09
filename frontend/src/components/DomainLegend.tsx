import { domains } from '../data/mockData'

export function DomainLegend({ compact = false }: { compact?: boolean }) {
  return (
    <div className={`graph-domain-legend ${compact ? 'graph-domain-legend--compact' : ''}`} aria-label="T1 至 T7 技术领域颜色图例">
      {domains.map((domain) => (
        <span key={domain.code} title={`${domain.code} ${domain.name}`}>
          <i style={{ background: domain.color }} />
          <strong>{domain.code}</strong>
          {compact ? null : <em>{domain.name}</em>}
        </span>
      ))}
    </div>
  )
}
