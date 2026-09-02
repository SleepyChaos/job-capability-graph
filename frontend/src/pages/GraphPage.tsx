import { Activity, ArrowRight, BriefcaseBusiness, FileUser, GitBranch, RefreshCw, Tags } from 'lucide-react'
import { useCallback, useEffect, useState } from 'react'
import { graphApi, type ClusterListResponse, type HeatmapResponse, type RelationGraphResponse } from '../api/graphs'
import { MetricStrip, Panel, StatusTag } from '../components/ui'
import type { PageId } from '../types'

const viewEntries: { id: PageId; title: string; description: string; icon: typeof Activity; meta: string }[] = [
  { id: 'industry-job-graph', title: '产业—岗位图谱', description: '从产业属性和企业逐层下钻到标准岗位与真实招聘岗位。', icon: BriefcaseBusiness, meta: '企业库 → 产业类别 → 企业 → 岗位' },
  { id: 'technology-job-graph', title: '技术—岗位图谱', description: '沿L1—L4技术主数据定位相关标准岗位与真实JD证据。', icon: Tags, meta: '技术域 → 技术类 → 技术点 → 技术词 → 岗位' },
  { id: 'job-portrait-graph', title: '岗位画像图谱', description: '从职业方向、种类和岗位簇进入标准岗位五维画像与完整JD。', icon: FileUser, meta: '方向 → 种类 → 岗位簇 → 标准岗位 → JD' },
  { id: 'graph-clusters', title: '岗位簇技能星图', description: '从产业链或全局关系图进入单个岗位簇，查看核心能力、企业覆盖和真实岗位证据。', icon: GitBranch, meta: '岗位簇局部视角 · 返回全局' },
  { id: 'graph-heatmap', title: '能力时间热力图', description: '以 21×15 日格汇总七个技术域过去 45 天的材料触发次数，并下钻标准技术层级。', icon: Activity, meta: '时间视角 · 45 天固定窗口' },
]

interface OverviewData {
  relations: RelationGraphResponse
  clusters: ClusterListResponse
  heatmap: HeatmapResponse
}

export function GraphPage({ onNavigate }: { onNavigate: (page: PageId) => void }) {
  const [data, setData] = useState<OverviewData | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [refreshKey, setRefreshKey] = useState(0)
  const refresh = useCallback(() => setRefreshKey((value) => value + 1), [])
  const hasProjection = Boolean(data && data.relations.data_version !== 'uninitialized')

  useEffect(() => {
    const controller = new AbortController()
    setError(null)
    Promise.all([
      graphApi.relations({ capabilityLevelCode: 'L2' }, controller.signal),
      graphApi.clusters(controller.signal),
      graphApi.heatmap(null, 'L2', controller.signal),
    ]).then(([relations, clusters, heatmap]) => setData({ relations, clusters, heatmap }))
      .catch((reason: Error) => {
        if (reason.name !== 'AbortError') setError(reason.message)
      })
    return () => controller.abort()
  }, [refreshKey])

  const metrics = data && hasProjection ? [
    { label: '有效岗位聚类', value: String(data.clusters.total_active_cluster_count), delta: '最新聚类快照' },
    { label: '预览能力节点', value: String(data.relations.capability_nodes.length), delta: '默认 L2' },
    { label: '预览重要关系', value: String(data.relations.edges.length), delta: 'Top-N 降采样' },
    { label: '可靠时间覆盖', value: `${data.heatmap.window.observed_date_count}/45`, delta: data.heatmap.window.data_status === 'partial' ? '数据不足' : '覆盖完整' },
  ] : [
    { label: '有效岗位聚类', value: '—' }, { label: '预览能力节点', value: '—' },
    { label: '预览重要关系', value: '—' }, { label: '可靠时间覆盖', value: '—' },
  ]

  return <div className="page-stack capability-home">
    <div className="page-intro"><div><h2>动态岗位能力图谱</h2><p>以产业链为统一入口，在全局关系、岗位簇技能和时间热度之间连续下钻同一份 JD 证据。</p></div><button className="secondary-button" onClick={refresh}><RefreshCw size={15} />刷新图谱快照</button></div>
    <MetricStrip items={metrics} />
    <section className="graph-view-entry-grid" aria-label="能力图谱分析入口">{viewEntries.map(({ id, title, description, icon: Icon, meta }) => <button key={id} onClick={() => onNavigate(id)}><Icon size={23} /><div><h3>{title}</h3><p>{description}</p><span>{meta}</span></div><ArrowRight size={17} /></button>)}</section>
    <div className="graph-home-grid">
      <Panel title="P0 图谱数据状态" subtitle={data ? `目标日期 ${data.relations.target_date}` : '正在读取最新快照'}>
        {error ? <div className="empty-state"><strong>图谱数据加载失败</strong><span>{error}</span></div> : data && hasProjection ? <div className="graph-update-status"><StatusTag tone="success">三类投影可用</StatusTag><strong>所有视图共享数据版本 {data.relations.data_version}</strong><p>关系图限制节点规模，聚类图独立计算重要性与近期活跃度，热力图固定 45 天并保留缺失警告。</p><dl><div><dt>聚类运行</dt><dd>{data.relations.clustering_run_code.slice(0, 16)}</dd></div><div><dt>投影版本</dt><dd>{data.relations.projection_version}</dd></div><div><dt>证据口径</dt><dd>已通过语境校验</dd></div></dl></div> : data ? <div className="empty-state"><strong>暂无图谱快照</strong><span>当前数据库尚未生成成功的岗位聚类运行；导入 JD、完成解析并运行聚类后，这里会显示三类投影。</span></div> : <div className="empty-state"><strong>正在生成图谱投影</strong><span>三个独立请求并行读取，避免页面加载瀑布。</span></div>}
      </Panel>
      <Panel title="数据解释边界" subtitle="图谱只呈现证据，不替代趋势结论">
        <div className="graph-update-status"><StatusTag tone={data?.heatmap.window.data_status === 'partial' ? 'warning' : 'success'}>{data?.heatmap.window.data_status === 'partial' ? '时间覆盖不足' : '时间覆盖可用'}</StatusTag><strong>{data?.heatmap.window.warning ?? '当前窗口时间覆盖达到展示门槛'}</strong><p>当前零值可能来自没有采集数据，不能解释为技术热度为零；页面会持续显示这一限制。</p></div>
      </Panel>
    </div>
  </div>
}
