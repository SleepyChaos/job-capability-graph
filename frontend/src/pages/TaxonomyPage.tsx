import { GitMerge, RefreshCw, Search, ShieldAlert, Waypoints } from 'lucide-react'
import { useCallback, useEffect, useState } from 'react'
import { taxonomyApi, type TechnologyDomain, type TechnologyNode } from '../api/taxonomy'
import { MetricStrip, Panel, StatusTag } from '../components/ui'

const LEVELS = ['L1', 'L2', 'L3', 'L4'] as const
const PAGE_SIZE = 50

export function TaxonomyPage({ notify }: { notify: (message: string) => void }) {
  const [level, setLevel] = useState<string>('L3')
  const [domainCode, setDomainCode] = useState<string | null>(null)
  const [query, setQuery] = useState('')
  const [domains, setDomains] = useState<TechnologyDomain[]>([])
  const [nodes, setNodes] = useState<TechnologyNode[]>([])
  const [total, setTotal] = useState(0)
  const [offset, setOffset] = useState(0)
  const [levelCounts, setLevelCounts] = useState<Record<string, number>>({})
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    const controller = new AbortController()
    Promise.all([
      taxonomyApi.domains(null, controller.signal),
      ...LEVELS.map((item) => taxonomyApi.nodes({ level: item, limit: 1 }, controller.signal)),
    ])
      .then(([domainRows, ...countRows]) => {
        setDomains(domainRows)
        setLevelCounts(Object.fromEntries(LEVELS.map((item, index) => [item, countRows[index].total])))
      })
      .catch((reason: Error) => { if (reason.name !== 'AbortError') setError(reason.message) })
    return () => controller.abort()
  }, [])

  const loadNodes = useCallback((signal?: AbortSignal) => {
    setLoading(true)
    taxonomyApi.nodes({ level, domainCode, search: query || undefined, limit: PAGE_SIZE, offset }, signal)
      .then((page) => { setNodes(page.items); setTotal(page.total) })
      .catch((reason: Error) => { if (reason.name !== 'AbortError') setError(reason.message) })
      .finally(() => setLoading(false))
  }, [level, domainCode, query, offset])

  useEffect(() => {
    const controller = new AbortController()
    const timer = window.setTimeout(() => loadNodes(controller.signal), query ? 300 : 0)
    return () => { window.clearTimeout(timer); controller.abort() }
  }, [loadNodes, query])

  const selectLevel = (next: string) => { setLevel(next); setOffset(0) }
  const selectDomain = (code: string | null) => { setDomainCode(code); setOffset(0) }
  const selectedDomain = domains.find((domain) => domain.code === domainCode)

  return (
    <div className="page-stack">
      <div className="page-intro">
        <div><h2>技术词标准管理</h2><p>统一维护技术词标准、L1–L4 知识层级与 T1–T7 技术领域；一个标准技术点可跨多个领域。</p></div>
        <button className="primary-button" onClick={() => notify('候选词登记接口待接入（阶段 E 治理流程提供），当前仅支持查询已发布主数据')}><GitMerge size={16} />创建候选词</button>
      </div>
      <MetricStrip items={LEVELS.map((item) => ({ label: item, value: (levelCounts[item] ?? 0).toLocaleString(), delta: item === 'L3' ? '标准技术点' : item === 'L4' ? '技术表面词' : '分类层级' }))} />
      {error ? <div className="empty-state"><ShieldAlert size={25} /><strong>加载失败</strong><span>{error}</span></div> : null}
      <div className="taxonomy-layout">
        <Panel title="T1–T7 技术领域" subtitle="点击领域筛选右侧节点" className="taxonomy-tree">
          <div className="segment-control">{LEVELS.map((item) => <button className={level === item ? 'active' : ''} onClick={() => selectLevel(item)} key={item}>{item}</button>)}</div>
          <div className="tree-list">
            <button className={domainCode === null ? 'selected' : ''} onClick={() => selectDomain(null)}><Waypoints size={16} /><span>全部领域</span><em>{domains.reduce((sum, domain) => sum + domain.node_count, 0)}</em></button>
            {domains.map((domain) => (
              <button key={domain.code} className={domainCode === domain.code ? 'selected' : ''} onClick={() => selectDomain(domain.code)}>
                <i style={{ background: domain.color ?? '#64748b', width: 10, height: 10, borderRadius: 3, display: 'inline-block' }} />
                <span>{domain.code} {domain.name}</span><em>{domain.node_count}</em>
              </button>
            ))}
          </div>
        </Panel>
        <Panel
          title={`${level} 技术节点${selectedDomain ? ` · ${selectedDomain.code} ${selectedDomain.name}` : ''}`}
          subtitle={`共 ${total.toLocaleString()} 条，来自 /taxonomy/nodes 接口`}
          action={<label className="inline-search"><Search size={15} /><input placeholder="搜索名称或编码" value={query} onChange={(event) => { setQuery(event.target.value); setOffset(0) }} /></label>}
        >
          <div className="table-wrap">
            <table className="data-table">
              <thead><tr><th>编码 / 名称</th><th>上级编码</th><th>表面词/别名</th><th>T 领域</th><th>语义角色</th><th>来源行</th></tr></thead>
              <tbody>{nodes.map((node) => (
                <tr key={node.code}>
                  <td><strong>{node.name}</strong><small>{node.code}</small></td>
                  <td>{node.parent_code ?? '—'}</td>
                  <td>{node.alias_count}</td>
                  <td><StatusTag tone="info">{node.domain_code} {node.domain_name}</StatusTag></td>
                  <td>{node.semantic_role ?? '—'}</td>
                  <td><small>{node.source_sheet} #{node.source_row_number}</small></td>
                </tr>
              ))}</tbody>
            </table>
            {loading ? <div className="empty-state"><RefreshCw className="spin" size={22} /><strong>正在加载…</strong></div> : nodes.length === 0 ? <div className="empty-state"><Waypoints size={25} /><strong>没有匹配的技术节点</strong><span>尝试切换层级、领域或修改搜索条件。</span></div> : null}
          </div>
          {total > PAGE_SIZE ? (
            <div className="pagination-row">
              <button className="secondary-button" disabled={offset === 0} onClick={() => setOffset((value) => Math.max(0, value - PAGE_SIZE))}>上一页</button>
              <span>{offset + 1}–{Math.min(offset + PAGE_SIZE, total)} / {total.toLocaleString()}</span>
              <button className="secondary-button" disabled={offset + PAGE_SIZE >= total} onClick={() => setOffset((value) => value + PAGE_SIZE)}>下一页</button>
            </div>
          ) : null}
        </Panel>
      </div>
      <Panel title="T1–T7 领域映射" subtitle="领域归属与 L 层级相互独立；跨领域项可设一个主领域和多个次领域">
        <div className="domain-rail">{domains.map((domain) => (
          <button key={domain.code} onClick={() => selectDomain(domain.code)}>
            <i style={{ background: domain.color ?? '#64748b' }} /><strong>{domain.code}</strong><span>{domain.name}</span><em>{domain.node_count} 个节点</em>
          </button>
        ))}</div>
      </Panel>
    </div>
  )
}
