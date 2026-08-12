import { useEffect, useState } from 'react'
import { cachedDomains, type TechnologyDomain } from '../api/taxonomy'
import { domainColors } from '../data/graphData'

export function DomainLegend({ compact = false }: { compact?: boolean }) {
  const [domains, setDomains] = useState<TechnologyDomain[]>([])
  useEffect(() => {
    const controller = new AbortController()
    cachedDomains().then(setDomains).catch(() => undefined)
    return () => controller.abort()
  }, [])
  return (
    <div className={`graph-domain-legend ${compact ? 'graph-domain-legend--compact' : ''}`} aria-label="T1 至 T7 技术领域颜色图例">
      {domains.map((domain) => (
        <span key={domain.code} title={`${domain.code} ${domain.name}`}>
          <i style={{ background: domainColors[domain.code] ?? domain.color ?? '#64748b' }} />
          <strong>{domain.code}</strong>
          {compact ? null : <em>{domain.name}</em>}
        </span>
      ))}
    </div>
  )
}
