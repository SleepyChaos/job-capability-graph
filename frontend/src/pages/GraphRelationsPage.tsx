import {
  BriefcaseBusiness, Building2, ChevronRight, Cpu, Database, GitBranch,
  Layers3, Network, Search, ShieldCheck,
} from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import {
  graphApi, type JobArchitectureOverview, type JobArchitectureRole,
  type JobArchitectureRoleDetail,
} from '../api/graphs'
import { StatusTag } from '../components/ui'

type GraphView = 'job' | 'technology' | 'enterprise'

const portraitDimensions = [
  { key: 'responsibilities', label: '职责' },
  { key: 'skills', label: '技能' },
  { key: 'capabilities', label: '通用能力' },
  { key: 'scenarios', label: '场景' },
  { key: 'conditions', label: '条件' },
] as const

const graphViews: Array<{ id: GraphView; label: string; description: string; icon: typeof Network }> = [
  { id: 'job', label: '岗位架构', description: '方向→类别→岗位簇→标准岗位→JD', icon: GitBranch },
  { id: 'technology', label: '技术—岗位', description: 'L1→L2→L3→标准岗位', icon: Cpu },
  { id: 'enterprise', label: '企业—岗位', description: '企业→标准岗位→具体JD', icon: Building2 },
]

const contains = (value: string | null | undefined, query: string) =>
  Boolean(value?.toLocaleLowerCase().includes(query.toLocaleLowerCase()))

export function GraphRelationsPage({ notify }: { notify: (message: string) => void }) {
  const [data, setData] = useState<JobArchitectureOverview | null>(null)
  const [detail, setDetail] = useState<JobArchitectureRoleDetail | null>(null)
  const [view, setView] = useState<GraphView>('job')
  const [query, setQuery] = useState('')
  const [direction, setDirection] = useState('')
  const [category, setCategory] = useState('')
  const [cluster, setCluster] = useState('')
  const [technologyCode, setTechnologyCode] = useState('')
  const [companyName, setCompanyName] = useState('')
  const [roleCode, setRoleCode] = useState('')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    const controller = new AbortController()
    setLoading(true); setError('')
    graphApi.jobArchitecture(controller.signal).then((response) => {
      setData(response)
      const initialDirection = Object.keys(response.hierarchy)[0] || ''
      const initialCategory = Object.keys(response.hierarchy[initialDirection] || {})[0] || ''
      const initialCluster = Object.keys(response.hierarchy[initialDirection]?.[initialCategory] || {})[0] || ''
      const initialRole = response.hierarchy[initialDirection]?.[initialCategory]?.[initialCluster]?.[0]
        || response.roles[0]?.role_code || ''
      setDirection(initialDirection); setCategory(initialCategory); setCluster(initialCluster)
      setTechnologyCode(response.technologies[0]?.code || '')
      setCompanyName(response.companies[0]?.name || '')
      setRoleCode(initialRole)
    }).catch((reason: Error) => setError(reason.message)).finally(() => setLoading(false))
    return () => controller.abort()
  }, [])

  useEffect(() => {
    if (!roleCode) { setDetail(null); return }
    const controller = new AbortController()
    graphApi.jobArchitectureRole(roleCode, controller.signal).then(setDetail)
      .catch((reason: Error) => { if (reason.name !== 'AbortError') notify(`岗位详情加载失败：${reason.message}`) })
    return () => controller.abort()
  }, [notify, roleCode])

  const roleMap = useMemo(
    () => new Map(data?.roles.map((role) => [role.role_code, role]) || []),
    [data],
  )
  const categories = data?.hierarchy[direction] || {}
  const clusters = categories[category] || {}
  const selectedTechnology = data?.technologies.find((item) => item.code === technologyCode)
  const selectedCompany = data?.companies.find((item) => item.name === companyName)
  const relatedRoleCodes = useMemo(() => {
    if (!data) return []
    if (view === 'technology') return selectedTechnology?.role_codes || []
    if (view === 'enterprise') return selectedCompany?.role_codes || []
    return clusters[cluster] || []
  }, [cluster, clusters, data, selectedCompany, selectedTechnology, view])
  const visibleRoles = useMemo(() => relatedRoleCodes
    .map((code) => roleMap.get(code))
    .filter((role): role is JobArchitectureRole => Boolean(role))
    .filter((role) => !query || [role.name, role.direction, role.category, role.cluster_name]
      .some((value) => contains(value, query)))
    .sort((a, b) => b.job_count - a.job_count), [query, relatedRoleCodes, roleMap])

  const chooseDirection = (next: string) => {
    const nextCategory = Object.keys(data?.hierarchy[next] || {})[0] || ''
    const nextCluster = Object.keys(data?.hierarchy[next]?.[nextCategory] || {})[0] || ''
    const nextRole = data?.hierarchy[next]?.[nextCategory]?.[nextCluster]?.[0] || ''
    setDirection(next); setCategory(nextCategory); setCluster(nextCluster); setRoleCode(nextRole)
  }
  const chooseCategory = (next: string) => {
    const nextCluster = Object.keys(categories[next] || {})[0] || ''
    setCategory(next); setCluster(nextCluster); setRoleCode(categories[next]?.[nextCluster]?.[0] || '')
  }
  const chooseCluster = (next: string) => {
    setCluster(next); setRoleCode(clusters[next]?.[0] || '')
  }
  const chooseTechnology = (code: string) => {
    const technology = data?.technologies.find((item) => item.code === code)
    setTechnologyCode(code); setRoleCode(technology?.role_codes[0] || '')
  }
  const chooseCompany = (name: string) => {
    const company = data?.companies.find((item) => item.name === name)
    setCompanyName(name); setRoleCode(company?.role_codes[0] || '')
  }

  if (loading) return <div className="empty-state new-graph-loading"><Network size={25} /><strong>正在读取新版岗位图谱</strong><span>加载岗位架构、技术关联与企业岗位投影。</span></div>
  if (error || !data) return <div className="empty-state new-graph-loading"><Network size={25} /><strong>新版岗位图谱加载失败</strong><span>{error || '没有可展示的数据'}</span></div>

  return <div className="graph-page graph-subpage new-job-graph-page">
    <div className="graph-subpage-intro"><div><h2>新版岗位图谱</h2><p>三个视角共享同一批岗位事实，并在标准岗位处交汇；点击任一节点即可查看五维画像和JD证据。</p></div><StatusTag tone="success">v4 · {data.metadata.job_count.toLocaleString()} 条岗位</StatusTag></div>
    <section className="new-graph-metrics">
      <div><span>职业方向</span><strong>{data.metadata.direction_count}</strong></div><div><span>职业类别</span><strong>{data.metadata.category_count}</strong></div><div><span>岗位簇</span><strong>{data.metadata.cluster_count}</strong></div><div><span>标准岗位</span><strong>{data.metadata.standard_role_count}</strong></div><div><span>技术节点</span><strong>{data.metadata.technology_count}</strong></div><div><span>企业实体</span><strong>{data.metadata.company_count}</strong></div>
    </section>
    <section className="new-graph-toolbar">
      <div>{graphViews.map(({ id, label, description, icon: Icon }) => <button className={view === id ? 'active' : ''} key={id} onClick={() => setView(id)}><Icon size={17} /><span><strong>{label}</strong><small>{description}</small></span></button>)}</div>
      <label><Search size={15} /><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="搜索标准岗位或关联节点" /></label>
    </section>
    <section className="new-graph-workspace">
      <aside className="new-graph-browser">
        {view === 'job' ? <div className="hierarchy-browser">
          <section><header><span>01</span><strong>职业方向</strong></header>{Object.keys(data.hierarchy).map((item) => <button className={direction === item ? 'active' : ''} key={item} onClick={() => chooseDirection(item)}><span>{item}</span><ChevronRight size={13} /></button>)}</section>
          <section><header><span>02</span><strong>职业类别</strong></header>{Object.keys(categories).map((item) => <button className={category === item ? 'active' : ''} key={item} onClick={() => chooseCategory(item)}><span>{item}</span><ChevronRight size={13} /></button>)}</section>
          <section><header><span>03</span><strong>岗位簇</strong></header>{Object.keys(clusters).map((item) => { const [code, name] = item.split('|'); return <button className={cluster === item ? 'active' : ''} key={item} onClick={() => chooseCluster(item)}><span><small>{code}</small>{name}</span><ChevronRight size={13} /></button> })}</section>
        </div> : null}
        {view === 'technology' ? <div className="entity-node-list"><header><Cpu size={16} /><div><strong>技术分层节点</strong><span>按岗位覆盖数量排序</span></div></header>{data.technologies.filter((item) => !query || contains(item.name, query) || contains(item.code, query)).slice(0, 120).map((item) => <button className={technologyCode === item.code ? 'active' : ''} key={item.code} onClick={() => chooseTechnology(item.code)}><div><strong>{item.name}</strong><span>{item.path.map((node) => node.code).join(' → ')}</span></div><b>{item.job_count}</b></button>)}</div> : null}
        {view === 'enterprise' ? <div className="entity-node-list"><header><Building2 size={16} /><div><strong>企业实体</strong><span>按具体JD数量排序</span></div></header>{data.companies.filter((item) => !query || contains(item.name, query)).slice(0, 160).map((item) => <button className={companyName === item.name ? 'active' : ''} key={item.name} onClick={() => chooseCompany(item.name)}><div><strong>{item.name}</strong><span>{item.role_codes.length} 个标准岗位</span></div><b>{item.job_count}</b></button>)}</div> : null}
      </aside>
      <main className="new-graph-role-stage">
        <header><div><Layers3 size={17} /><span><strong>关联标准岗位</strong><small>{view === 'job' ? cluster.split('|')[1] : view === 'technology' ? selectedTechnology?.name : selectedCompany?.name}</small></span></div><StatusTag tone="info">{visibleRoles.length} 个节点</StatusTag></header>
        <div className="role-node-cloud">{visibleRoles.length ? visibleRoles.map((role) => <button className={roleCode === role.role_code ? 'active' : ''} key={role.role_code} onClick={() => setRoleCode(role.role_code)}><BriefcaseBusiness size={16} /><div><strong>{role.name}</strong><span>{role.cluster_code} · {role.cluster_name}</span></div><b>{role.job_count}<small> JD</small></b></button>) : <div className="empty-state"><strong>没有匹配的标准岗位</strong><span>请清空搜索词或选择其他节点。</span></div>}</div>
        {view === 'technology' && selectedTechnology ? <footer className="graph-evidence-policy"><ShieldCheck size={14} /><span>该技术节点覆盖 {selectedTechnology.job_count} 条岗位，其中 {selectedTechnology.exact_evidence_count} 条为JD精确证据；其余仅作候选分类。</span></footer> : null}
      </main>
      <aside className="new-graph-inspector">
        {detail ? <>
          <header><span>标准岗位详情</span><h3>{detail.role.name}</h3><p>{detail.role.direction} → {detail.role.category} → {detail.role.cluster_code} {detail.role.cluster_name}</p></header>
          <div className="inspector-summary"><div><span>岗位事实</span><strong>{detail.jobs.length}</strong></div><div><span>关联企业</span><strong>{detail.companies.length}</strong></div><div><span>技术节点</span><strong>{detail.technologies.length}</strong></div></div>
          <section><h4>五维岗位画像</h4><div className="inspector-portrait">{portraitDimensions.map((dimension) => { const items = detail.role.portrait?.[dimension.key] || []; return <article key={dimension.key}><strong>{dimension.label}</strong>{items.length ? <ul>{items.slice(0, 4).map((item) => <li key={item}>{item}</li>)}</ul> : <span>暂无可靠画像项</span>}</article> })}</div></section>
          <section><h4>高频技术关联</h4><div className="inspector-technology-list">{detail.technologies.slice(0, 8).map((item) => <button key={item.code} onClick={() => { setView('technology'); chooseTechnology(item.code) }}><Cpu size={13} /><span><strong>{item.name}</strong><small>{item.path.map((node) => node.code).join(' → ')}</small></span><b>{item.job_count}</b></button>)}</div></section>
          <section><h4>具体JD证据</h4><div className="inspector-job-list">{detail.jobs.slice(0, 12).map((job) => <article key={job.occ_id}><Database size={13} /><div><strong>{job.title || '岗位名称未注明'}</strong><span>{job.company || '企业信息未公开'} · {job.occ_id}</span></div></article>)}</div></section>
        </> : <div className="empty-state"><BriefcaseBusiness size={22} /><strong>选择标准岗位</strong><span>右侧将显示五维画像、技术路径和JD证据。</span></div>}
      </aside>
    </section>
  </div>
}
