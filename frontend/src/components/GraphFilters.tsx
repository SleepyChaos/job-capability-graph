import { RotateCcw } from 'lucide-react'
import { useState } from 'react'
import { domains } from '../data/mockData'

interface GraphFiltersProps {
  onApply?: (summary: string) => void
  onChange?: (filters: GraphFilterState) => void
  initialValues?: Partial<GraphFilterState>
}

export interface GraphFilterState {
  domain: string
  level: string
}

const defaultFilters: GraphFilterState = { domain: '全部 T 领域', level: 'L2 能力域' }

export function GraphFilters({ onApply, onChange, initialValues }: GraphFiltersProps) {
  const initialFilters = { ...defaultFilters, ...initialValues }
  const [filters, setFilters] = useState<GraphFilterState>(initialFilters)
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
