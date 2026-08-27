import { ArrowRight, Bot, Database, FileUser, Network, RefreshCw, ScanSearch, ShieldAlert } from 'lucide-react'
import { useEffect, useState } from 'react'
import { clusteringApi } from '../api/clustering'
import { dataCenterApi, type DataSourceItem, type ReviewTask } from '../api/dataCenter'
import { discoveryApi, maturityStageLabels, type CandidateListItem } from '../api/discovery'
import { jobsApi, type JobSummary } from '../api/jobs'
import { talentApi } from '../api/talent'
import { taxonomyApi, type TechnologyDomain } from '../api/taxonomy'
import { LinkButton, MetricStrip, Panel, StatusTag } from '../components/ui'
import { domainColors } from '../data/graphData'
import type { PageId } from '../types'

interface OverviewStats {
  jobSummary: JobSummary
  sources: DataSourceItem[]
  domains: TechnologyDomain[]
  levelCounts: Record<string, number>
  clusterTotal: number
  candidateTotal: number
  topCandidates: CandidateListItem[]
  queuedReviews: ReviewTask[]
  profileCount: number
}

export function OverviewPage({ onNavigate }: { onNavigate: (page: PageId) => void }) {
  const [stats, setStats] = useState<OverviewStats | null>(null)
  const [error, setError] = useState('')

  useEffect(() => {
    const controller = new AbortController()
    Promise.all([
      jobsApi.summary(controller.signal),
      dataCenterApi.sources(controller.signal),
      taxonomyApi.domains(null, controller.signal),
      taxonomyApi.nodes({ level: 'L1', limit: 1 }, controller.signal),
      taxonomyApi.nodes({ level: 'L2', limit: 1 }, controller.signal),
      taxonomyApi.nodes({ level: 'L3', limit: 1 }, controller.signal),
      taxonomyApi.nodes({ level: 'L4', limit: 1 }, controller.signal),
      clusteringApi.clusters({ limit: 1 }, controller.signal),
      discoveryApi.candidates({ limit: 4 }, controller.signal),
      dataCenterApi.reviews('queued', controller.signal),
      talentApi.profiles(controller.signal),
    ])
      .then(([jobSummary, sources, domains, l1, l2, l3, l4, clusters, candidates, queuedReviews, profiles]) => {
        setStats({
          jobSummary,
          sources,
          domains,
          levelCounts: { L1: l1.total, L2: l2.total, L3: l3.total, L4: l4.total },
          clusterTotal: clusters.total,
          candidateTotal: candidates.total,
          topCandidates: candidates.items,
          queuedReviews,
          profileCount: profiles.length,
        })
      })
      .catch((reason: Error) => { if (reason.name !== 'AbortError') setError(reason.message) })
    return () => controller.abort()
  }, [])

  if (error) {
    return <div className="page-stack"><div className="empty-state"><ShieldAlert size={26} /><strong>总览加载失败</strong><span>{error}</span></div></div>
  }
  if (!stats) {
    return <div className="page-stack"><div className="empty-state"><RefreshCw className="spin" size={24} /><strong>正在聚合真实数据…</strong></div></div>
  }

  const workflow = [
    { label: '多源采集', detail: `${stats.sources.length} 个数据源`, icon: Database, page: 'sources' as PageId },
    { label: '岗位发现', detail: `${stats.candidateTotal} 个候选`, icon: ScanSearch, page: 'jobs' as PageId },
    { label: '能力演化', detail: `${stats.clusterTotal} 个岗位簇`, icon: Network, page: 'graph-clusters' as PageId },
    { label: '简历画像', detail: `${stats.profileCount} 份画像`, icon: FileUser, page: 'resume' as PageId },
    { label: '精准匹配', detail: '差距驱动路径', icon: Bot, page: 'match' as PageId },
  ]

  const totalNodes = stats.domains.reduce((sum, item) => sum + item.node_count, 0)
  let angle = 0
  const segments = stats.domains.map((item) => {
    const start = angle
    angle += totalNodes > 0 ? (item.node_count / totalNodes) * 360 : 0
    return `${domainColors[item.code] ?? item.color ?? '#64748b'} ${start}deg ${angle}deg`
  }).join(', ')

  return (
    <div className="page-stack">
      <section className="workflow-rail" aria-label="系统闭环">
        {workflow.map(({ label, detail, icon: Icon, page }, index) => (
          <button className="workflow-step" key={label} onClick={() => onNavigate(page)} style={{ background: 'none', border: 0, cursor: 'pointer' }}>
            <div className="workflow-icon"><Icon size={19} /></div>
            <div><strong>{label}</strong><span>{detail}</span></div>
            {index < workflow.length - 1 ? <ArrowRight className="workflow-arrow" size={18} /> : null}
          </button>
        ))}
      </section>

      <MetricStrip items={[
        { label: '正式 JD', value: stats.jobSummary.total_jobs.toLocaleString(), delta: `${stats.jobSummary.organization_count} 家机构` },
        { label: '岗位聚类', value: stats.clusterTotal.toLocaleString(), delta: '最新成功运行' },
        { label: '新岗位候选', value: String(stats.candidateTotal), delta: '推演候选库' },
        { label: '标准技术点', value: stats.levelCounts.L3.toLocaleString(), delta: `体系 ${Object.values(stats.levelCounts).reduce((sum, count) => sum + count, 0).toLocaleString()} 节点` },
      ]} />

      <div className="overview-grid">
        <Panel title="T1–T7 领域分布" subtitle="技术体系节点在各领域的归属数量">
          <div className="domain-distribution">
            <div className="donut" style={{ background: `conic-gradient(${segments})` }}>
              <div><strong>{totalNodes.toLocaleString()}</strong><span>体系节点</span></div>
            </div>
            <div className="domain-legend">
              {stats.domains.map((item) => <div key={item.code}><i style={{ background: domainColors[item.code] ?? item.color ?? '#64748b' }} /><span>{item.code} {item.name}</span><strong>{totalNodes > 0 ? Math.round(item.node_count / totalNodes * 100) : 0}%</strong></div>)}
            </div>
          </div>
        </Panel>

        <Panel title="数据时间边界" subtitle="趋势结论的主要限制，来自真实数据统计">
          <div className="governance-list">
            <div><Database size={17} /><span>具备来源时间的 JD</span><strong>{stats.jobSummary.source_timed_count.toLocaleString()}</strong></div>
            <div><Database size={17} /><span>仅迁移时间的 JD</span><strong>{stats.jobSummary.migration_timed_count.toLocaleString()}</strong></div>
            <div><ShieldAlert size={17} /><span>重复簇（转载降权）</span><strong>{stats.jobSummary.duplicate_group_count.toLocaleString()}</strong></div>
            <div><ShieldAlert size={17} /><span>热力图口径</span><strong>45 天窗口</strong></div>
          </div>
        </Panel>

        <Panel title="L1–L4 分层状态" action={<LinkButton onClick={() => onNavigate('taxonomy')}>查看主数据</LinkButton>}>
          <table className="compact-table">
            <thead><tr><th>层级</th><th>节点数</th><th>说明</th></tr></thead>
            <tbody>
              <tr><td><strong>L1</strong></td><td>{stats.levelCounts.L1}</td><td>一级分类</td></tr>
              <tr><td><strong>L2</strong></td><td>{stats.levelCounts.L2}</td><td>二级分类 / 技术栈</td></tr>
              <tr><td><strong>L3</strong></td><td>{stats.levelCounts.L3}</td><td>标准技术点（图谱主节点）</td></tr>
              <tr><td><strong>L4</strong></td><td>{stats.levelCounts.L4}</td><td>技术表面词（识别与证据）</td></tr>
            </tbody>
          </table>
        </Panel>
      </div>

      <div className="overview-lower">
        <Panel title="数据源状态" action={<LinkButton onClick={() => onNavigate('sources')}>进入采集中枢</LinkButton>}>
          <div className="activity-list">
            {stats.sources.slice(0, 5).map((source) => (
              <button key={source.source_code} onClick={() => onNavigate('sources')}>
                <i /><div><strong>{source.source_name}</strong><span>{source.source_code} · {source.source_status_code}</span></div><ArrowRight size={15} />
              </button>
            ))}
          </div>
        </Panel>
        <Panel title="新岗位候选" action={<LinkButton onClick={() => onNavigate('jobs')}>进入推演</LinkButton>}>
          <div className="timeline-list">
            {stats.topCandidates.map((candidate) => (
              <button key={candidate.candidate_code} onClick={() => onNavigate('jobs')}>
                <time>{Number(candidate.candidate_score).toFixed(1)} 分</time><i />
                <div>
                  <StatusTag tone={candidate.workflow_status_code === 'approved' ? 'success' : 'warning'}>{maturityStageLabels[candidate.maturity_stage_code] ?? candidate.maturity_stage_code}</StatusTag>
                  <strong>{candidate.proposed_name}</strong>
                  <span>{candidate.run_code} · {candidate.workflow_status_code}</span>
                </div>
              </button>
            ))}
            {stats.topCandidates.length === 0 ? <p className="table-note">暂无候选；可在"新岗位发现"运行自动预测。</p> : null}
          </div>
        </Panel>
        <Panel title={`待审核队列 · ${stats.queuedReviews.length}`} action={<LinkButton onClick={() => onNavigate('review')}>进入审核</LinkButton>}>
          <table className="compact-table review-preview">
            <thead><tr><th>类型</th><th>内容</th><th>优先级</th></tr></thead>
            <tbody>{stats.queuedReviews.slice(0, 4).map((task) => (
              <tr key={task.task_code}>
                <td>{task.target_type_code === 'job_role_version' ? '岗位版本建议' : task.target_type_code}</td>
                <td>{String(task.target_snapshot.role_name ?? task.target_snapshot.milestone_name ?? `目标 #${task.target_id}`)}</td>
                <td>{Number(task.priority_score).toFixed(0)}</td>
              </tr>
            ))}</tbody>
          </table>
        </Panel>
      </div>
    </div>
  )
}
