import { RotateCcw } from 'lucide-react'
import { useEffect, useState } from 'react'
import { cachedDomains, type TechnologyDomain } from '../api/taxonomy'

interface GraphFiltersProps {
  onApply?: (summary: string) => void
  onChange?: (filters: GraphFilterState) => void
  initialValues?: Partial<GraphFilterState>
}

export interface GraphFilterState {
  domain: string
  level: string
}

export interface RelationGraphFilterState {
  clusterDomain: string
  capabilityDomain: string
  capabilityLevel: string
}

const defaultFilters: GraphFilterState = { domain: '全部 T 领域', level: 'L2 能力域' }
const defaultRelationFilters: RelationGraphFilterState = {
  clusterDomain: '',
  capabilityDomain: '',
  capabilityLevel: 'L2',
}

export function GraphFilters({ onApply, onChange, initialValues }: GraphFiltersProps) {
  const initialFilters = { ...defaultFilters, ...initialValues }
  const [filters, setFilters] = useState<GraphFilterState>(initialFilters)
  const [domains, setDomains] = useState<TechnologyDomain[]>([])
  useEffect(() => {
    cachedDomains().then(setDomains).catch(() => undefined)
  }, [])
  const update = (key: keyof GraphFilterState, value: string) => {
    const next = { ...filters, [key]: value }
    setFilters(next)
    onChange?.(next)
  }
  const reset = () => {
    setFilters(initialFilters)
    onChange?.(initialFilters)
    onApply?.('筛选条件已重置')
  }

  return (
    <div className="graph-filterbar" aria-label="图谱筛选条件">
      <label><span>技术领域</span><select aria-label="技术领域" value={filters.domain} onChange={(event) => update('domain', event.target.value)}><option>全部 T 领域</option>{domains.map((domain) => <option key={domain.code}>{domain.code} {domain.name}</option>)}</select></label>
      <label><span>能力层级</span><select aria-label="能力层级" value={filters.level} onChange={(event) => update('level', event.target.value)}><option>L1 领域</option><option>L2 能力域</option><option>L3 标准技术点</option></select></label>
      <div className="graph-filter-actions"><button className="secondary-button" onClick={reset}><RotateCcw size={14} />重置</button><button className="primary-button" onClick={() => onApply?.(`${filters.domain} · ${filters.level}`)}>应用筛选</button></div>
    </div>
  )
}

interface RelationGraphFiltersProps {
  onApply?: (summary: string) => void
  onChange?: (filters: RelationGraphFilterState) => void
}

export function RelationGraphFilters({ onApply, onChange }: RelationGraphFiltersProps) {
  const [filters, setFilters] = useState<RelationGraphFilterState>(defaultRelationFilters)
  const [domains, setDomains] = useState<TechnologyDomain[]>([])

  useEffect(() => {
    cachedDomains().then(setDomains).catch(() => undefined)
  }, [])

  const update = (key: keyof RelationGraphFilterState, value: string) => {
    const next = { ...filters, [key]: value }
    setFilters(next)
    onChange?.(next)
  }

  const reset = () => {
    setFilters(defaultRelationFilters)
    onChange?.(defaultRelationFilters)
    onApply?.('筛选条件已重置')
  }

  const domainOptions = (allLabel: string) => <>
    <option value="">{allLabel}</option>
    {domains.map((domain) => <option key={domain.code} value={domain.code}>{domain.code} {domain.name}</option>)}
  </>

  return (
    <div className="graph-filterbar graph-filterbar--relation" aria-label="岗位聚类与能力分开筛选">
      <fieldset className="graph-filter-group">
        <legend>岗位聚类筛选</legend>
        <label><span>聚类领域</span><select aria-label="岗位聚类领域" value={filters.clusterDomain} onChange={(event) => update('clusterDomain', event.target.value)}>{domainOptions('全部岗位聚类')}</select></label>
      </fieldset>
      <fieldset className="graph-filter-group graph-filter-group--capability">
        <legend>能力筛选</legend>
        <label><span>技术领域</span><select aria-label="能力技术领域" value={filters.capabilityDomain} onChange={(event) => update('capabilityDomain', event.target.value)}>{domainOptions('全部能力领域')}</select></label>
        <label><span>能力层级</span><select aria-label="能力层级" value={filters.capabilityLevel} onChange={(event) => update('capabilityLevel', event.target.value)}><option value="L1">L1 领域</option><option value="L2">L2 能力域</option><option value="L3">L3 标准技术点</option></select></label>
      </fieldset>
      <div className="graph-filter-actions"><button className="secondary-button" onClick={reset}><RotateCcw size={14} />重置</button><button className="primary-button" onClick={() => onApply?.(`岗位聚类：${filters.clusterDomain || '全部'} · 能力：${filters.capabilityDomain || '全部'} / ${filters.capabilityLevel}`)}>应用筛选</button></div>
    </div>
  )
}
