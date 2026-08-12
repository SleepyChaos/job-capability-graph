import { Network, Table2 } from 'lucide-react'
import { useCallback, useEffect, useMemo, useState } from 'react'
import { graphApi, type RelationGraphExpansion, type RelationGraphResponse, type RelationNode } from '../api/graphs'
import { DomainLegend } from '../components/DomainLegend'
import { RelationGraphFilters, type RelationGraphFilterState } from '../components/GraphFilters'
import { RelationForceGraph } from '../components/RelationForceGraph'
import { StatusTag } from '../components/ui'
import { domainColors } from '../data/graphData'

const densityOptions = [80, 240, 400, 720, 1000]
const supportOptions = [1, 2, 3, 5]
const MAX_RENDERED_NODES = 1000
const FULL_CLUSTER_LIMIT = 1000

function mergeRelationExpansion(base: RelationGraphResponse, expansion: RelationGraphExpansion): RelationGraphResponse {
  const mergeNodes = (current: RelationNode[], incoming: RelationNode[]) => {
    const nodes = new Map(current.map((node) => [node.id, node]))
    incoming.forEach((node) => nodes.set(node.id, node))
    return [...nodes.values()]
  }
  const edges = new Map(base.edges.map((edge) => [edge.id, edge]))
  expansion.edges.forEach((edge) => edges.set(edge.id, edge))
  return {
    ...base,
    generated_at: expansion.generated_at,
    role_nodes: mergeNodes(base.role_nodes, expansion.role_nodes),
    capability_nodes: mergeNodes(base.capability_nodes, expansion.capability_nodes),
    edges: [...edges.values()],
  }
}

export function GraphRelationsPage({ notify }: { notify: (message: string) => void }) {
  const [filters, setFilters] = useState<RelationGraphFilterState>({ clusterDomain: '', capabilityDomain: '', capabilityLevel: 'L2' })
  const [nodeBudget, setNodeBudget] = useState(720)
  const [minSupportingJobCount, setMinSupportingJobCount] = useState(1)
  const [focusNodeId, setFocusNodeId] = useState<string | null>(null)
  const [data, setData] = useState<RelationGraphResponse | null>(null)
  const [selected, setSelected] = useState<string | null>(null)
  const [expandedNodeIds, setExpandedNodeIds] = useState<Set<string>>(() => new Set())
  const [expandingNodeId, setExpandingNodeId] = useState<string | null>(null)
  const [tableView, setTableView] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const selectNode = useCallback((id: string) => setSelected(id), [])
  const changeFilters = useCallback((next: RelationGraphFilterState) => {
    setFocusNodeId(null)
    setFilters(next)
  }, [])

  useEffect(() => {
    const controller = new AbortController()
    setError(null)
    graphApi.relations({
      clusterDomainCode: filters.clusterDomain || null,
      capabilityDomainCode: filters.capabilityDomain || null,
      capabilityLevelCode: filters.capabilityLevel,
      clusterLimit: FULL_CLUSTER_LIMIT,
      nodeBudget,
      minSupportingJobCount,
      mode: focusNodeId ? 'focus' : 'overview',
      focusNodeId,
    }, controller.signal)
      .then((response) => {
        setData(response)
        setExpandedNodeIds(new Set())
        setSelected((current) => {
          const ids = new Set([...response.role_nodes, ...response.capability_nodes].map((node) => node.id))
          return current && ids.has(current) ? current : response.role_nodes[0]?.id ?? response.capability_nodes[0]?.id ?? null
        })
      })
      .catch((reason: Error) => {
        if (reason.name !== 'AbortError') setError(reason.message)
      })
    return () => controller.abort()
  }, [filters.clusterDomain, filters.capabilityDomain, filters.capabilityLevel, focusNodeId, minSupportingJobCount, nodeBudget])

  const nodeMap = useMemo(
    () => new Map<string, RelationNode>(data ? [...data.role_nodes, ...data.capability_nodes].map((node) => [node.id, node]) : []),
    [data],
  )
  const selectedNode = selected ? nodeMap.get(selected) : undefined
  const connections = useMemo(
    () => data?.edges.filter((edge) => edge.source === selected || edge.target === selected) ?? [],
    [data, selected],
  )
  const connectedNodes = useMemo(
    () => connections
      .map((edge) => nodeMap.get(edge.source === selected ? edge.target : edge.source))
      .filter((node): node is RelationNode => Boolean(node)),
    [connections, nodeMap, selected],
  )
  const hasProjection = Boolean(data && data.data_version !== 'uninitialized')
  const totalNodeCount = data ? data.role_nodes.length + data.capability_nodes.length : 0
  const expandNode = useCallback((nodeId: string) => {
    if (!data || expandedNodeIds.has(nodeId) || expandingNodeId) return
    const remainingBudget = MAX_RENDERED_NODES - totalNodeCount
    if (remainingBudget < 2) {
      notify(`已达到 ${MAX_RENDERED_NODES} 个节点的交互预算；请先收窄筛选条件。`)
      return
    }
    const controller = new AbortController()
    setExpandingNodeId(nodeId)
    graphApi.relationNeighbors(nodeId, {
      clusterDomainCode: filters.clusterDomain || null,
      capabilityDomainCode: filters.capabilityDomain || null,
      capabilityLevelCode: filters.capabilityLevel,
      minSupportingJobCount,
    }, Math.min(80, remainingBudget), controller.signal)
      .then((expansion) => {
        setData((current) => current ? mergeRelationExpansion(current, expansion) : current)
        setExpandedNodeIds((current) => new Set(current).add(nodeId))
        notify(`已展开 ${expansion.expansion.returned_neighbor_count} 个关联节点${expansion.expansion.truncated ? '（达到本次上限）' : ''}。`)
      })
      .catch((reason: Error) => {
        if (reason.name !== 'AbortError') notify(`展开邻居失败：${reason.message}`)
      })
      .finally(() => setExpandingNodeId(null))
  }, [data, expandedNodeIds, expandingNodeId, filters.capabilityDomain, filters.capabilityLevel, filters.clusterDomain, minSupportingJobCount, notify, totalNodeCount])

  return (
    <div className="graph-page graph-subpage">
      <div className="graph-subpage-intro"><div><h2>岗位—能力关联图</h2><p>展示当前岗位聚类及其高频标准技术能力；仅使用通过语境校验的真实 JD 证据。</p></div><StatusTag tone={hasProjection ? 'success' : 'info'}>{data ? (hasProjection ? `数据版本 ${data.data_version.slice(0, 8)}` : '暂无图谱快照') : '加载中'}</StatusTag></div>
      <RelationGraphFilters onChange={changeFilters} onApply={(summary) => notify(`关联图筛选已更新：${summary}`)} />
      {hasProjection ? <div className="relation-density-toolbar" aria-label="图谱展示密度">
        <label>节点预算<select value={nodeBudget} onChange={(event) => setNodeBudget(Number(event.target.value))}>{densityOptions.map((value) => <option key={value} value={value}>{value} 个节点</option>)}</select></label>
        <label>最小支持 JD<select value={minSupportingJobCount} onChange={(event) => setMinSupportingJobCount(Number(event.target.value))}>{supportOptions.map((value) => <option key={value} value={value}>{value} 条</option>)}</select></label>
        <span>当前 {totalNodeCount} 个节点 · {data?.edges.length ?? 0} 条关系{expandedNodeIds.size ? ` · 已展开 ${expandedNodeIds.size} 处邻居` : ''}</span>
        {focusNodeId ? <button className="secondary-button relation-focus-exit" onClick={() => setFocusNodeId(null)}>返回全局图</button> : null}
      </div> : null}
      {error ? <div className="empty-state"><Network size={24} /><strong>图谱加载失败</strong><span>{error}</span></div> : null}
      {!error && !data ? <div className="empty-state"><Network size={24} /><strong>正在生成关系投影</strong><span>从最新岗位聚类和有效技术证据读取数据。</span></div> : null}
      {data && !hasProjection ? <div className="empty-state"><Network size={24} /><strong>暂无关联图快照</strong><span>当前数据库尚未生成成功的岗位聚类运行；完成 JD 解析和聚类后，这里会显示岗位与能力关系。</span></div> : null}
      {data && hasProjection ? <div className="graph-workspace graph-workspace--global">
        <div className="graph-legend"><strong>节点类型</strong><span><i className="legend-cluster" />岗位聚类</span><span><i className="legend-skill" />标准技术能力</span><hr /><strong>T1–T7 领域色</strong><DomainLegend compact /><hr /><p>{focusNodeId ? '当前为单岗位聚类局部图；返回全局图可继续浏览其他聚类。' : '岗位聚类按 T1–T7 技术域锚点形成七个语义簇，能力节点位于关联岗位簇的加权中心；远景保留岗位名称，中近景尽量展示全部节点名称。'}</p><button onClick={() => setTableView((value) => !value)}><Table2 size={15} />{tableView ? '图谱视图' : '表格视图'}</button></div>
        {tableView ? <div className="relation-table-view"><table><thead><tr><th>岗位聚类</th><th>重要能力</th><th>覆盖率</th><th>支持 JD</th></tr></thead><tbody>{data.edges.map((edge) => <tr key={edge.id}><td><button onClick={() => selectNode(edge.source)}>{nodeMap.get(edge.source)?.label}</button></td><td><button onClick={() => selectNode(edge.target)}>{nodeMap.get(edge.target)?.label}</button></td><td>{Math.round(edge.coverage_rate * 100)}%</td><td>{edge.supporting_job_count}</td></tr>)}</tbody></table></div> : <RelationForceGraph graph={data} selectedId={selected} onSelect={selectNode} onExpand={expandNode} />}
        <aside className="evidence-inspector">{selectedNode ? <><div className="inspector-title"><div><span>{selectedNode.type === 'job_cluster' ? '岗位聚类详情' : '标准技术能力'}</span><h3>{selectedNode.label}</h3></div></div><StatusTag tone={selectedNode.type === 'job_cluster' ? 'info' : 'success'}>{selectedNode.domain_code}</StatusTag><div className="evidence-count-stat"><span>证据数量</span><strong>{selectedNode.evidence_count}</strong><small>条</small></div><dl className="inspector-facts"><div><dt>关联节点</dt><dd>{connectedNodes.length} 个</dd></div><div><dt>目标日期</dt><dd>{data.target_date}</dd></div><div><dt>证据规则</dt><dd>已通过语境校验</dd></div><div><dt>图谱层级</dt><dd>{selectedNode.type === 'technology' ? filters.capabilityLevel : '岗位聚类'}</dd></div></dl>{selectedNode.type === 'job_cluster' && !focusNodeId ? <button className="secondary-button relation-focus-button" onClick={() => setFocusNodeId(selectedNode.id)}>聚焦此岗位聚类</button> : null}<button className="secondary-button relation-expand-button" onClick={() => expandNode(selectedNode.id)} disabled={Boolean(expandingNodeId) || expandedNodeIds.has(selectedNode.id)}>{expandingNodeId === selectedNode.id ? '正在展开邻居…' : expandedNodeIds.has(selectedNode.id) ? '邻居已展开' : '展开关联邻居'}</button><h4>{selectedNode.type === 'job_cluster' ? '重要能力' : '关联岗位聚类'}</h4><div className="connected-node-list">{connectedNodes.map((node) => <button key={node.id} onClick={() => selectNode(node.id)}><i style={{ background: domainColors[node.domain_code] }} /><span>{node.label}</span><strong>{node.evidence_count}</strong></button>)}</div></> : <div className="empty-state"><strong>当前筛选没有关系</strong><span>可分别调整岗位聚类和能力筛选。</span></div>}</aside>
      </div> : null}
    </div>
  )
}
