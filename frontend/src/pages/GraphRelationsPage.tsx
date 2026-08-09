import type { CSSProperties } from 'react'
import { Maximize2, Minus, Plus, Table2, ZoomIn } from 'lucide-react'
import { useState } from 'react'
import { DomainLegend } from '../components/DomainLegend'
import { GraphFilters } from '../components/GraphFilters'
import { ScoreBar, StatusTag } from '../components/ui'
import { domainColors, relationEdges, relationNodeMap, relationNodes } from '../data/graphData'

export function GraphRelationsPage({ notify }: { notify: (message: string) => void }) {
  const [selected, setSelected] = useState('integration')
  const [tableView, setTableView] = useState(false)
  const selectedNode = relationNodeMap.get(selected) ?? relationNodes[0]
  const connections = relationEdges.filter(([from, to]) => from === selected || to === selected)
  const connectedNodes = connections.map(([from, to]) => relationNodeMap.get(from === selected ? to : from)!).filter(Boolean)

  return (
    <div className="graph-page graph-subpage">
      <div className="graph-subpage-intro"><div><h2>岗位—能力关联图</h2><p>全局展示全部岗位聚类与技术能力关键词，仅连接各岗位聚类中达到阈值的重要能力。</p></div><StatusTag tone="success">全局快照</StatusTag></div>
      <GraphFilters onApply={(summary) => notify(`关联图筛选已更新：${summary}`)} />
      <div className="graph-workspace graph-workspace--global">
        <div className="graph-legend"><strong>节点类型</strong><span><i className="legend-cluster" />岗位聚类</span><span><i className="legend-skill" />技术能力关键词</span><hr /><strong>T1–T7 领域色</strong><DomainLegend compact /><hr /><p>连线仅表示“岗位簇的重要能力”，选中节点后高亮其一阶邻域。</p><button onClick={() => setTableView((value) => !value)}><Table2 size={15} />{tableView ? '图谱视图' : '表格视图'}</button></div>
        {tableView ? <div className="relation-table-view"><table><thead><tr><th>岗位聚类</th><th>关系</th><th>重要能力</th><th>出现强度</th></tr></thead><tbody>{relationEdges.map(([from, to]) => { const cluster = relationNodeMap.get(from)!; const skill = relationNodeMap.get(to)!; return <tr key={`${from}-${to}`}><td><button onClick={() => setSelected(from)}>{cluster.label}</button></td><td>重要能力</td><td><button onClick={() => setSelected(to)}>{skill.label}</button></td><td>{skill.strength}%</td></tr> })}</tbody></table></div> : <div className="graph-canvas graph-canvas--global" role="group" aria-label="全部岗位聚类与重要能力关键词的全局关联网络"><svg className="edge-layer" viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden="true">{relationEdges.map(([from, to]) => { const a = relationNodeMap.get(from)!; const b = relationNodeMap.get(to)!; const highlighted = selected === from || selected === to; return <line key={`${from}-${to}`} x1={a.x} y1={a.y} x2={b.x} y2={b.y} className={highlighted ? 'selected-edge' : ''} style={{ '--edge-color': domainColors[a.domain] } as CSSProperties} /> })}</svg>{relationNodes.map((node) => <button key={node.id} aria-pressed={selected === node.id} className={`graph-node graph-node--${node.type} ${selected === node.id ? 'selected' : ''}`} style={{ left: `${node.x}%`, top: `${node.y}%`, '--domain-color': domainColors[node.domain], '--node-heat': `${node.recentRate}%` } as CSSProperties} onClick={() => setSelected(node.id)}><small>{node.domain}</small><span>{node.label}</span>{node.type === 'skill' ? <em>{node.strength}%</em> : <em>{connectedNodes.length && selected === node.id ? `${connections.length} 项重要能力` : '岗位聚类'}</em>}</button>)}<div className="graph-zoom"><button aria-label="放大"><Plus size={16} /></button><button aria-label="缩小"><Minus size={16} /></button><button aria-label="适应画布"><Maximize2 size={15} /></button></div></div>}
        <aside className="evidence-inspector"><div className="inspector-title"><div><span>{selectedNode.type === 'cluster' ? '岗位聚类详情' : '能力关键词详情'}</span><h3>{selectedNode.label}</h3></div><ZoomIn size={18} /></div><StatusTag tone={selectedNode.type === 'cluster' ? 'info' : 'success'}>{selectedNode.domain} · {selectedNode.type === 'cluster' ? '岗位聚类' : '重要能力'}</StatusTag><ScoreBar label="出现强度" value={selectedNode.strength} tone="teal" /><ScoreBar label="近期活跃度" value={selectedNode.recentRate} /><dl className="inspector-facts"><div><dt>关联节点</dt><dd>{connectedNodes.length} 个</dd></div><div><dt>最近更新</dt><dd>2026 Q2</dd></div><div><dt>领域归属</dt><dd>{selectedNode.domain}</dd></div><div><dt>关系规则</dt><dd>Top-N + 阈值</dd></div></dl><h4>{selectedNode.type === 'cluster' ? '重要能力' : '关联岗位聚类'}</h4><div className="connected-node-list">{connectedNodes.map((node) => <button key={node.id} onClick={() => setSelected(node.id)}><i style={{ background: domainColors[node.domain] }} /><span>{node.label}</span><strong>{node.strength}%</strong></button>)}</div><h4>来源证据</h4><div className="source-evidence"><button><strong>正式 JD 聚合证据</strong><span>基于去重 JD 中的能力出现频次、必需性和近期窗口计算。</span><em>证据置信度 0.92</em></button></div></aside>
      </div>
    </div>
  )
}
