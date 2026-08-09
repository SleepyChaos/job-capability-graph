import { Activity, ArrowRight, GitBranch, Network, RefreshCw } from 'lucide-react'
import { MetricStrip, MiniLineChart, Panel, StatusTag } from '../components/ui'
import { skillRows } from '../data/mockData'
import type { PageId } from '../types'

const viewEntries: { id: PageId; title: string; description: string; icon: typeof Activity; meta: string }[] = [
  { id: 'graph-heatmap', title: '能力热力图', description: '以 21×15 日格汇总七个技术域过去 45 天的材料触发次数，并下钻 L2 技术词。', icon: Activity, meta: '7 个技术域 · 315 个逐日热力格' },
  { id: 'graph-relations', title: '岗位—能力关联图', description: '全局展示全部岗位聚类与技术能力关键词，并连接各岗位簇的重要能力。', icon: Network, meta: '43 个岗位聚类 · 8,936 条重要能力关系' },
  { id: 'graph-clusters', title: '聚类岗位能力图谱', description: '选择岗位聚类，以距离查看能力重要性，以颜色深浅查看近期活跃度。', icon: GitBranch, meta: '距离 = 出现次数 · 深浅 = 近期频次' },
]

export function GraphPage({ onNavigate }: { onNavigate: (page: PageId) => void }) {
  return (
    <div className="page-stack capability-home">
      <div className="page-intro"><div><h2>动态岗位能力图谱</h2><p>从热度、关联结构和岗位聚类三个视角观察具身智能岗位能力的分布与演化。</p></div><button className="secondary-button"><RefreshCw size={15} />刷新图谱快照</button></div>
      <MetricStrip items={[{ label: '岗位聚类', value: '43', delta: '↑ 2' }, { label: '标准能力节点', value: '229', delta: '↑ 8' }, { label: '岗位—能力关系', value: '8,936', delta: '↑ 312' }, { label: '本期新兴能力', value: '17', delta: '↑ 5' }]} />

      <section className="graph-view-entry-grid" aria-label="能力图谱分析入口">
        {viewEntries.map(({ id, title, description, icon: Icon, meta }) => <button key={id} onClick={() => onNavigate(id)}><Icon size={23} /><div><h3>{title}</h3><p>{description}</p><span>{meta}</span></div><ArrowRight size={17} /></button>)}
      </section>

      <div className="graph-home-grid">
        <Panel title="能力需求变化" subtitle="近 90 天需求强度变化最大的标准能力">
          <div className="graph-trend-list">{skillRows.map((row) => <div key={row.skill}><div><strong>{row.skill}</strong><span>{row.state}</span></div><MiniLineChart values={[50, 44, 55, row.strength]} /><b>+{row.trend}%</b></div>)}</div>
        </Panel>
        <Panel title="图谱更新状态" subtitle="正式数据库快照 2026.08.09">
          <div className="graph-update-status"><StatusTag tone="success">更新完成</StatusTag><strong>本期新增 312 条岗位—能力关系</strong><p>更新覆盖 68 条新入库 JD、9 个能力节点和 3 个岗位聚类，所有关系均保留来源与时间证据。</p><dl><div><dt>最近构建</dt><dd>今天 11:30</dd></div><div><dt>图谱版本</dt><dd>graph-v0.6</dd></div><div><dt>关系覆盖率</dt><dd>94.2%</dd></div></dl></div>
        </Panel>
      </div>
    </div>
  )
}
