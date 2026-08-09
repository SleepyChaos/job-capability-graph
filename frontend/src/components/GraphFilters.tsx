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
  stack: string
  period: string
}

const defaultFilters: GraphFilterState = { domain: '全部 T 领域', level: 'L2 能力域', stack: '全部技术栈', period: '近 90 天' }

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
      <label><span>能力层级</span><select aria-label="能力层级" value={filters.level} onChange={(event) => update('level', event.target.value)}><option>L1 领域</option><option>L2 能力域</option><option>L3 标准技术点</option><option>L4 技术表面词</option></select></label>
      <label><span>技术栈</span><select aria-label="技术栈" value={filters.stack} onChange={(event) => update('stack', event.target.value)}><option>全部技术栈</option><option>机器人中间件</option><option>感知算法</option><option>决策与规划</option><option>仿真与数据</option></select></label>
      <label><span>时间窗口</span><select aria-label="时间窗口" value={filters.period} onChange={(event) => update('period', event.target.value)}><option>近 30 天</option><option>近 45 天</option><option>近 90 天</option><option>近 180 天</option><option>近 1 年</option></select></label>
      <div className="graph-filter-actions"><button className="secondary-button" onClick={reset}><RotateCcw size={14} />重置</button><button className="primary-button" onClick={() => onApply?.(`${filters.domain} · ${filters.level} · ${filters.stack} · ${filters.period}`)}>应用筛选</button></div>
    </div>
  )
}
