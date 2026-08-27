import { Activity, ArrowRight, GitBranch, Network, RefreshCw } from 'lucide-react'
import { useCallback, useEffect, useState } from 'react'
import { graphApi, type ClusterListResponse, type HeatmapResponse, type JobArchitectureOverview } from '../api/graphs'
import { MetricStrip, Panel, StatusTag } from '../components/ui'
import type { PageId } from '../types'

const viewEntries: { id: PageId; title: string; description: string; icon: typeof Activity; meta: string }[] = [
  { id: 'graph-heatmap', title: '能力热力图', description: '以 21×15 日格汇总七个技术域过去 45 天的材料触发次数，并下钻标准技术层级。', icon: Activity, meta: '矩阵比较 · 45 天固定窗口' },
  { id: 'graph-relations', title: '新版岗位图谱', description: '从岗位架构、技术—岗位、企业—岗位三个视角查看同一批岗位事实。', icon: Network, meta: '四层架构 · 五维画像 · JD证据' },
  { id: 'graph-clusters', title: '聚类岗位能力图谱', description: '选择岗位聚类，以距离查看能力重要性，以颜色深浅查看近期活跃度。', icon: GitBranch, meta: '距离 = 长期重要性 · 深浅 = 近期活跃' },
]

interface OverviewData {
  jobGraph: JobArchitectureOverview
  clusters: ClusterListResponse
  heatmap: HeatmapResponse
}

export function GraphPage({ onNavigate }: { onNavigate: (page: PageId) => void }) {
  const [data, setData] = useState<OverviewData | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [refreshKey, setRefreshKey] = useState(0)
  const refresh = useCallback(() => setRefreshKey((value) => value + 1), [])

  useEffect(() => {
    const controller = new AbortController()
    setError(null)
    Promise.all([
      graphApi.jobArchitecture(controller.signal),
      graphApi.clusters(controller.signal),
      graphApi.heatmap(null, 'L2', controller.signal),
    ]).then(([jobGraph, clusters, heatmap]) => setData({ jobGraph, clusters, heatmap }))
      .catch((reason: Error) => {
        if (reason.name !== 'AbortError') setError(reason.message)
      })
    return () => controller.abort()
  }, [refreshKey])

  const metrics = data ? [
    { label: '岗位事实', value: data.jobGraph.metadata.job_count.toLocaleString(), delta: 'v4 新版口径' },
    { label: '标准岗位', value: String(data.jobGraph.metadata.standard_role_count), delta: `${data.jobGraph.metadata.cluster_count} 个岗位簇` },
    { label: '图谱企业', value: String(data.jobGraph.metadata.company_count), delta: '企业—岗位关联' },
    { label: '可靠时间覆盖', value: `${data.heatmap.window.observed_date_count}/45`, delta: data.heatmap.window.data_status === 'partial' ? '数据不足' : '覆盖完整' },
  ] : [
    { label: '岗位事实', value: '—' }, { label: '标准岗位', value: '—' },
    { label: '图谱企业', value: '—' }, { label: '可靠时间覆盖', value: '—' },
  ]

  return <div className="page-stack capability-home">
    <div className="page-intro"><div><h2>具身智能岗位图谱</h2><p>新版岗位架构作为主图谱，热力与算法聚类作为岗位演化和发现的辅助分析。</p></div><button className="secondary-button" onClick={refresh}><RefreshCw size={15} />刷新图谱快照</button></div>
    <MetricStrip items={metrics} />
    <section className="graph-view-entry-grid" aria-label="能力图谱分析入口">{viewEntries.map(({ id, title, description, icon: Icon, meta }) => <button key={id} onClick={() => onNavigate(id)}><Icon size={23} /><div><h3>{title}</h3><p>{description}</p><span>{meta}</span></div><ArrowRight size={17} /></button>)}</section>
    <div className="graph-home-grid">
      <Panel title="新版图谱数据状态" subtitle={data ? `数据版本 ${data.jobGraph.source_version}` : '正在读取最新快照'}>
        {error ? <div className="empty-state"><strong>图谱数据加载失败</strong><span>{error}</span></div> : data ? <div className="graph-update-status"><StatusTag tone="success">三图谱联动可用</StatusTag><strong>{data.jobGraph.metadata.direction_count}方向 → {data.jobGraph.metadata.category_count}类别 → {data.jobGraph.metadata.cluster_count}簇 → {data.jobGraph.metadata.standard_role_count}标准岗位</strong><p>产业、技术和岗位画像通过标准岗位与具体JD证据关联；人岗匹配页面使用同一关联索引。</p><dl><div><dt>关联主键</dt><dd>{data.jobGraph.metadata.join_key}</dd></div><div><dt>技术节点</dt><dd>{data.jobGraph.metadata.technology_count}</dd></div><div><dt>证据口径</dt><dd>精确证据与候选分类分开</dd></div></dl></div> : <div className="empty-state"><strong>正在生成图谱投影</strong><span>并行读取新版岗位图谱和演化分析数据。</span></div>}
      </Panel>
      <Panel title="数据解释边界" subtitle="图谱只呈现证据，不替代趋势结论">
        <div className="graph-update-status"><StatusTag tone={data?.heatmap.window.data_status === 'partial' ? 'warning' : 'success'}>{data?.heatmap.window.data_status === 'partial' ? '时间覆盖不足' : '时间覆盖可用'}</StatusTag><strong>{data?.heatmap.window.warning ?? '当前窗口时间覆盖达到展示门槛'}</strong><p>当前零值可能来自没有采集数据，不能解释为技术热度为零；页面会持续显示这一限制。</p></div>
      </Panel>
    </div>
  </div>
}
