import { ArrowRight, Building2, GitBranch, Network, Users } from 'lucide-react'
import type { CSSProperties } from 'react'
import { useEffect, useMemo, useState } from 'react'
import {
  graphApi,
  graphLevelCode,
  type ClusterCapability,
  type ClusterGraphResponse,
  type ClusterListItem,
} from '../api/graphs'
import { DomainLegend } from '../components/DomainLegend'
import { GraphFilters, type GraphFilterState } from '../components/GraphFilters'
import { StatusTag } from '../components/ui'
import { domainColors } from '../data/graphData'

interface PositionedCapability extends ClusterCapability { x: number; y: number }

function positionCapabilities(items: ClusterCapability[]): PositionedCapability[] {
  return items.map((item, index) => {
    const angle = -.8 + (Math.PI * 2 * index) / Math.max(1, items.length)
    const radius = 39 - item.importance * .23
    return { ...item, x: 50 + Math.cos(angle) * radius, y: 50 + Math.sin(angle) * radius }
  })
}

export function GraphClusterPage({ notify }: { notify: (message: string) => void }) {
  const [filters, setFilters] = useState<GraphFilterState>({ domain: '全部 T 领域', level: 'L2 能力域' })
  const [clusters, setClusters] = useState<ClusterListItem[]>([])
  const [selectedCode, setSelectedCode] = useState<string | null>(null)
  const [detail, setDetail] = useState<ClusterGraphResponse | null>(null)
  const [selectedTechnologyId, setSelectedTechnologyId] = useState<number | null>(null)
  const [error, setError] = useState<string | null>(null)
  const levelCode = graphLevelCode(filters.level)

  useEffect(() => {
    const controller = new AbortController()
    graphApi.clusters(controller.signal)
      .then((response) => {
        setClusters(response.items)
        setSelectedCode((current) => current ?? response.items[0]?.stable_cluster_code ?? null)
      })
      .catch((reason: Error) => {
        if (reason.name !== 'AbortError') setError(reason.message)
      })
    return () => controller.abort()
  }, [])

  useEffect(() => {
    if (!selectedCode) return
    const controller = new AbortController()
    setDetail(null)
    setError(null)
    graphApi.clusterDetail(selectedCode, levelCode, controller.signal)
      .then((response) => {
        setDetail(response)
        setSelectedTechnologyId(response.capabilities[0]?.technology_node_id ?? null)
      })
      .catch((reason: Error) => {
        if (reason.name !== 'AbortError') setError(reason.message)
      })
    return () => controller.abort()
  }, [selectedCode, levelCode])

  const visibleClusters = useMemo(() => {
    const domain = filters.domain.slice(0, 2)
    return filters.domain.startsWith('T') ? clusters.filter((item) => item.domain_code === domain) : clusters
  }, [clusters, filters.domain])
  useEffect(() => {
    if (!visibleClusters.some((item) => item.stable_cluster_code === selectedCode)) {
      setSelectedCode(visibleClusters[0]?.stable_cluster_code ?? null)
    }
  }, [selectedCode, visibleClusters])
  const capabilities = useMemo(() => positionCapabilities(detail?.capabilities ?? []), [detail])
  const selectedCapability = capabilities.find((item) => item.technology_node_id === selectedTechnologyId) ?? capabilities[0]

  return (
    <div className="page-stack graph-analysis-page">
      <div className="page-intro"><div><h2>聚类岗位能力图谱</h2><p>距离编码全窗口重要性，领域色深浅编码最近 10 条相关 JD 的活跃度；两项指标独立计算。</p></div>{detail ? <StatusTag tone="success">数据版本 {detail.data_version.slice(0, 8)}</StatusTag> : null}</div>
      <GraphFilters onChange={setFilters} onApply={(summary) => notify(`聚类图谱筛选已更新：${summary}`)} />
      {error ? <div className="empty-state"><Network size={24} /><strong>聚类图谱加载失败</strong><span>{error}</span></div> : null}
      {!error && clusters.length === 0 ? <div className="empty-state"><Network size={24} /><strong>暂无聚类图谱快照</strong><span>当前数据库尚未生成成功的岗位聚类运行；完成 JD 解析和聚类后，这里会显示岗位簇与能力分布。</span></div> : null}
      {!error && clusters.length > 0 ? <div className="cluster-graph-workspace">
        <aside className="cluster-list" aria-label="岗位聚类列表"><header><strong>岗位聚类</strong><span>{visibleClusters.length} 个可浏览聚类</span></header>{visibleClusters.map((cluster) => <button className={cluster.stable_cluster_code === selectedCode ? 'selected' : ''} key={cluster.stable_cluster_code} onClick={() => setSelectedCode(cluster.stable_cluster_code)}><span>{cluster.domain_code}</span><strong>{cluster.label}</strong><small>{cluster.member_count} 条 JD · {cluster.organization_count} 家企业</small><ArrowRight size={14} /></button>)}</aside>
        <section className="cluster-map" aria-label={detail ? `${detail.cluster.label}能力重要性与近期活跃度分布` : '正在加载聚类能力'}>
          {detail ? <><div className="cluster-importance-key" aria-hidden="true"><span>重要</span><span>次要</span><span>长尾</span></div><div className="cluster-guide cluster-guide--near" /><div className="cluster-guide cluster-guide--mid" /><div className="cluster-guide cluster-guide--far" /><div className="cluster-core" style={{ '--domain-color': domainColors[detail.cluster.domain_code] } as CSSProperties}><span>{detail.cluster.domain_code}</span><strong>{detail.cluster.label}</strong><small>{detail.cluster.member_count} 条真实 JD</small></div><div className="cluster-skill-field">{capabilities.map((capability) => <button key={capability.technology_node_id} className={selectedCapability?.technology_node_id === capability.technology_node_id ? 'selected' : ''} style={{ left: `${capability.x}%`, top: `${capability.y}%`, '--domain-color': domainColors[capability.domain_code], '--recency': `${Math.max(7, capability.recent_activity)}%`, '--node-text': capability.recent_activity >= 58 ? '#fff' : '#24445f' } as CSSProperties} aria-pressed={selectedCapability?.technology_node_id === capability.technology_node_id} aria-label={`${capability.technology_name}，支持 ${capability.supporting_job_count} 条 JD，近期活跃度 ${capability.recent_activity}%`} onClick={() => setSelectedTechnologyId(capability.technology_node_id)}><small>{capability.domain_code} · {capability.level_code}</small><strong>{capability.technology_name}</strong><span>{capability.supporting_job_count} 条 JD</span><em>{capability.last_seen_at?.slice(0, 10) ?? '时间未知'}</em></button>)}</div><svg className="cluster-edge-layer" viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden="true">{capabilities.map((capability) => <line key={capability.technology_node_id} x1="50" y1="50" x2={capability.x} y2={capability.y} style={{ '--edge-color': domainColors[capability.domain_code], opacity: Math.max(.25, capability.recent_activity / 100) } as CSSProperties} />)}</svg><div className="cluster-map-legend"><DomainLegend compact /><div className="recency-key"><span>低活跃</span><i style={{ '--domain-color': domainColors[selectedCapability?.domain_code ?? 'T7'] } as CSSProperties} /><span>近期高频</span></div></div></> : <div className="empty-state"><Network size={24} /><strong>正在读取聚类能力</strong><span>仅聚合通过语境校验的技术证据。</span></div>}
        </section>
        <aside className="cluster-inspector">{detail && selectedCapability ? <><StatusTag tone="info">{detail.cluster.domain_code} 主领域</StatusTag><h3>{detail.cluster.label}</h3><p>{detail.cluster.description}</p><div className="cluster-facts"><div><Users size={16} /><span>关联 JD</span><strong>{detail.cluster.member_count}</strong></div><div><Building2 size={16} /><span>独立企业</span><strong>{detail.cluster.organization_count}</strong></div><div><GitBranch size={16} /><span>能力节点</span><strong>{detail.capabilities.length}</strong></div></div><h4>选中能力</h4><div className="selected-skill-summary"><i style={{ background: domainColors[selectedCapability.domain_code] }} /><div><strong>{selectedCapability.technology_name}</strong><span>{selectedCapability.domain_code} · 最近出现 {selectedCapability.last_seen_at?.slice(0, 10) ?? '未知'}</span></div><b>{selectedCapability.supporting_job_count} 条</b></div><dl className="inspector-facts"><div><dt>全窗重要性</dt><dd>{selectedCapability.importance}%</dd></div><div><dt>近期活跃度</dt><dd>{selectedCapability.recent_activity}%</dd></div><div><dt>岗位覆盖率</dt><dd>{Math.round(selectedCapability.coverage_rate * 100)}%</dd></div><div><dt>有效提及次数</dt><dd>{selectedCapability.mention_count}</dd></div></dl><h4>能力频次排序</h4><div className="cluster-skill-bars">{detail.capabilities.map((capability) => <button className={capability.technology_node_id === selectedCapability.technology_node_id ? 'selected' : ''} key={capability.technology_node_id} onClick={() => setSelectedTechnologyId(capability.technology_node_id)}><span><i style={{ background: domainColors[capability.domain_code] }} />{capability.technology_name}</span><div><i style={{ width: `${capability.importance}%`, background: domainColors[capability.domain_code] }} /></div><strong>{capability.supporting_job_count}</strong></button>)}</div></> : <div className="empty-state"><strong>请选择包含有效技术证据的岗位聚类</strong><span>当前聚类可能没有符合所选层级的标准技术能力。</span></div>}</aside>
      </div> : null}
      <p className="chart-source-note">证据口径：最新成功聚类运行中的真实 JD，且技术关系必须通过语境校验。近期活跃度按可靠时间优先、岗位序列兜底计算，不宣称长期趋势。</p>
    </div>
  )
}
