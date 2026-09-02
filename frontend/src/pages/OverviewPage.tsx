import { ArrowRight, BookOpen, ClipboardCheck, Database, Network, RefreshCw, ShieldAlert, Sparkles } from 'lucide-react'
import { useEffect, useState } from 'react'
import { clusteringApi } from '../api/clustering'
import { dataCenterApi, type DataSourceItem, type DocumentFacets, type ReviewTask } from '../api/dataCenter'
import { discoveryApi, maturityStageLabels, type CandidateListItem } from '../api/discovery'
import { jobsApi, type JobSummary } from '../api/jobs'
import { rolesApi } from '../api/roles'
import { talentApi } from '../api/talent'
import { taxonomyApi, type TechnologyDomain } from '../api/taxonomy'
import { LinkButton, MetricStrip, Panel, StatusTag } from '../components/ui'
import { jobPostingBaseline, organizationBaseline, roleStructureBaseline, techAssetBaseline } from '../data/dataBaseline'
import { domainColors } from '../data/graphData'
import type { PageId } from '../types'

interface OverviewStats {
  jobSummary: JobSummary
  sources: DataSourceItem[]
  domains: TechnologyDomain[]
  levelCounts: Record<string, number>
  termTotal: number
  clusterTotal: number
  candidateTotal: number
  topCandidates: CandidateListItem[]
  queuedReviews: ReviewTask[]
  profileCount: number
  roleTotal: number
  evolvedRoleTotal: number
  facets: DocumentFacets
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
      taxonomyApi.nodes({ limit: 1 }, controller.signal),
      clusteringApi.clusters({ limit: 1 }, controller.signal),
      discoveryApi.candidates({ limit: 4 }, controller.signal),
      dataCenterApi.reviews('queued', controller.signal),
      talentApi.profiles(controller.signal),
      rolesApi.list({ limit: 1 }, controller.signal),
      rolesApi.list({ evolvedOnly: true, limit: 1 }, controller.signal),
      dataCenterApi.documentFacets(controller.signal),
    ])
      .then(([jobSummary, sources, domains, l1, l2, l3, l4, allTerms, clusters, candidates, queuedReviews, profiles, roles, evolvedRoles, facets]) => {
        setStats({
          jobSummary,
          sources,
          domains,
          levelCounts: { L1: l1.total, L2: l2.total, L3: l3.total, L4: l4.total },
          termTotal: allTerms.total,
          clusterTotal: clusters.total,
          candidateTotal: candidates.total,
          topCandidates: candidates.items,
          queuedReviews,
          profileCount: profiles.length,
          roleTotal: roles.total,
          evolvedRoleTotal: evolvedRoles.total,
          facets,
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

  const paperCount = stats.facets.types.find((item) => item.code === 'paper')?.count ?? 0
  const layerCards = [
    {
      label: '数据层',
      // 机构数取第三章口径：运行库只导入了带招聘证据的企业（84 家），高校、科研院所
      // 与政府主体尚未建表，用实数会把「尚未入库」显示成「项目没有这些数据」。
      // JD 则两级都给：原始量说明采集规模，有效量说明进入分析的部分。
      description: `汇聚 ${jobPostingBaseline.raw.toLocaleString()} 条原始岗位 JD（有效 ${jobPostingBaseline.valid.toLocaleString()} 条）、${organizationBaseline.total.toLocaleString()} 家机构与 ${techAssetBaseline.papers.toLocaleString()} 篇研究文献。`,
      destination: '进入数据管理中心',
      icon: Database,
      page: 'management' as PageId,
      tone: 'data',
    },
    {
      label: '图谱层',
      description: '构建岗位全景图谱，将企业、技术、标准岗位与人才画像统一关联。',
      destination: '进入岗位图谱',
      icon: Network,
      page: 'job-graph' as PageId,
      tone: 'graph',
    },
    {
      label: '标注层',
      description: '对岗位进行标准化定义与证据标注，事实与结果分层保存，确保每条结论可回溯。',
      destination: '进入数据标注审核中心',
      icon: ClipboardCheck,
      page: 'review' as PageId,
      tone: 'review',
    },
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
      <section className="layer-rail" aria-label="平台四层能力架构">
        {layerCards.map(({ label, description, destination, icon: Icon, page, tone }) => (
          <button className={`layer-card layer-card--${tone}`} key={label} onClick={() => onNavigate(page)}>
            <div className="layer-card-icon"><Icon size={21} /></div>
            <div className="layer-card-copy">
              <strong>{label}</strong>
              <p>{description}</p>
              <span>{destination}<ArrowRight size={14} /></span>
            </div>
          </button>
        ))}
        <article className="layer-card layer-card--ability">
          <div className="layer-card-icon"><Sparkles size={21} /></div>
          <div className="layer-card-copy">
            <strong>应用层</strong>
            <p>贯通岗位能力演变、新岗位发现与人岗匹配，让图谱洞察进入持续推演和人才应用。</p>
            <div className="layer-card-links" aria-label="应用层页面入口">
              <button onClick={() => onNavigate('role-evolution')}>岗位能力演变</button>
              <button onClick={() => onNavigate('jobs')}>新岗位发现</button>
              <button onClick={() => onNavigate('talent')}>人岗匹配</button>
            </div>
          </div>
        </article>
      </section>

      <MetricStrip items={[
        // 3,718 是运行库实数，也正是第三章的「有效 JD」，两边一致，保留实数；
        // 副标题补上它在 4,655 条原始采集量中的位置，避免被读成总采集量。
        { label: '正式 JD', value: stats.jobSummary.total_jobs.toLocaleString(), delta: `${jobPostingBaseline.raw.toLocaleString()} 条原始采集的有效部分` },
        // 624 是聚类直出的岗位版本数，第三章记的 107 是人工归并后的标准岗位。
        // 两者粒度不同、不是同一个量，因此保留实数并在副标题里点明另一口径。
        { label: '正式岗位', value: stats.roleTotal.toLocaleString(), delta: `归并为 ${roleStructureBaseline.standardRoles} 个标准岗位` },
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

        <Panel title="语料与时间边界" subtitle="趋势结论的主要限制，来自真实数据统计">
          <div className="governance-list">
            <div><Database size={17} /><span>具备来源时间的 JD</span><strong>{stats.jobSummary.source_timed_count.toLocaleString()}</strong></div>
            <div><Database size={17} /><span>仅迁移时间的 JD</span><strong>{stats.jobSummary.migration_timed_count.toLocaleString()}</strong></div>
            <div><ShieldAlert size={17} /><span>重复簇（转载降权）</span><strong>{stats.jobSummary.duplicate_group_count.toLocaleString()}</strong></div>
            <div><BookOpen size={17} /><span>上游论文（发表日期可信）</span><strong>{paperCount.toLocaleString()}</strong></div>
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
        <Panel title="新岗位候选" action={<LinkButton onClick={() => onNavigate('discovery-library')}>进入发现库</LinkButton>}>
          <div className="timeline-list">
            {stats.topCandidates.map((candidate) => (
              <button key={candidate.candidate_code} onClick={() => onNavigate('discovery-library')}>
                <time>{Number(candidate.candidate_score).toFixed(1)} 分</time><i />
                <div>
                  <StatusTag tone={candidate.workflow_status_code === 'approved' ? 'success' : 'warning'}>{maturityStageLabels[candidate.maturity_stage_code] ?? candidate.maturity_stage_code}</StatusTag>
                  <strong>{candidate.proposed_name}</strong>
                  <span>{candidate.run_code} · {candidate.workflow_status_code}</span>
                </div>
              </button>
            ))}
            {stats.topCandidates.length === 0 ? <p className="table-note">暂无候选；可在「新岗位发现台」运行自动推演。</p> : null}
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
