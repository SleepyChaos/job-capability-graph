import { ArrowRight, Bot, Database, FileUser, Network, ScanSearch } from 'lucide-react'
import { domains, initialReviews, roleCandidates, sources, taxonomyRows } from '../data/mockData'
import { LinkButton, MetricStrip, MiniLineChart, Panel, StatusTag } from '../components/ui'
import type { PageId } from '../types'

const workflow = [
  { label: '多源采集', detail: '12 个数据源', icon: Database },
  { label: '岗位发现', detail: '识别 7 个候选', icon: ScanSearch },
  { label: '能力演化', detail: '更新 312 条关系', icon: Network },
  { label: '简历画像', detail: '待确认 4 项事实', icon: FileUser },
  { label: '精准匹配', detail: '生成 3 条路径', icon: Bot },
]

export function OverviewPage({ onNavigate }: { onNavigate: (page: PageId) => void }) {
  const total = domains.reduce((sum, item) => sum + item.value, 0)
  let angle = 0
  const segments = domains.map((item) => {
    const start = angle
    angle += (item.value / total) * 360
    return `${item.color} ${start}deg ${angle}deg`
  }).join(', ')

  return (
    <div className="page-stack">
      <section className="workflow-rail" aria-label="系统闭环">
        {workflow.map(({ label, detail, icon: Icon }, index) => (
          <div className="workflow-step" key={label}>
            <div className="workflow-icon"><Icon size={19} /></div>
            <div><strong>{label}</strong><span>{detail}</span></div>
            {index < workflow.length - 1 ? <ArrowRight className="workflow-arrow" size={18} /> : null}
          </div>
        ))}
      </section>

      <MetricStrip items={[
        { label: '有效 JD', value: '1,284', delta: '↑ 12.6%' },
        { label: '岗位聚类', value: '36', delta: '↑ 2' },
        { label: '新岗位候选', value: '7', delta: '↑ 3' },
        { label: '标准技术点', value: '229', delta: '↑ 8' },
      ]} />

      <div className="overview-grid">
        <Panel title="T1–T7 领域分布" subtitle="近 90 天有效 JD">
          <div className="domain-distribution">
            <div className="donut" style={{ background: `conic-gradient(${segments})` }}>
              <div><strong>{total.toLocaleString()}</strong><span>有效 JD</span></div>
            </div>
            <div className="domain-legend">
              {domains.map((item) => <div key={item.code}><i style={{ background: item.color }} /><span>{item.code} {item.name}</span><strong>{Math.round(item.value / total * 100)}%</strong></div>)}
            </div>
          </div>
        </Panel>

        <Panel title="领域趋势" subtitle="各 T 领域新增 JD 指数">
          <div className="trend-legend">{domains.slice(0, 5).map((item) => <span key={item.code}><i style={{ background: item.color }} />{item.code}</span>)}</div>
          <div className="trend-stack">
            <MiniLineChart color="#1769e0" values={[38, 54, 49, 68, 61, 74, 69, 83, 76, 91]} />
            <MiniLineChart color="#0b9c93" values={[24, 31, 29, 42, 38, 49, 44, 55, 51, 62]} />
            <MiniLineChart color="#38a8dc" values={[18, 22, 25, 30, 27, 36, 39, 43, 41, 48]} />
          </div>
          <div className="chart-axis"><span>05-01</span><span>05-15</span><span>05-29</span></div>
        </Panel>

        <Panel title="L1–L4 分层状态" action={<LinkButton onClick={() => onNavigate('taxonomy')}>查看主数据</LinkButton>}>
          <table className="compact-table">
            <thead><tr><th>层级</th><th>节点</th><th>已映射</th><th>覆盖率</th></tr></thead>
            <tbody>{taxonomyRows.map((row) => <tr key={row.level}><td><strong>{row.level}</strong> {row.name}</td><td>{row.nodes}</td><td>{row.mapped}</td><td>{row.coverage}</td></tr>)}</tbody>
          </table>
        </Panel>
      </div>

      <div className="overview-lower">
        <Panel title="数据活动" action={<LinkButton onClick={() => onNavigate('sources')}>全部活动</LinkButton>}>
          <div className="activity-list">
            {sources.slice(0, 5).map((source) => <button key={source.id}><i /><div><strong>{source.name}</strong><span>新增 {source.additions} 条 · {source.lastRun}</span></div><ArrowRight size={15} /></button>)}
          </div>
        </Panel>
        <Panel title="岗位演化" action={<LinkButton onClick={() => onNavigate('jobs')}>完整时间线</LinkButton>}>
          <div className="timeline-list">
            {roleCandidates.map((role, index) => <button key={role.id}><time>05-{28 - index * 2}</time><i /><div><StatusTag tone={index === 2 ? 'info' : 'warning'}>{role.stage}</StatusTag><strong>{role.name}</strong><span>{role.summary}</span></div></button>)}
          </div>
        </Panel>
        <Panel title={`待审核队列 · ${initialReviews.length}`} action={<LinkButton onClick={() => onNavigate('review')}>进入审核</LinkButton>}>
          <table className="compact-table review-preview">
            <thead><tr><th>类型</th><th>内容</th><th>置信度</th></tr></thead>
            <tbody>{initialReviews.slice(0, 4).map((item) => <tr key={item.id}><td>{item.type}</td><td>{item.content}</td><td>{Math.round(item.confidence * 100)}%</td></tr>)}</tbody>
          </table>
        </Panel>
      </div>
    </div>
  )
}
