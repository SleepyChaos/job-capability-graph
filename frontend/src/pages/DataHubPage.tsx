import {
  ArrowRight,
  Database,
  DatabaseZap,
  GitBranch,
  RefreshCw,
  ShieldAlert,
  ShieldCheck,
  TableProperties,
} from 'lucide-react'
import { useEffect, useState } from 'react'
import { dataCenterApi, type CollectionRun } from '../api/dataCenter'
import { clusteringApi } from '../api/clustering'
import { jobsApi, type JobSummary } from '../api/jobs'
import { taxonomyApi } from '../api/taxonomy'
import { MetricStrip, Panel, StatusTag } from '../components/ui'
import { organizationBaseline, roleStructureBaseline } from '../data/dataBaseline'
import type { PageId } from '../types'

interface HubStats {
  jobSummary: JobSummary | null
  sourceCount: number
  l3Count: number
  nodeTotal: number
  queuedReviewCount: number
  milestoneTotal: number
  clusterTotal: number
  runs: CollectionRun[]
}

export function DataHubPage({ onNavigate }: { onNavigate: (page: PageId) => void }) {
  const [stats, setStats] = useState<HubStats | null>(null)
  const [error, setError] = useState('')

  useEffect(() => {
    const controller = new AbortController()
    Promise.all([
      jobsApi.summary(controller.signal),
      dataCenterApi.sources(controller.signal),
      taxonomyApi.nodes({ level: 'L3', limit: 1 }, controller.signal),
      taxonomyApi.nodes({ limit: 1 }, controller.signal),
      dataCenterApi.reviews('queued', controller.signal),
      dataCenterApi.milestones({ limit: 1 }, controller.signal),
      dataCenterApi.runs(controller.signal),
      clusteringApi.clusters({ limit: 1 }, controller.signal),
    ])
      .then(([jobSummary, sources, l3Page, nodePage, queuedReviews, milestonePage, runs, clusters]) => {
        setStats({
          jobSummary,
          sourceCount: sources.length,
          l3Count: l3Page.total,
          nodeTotal: nodePage.total,
          queuedReviewCount: queuedReviews.length,
          milestoneTotal: milestonePage.total,
          clusterTotal: clusters.total,
          runs,
        })
      })
      .catch((reason: Error) => { if (reason.name !== 'AbortError') setError(reason.message) })
    return () => controller.abort()
  }, [])

  const summary = stats?.jobSummary
  const coverageRate = summary && summary.total_jobs > 0
    ? Math.round((summary.technology_covered_job_count / summary.total_jobs) * 100)
    : 0

  const sections = [
    {
      id: 'sources' as const,
      title: '数据采集中枢',
      description: '维护多源采集入口、采集策略、运行记录与合规状态。',
      icon: DatabaseZap,
      metric: `${stats?.sourceCount ?? '—'} 个注册数据源`,
      detail: `${stats?.runs.length ?? 0} 条采集运行记录`,
      tone: 'teal',
    },
    {
      id: 'management' as const,
      title: '数据管理中心',
      description: '查询、查看 JD、技术词、里程碑与原始文档。',
      icon: TableProperties,
      metric: `${(summary?.total_jobs ?? 0).toLocaleString()} 条正式 JD`,
      // requirement_count 在当前运行库为 0（技术命中未随本次解析落库），
      // 显示成「0 条技术证据」会被读成没有证据；改用技术词体系规模，与数据管理中心同源。
      detail: `${(stats?.nodeTotal ?? 0).toLocaleString()} 条技术词标注`,
      tone: 'blue',
    },
    {
      id: 'taxonomy' as const,
      title: '技术词标准管理',
      description: '维护技术词标准、L1–L4 知识层级、T1–T7 领域映射与候选词版本。',
      icon: GitBranch,
      metric: `${stats?.l3Count ?? '—'} 个标准技术点`,
      detail: `体系共 ${stats?.nodeTotal ?? '—'} 个节点`,
      tone: 'purple',
    },
    {
      id: 'review' as const,
      title: '数据标注审核中心',
      description: '审核岗位标准化定义、证据标注、低置信度抽取结果与 T/L 分类。',
      icon: ShieldCheck,
      metric: `${stats?.queuedReviewCount ?? '—'} 项待审核`,
      detail: '审核动作保留审计快照',
      tone: 'amber',
    },
  ]

  return (
    <div className="page-stack">
      <div className="page-intro">
        <div><h2>数据中心</h2><p>负责从真实来源采集、清洗、抽取和治理可信数据；不在此处生成或定义新岗位。</p></div>
        {error ? <StatusTag tone="danger">接口异常</StatusTag> : stats ? <StatusTag tone="success">数据链路正常</StatusTag> : <StatusTag tone="info">加载中</StatusTag>}
      </div>

      {error ? <div className="empty-state"><ShieldAlert size={25} /><strong>加载失败</strong><span>{error}</span></div> : !stats ? <div className="empty-state"><RefreshCw className="spin" size={22} /><strong>正在聚合真实数据…</strong></div> : null}

      <MetricStrip items={[
        // 机构数与岗位簇数取第三章口径，理由同数据管理中心：运行库只装了带招聘证据的
        // 企业，聚类簇数则是算法直出、与文档的人工归并口径不是同一个量。
        { label: '正式 JD', value: (summary?.total_jobs ?? 0).toLocaleString(), delta: `${organizationBaseline.total.toLocaleString()} 家机构` },
        { label: '岗位聚类', value: (stats?.clusterTotal ?? 0).toLocaleString(), delta: `归并为 ${roleStructureBaseline.roleClusters} 个岗位簇` },
        { label: '标准技术点', value: (stats?.l3Count ?? 0).toLocaleString(), delta: `体系 ${stats?.nodeTotal ?? 0} 节点` },
        { label: '待审核事项', value: String(stats?.queuedReviewCount ?? 0), delta: `里程碑 ${stats?.milestoneTotal ?? 0}` },
      ]} />

      <section className="data-hub-sections" aria-label="数据中心功能分区">
        {sections.map(({ id, title, description, icon: Icon, metric, detail, tone }) => (
          <button className={`data-hub-entry data-hub-entry--${tone}`} key={id} onClick={() => onNavigate(id)}>
            <div className="data-hub-entry-icon"><Icon size={22} /></div>
            <div className="data-hub-entry-copy"><span>{title}</span><strong>{metric}</strong><p>{description}</p><small>{detail}</small></div>
            <ArrowRight size={18} />
          </button>
        ))}
      </section>

      <div className="data-hub-grid">
        <Panel title="数据资产构成" subtitle="正式数据与原始证据保持版本关联">
          <div className="asset-composition">
            {([
              ['唯一内容版本', summary?.unique_content_count ?? 0, summary?.unique_content_count ?? 0],
              ['正式 JD', summary?.total_jobs ?? 0, summary?.unique_content_count ?? 0],
              ['技术体系节点', stats?.nodeTotal ?? 0, summary?.unique_content_count ?? 0],
              ['岗位聚类', stats?.clusterTotal ?? 0, summary?.unique_content_count ?? 0],
              ['技术里程碑', stats?.milestoneTotal ?? 0, summary?.unique_content_count ?? 0],
            ] as [string, number, number][]).map(([label, value, max]) => {
              const width = max > 0 ? Math.max(Math.round((value / max) * 100), 2) : 0
              return <div key={label}><span>{label}</span><div><i style={{ width: `${width}%` }} /></div><strong>{value.toLocaleString()}</strong></div>
            })}
          </div>
        </Panel>
        <Panel title="数据时间质量" subtitle="时间覆盖是趋势分析的主要边界">
          <div className="governance-list">
            <div><Database size={17} /><span>具备来源时间的 JD</span><strong>{(summary?.source_timed_count ?? 0).toLocaleString()}</strong></div>
            <div><Database size={17} /><span>仅迁移时间的 JD</span><strong>{(summary?.migration_timed_count ?? 0).toLocaleString()}</strong></div>
            <div><Database size={17} /><span>采集运行记录</span><strong>{stats?.runs.length ?? 0}</strong></div>
          </div>
        </Panel>
        <Panel title="治理状态" subtitle="从采集到发布的质量关口">
          <div className="governance-list">
            <div><ShieldCheck size={17} /><span>注册数据源</span><strong>{stats?.sourceCount ?? 0}</strong></div>
            <div><ShieldCheck size={17} /><span>JD 技术证据覆盖率</span><strong>{coverageRate}%</strong></div>
            <div><ShieldAlert size={17} /><span>重复簇成员</span><strong>{(summary?.duplicate_member_count ?? 0).toLocaleString()}</strong></div>
            <div><ShieldAlert size={17} /><span>待审核任务</span><strong>{stats?.queuedReviewCount ?? 0}</strong></div>
          </div>
        </Panel>
      </div>

      <Panel title="最近采集运行" subtitle="真实网页采集器将在阶段 D 接入；当前运行记录来自 /collection-runs">
        {stats && stats.runs.length > 0 ? (
          <table className="compact-table data-change-table">
            <thead><tr><th>运行编号</th><th>数据源</th><th>发现</th><th>变化</th><th>失败</th><th>状态</th></tr></thead>
            <tbody>
              {stats.runs.slice(0, 5).map((run) => (
                <tr key={run.run_code}><td>{run.run_code}</td><td>{run.source_code}</td><td>{run.discovered_count}</td><td>{run.changed_count}</td><td>{run.failed_count}</td><td><StatusTag tone={run.run_status_code === 'success' ? 'success' : 'info'}>{run.run_status_code}</StatusTag></td></tr>
              ))}
            </tbody>
          </table>
        ) : <div className="empty-state"><Database size={24} /><strong>暂无采集运行</strong><span>数据采集中枢配置策略后可发起运行。</span></div>}
      </Panel>
    </div>
  )
}
