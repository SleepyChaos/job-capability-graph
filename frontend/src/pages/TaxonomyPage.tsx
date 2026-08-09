import { ChevronRight, GitMerge, Search, Split, Waypoints } from 'lucide-react'
import { useState } from 'react'
import { domains, taxonomyRows } from '../data/mockData'
import { MetricStrip, Panel, StatusTag } from '../components/ui'

const concepts = [
  { code: 'L3-014', name: '运动规划', parent: '规划与决策', terms: 21, domain: 'T3', role: '核心技术', status: '正式' },
  { code: 'L3-027', name: '传感器融合', parent: '环境感知', terms: 18, domain: 'T2', role: '核心技术', status: '正式' },
  { code: 'L3-083', name: 'Sim2Real', parent: '仿真与迁移', terms: 14, domain: 'T5', role: '工程方法', status: '正式' },
  { code: 'L3-106', name: '实时控制', parent: '控制系统', terms: 12, domain: 'T1', role: '核心技术', status: '正式' },
  { code: '候选-19', name: '4D 高斯溅射', parent: '待确认', terms: 7, domain: 'T2 / T5', role: '候选技术', status: '待审核' },
]

export function TaxonomyPage({ notify }: { notify: (message: string) => void }) {
  const [level, setLevel] = useState('L3')
  const [query, setQuery] = useState('')
  const filtered = concepts.filter((item) => item.name.toLowerCase().includes(query.toLowerCase()))
  return (
    <div className="page-stack">
      <div className="page-intro"><div><h2>技术词标准管理</h2><p>统一维护技术词标准、L1–L4 知识层级与 T1–T7 技术领域；一个标准技术点可跨多个领域。</p></div><button className="primary-button" onClick={() => notify('Mock：已创建技术候选词草稿')}><GitMerge size={16} />创建候选词</button></div>
      <MetricStrip items={taxonomyRows.map((row) => ({ label: `${row.level} ${row.name}`, value: row.nodes.toLocaleString(), delta: row.coverage }))} />
      <div className="taxonomy-layout">
        <Panel title="L1–L4 分类树" className="taxonomy-tree">
          <div className="segment-control">{['L1', 'L2', 'L3', 'L4'].map((item) => <button className={level === item ? 'active' : ''} onClick={() => setLevel(item)} key={item}>{item}</button>)}</div>
          <div className="tree-list">
            <button className="selected"><Waypoints size={16} /><span>机器人系统</span><em>63</em><ChevronRight size={15} /></button>
            <button><Waypoints size={16} /><span>感知与认知</span><em>48</em><ChevronRight size={15} /></button>
            <button><Waypoints size={16} /><span>规划与决策</span><em>39</em><ChevronRight size={15} /></button>
            <button><Waypoints size={16} /><span>仿真与数据</span><em>31</em><ChevronRight size={15} /></button>
            <button><Waypoints size={16} /><span>工程基础设施</span><em>28</em><ChevronRight size={15} /></button>
          </div>
        </Panel>
        <Panel title={`${level} 技术概念`} subtitle="标准概念、表面词与语义角色" action={<label className="inline-search"><Search size={15} /><input placeholder="搜索技术词" value={query} onChange={(e) => setQuery(e.target.value)} /></label>}>
          <div className="table-wrap"><table className="data-table"><thead><tr><th>编码 / 名称</th><th>上级分类</th><th>L4 表面词</th><th>T 领域</th><th>语义角色</th><th>状态</th></tr></thead><tbody>{filtered.map((item) => <tr key={item.code}><td><strong>{item.name}</strong><small>{item.code}</small></td><td>{item.parent}</td><td>{item.terms}</td><td>{item.domain}</td><td>{item.role}</td><td><StatusTag tone={item.status === '正式' ? 'success' : 'warning'}>{item.status}</StatusTag></td></tr>)}</tbody></table></div>
        </Panel>
      </div>
      <Panel title="T1–T7 领域映射" subtitle="领域归属与 L 层级相互独立；跨领域项可设一个主领域和多个次领域">
        <div className="domain-rail">{domains.map((domain) => <button key={domain.code}><i style={{ background: domain.color }} /><strong>{domain.code}</strong><span>{domain.name}</span><em>{domain.value} 条 JD</em><Split size={15} /></button>)}</div>
      </Panel>
    </div>
  )
}
