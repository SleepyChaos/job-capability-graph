import { Network, Table2 } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import {
  graphApi,
  type RelationGraphResponse,
  type RelationNode,
} from '../api/graphs'
import { DomainLegend } from '../components/DomainLegend'
import { ForceRelationGraph } from '../components/ForceRelationGraph'
import { RelationGraphFilters, type RelationGraphFilterState } from '../components/GraphFilters'
import { StatusTag } from '../components/ui'
import { domainColors } from '../data/graphData'

export function GraphRelationsPage({ notify }: { notify: (message: string) => void }) {
  const [filters, setFilters] = useState<RelationGraphFilterState>({ clusterDomain: '', capabilityDomain: '', capabilityLevel: 'L2' })
  const [data, setData] = useState<RelationGraphResponse | null>(null)
  const [selected, setSelected] = useState<string | null>(null)
  const [tableView, setTableView] = useState(false)
  const [error, setError] = useState<string | null>(null)
  useEffect(() => {
    const controller = new AbortController()
    setError(null)
    graphApi.relations({
      clusterDomainCode: filters.clusterDomain || null,
      capabilityDomainCode: filters.capabilityDomain || null,
      capabilityLevelCode: filters.capabilityLevel,
      clusterLimit: 30,
      capabilitiesPerCluster: 12,
    }, controller.signal)
      .then((response) => {
        setData(response)
        setSelected((current) => {
          const ids = new Set([...response.role_nodes, ...response.capability_nodes].map((node) => node.id))
          return current && ids.has(current) ? current : response.role_nodes[0]?.id ?? response.capability_nodes[0]?.id ?? null
        })
      })
      .catch((reason: Error) => {
        if (reason.name !== 'AbortError') setError(reason.message)
      })
    return () => controller.abort()
  }, [filters.clusterDomain, filters.capabilityDomain, filters.capabilityLevel])

  const nodes = useMemo(() => data ? [...data.role_nodes, ...data.capability_nodes] : [], [data])
  const nodeMap = useMemo(() => new Map(nodes.map((node) => [node.id, node])), [nodes])
  const selectedNode = selected ? nodeMap.get(selected) : undefined
  const connections = useMemo(
    () => data?.edges.filter((edge) => edge.source === selected || edge.target === selected) ?? [],
    [data, selected],
  )
  const connectedNodes = connections
    .map((edge) => nodeMap.get(edge.source === selected ? edge.target : edge.source))
    .filter((node): node is RelationNode => Boolean(node))
  const hasProjection = Boolean(data && data.data_version !== 'uninitialized')

  return (
    <div className="graph-page graph-subpage">
      <div className="graph-subpage-intro"><div><h2>岗位—能力关联图</h2><p>展示当前岗位聚类及其高频标准技术能力；仅使用通过语境校验的真实 JD 证据。</p></div><StatusTag tone={hasProjection ? 'success' : 'info'}>{data ? (hasProjection ? `数据版本 ${data.data_version.slice(0, 8)}` : '暂无图谱快照') : '加载中'}</StatusTag></div>
      <RelationGraphFilters onChange={setFilters} onApply={(summary) => notify(`关联图筛选已更新：${summary}`)} />
      {error ? <div className="empty-state"><Network size={24} /><strong>图谱加载失败</strong><span>{error}</span></div> : null}
      {!error && !data ? <div className="empty-state"><Network size={24} /><strong>正在生成关系投影</strong><span>从最新岗位聚类和有效技术证据读取数据。</span></div> : null}
      {data && !hasProjection ? <div className="empty-state"><Network size={24} /><strong>暂无关联图快照</strong><span>当前数据库尚未生成成功的岗位聚类运行；完成 JD 解析和聚类后，这里会显示岗位与能力关系。</span></div> : null}
      {data && hasProjection ? <div className="graph-workspace graph-workspace--global">
        <div className="graph-legend"><strong>节点类型</strong><span><i className="legend-cluster" />岗位聚类</span><span><i className="legend-skill" />标准技术能力</span><hr /><strong>T1–T7 领域色</strong><DomainLegend compact /><hr /><p>最多展示 30 个岗位聚类及每簇 12 项重要能力；画布支持缩放、拖拽和力导向布局，完整证据可切换表格读取。</p><button onClick={() => setTableView((value) => !value)}><Table2 size={15} />{tableView ? '图谱视图' : '表格视图'}</button></div>
        {tableView ? <div className="relation-table-view"><table><thead><tr><th>岗位聚类</th><th>重要能力</th><th>覆盖率</th><th>支持 JD</th></tr></thead><tbody>{data.edges.map((edge) => <tr key={edge.id}><td><button onClick={() => setSelected(edge.source)}>{nodeMap.get(edge.source)?.label}</button></td><td><button onClick={() => setSelected(edge.target)}>{nodeMap.get(edge.target)?.label}</button></td><td>{Math.round(edge.coverage_rate * 100)}%</td><td>{edge.supporting_job_count}</td></tr>)}</tbody></table></div> : <div className="graph-canvas graph-canvas--global" role="group" aria-label="岗位聚类与标准技术能力的全局关联网络"><ForceRelationGraph data={data} selected={selected} onSelect={(nodeId) => setSelected(nodeId || null)} /></div>}
        <aside className="evidence-inspector">{selectedNode ? <><div className="inspector-title"><div><span>{selectedNode.type === 'job_cluster' ? '岗位聚类详情' : '标准技术能力'}</span><h3>{selectedNode.label}</h3></div></div><StatusTag tone={selectedNode.type === 'job_cluster' ? 'info' : 'success'}>{selectedNode.domain_code}</StatusTag><div className="evidence-count-stat"><span>证据数量</span><strong>{selectedNode.evidence_count}</strong><small>条</small></div><dl className="inspector-facts"><div><dt>关联节点</dt><dd>{connectedNodes.length} 个</dd></div><div><dt>目标日期</dt><dd>{data.target_date}</dd></div><div><dt>证据规则</dt><dd>已通过语境校验</dd></div><div><dt>图谱层级</dt><dd>{selectedNode.type === 'technology' ? filters.capabilityLevel : '岗位聚类'}</dd></div></dl><h4>{selectedNode.type === 'job_cluster' ? '重要能力' : '关联岗位聚类'}</h4><div className="connected-node-list">{connectedNodes.map((node) => <button key={node.id} onClick={() => setSelected(node.id)}><i style={{ background: domainColors[node.domain_code] }} /><span>{node.label}</span><strong>{node.evidence_count}</strong></button>)}</div></> : <div className="empty-state"><strong>当前筛选没有关系</strong><span>可分别调整岗位聚类和能力筛选。</span></div>}</aside>
      </div> : null}
    </div>
  )
}
