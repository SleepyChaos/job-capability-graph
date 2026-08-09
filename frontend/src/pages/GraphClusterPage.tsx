import { ArrowRight, Building2, GitBranch, TrendingUp, Users } from 'lucide-react'
import type { CSSProperties } from 'react'
import { useState } from 'react'
import { DomainLegend } from '../components/DomainLegend'
import { GraphFilters } from '../components/GraphFilters'
import { StatusTag } from '../components/ui'
import { capabilityClusters, domainColors } from '../data/graphData'

export function GraphClusterPage({ notify }: { notify: (message: string) => void }) {
  const [selectedId, setSelectedId] = useState(capabilityClusters[0].id)
  const selected = capabilityClusters.find((cluster) => cluster.id === selectedId) ?? capabilityClusters[0]
  const [selectedSkillName, setSelectedSkillName] = useState(selected.skills[0].name)
  const selectedSkill = selected.skills.find((skill) => skill.name === selectedSkillName) ?? selected.skills[0]

  const selectCluster = (cluster: typeof selected) => {
    setSelectedId(cluster.id)
    setSelectedSkillName(cluster.skills[0].name)
  }

  return (
    <div className="page-stack graph-analysis-page">
      <div className="page-intro"><div><h2>聚类岗位能力图谱</h2><p>聚焦一个岗位聚类：越靠近中心的能力出现次数越多；同域颜色越深，表示最近几批相关 JD 中出现越频繁。</p></div></div>
      <GraphFilters onApply={(summary) => notify(`聚类图谱筛选已更新：${summary}`)} />
      <div className="cluster-graph-workspace">
        <aside className="cluster-list" aria-label="岗位聚类列表"><header><strong>岗位聚类</strong><span>{capabilityClusters.length} 个示例簇</span></header>{capabilityClusters.map((cluster) => <button className={cluster.id === selected.id ? 'selected' : ''} key={cluster.id} onClick={() => selectCluster(cluster)}><span>{cluster.domain}</span><strong>{cluster.name}</strong><small>{cluster.roles} 个岗位 · {cluster.jdCount} 条 JD</small><ArrowRight size={14} /></button>)}</aside>
        <section className="cluster-map" aria-label={`${selected.name}能力重要性与新鲜度分布`}>
          <div className="cluster-importance-key" aria-hidden="true"><span>重要</span><span>次要</span><span>长尾</span></div>
          <div className="cluster-guide cluster-guide--near" /><div className="cluster-guide cluster-guide--mid" /><div className="cluster-guide cluster-guide--far" />
          <div className="cluster-core" style={{ '--domain-color': domainColors[selected.domain] } as CSSProperties}><span>{selected.domain}</span><strong>{selected.name}</strong><small>能力频次中心</small></div>
          <div className="cluster-skill-field">{selected.skills.map((skill) => <button key={skill.name} className={selectedSkill.name === skill.name ? 'selected' : ''} style={{ left: `${skill.x}%`, top: `${skill.y}%`, '--domain-color': domainColors[skill.domain], '--recency': `${skill.recentRate}%`, '--node-text': skill.recentRate >= 58 ? '#fff' : '#24445f' } as CSSProperties} aria-pressed={selectedSkill.name === skill.name} aria-label={`${skill.name}，出现 ${skill.occurrences} 次，近期活跃度 ${skill.recentRate}%，最近出现 ${skill.lastSeen}`} onClick={() => setSelectedSkillName(skill.name)}><small>{skill.domain}</small><strong>{skill.name}</strong><span>{skill.occurrences} 次</span><em>{skill.lastSeen}</em></button>)}</div>
          <svg className="cluster-edge-layer" viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden="true">{selected.skills.map((skill) => <line key={skill.name} x1="50" y1="50" x2={skill.x} y2={skill.y} style={{ '--edge-color': domainColors[skill.domain], opacity: Math.max(.28, skill.recentRate / 100) } as CSSProperties} />)}</svg>
          <div className="cluster-map-legend"><DomainLegend compact /><div className="recency-key"><span>久未出现</span><i style={{ '--domain-color': domainColors[selectedSkill.domain] } as CSSProperties} /><span>近期高频</span></div></div>
        </section>
        <aside className="cluster-inspector"><StatusTag tone="info">{selected.domain} 主领域</StatusTag><h3>{selected.name}</h3><p>{selected.description}</p><div className="cluster-facts"><div><Users size={16} /><span>岗位名称</span><strong>{selected.roles}</strong></div><div><Building2 size={16} /><span>关联 JD</span><strong>{selected.jdCount}</strong></div><div><TrendingUp size={16} /><span>近窗增长</span><strong>+{selected.growth}%</strong></div></div><h4>选中能力</h4><div className="selected-skill-summary"><i style={{ background: domainColors[selectedSkill.domain] }} /><div><strong>{selectedSkill.name}</strong><span>{selectedSkill.domain} · 最近出现 {selectedSkill.lastSeen}</span></div><b>{selectedSkill.occurrences} 次</b></div><dl className="inspector-facts"><div><dt>全窗重要性</dt><dd>{selectedSkill.strength}%</dd></div><div><dt>近期活跃度</dt><dd>{selectedSkill.recentRate}%</dd></div><div><dt>距离含义</dt><dd>越近越重要</dd></div></dl><h4>能力频次排序</h4><div className="cluster-skill-bars">{selected.skills.map((skill) => <button className={skill.name === selectedSkill.name ? 'selected' : ''} key={skill.name} onClick={() => setSelectedSkillName(skill.name)}><span><i style={{ background: domainColors[skill.domain] }} />{skill.name}</span><div><i style={{ width: `${skill.strength}%`, background: domainColors[skill.domain] }} /></div><strong>{skill.occurrences}</strong></button>)}</div><button className="secondary-button" onClick={() => notify('已打开该岗位簇的 JD 频次与时间证据')}><GitBranch size={15} />查看 JD 频次证据</button></aside>
      </div>
      <p className="chart-source-note">距离编码全时间窗出现次数，颜色深浅编码近期 JD 高频程度；两者分开计算，避免把“长期重要”与“近期活跃”混为一谈。</p>
    </div>
  )
}
