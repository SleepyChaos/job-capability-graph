import { AlertTriangle, ArrowLeft, BarChart3, BrainCircuit, BriefcaseBusiness, Building2, CheckCircle2, ChevronDown, ChevronRight, FileText, GitBranch, Landmark, Layers3, ListChecks, MapPinned, Network, RotateCcw, Search, ShieldCheck, Sparkles, Tags, UserRound, WalletCards, Workflow, Wrench } from 'lucide-react'
import { useEffect, useMemo, useRef, useState } from 'react'
import { loadDiscoveryRolePortraits, loadJobEcosystemGraph, type EnterpriseRecord, type JobCategory, type JobCluster, type JobDirection, type JobEcosystemGraph, type JobPortrait, type JobRecord, type JobTechnologyNode, type RepresentativeJob, type StandardProfilePoint, type StandardRole } from '../api/jobGraph'
import { MetricStrip, Panel, StatusTag } from '../components/ui'
import { IndustryJobGraph } from '../components/IndustryJobGraph'
import { DiscoveryOverlayPanel } from '../components/DiscoveryOverlayPanel'
import { fetchDiscoveryOverlay, type DiscoveryCandidate, type DiscoveryOverlay } from '../api/newRoleDiscovery'
import { classificationColor, discoveryApi } from '../api/discovery'
import type { PageId } from '../types'

/**
 * 把一条画像文本包成画像点。
 *
 * `count` / `coverage` / `evidenceOccIds` 一律留空：推演岗位的画像没有 JD 证据支撑，
 * 给它们填数就是把生成的文字伪装成观测事实。
 */
const toProfilePoint = (name: string): StandardProfilePoint => ({
  name,
  count: 0,
  coverage: 0,
  evidenceOccIds: [],
})

type PositionedNode = {
  id: string
  label: string
  kind: 'root' | 'direction' | 'category' | 'cluster' | 'parent' | 'dimension' | 'enterprise' | 'portrait' | 'capability' | 'evidence' | 'job' | 'standardRole'
  x: number
  y: number
  color: string
  count: number
  unit?: string
  selected?: boolean
}

type PositionedEdge = { source: PositionedNode; target: PositionedNode }

const polar = (cx: number, cy: number, radius: number, angle: number) => ({
  x: cx + Math.cos(angle) * radius,
  y: cy + Math.sin(angle) * radius,
})

function averageAngle(angles: number[]) {
  if (!angles.length) return 0
  const x = angles.reduce((sum, angle) => sum + Math.cos(angle), 0)
  const y = angles.reduce((sum, angle) => sum + Math.sin(angle), 0)
  return Math.atan2(y, x)
}

function splitLabel(label: string, length = 8) {
  if (label.length <= length) return [label]
  const lines = []
  for (let index = 0; index < label.length && lines.length < 3; index += length) lines.push(label.slice(index, index + length))
  if (label.length > length * 3) lines[2] = `${lines[2].slice(0, Math.max(1, length - 1))}…`
  return lines
}

function jobGraphRouteParams() {
  const query = window.location.hash.split('?')[1] ?? ''
  return new URLSearchParams(query)
}

function GraphNode({ node, onClick }: { node: PositionedNode; onClick: () => void }) {
  const lines = splitLabel(node.label, node.kind === 'evidence' || node.kind === 'job' || node.kind === 'standardRole' ? 11 : node.kind === 'enterprise' ? 10 : node.kind === 'cluster' ? 9 : 8)
  const isFilledCircle = node.kind === 'root' || node.kind === 'direction' || node.kind === 'parent'
  const isCircle = isFilledCircle || node.kind === 'capability'
  const width = node.kind === 'evidence' || node.kind === 'job' || node.kind === 'standardRole' ? 154 : node.kind === 'enterprise' ? 142 : node.kind === 'cluster' ? 126 : 112
  const height = lines.length > 1 ? 38 + (lines.length - 1) * 15 : 38
  return <g
    className={`job-ecosystem-node job-ecosystem-node--${node.kind}${node.selected ? ' is-selected' : ''}`}
    role="button"
    tabIndex={0}
    aria-label={`${node.label}，${node.count}${node.unit ?? '个岗位'}`}
    onClick={onClick}
    onKeyDown={(event) => {
      if (event.key === 'Enter' || event.key === ' ') {
        event.preventDefault()
        onClick()
      }
    }}
  >
    {isCircle ? <circle cx={node.x} cy={node.y} r={node.kind === 'root' ? 60 : node.kind === 'direction' ? 50 : node.kind === 'parent' ? 38 : 48} fill={node.kind === 'capability' ? '#fff' : node.color} stroke={node.kind === 'capability' ? node.color : undefined} strokeWidth={node.kind === 'capability' ? (node.selected ? 4 : 3) : undefined} /> : <rect x={node.x - width / 2} y={node.y - height / 2} width={width} height={height} rx="10" fill="#fff" stroke={node.color} strokeWidth={node.selected ? 3 : 1.7} />}
    <text x={node.x} y={node.y - (lines.length - 1) * 8} textAnchor="middle" className={isFilledCircle ? 'job-ecosystem-node-label light' : 'job-ecosystem-node-label'}>
      {lines.map((line, index) => <tspan key={line} x={node.x} dy={index ? 16 : 0}>{line}</tspan>)}
    </text>
    <text x={node.x} y={node.y + (isCircle ? 27 : height / 2 + 14)} textAnchor="middle" className="job-ecosystem-node-count">{node.count.toLocaleString()} {node.unit ?? '岗位'}</text>
  </g>
}

function JobHierarchyGraph({
  data,
  direction,
  category,
  cluster,
  onDirection,
  onCategory,
  onCluster,
}: {
  data: JobEcosystemGraph
  direction: JobDirection | null
  category: JobCategory | null
  cluster: JobCluster | null
  onDirection: (id: string | null) => void
  onCategory: (id: string | null) => void
  onCluster: (id: string | null) => void
}) {
  const graph = useMemo(() => {
    const nodes: PositionedNode[] = []
    const edges: PositionedEdge[] = []
    const addEdge = (source: PositionedNode, target: PositionedNode) => edges.push({ source, target })
    const center = { x: 520, y: 335 }

    if (!direction) {
      const root: PositionedNode = { id: 'root', label: '具身智能岗位生态', kind: 'root', ...center, color: '#052849', count: data.metadata.jobCount }
      nodes.push(root)
      data.directions.forEach((item, index) => {
        const angle = -Math.PI / 2 + index * Math.PI * 2 / data.directions.length
        const point = polar(center.x, center.y, 155, angle)
        const directionNode: PositionedNode = { id: item.id, label: item.name, kind: 'direction', ...point, color: item.color, count: item.jobCount }
        nodes.push(directionNode); addEdge(root, directionNode)
        const items = data.categories.filter((entry) => entry.directionId === item.id)
        items.forEach((entry, categoryIndex) => {
          const spreadStep = items.length >= 4 ? 0.29 : items.length === 3 ? 0.34 : items.length === 2 ? 0.3 : 0
          const spread = (categoryIndex - (items.length - 1) / 2) * spreadStep
          const categoryAngle = angle + spread
          const categoryPoint = {
            x: center.x + Math.cos(categoryAngle) * 410,
            y: center.y + Math.sin(categoryAngle) * 270,
          }
          const categoryNode: PositionedNode = { id: entry.id, label: entry.name, kind: 'category', ...categoryPoint, color: item.color, count: entry.jobCount }
          nodes.push(categoryNode); addEdge(directionNode, categoryNode)
        })
      })
      return { nodes, edges, mode: 'overview' as const }
    }

    if (category) {
      const categoryNode: PositionedNode = { id: category.id, label: category.name, kind: 'category', ...center, color: direction.color, count: category.jobCount }
      const parent: PositionedNode = { id: direction.id, label: direction.name, kind: 'parent', x: 125, y: 92, color: direction.color, count: direction.jobCount }
      nodes.push(categoryNode, parent); addEdge(parent, categoryNode)
      const clusterItems = data.clusters.filter((item) => item.categoryId === category.id)
      clusterItems.forEach((item, index) => {
        const angle = -Math.PI / 2 + index * Math.PI * 2 / clusterItems.length
        const point = polar(center.x, center.y, clusterItems.length <= 3 ? 245 : 280, angle)
        const clusterNode: PositionedNode = { id: item.id, label: item.name, kind: 'cluster', ...point, color: direction.color, count: item.jobCount, selected: cluster?.id === item.id }
        nodes.push(clusterNode); addEdge(categoryNode, clusterNode)
      })
      return { nodes, edges, mode: 'category' as const }
    }

    const directionNode: PositionedNode = { id: direction.id, label: direction.name, kind: 'direction', ...center, color: direction.color, count: direction.jobCount }
    nodes.push(directionNode)
    const clusterItems = data.clusters.filter((item) => item.directionId === direction.id)
    const clusterAngles = new Map<string, number>()
    clusterItems.forEach((item, index) => {
      const angle = -Math.PI / 2 + index * Math.PI * 2 / clusterItems.length
      clusterAngles.set(item.id, angle)
      const point = polar(center.x, center.y, clusterItems.length > 10 ? 295 : 270, angle)
      nodes.push({ id: item.id, label: item.name, kind: 'cluster', ...point, color: direction.color, count: item.jobCount, selected: cluster?.id === item.id })
    })
    data.categories.filter((item) => item.directionId === direction.id).forEach((item) => {
      const angles = clusterItems.filter((clusterItem) => clusterItem.categoryId === item.id).map((clusterItem) => clusterAngles.get(clusterItem.id) ?? 0)
      const point = polar(center.x, center.y, 148, averageAngle(angles))
      const categoryNode: PositionedNode = { id: item.id, label: item.name, kind: 'category', ...point, color: direction.color, count: item.jobCount }
      nodes.push(categoryNode); addEdge(directionNode, categoryNode)
      nodes.filter((node) => node.kind === 'cluster' && data.clusters.find((clusterItem) => clusterItem.id === node.id)?.categoryId === item.id).forEach((node) => addEdge(categoryNode, node))
    })
    return { nodes, edges, mode: 'direction' as const }
  }, [category, cluster?.id, data, direction])

  const clickNode = (node: PositionedNode) => {
    if (node.kind === 'root') { onDirection(null); onCategory(null); onCluster(null) }
    else if (node.kind === 'direction' || node.kind === 'parent') { onDirection(node.id); onCategory(null); onCluster(null) }
    else if (node.kind === 'category') { onCategory(node.id); onCluster(null) }
    else if (node.kind === 'cluster') onCluster(node.id)
  }

  return <div className="job-ecosystem-canvas">
    <svg viewBox="0 0 1040 670" role="img" aria-label="具身智能岗位生态层级图">
      <defs><filter id="job-node-shadow" x="-30%" y="-30%" width="160%" height="160%"><feDropShadow dx="0" dy="3" stdDeviation="4" floodColor="#153452" floodOpacity=".15" /></filter></defs>
      <g className="job-ecosystem-edges">{graph.edges.map((edge) => <path key={`${edge.source.id}-${edge.target.id}`} d={`M ${edge.source.x} ${edge.source.y} L ${edge.target.x} ${edge.target.y}`} />)}</g>
      {graph.nodes.map((node) => <GraphNode key={node.id} node={node} onClick={() => clickNode(node)} />)}
    </svg>
    <div className="job-ecosystem-canvas-hint"><GitBranch size={14} />{graph.mode === 'overview' ? '点击职业方向或职业种类下钻' : graph.mode === 'direction' ? '点击职业种类聚焦，再选择岗位簇' : '点击岗位簇查看证据画像'}</div>
  </div>
}

const CLUSTER_JOB_PAGE_SIZE = 14

function ClusterJobsGraph({
  cluster,
  jobs,
  page,
  onPage,
  onJob,
}: {
  cluster: JobCluster
  jobs: JobRecord[]
  page: number
  onPage: (page: number) => void
  onJob: (job: JobRecord) => void
}) {
  const pageCount = Math.max(1, Math.ceil(jobs.length / CLUSTER_JOB_PAGE_SIZE))
  const safePage = Math.min(page, pageCount - 1)
  const pageJobs = jobs.slice(safePage * CLUSTER_JOB_PAGE_SIZE, (safePage + 1) * CLUSTER_JOB_PAGE_SIZE)
  const center: PositionedNode = { id: cluster.id, label: cluster.name, kind: 'root', x: 520, y: 335, color: cluster.color, count: jobs.length, unit: '个岗位' }
  const nodes: PositionedNode[] = [center]
  const edges: PositionedEdge[] = []
  pageJobs.forEach((job, index) => {
    const angle = -Math.PI / 2 + index * Math.PI * 2 / Math.max(1, pageJobs.length)
    const node: PositionedNode = {
      id: job.id,
      label: job.title,
      kind: 'job',
      x: 520 + Math.cos(angle) * 420,
      y: 335 + Math.sin(angle) * 270,
      color: cluster.color,
      count: job.profile.skills.length || job.skills.length,
      unit: '项技能',
    }
    nodes.push(node); edges.push({ source: center, target: node })
  })
  return <div className="job-ecosystem-canvas cluster-jobs-canvas">
    <div className="cluster-jobs-status"><span>全量岗位层</span><strong>{jobs.length.toLocaleString()} 个岗位节点均已纳入</strong><em>当前第 {safePage + 1} / {pageCount} 页</em></div>
    <svg viewBox="0 0 1040 670" role="img" aria-label={`${cluster.name}岗位簇内全量岗位分页图`}>
      <defs><filter id="cluster-job-shadow" x="-30%" y="-30%" width="160%" height="160%"><feDropShadow dx="0" dy="3" stdDeviation="4" floodColor="#153452" floodOpacity=".15" /></filter></defs>
      <g className="job-ecosystem-edges">{edges.map((edge) => <path key={`${edge.source.id}-${edge.target.id}`} d={`M ${edge.source.x} ${edge.source.y} L ${edge.target.x} ${edge.target.y}`} />)}</g>
      {nodes.map((node) => <GraphNode key={node.id} node={node} onClick={() => node.kind === 'job' ? onJob(pageJobs.find((job) => job.id === node.id) as JobRecord) : undefined} />)}
    </svg>
    <div className="cluster-jobs-pager"><button type="button" disabled={safePage === 0} onClick={() => onPage(safePage - 1)}>上一页</button><span>{safePage * CLUSTER_JOB_PAGE_SIZE + 1}–{Math.min((safePage + 1) * CLUSTER_JOB_PAGE_SIZE, jobs.length)} / {jobs.length}</span><button type="button" disabled={safePage >= pageCount - 1} onClick={() => onPage(safePage + 1)}>下一页</button></div>
    <div className="job-ecosystem-canvas-hint"><BriefcaseBusiness size={14} />点击任意岗位，继续展开该岗位自己的技能、画像与JD证据</div>
  </div>
}

function ClusterAllJobsDetail({
  cluster,
  allJobs,
  jobs,
  query,
  onQuery,
  page,
  onPage,
  onJob,
}: {
  cluster: JobCluster
  allJobs: JobRecord[]
  jobs: JobRecord[]
  query: string
  onQuery: (value: string) => void
  page: number
  onPage: (page: number) => void
  onJob: (job: JobRecord) => void
}) {
  const pageCount = Math.max(1, Math.ceil(jobs.length / CLUSTER_JOB_PAGE_SIZE))
  const safePage = Math.min(page, pageCount - 1)
  const pageJobs = jobs.slice(safePage * CLUSTER_JOB_PAGE_SIZE, (safePage + 1) * CLUSTER_JOB_PAGE_SIZE)
  return <div className="job-cluster-detail cluster-all-jobs-detail">
    <div className="job-cluster-detail-head"><div><StatusTag tone="success">全量岗位已接入</StatusTag><h3>{cluster.name}</h3><p>{cluster.directionName} / {cluster.categoryName} · 非抽样</p></div><span className="job-cluster-total">{allJobs.length}<small>岗位节点</small></span></div>
    <section><h4><Tags size={15} />岗位簇技能概览</h4>{cluster.topSkills.length ? <div className="job-cluster-skill-tags">{cluster.topSkills.slice(0, 6).map((skill) => <span key={skill.name}>{skill.name}<em>{skill.count}</em></span>)}</div> : <p className="job-cluster-muted">技能标签覆盖不足，点击具体岗位查看JD证据。</p>}</section>
    <div className="cluster-job-search"><Search size={14} /><input value={query} onChange={(event) => { onQuery(event.target.value); onPage(0) }} placeholder="在本岗位簇内搜索岗位、公司或技能" />{query ? <button type="button" onClick={() => { onQuery(''); onPage(0) }}>清空</button> : null}</div>
    <section><h4><BriefcaseBusiness size={15} />岗位列表 · {jobs.length.toLocaleString()} 条</h4>{pageJobs.length ? <ul className="job-cluster-job-list cluster-all-job-list">{pageJobs.map((job) => <li key={job.id}><button type="button" className="job-landing-link" onClick={() => onJob(job)}><strong>{job.title}</strong><span>{job.company || '公司未说明'}<ChevronRight size={13} /></span></button></li>)}</ul> : <p className="job-cluster-muted">没有符合当前搜索条件的岗位。</p>}</section>
    <div className="cluster-job-list-pager"><button type="button" disabled={safePage === 0} onClick={() => onPage(safePage - 1)}>上一页</button><span>{safePage + 1} / {pageCount}</span><button type="button" disabled={safePage >= pageCount - 1} onClick={() => onPage(safePage + 1)}>下一页</button></div>
    <section className="job-cluster-governance"><CheckCircle2 size={16} /><p><strong>完整性口径</strong>图谱数据层含 v4 的全部 4,655 个岗位节点；当前画布按岗位簇分页呈现，分页不是抽样，搜索与翻页可访问该簇全部岗位。</p></section>
  </div>
}

function StandardRoleGraph({
  cluster,
  roles,
  selected,
  onRole,
}: {
  cluster: JobCluster
  roles: StandardRole[]
  selected: StandardRole | null
  onRole: (id: string) => void
}) {
  const center: PositionedNode = { id: cluster.id, label: cluster.name, kind: 'root', x: 520, y: 335, color: cluster.color, count: roles.length, unit: '个标准岗位' }
  const nodes: PositionedNode[] = [center]
  const edges: PositionedEdge[] = []
  roles.forEach((role, index) => {
    const angle = -Math.PI / 2 + index * Math.PI * 2 / Math.max(1, roles.length)
    const node: PositionedNode = {
      id: role.id,
      label: role.name,
      kind: 'standardRole',
      x: 520 + Math.cos(angle) * (roles.length > 10 ? 405 : 300),
      y: 335 + Math.sin(angle) * (roles.length > 10 ? 270 : 240),
      color: cluster.color,
      count: role.jobCount,
      unit: '条JD证据',
      selected: selected?.id === role.id,
    }
    nodes.push(node); edges.push({ source: center, target: node })
  })
  return <div className="job-ecosystem-canvas standard-role-canvas">
    <div className="standard-role-status"><span>标准岗位层</span><strong>搜索词包标准名称 + 名称变体 + 多JD证据</strong><em>{roles.length}个标准岗位</em></div>
    <svg viewBox="0 0 1040 670" role="img" aria-label={`${cluster.name}岗位簇内标准岗位图`}>
      <defs><filter id="standard-role-shadow" x="-30%" y="-30%" width="160%" height="160%"><feDropShadow dx="0" dy="3" stdDeviation="4" floodColor="#153452" floodOpacity=".15" /></filter></defs>
      <g className="job-ecosystem-edges">{edges.map((edge) => <path key={`${edge.source.id}-${edge.target.id}`} d={`M ${edge.source.x} ${edge.source.y} L ${edge.target.x} ${edge.target.y}`} />)}</g>
      {nodes.map((node) => <GraphNode key={node.id} node={node} onClick={() => node.kind === 'standardRole' ? onRole(node.id) : undefined} />)}
    </svg>
    <div className="job-ecosystem-canvas-hint"><BriefcaseBusiness size={14} />主图止于标准岗位；具体招聘岗位和完整JD在右侧证据区查看</div>
  </div>
}

function JobEvidenceDetail({ job, onBack, onOpenPortrait }: { job: JobRecord; onBack: () => void; onOpenPortrait?: () => void }) {
  return <div className="job-cluster-detail jd-evidence-detail">
    <button type="button" className="job-evidence-back" onClick={onBack}><ArrowLeft size={14} />返回标准岗位证据</button>
    <div className="job-cluster-detail-head"><div><StatusTag tone="info">具体JD证据</StatusTag><h3>{job.title}</h3><p>{job.company || '公司未说明'} · {job.occId}</p></div><span className="job-cluster-total">{Math.round(job.standardRoleMappingConfidence * 100)}<small>映射置信%</small></span></div>
    {onOpenPortrait ? <button type="button" className="standard-role-profile-button" onClick={onOpenPortrait}><BrainCircuit size={15} />进入该岗位的岗位画像图谱</button> : null}
    <div className="enterprise-fact-grid job-evidence-facts">
      <div><Sparkles size={15} /><span>能力等级</span><strong>{job.abilityLevel || '未说明'}</strong></div>
      <div><ListChecks size={15} /><span>工作经验</span><strong>{job.experience || '未说明'}</strong></div>
      <div><ShieldCheck size={15} /><span>学历要求</span><strong>{job.education || '未说明'}</strong></div>
      <div><MapPinned size={15} /><span>企业地区</span><strong>{job.companyRegion || '未说明'}</strong></div>
    </div>
    <section><h4><Tags size={15} />岗位技能标签</h4>{job.skills.length ? <div className="job-cluster-skill-tags">{job.skills.map((skill) => <span key={skill}>{skill}</span>)}</div> : <p className="job-cluster-muted">该JD暂无结构化技能标签。</p>}</section>
    <section><h4><FileText size={15} />完整JD文本</h4><div className="full-jd-text">{job.jd || '该岗位暂无可展示的JD原文。'}</div>{job.url ? <a className="job-source-link" href={job.url} target="_blank" rel="noreferrer">打开岗位来源</a> : null}</section>
    <section className="job-cluster-governance"><ShieldCheck size={16} /><p><strong>证据关系</strong>该记录通过“{job.standardRoleMappingMethod}”归入“{job.standardRoleName || '待映射标准岗位'}”；它只作为标准岗位画像的证据，不单独决定五维结论。</p></section>
  </div>
}

function JobCapabilityDetail({
  job,
  cluster,
  dimension,
  onDimension,
  onBack,
}: {
  job: JobRecord
  cluster: JobCluster | null
  dimension: PortraitDimension
  onDimension: (dimension: PortraitDimension) => void
  onBack: () => void
}) {
  return <div className="job-cluster-detail job-capability-detail">
    <button type="button" className="job-evidence-back" onClick={onBack}><ArrowLeft size={14} />返回岗位证据</button>
    <JobLandingGraph cluster={cluster} job={job} dimension={dimension} onDimension={onDimension} />
    <PortraitDetail job={job} cluster={cluster} dimension={dimension} />
  </div>
}

function StandardRoleDetail({
  role,
  jobs,
  selectedJob,
  onJob,
  onBackJob,
  onOpenProfile,
}: {
  role: StandardRole
  jobs: JobRecord[]
  selectedJob: JobRecord | null
  onJob: (job: JobRecord) => void
  onBackJob: () => void
  onOpenProfile: () => void
}) {
  if (selectedJob) {
    return <JobCapabilityDetail
      job={selectedJob}
      cluster={null}
      dimension="responsibilities"
      onDimension={() => undefined}
      onBack={onBackJob}
    />
  }
  return <div className="job-cluster-detail standard-role-detail">
    <div className="job-cluster-detail-head"><div><StatusTag tone="warning">标准岗位候选 · 待专家校准</StatusTag><h3>{role.name}</h3><p>{role.code} · {role.clusterName}</p></div><span className="job-cluster-total">{role.jobCount}<small>JD证据</small></span></div>
    <div className="job-cluster-facts"><div><Building2 size={16} /><span>覆盖企业</span><strong>{role.companyCount}</strong></div><div><FileText size={16} /><span>有效JD</span><strong>{role.jdCount}</strong></div></div>
    <section><h4><Tags size={15} />名称变体 · 搜索词包</h4><div className="role-variant-tags">{role.seedVariants.slice(0, 12).map((variant) => <span key={variant}>{variant}</span>)}</div></section>
    <section><h4><BriefcaseBusiness size={15} />数据中实际出现的标题</h4>{role.observedVariants.length ? <div className="role-observed-variants">{role.observedVariants.slice(0, 8).map((variant) => <span key={variant.name}><strong>{variant.name}</strong><em>{variant.count}条</em></span>)}</div> : <p className="job-cluster-muted">当前v4中尚无高置信JD证据，保留为待补证标准岗位。</p>}</section>
    <button type="button" className="standard-role-profile-button" onClick={onOpenProfile}><BrainCircuit size={15} />查看该标准岗位的五维画像</button>
    <section><h4><FileText size={15} />具体岗位与JD证据 · {jobs.length}条</h4>{jobs.length ? <ul className="job-cluster-job-list standard-role-jd-list">{jobs.slice(0, 10).map((job) => <li key={job.id}><button type="button" className="job-landing-link" onClick={() => onJob(job)}><strong>{job.title}</strong><span>{job.company || '公司未说明'}<ChevronRight size={13} /></span></button></li>)}</ul> : <p className="job-cluster-muted">暂无达到当前映射阈值的JD，后续由专家补充别名或调整归并。</p>}</section>
    <section className="job-cluster-governance"><ShieldCheck size={16} /><p><strong>画像口径</strong>{role.profileMethod}。单条JD只提供证据，不直接生成标准岗位画像。</p></section>
  </div>
}

function StandardRoleCapabilityGraph({
  role,
  dimension,
  selectedPoint,
  onDimension,
  onPoint,
}: {
  role: StandardRole
  dimension: PortraitDimension
  selectedPoint: string | null
  onDimension: (dimension: PortraitDimension) => void
  onPoint: (dimension: PortraitDimension, point: StandardProfilePoint) => void
}) {
  const center: PositionedNode = { id: role.id, label: role.name, kind: 'root', x: 520, y: 335, color: '#112f53', count: role.jobCount, unit: '条JD支撑' }
  const nodes: PositionedNode[] = [center]
  const edges: PositionedEdge[] = []
  const pointLookup = new Map<string, { dimension: PortraitDimension; point: StandardProfilePoint }>()
  PORTRAIT_DIMENSIONS.forEach((item, index) => {
    const angle = -Math.PI / 2 + index * Math.PI * 2 / PORTRAIT_DIMENSIONS.length
    const point = polar(520, 335, 176, angle)
    const dimensionNode: PositionedNode = { id: item.key, label: item.label, kind: 'capability', ...point, color: item.color, count: role.standardProfile[item.key].length, unit: '项标准点', selected: dimension === item.key }
    nodes.push(dimensionNode); edges.push({ source: center, target: dimensionNode })
    const displayItems = role.standardProfile[item.key].slice(0, 6)
    displayItems.forEach((profilePoint, pointIndex, pointItems) => {
      const spread = pointItems.length <= 1 ? 0 : (pointIndex - (pointItems.length - 1) / 2) * 0.09
      const evidenceAngle = angle + spread
      const nodeId = `${item.key}-${pointIndex}`
      const evidenceNode: PositionedNode = {
        id: nodeId,
        label: profilePoint.name,
        kind: 'evidence',
        x: 520 + Math.cos(evidenceAngle) * 455,
        y: 335 + Math.sin(evidenceAngle) * 300,
        color: item.color,
        count: profilePoint.count,
        unit: '条JD支撑',
        selected: dimension === item.key && selectedPoint === profilePoint.name,
      }
      pointLookup.set(nodeId, { dimension: item.key, point: profilePoint })
      nodes.push(evidenceNode); edges.push({ source: dimensionNode, target: evidenceNode })
    })
  })
  return <div className="job-ecosystem-canvas job-portrait-canvas standard-role-profile-canvas">
    <div className="job-landing-context"><span>标准岗位五维画像</span><strong>{role.name} · 多JD聚合，不由单条JD生成</strong></div>
    <svg viewBox="0 0 1040 670" role="img" aria-label={`${role.name}标准岗位五维画像图`}>
      <defs><filter id="standard-profile-shadow" x="-30%" y="-30%" width="160%" height="160%"><feDropShadow dx="0" dy="3" stdDeviation="4" floodColor="#153452" floodOpacity=".15" /></filter></defs>
      <g className="job-ecosystem-edges">{edges.map((edge) => <path key={`${edge.source.id}-${edge.target.id}`} d={`M ${edge.source.x} ${edge.source.y} L ${edge.target.x} ${edge.target.y}`} />)}</g>
      {nodes.map((node) => <GraphNode key={node.id} node={node} onClick={() => {
        if (PORTRAIT_DIMENSIONS.some((item) => item.key === node.id)) onDimension(node.id as PortraitDimension)
        const found = pointLookup.get(node.id)
        if (found) onPoint(found.dimension, found.point)
      }} />)}
    </svg>
    <div className="job-ecosystem-canvas-hint"><FileText size={14} />点击能力点，右侧查看覆盖率、支持它的具体岗位和完整JD</div>
  </div>
}

function StandardRoleEvidenceDetail({
  role,
  cluster,
  dimension,
  selectedPoint,
  jobs,
  selectedJob,
  onPoint,
  onJob,
  onBackJob,
}: {
  role: StandardRole
  cluster: JobCluster | null
  dimension: PortraitDimension
  selectedPoint: string | null
  jobs: JobRecord[]
  selectedJob: JobRecord | null
  onPoint: (point: StandardProfilePoint) => void
  onJob: (job: JobRecord) => void
  onBackJob: () => void
}) {
  if (selectedJob) {
    return <JobEvidenceDetail job={selectedJob} onBack={onBackJob} />
  }
  const config = PORTRAIT_DIMENSIONS.find((item) => item.key === dimension) ?? PORTRAIT_DIMENSIONS[0]
  const Icon = config.icon
  const points = role.standardProfile[dimension]
  return <div className="job-cluster-detail standard-role-evidence-detail">
    <div className="job-cluster-detail-head"><div><StatusTag tone="success">多JD聚合画像</StatusTag><h3>{role.name}</h3><p>{role.clusterName} · {role.jobCount}条岗位证据</p></div><span className="job-cluster-total">{points.length}<small>{config.label}标准点</small></span></div>
    <section className="job-cluster-governance evolution-snapshot"><FileText size={16} /><p><strong>演化基线</strong>当前发布的是v4单一时间截面；下一期同口径快照到位后，系统再计算新增、删除、强弱变化及“必备↔加分”迁移，不用单期频次伪造趋势。</p></section>
    <section className="portrait-question"><Icon size={18} /><div><strong>{config.label}</strong><p>{config.question} · 点击标准点筛选证据</p></div></section>
    <section><h4><CheckCircle2 size={15} />标准化画像点</h4>{points.length ? <div className="standard-profile-point-list">{points.map((point) => <button key={point.name} type="button" className={selectedPoint === point.name ? 'active' : ''} onClick={() => onPoint(point)}><span>{point.name}</span><strong>{point.count}条</strong><em>{Math.round(point.coverage * 100)}%覆盖</em></button>)}</div> : <p className="job-cluster-muted">当前维度证据不足，保留为空，不由单条JD推测生成。</p>}</section>
    <section><h4><FileText size={15} />支持当前结论的具体JD · {jobs.length}条</h4>{jobs.length ? <ul className="job-cluster-job-list standard-role-jd-list">{jobs.slice(0, 12).map((job) => <li key={job.id}><button type="button" className="job-landing-link" onClick={() => onJob(job)}><strong>{job.title}</strong><span>{job.company || '公司未说明'}<ChevronRight size={13} /></span></button></li>)}</ul> : <p className="job-cluster-muted">请选择其他标准点，或等待补充更多JD证据。</p>}</section>
    <section className="job-cluster-governance"><ShieldCheck size={16} /><p><strong>交叉验证</strong>标准点同时显示JD数量和岗位覆盖率；点击具体岗位可查看完整JD，专家可据此合并、拆分或驳回画像点。</p></section>
  </div>
}

type EnterpriseDimensionKey = 'industryStage' | 'companySpecialty' | 'financingRound' | 'companyRegion' | 'headquartersCity'

const ENTERPRISE_DIMENSIONS: Array<{
  key: EnterpriseDimensionKey
  label: string
  color: string
  icon: typeof Network
}> = [
  { key: 'industryStage', label: '产业链层级', color: '#0f9d91', icon: Network },
  { key: 'companySpecialty', label: '公司细分领域', color: '#d88b28', icon: Tags },
  { key: 'financingRound', label: '融资轮次', color: '#8a62c7', icon: WalletCards },
  { key: 'companyRegion', label: '所属地区', color: '#2e75b6', icon: MapPinned },
  { key: 'headquartersCity', label: '总部城市', color: '#526f92', icon: Building2 },
]

function enterpriseDistribution(data: JobEcosystemGraph, dimension: EnterpriseDimensionKey) {
  if (dimension === 'industryStage') return data.enterpriseAnalysis.industryDistribution
  if (dimension === 'companySpecialty') {
    const values = data.enterprises.reduce<Record<string, number>>((result, enterprise) => {
      const name = enterprise.companySpecialty || '待补全'
      result[name] = (result[name] ?? 0) + enterprise.jobCount
      return result
    }, {})
    return Object.entries(values).map(([name, count]) => ({ name, count })).sort((a, b) => b.count - a.count)
  }
  if (dimension === 'companyRegion') return data.enterpriseAnalysis.regionDistribution
  if (dimension === 'headquartersCity') return data.enterpriseAnalysis.headquartersCityDistribution
  return data.enterpriseAnalysis.financingDistribution
}

function EnterpriseDimensionGraph({
  data,
  dimension,
  selectedValue,
  selectedEnterprise,
  onValue,
  onEnterprise,
  onRole,
}: {
  data: JobEcosystemGraph
  dimension: EnterpriseDimensionKey
  selectedValue: string | null
  selectedEnterprise: EnterpriseRecord | null
  onValue: (value: string | null) => void
  onEnterprise: (id: string | null) => void
  onRole: (id: string) => void
}) {
  const graph = useMemo(() => {
    const nodes: PositionedNode[] = []
    const edges: PositionedEdge[] = []
    const center = { x: 520, y: 335 }
    const current = ENTERPRISE_DIMENSIONS.find((item) => item.key === dimension) ?? ENTERPRISE_DIMENSIONS[0]
    const addEdge = (source: PositionedNode, target: PositionedNode) => edges.push({ source, target })

    if (selectedEnterprise) {
      const enterpriseNode: PositionedNode = {
        id: selectedEnterprise.id, label: selectedEnterprise.name, kind: 'root', ...center,
        color: current.color, count: selectedEnterprise.jobCount,
      }
      const parent: PositionedNode = {
        id: `dimension-${selectedValue ?? selectedEnterprise[dimension]}`, label: selectedValue ?? selectedEnterprise[dimension],
        kind: 'parent', x: 125, y: 92, color: current.color, count: selectedEnterprise.jobCount,
      }
      nodes.push(enterpriseNode, parent); addEdge(parent, enterpriseNode)
      const enterpriseJobs = data.jobs.filter((job) => job.enterpriseName === selectedEnterprise.name || job.company === selectedEnterprise.name)
      const roleCounts = new Map<string, { id: string; name: string; count: number }>()
      enterpriseJobs.forEach((job) => {
        const id = job.standardRoleId || 'pending-standard-role'
        const name = job.standardRoleName || '待映射标准岗位'
        const item = roleCounts.get(id)
        if (item) item.count += 1
        else roleCounts.set(id, { id, name, count: 1 })
      })
      const roles = [...roleCounts.values()].sort((a, b) => b.count - a.count).slice(0, 18)
      roles.forEach((role, index) => {
        const angle = -Math.PI / 2 + index * Math.PI * 2 / Math.max(1, roles.length)
        const point = roles.length > 12
          ? { x: center.x + Math.cos(angle) * 360, y: center.y + Math.sin(angle) * 245 }
          : polar(center.x, center.y, 275, angle)
        const node: PositionedNode = {
          id: role.id, label: role.name, kind: 'standardRole', ...point,
          color: role.id === 'pending-standard-role' ? '#7c8b9b' : current.color,
          count: role.count, unit: '条JD',
        }
        nodes.push(node); addEdge(enterpriseNode, node)
      })
      return { nodes, edges, mode: 'roles' as const }
    }

    if (!selectedValue) {
      const root: PositionedNode = {
        id: 'enterprise-root', label: '企业库关联岗位', kind: 'root', ...center,
        color: '#052849', count: data.enterpriseAnalysis.matchedJobCount,
      }
      nodes.push(root)
      enterpriseDistribution(data, dimension).slice(0, 12).forEach((item, index, items) => {
        const angle = -Math.PI / 2 + index * Math.PI * 2 / items.length
        const point = polar(center.x, center.y, items.length > 8 ? 290 : 245, angle)
        const node: PositionedNode = {
          id: `dimension-${item.name}`, label: item.name, kind: 'dimension', ...point,
          color: current.color, count: item.count,
        }
        nodes.push(node); addEdge(root, node)
      })
      return { nodes, edges, mode: 'dimension' as const }
    }

    const jobsInValue = enterpriseDistribution(data, dimension).find((item) => item.name === selectedValue)?.count ?? 0
    const valueNode: PositionedNode = { id: `dimension-${selectedValue}`, label: selectedValue, kind: 'root', ...center, color: current.color, count: jobsInValue }
    const parent: PositionedNode = { id: 'enterprise-root', label: '企业库关联岗位', kind: 'parent', x: 125, y: 92, color: '#052849', count: data.enterpriseAnalysis.matchedJobCount }
    nodes.push(valueNode, parent); addEdge(parent, valueNode)
    const companies = data.enterprises
      .filter((enterprise) => enterprise[dimension] === selectedValue)
      .sort((a, b) => b.jobCount - a.jobCount)
      .slice(0, 18)
    companies.forEach((enterprise, index) => {
      const angle = -Math.PI / 2 + index * Math.PI * 2 / companies.length
      const point = companies.length > 12
        ? { x: center.x + Math.cos(angle) * 360, y: center.y + Math.sin(angle) * 245 }
        : polar(center.x, center.y, 270, angle)
      const node: PositionedNode = {
        id: enterprise.id, label: enterprise.name, kind: 'enterprise', ...point,
        color: current.color, count: enterprise.jobCount, selected: false,
      }
      nodes.push(node); addEdge(valueNode, node)
    })
    return { nodes, edges, mode: 'enterprise' as const }
  }, [data, dimension, selectedEnterprise?.id, selectedValue])

  const clickNode = (node: PositionedNode) => {
    if (node.id === 'enterprise-root') { onValue(null); onEnterprise(null) }
    else if (node.kind === 'dimension') { onValue(node.label); onEnterprise(null) }
    else if (node.kind === 'enterprise') onEnterprise(node.id)
    else if (node.kind === 'standardRole' && node.id !== 'pending-standard-role') onRole(node.id)
  }

  return <div className="job-ecosystem-canvas enterprise-ecosystem-canvas">
    <svg viewBox="0 0 1040 670" role="img" aria-label="企业库驱动的岗位需求关系图">
      <defs><filter id="enterprise-node-shadow" x="-30%" y="-30%" width="160%" height="160%"><feDropShadow dx="0" dy="3" stdDeviation="4" floodColor="#153452" floodOpacity=".15" /></filter></defs>
      <g className="job-ecosystem-edges">{graph.edges.map((edge) => <path key={`${edge.source.id}-${edge.target.id}`} d={`M ${edge.source.x} ${edge.source.y} L ${edge.target.x} ${edge.target.y}`} />)}</g>
      {graph.nodes.map((node) => <GraphNode key={node.id} node={node} onClick={() => clickNode(node)} />)}
    </svg>
    <div className="job-ecosystem-canvas-hint"><Network size={14} />{graph.mode === 'dimension' ? '点击属性值，查看关联企业' : graph.mode === 'enterprise' ? '展示岗位量靠前的18家企业，点击企业继续下钻' : '企业需求最终落到标准岗位；右侧可逐条打开真实JD'}</div>
  </div>
}

function EnterpriseDetail({
  enterprise,
  jobs,
  onJob,
  selectedJobId,
}: {
  enterprise: EnterpriseRecord
  jobs: JobRecord[]
  onJob: (job: JobRecord) => void
  selectedJobId?: string | null
}) {
  const roleCounts = jobs.reduce<Record<string, number>>((result, job) => {
    const name = job.standardRoleName || '待映射标准岗位'
    result[name] = (result[name] ?? 0) + 1
    return result
  }, {})
  return <div className="enterprise-detail">
    <div className="job-cluster-detail-head">
      <div><StatusTag tone="success">企业库已关联</StatusTag><h3>{enterprise.name}</h3><p>{enterprise.industryStage || '产业链待补'} · {enterprise.companyRegion || '地区待补'}</p></div>
      <span className="job-cluster-total">{enterprise.jobCount}<small>岗位</small></span>
    </div>
    <div className="enterprise-fact-grid">
      <div><Network size={15} /><span>产业链层级</span><strong>{enterprise.industryStage || '待补全'}</strong></div>
      <div><Landmark size={15} /><span>融资轮次</span><strong>{enterprise.financingRound || '待补全'}</strong></div>
      <div><MapPinned size={15} /><span>总部地区</span><strong>{enterprise.companyRegion || '待补全'}</strong></div>
      <div><Building2 size={15} /><span>总部城市</span><strong>{enterprise.headquartersCity || '待补全'}</strong></div>
    </div>
    <section><h4><BarChart3 size={15} />岗位方向分布</h4><DistributionBars values={enterprise.directionDistribution} color="#0f9d91" /></section>
    <section><h4><Tags size={15} />公司细分领域</h4><p className="job-cluster-muted">{enterprise.companySpecialty || '企业库暂未补全细分领域。'}</p></section>
    <section><h4><BriefcaseBusiness size={15} />企业需求映射到标准岗位</h4><DistributionBars values={roleCounts} color="#0f9d91" /></section>
    <section><h4><BriefcaseBusiness size={15} />具体招聘岗位与JD证据</h4>{jobs.length ? <ul className="job-cluster-job-list">{jobs.map((job) => <li key={job.id}><button type="button" className={`job-landing-link ${selectedJobId === job.id ? 'active' : ''}`} onClick={() => onJob(job)}><strong>{job.title}</strong><span>{job.standardRoleName || '标准岗位待映射'}<ChevronRight size={13} /></span></button></li>)}</ul> : <p className="job-cluster-muted">该企业暂无可展示的岗位JD证据。</p>}</section>
  </div>
}

function DistributionBars({ values, color }: { values: Record<string, number>; color: string }) {
  const items = Object.entries(values).slice(0, 4)
  const total = items.reduce((sum, [, value]) => sum + value, 0) || 1
  return <div className="job-cluster-bars">{items.map(([name, value]) => <div key={name}><span>{name}</span><div><i style={{ width: `${value / total * 100}%`, background: color }} /></div><strong>{value}</strong></div>)}</div>
}

function technologyDescendantIds(nodes: JobTechnologyNode[], rootId: string) {
  const children = new Map<string, string[]>()
  nodes.forEach((node) => {
    const values = children.get(node.parentId) ?? []
    values.push(node.id)
    children.set(node.parentId, values)
  })
  const result = new Set<string>()
  const stack = [rootId]
  while (stack.length) {
    const id = stack.pop() as string
    result.add(id)
    stack.push(...(children.get(id) ?? []))
  }
  return result
}

function technologyPath(nodes: JobTechnologyNode[], selected: JobTechnologyNode | null) {
  if (!selected) return []
  const lookup = new Map(nodes.map((node) => [node.id, node]))
  const path: JobTechnologyNode[] = []
  let current: JobTechnologyNode | undefined = selected
  while (current) {
    path.unshift(current)
    current = current.parentId ? lookup.get(current.parentId) : undefined
  }
  return path
}

const TECHNOLOGY_LEVEL_COLORS: Record<JobTechnologyNode['level'], string> = {
  L1: '#123e6a',
  L2: '#0e8f88',
  L3: '#d88b28',
  L4: '#6b4fc2',
}

function TechnologyLayeredTree({
  nodes,
  selected,
  expanded,
  onToggle,
  onTechnology,
}: {
  nodes: JobTechnologyNode[]
  selected: JobTechnologyNode | null
  expanded: Set<string>
  onToggle: (id: string) => void
  onTechnology: (id: string) => void
}) {
  const childrenByParent = useMemo(() => {
    const result = new Map<string, JobTechnologyNode[]>()
    nodes.forEach((node) => {
      const children = result.get(node.parentId) ?? []
      children.push(node)
      result.set(node.parentId, children)
    })
    result.forEach((children) => children.sort((a, b) => {
      if (a.level === 'L4' || b.level === 'L4') return b.jobCount - a.jobCount || a.name.localeCompare(b.name, 'zh-CN')
      return a.code.localeCompare(b.code, undefined, { numeric: true })
    }))
    return result
  }, [nodes])

  const renderNode = (node: JobTechnologyNode) => {
    const children = childrenByParent.get(node.id) ?? []
    const isOpen = expanded.has(node.id)
    const selectedNode = selected?.id === node.id
    const levelClass = node.level === 'L1' ? 'tree-dir' : node.level === 'L2' ? 'tree-cat' : node.level === 'L3' ? 'tree-cluster' : 'tree-role'
    return <div key={node.id} className={`tree-node ${levelClass} technology-tree-node technology-tree-${node.level.toLowerCase()}`}>
      <div className={`tree-row ${selectedNode ? 'active' : ''}`}>
        {children.length ? <button
          type="button"
          className="tree-toggle"
          aria-label={`${isOpen ? '收起' : '展开'}${node.name}`}
          aria-expanded={isOpen}
          onClick={(event) => { event.stopPropagation(); onToggle(node.id) }}
        >{isOpen ? <ChevronDown size={14} /> : <ChevronRight size={14} />}</button> : <span className="tree-toggle tree-spacer" />}
        <button type="button" className="tree-label" title={`${node.code ? `${node.code} · ` : ''}${node.name}`} onClick={() => onTechnology(node.id)}>
          <i style={{ background: TECHNOLOGY_LEVEL_COLORS[node.level] }} />
          <span><small>{node.level}</small>{node.name}</span>
          <em>{node.jobCount.toLocaleString()}岗</em>
        </button>
      </div>
      {children.length && isOpen ? <div className="tree-children">{children.map((child) => renderNode(child))}</div> : null}
    </div>
  }

  const roots = childrenByParent.get('') ?? []
  return <div className="portrait-layered-tree technology-layered-tree">
    <div className="technology-tree-summary"><strong>{roots.length} 个 L1 技术域</strong><span>逐级展开至 {nodes.filter((node) => node.level === 'L4').length.toLocaleString()} 个 L4 技术词</span></div>
    {roots.map((node) => renderNode(node))}
  </div>
}

function TechnologyHierarchyGraph({
  data,
  selected,
  jobs,
  onTechnology,
  onRole,
}: {
  data: JobEcosystemGraph
  selected: JobTechnologyNode | null
  jobs: JobRecord[]
  onTechnology: (id: string | null) => void
  onRole: (id: string) => void
}) {
  const graph = useMemo(() => {
    const nodes: PositionedNode[] = []
    const edges: PositionedEdge[] = []
    const center = { x: 520, y: 335 }
    const addEdge = (source: PositionedNode, target: PositionedNode) => edges.push({ source, target })
    if (!selected) {
      const root: PositionedNode = { id: 'technology-root', label: '技术主数据', kind: 'root', ...center, color: '#123e6a', count: data.technologyAudit.levelCounts.L4, unit: '个L4词' }
      nodes.push(root)
      data.technologyNodes.filter((node) => node.level === 'L1').forEach((item, index, items) => {
        const angle = -Math.PI / 2 + index * Math.PI * 2 / items.length
        const point = polar(center.x, center.y, 270, angle)
        const node: PositionedNode = { id: item.id, label: item.name, kind: 'dimension', ...point, color: '#0e8f88', count: item.jobCount }
        nodes.push(node); addEdge(root, node)
      })
      return { nodes, edges, mode: 'root' as const }
    }

    const centerNode: PositionedNode = { id: selected.id, label: selected.name, kind: 'root', ...center, color: selected.level === 'L4' ? '#6b4fc2' : '#0e8f88', count: selected.jobCount }
    nodes.push(centerNode)
    if (selected.parentId) {
      const parentData = data.technologyNodes.find((item) => item.id === selected.parentId)
      if (parentData) {
        const parent: PositionedNode = { id: parentData.id, label: parentData.name, kind: 'parent', x: 125, y: 92, color: '#123e6a', count: parentData.jobCount }
        nodes.push(parent); addEdge(parent, centerNode)
      }
    } else {
      const parent: PositionedNode = { id: 'technology-root', label: '技术主数据', kind: 'parent', x: 125, y: 92, color: '#123e6a', count: data.technologyAudit.levelCounts.L4, unit: '个L4词' }
      nodes.push(parent); addEdge(parent, centerNode)
    }

    if (selected.level !== 'L4') {
      const children = data.technologyNodes
        .filter((item) => item.parentId === selected.id)
        .sort((a, b) => b.jobCount - a.jobCount || a.name.localeCompare(b.name, 'zh-CN'))
        .slice(0, 20)
      children.forEach((item, index) => {
        const angle = -Math.PI / 2 + index * Math.PI * 2 / Math.max(1, children.length)
        const point = children.length > 12
          ? { x: center.x + Math.cos(angle) * 370, y: center.y + Math.sin(angle) * 245 }
          : polar(center.x, center.y, 280, angle)
        const node: PositionedNode = { id: item.id, label: item.name, kind: 'dimension', ...point, color: item.level === 'L4' ? '#6b4fc2' : '#0e8f88', count: item.jobCount }
        nodes.push(node); addEdge(centerNode, node)
      })
      return { nodes, edges, mode: 'children' as const, hidden: Math.max(0, data.technologyNodes.filter((item) => item.parentId === selected.id).length - children.length) }
    }

    const roleCounts = new Map<string, { id: string; name: string; count: number }>()
    jobs.forEach((job) => {
      const id = job.standardRoleId || 'pending-standard-role'
      const name = job.standardRoleName || '待映射标准岗位'
      const item = roleCounts.get(id)
      if (item) item.count += 1
      else roleCounts.set(id, { id, name, count: 1 })
    })
    const roles = [...roleCounts.values()].sort((a, b) => b.count - a.count).slice(0, 18)
    roles.forEach((role, index) => {
      const angle = -Math.PI / 2 + index * Math.PI * 2 / Math.max(1, roles.length)
      const point = roles.length > 12
        ? { x: center.x + Math.cos(angle) * 360, y: center.y + Math.sin(angle) * 245 }
        : polar(center.x, center.y, 275, angle)
      const node: PositionedNode = { id: role.id, label: role.name, kind: 'standardRole', ...point, color: role.id === 'pending-standard-role' ? '#7c8b9b' : '#6b4fc2', count: role.count, unit: '条JD' }
      nodes.push(node); addEdge(centerNode, node)
    })
    return { nodes, edges, mode: 'roles' as const }
  }, [data, jobs, selected])

  const clickNode = (node: PositionedNode) => {
    if (node.id === 'technology-root') onTechnology(null)
    else if (node.kind === 'dimension' || node.kind === 'parent') onTechnology(node.id)
    else if (node.kind === 'standardRole' && node.id !== 'pending-standard-role') onRole(node.id)
  }

  return <div className="job-ecosystem-canvas technology-ecosystem-canvas">
    <svg viewBox="0 0 1040 670" role="img" aria-label="L1到L4技术词映射岗位图">
      <defs><filter id="technology-node-shadow" x="-30%" y="-30%" width="160%" height="160%"><feDropShadow dx="0" dy="3" stdDeviation="4" floodColor="#153452" floodOpacity=".15" /></filter></defs>
      <g className="job-ecosystem-edges">{graph.edges.map((edge) => <path key={`${edge.source.id}-${edge.target.id}`} d={`M ${edge.source.x} ${edge.source.y} L ${edge.target.x} ${edge.target.y}`} />)}</g>
      {graph.nodes.map((node) => <GraphNode key={node.id} node={node} onClick={() => clickNode(node)} />)}
    </svg>
    <div className="job-ecosystem-canvas-hint"><Wrench size={14} />{graph.mode === 'root' ? '从7个技术域进入L2–L4技术主数据' : graph.mode === 'children' ? `点击子节点继续下钻${graph.hidden ? `；另有${graph.hidden}个节点可用搜索定位` : ''}` : '技术词尾端落到标准岗位，右侧保留全部具体JD证据'}</div>
  </div>
}

function TechnologyDetail({
  data,
  selected,
  jobs,
  selectedJob,
  onTechnology,
  onJob,
  onBackJob,
  onOpenPortrait,
}: {
  data: JobEcosystemGraph
  selected: JobTechnologyNode | null
  jobs: JobRecord[]
  selectedJob: JobRecord | null
  onTechnology: (id: string) => void
  onJob: (job: JobRecord) => void
  onBackJob: () => void
  onOpenPortrait?: (job: JobRecord) => void
}) {
  if (selectedJob) return <JobEvidenceDetail job={selectedJob} onBack={onBackJob} onOpenPortrait={() => onOpenPortrait ? onOpenPortrait(selectedJob) : window.location.hash = `/job-portrait-graph?job=${encodeURIComponent(selectedJob.id)}`} />
  if (!selected) return <div className="job-ecosystem-guide"><div><span>01</span><p><strong>主数据起点</strong>7个L1技术域、43个L2技术类、229个L3技术点、1,872个L4技术词是唯一技术层级口径。</p></div><div><span>02</span><p><strong>证据回接</strong>仅使用JD全文一致和L4精确命中，当前覆盖{data.technologyAudit.mappedJobCount.toLocaleString()}条岗位。</p></div><div><span>03</span><p><strong>岗位落点</strong>技术词先聚合到标准岗位，具体招聘岗位和完整JD保留在右侧。</p></div><div><span>04</span><p><strong>空值可见</strong>{data.technologyAudit.pendingJobCount.toLocaleString()}条未安全映射岗位保留待补，不用模糊猜测补值。</p></div></div>
  const path = technologyPath(data.technologyNodes, selected)
  const children = data.technologyNodes.filter((item) => item.parentId === selected.id).sort((a, b) => b.jobCount - a.jobCount)
  const roleCounts = jobs.reduce<Record<string, number>>((result, job) => {
    const name = job.standardRoleName || '待映射标准岗位'
    result[name] = (result[name] ?? 0) + 1
    return result
  }, {})
  return <div className="job-cluster-detail technology-detail">
    <div className="job-cluster-detail-head"><div><StatusTag tone={selected.jobCount ? 'success' : 'neutral'}>{selected.level}技术节点</StatusTag><h3>{selected.name}</h3><p>{path.map((item) => item.name).join(' / ')}</p></div><span className="job-cluster-total">{selected.jobCount}<small>关联岗位</small></span></div>
    {selected.definition ? <section><h4><FileText size={15} />节点说明</h4><p className="job-cluster-muted">{selected.definition}</p></section> : null}
    {children.length ? <section><h4><Layers3 size={15} />下一级技术节点</h4><div className="standard-profile-point-list">{children.slice(0, 12).map((item) => <button key={item.id} type="button" onClick={() => onTechnology(item.id)}><span>{item.name}</span><strong>{item.jobCount}岗</strong><em>{item.level}</em></button>)}</div></section> : null}
    <section><h4><BriefcaseBusiness size={15} />技术词引出的标准岗位</h4>{Object.keys(roleCounts).length ? <DistributionBars values={roleCounts} color="#6b4fc2" /> : <p className="job-cluster-muted">当前技术节点尚无安全映射的标准岗位。</p>}</section>
    <section><h4><FileText size={15} />具体岗位与JD证据 · {jobs.length}条</h4>{jobs.length ? <ul className="job-cluster-job-list standard-role-jd-list">{jobs.slice(0, 12).map((job) => <li key={job.id}><button type="button" className="job-landing-link" onClick={() => onJob(job)}><strong>{job.title}</strong><span>{job.company || '公司未说明'}<ChevronRight size={13} /></span></button></li>)}</ul> : <p className="job-cluster-muted">该节点暂无可发布的岗位证据。</p>}</section>
    <section className="job-cluster-governance"><ShieldCheck size={16} /><p><strong>映射口径</strong>{data.technologyAudit.mappingRule}。</p></section>
  </div>
}

function ClusterDetail({ cluster, onJob }: { cluster: JobCluster; onJob: (job: RepresentativeJob) => void }) {
  return <div className="job-cluster-detail">
    <div className="job-cluster-detail-head">
      <div><StatusTag tone="warning">候选簇 · 待校准</StatusTag><h3>{cluster.name}</h3><p>{cluster.code} · {cluster.directionName} / {cluster.categoryName}</p></div>
      <span className="job-cluster-total">{cluster.jobCount}<small>岗位</small></span>
    </div>
    <div className="job-cluster-facts"><div><Building2 size={16} /><span>覆盖企业</span><strong>{cluster.companyCount}</strong></div><div><CheckCircle2 size={16} /><span>规则命中</span><strong>{Math.round(cluster.ruleMatchedRate * 100)}%</strong></div></div>
    <section><h4><Tags size={15} />核心技能</h4>{cluster.topSkills.length ? <div className="job-cluster-skill-tags">{cluster.topSkills.slice(0, 6).map((skill) => <span key={skill.name}>{skill.name}<em>{skill.count}</em></span>)}</div> : <p className="job-cluster-muted">该簇技能标签覆盖不足，正式聚类应以完整JD语义为主。</p>}</section>
    <section><h4><BriefcaseBusiness size={15} />代表岗位 · 图谱最终落点</h4><ul className="job-cluster-job-list">{cluster.representativeJobs.slice(0, 4).map((job) => <li key={`${job.occId}-${job.title}`}><button type="button" className="job-landing-link" onClick={() => onJob(job)}><strong>{job.title}</strong><span>{job.company || '公司未说明'}{job.count > 1 ? ` · ${job.count}条` : ''}<ChevronRight size={13} /></span></button></li>)}</ul></section>
    <section><h4><Sparkles size={15} />能力等级</h4><DistributionBars values={cluster.levelDistribution} color={cluster.color} /></section>
    <section className="job-cluster-governance"><AlertTriangle size={16} /><p><strong>发布边界</strong>{cluster.candidateStatus}。正式发布需补充HDBSCAN稳定性、异常率、公司集中度与专家命名记录。</p></section>
  </div>
}

type PortraitDimension = keyof Pick<JobPortrait, 'responsibilities' | 'skills' | 'abilities' | 'scenarios' | 'conditions'>
type ViewMode = 'industry' | 'technology' | 'portrait'

const PORTRAIT_DIMENSIONS: Array<{
  key: PortraitDimension
  label: string
  color: string
  icon: typeof FileText
  question: string
}> = [
  { key: 'responsibilities', label: '职责', color: '#1769e0', icon: ListChecks, question: '岗位要做什么？' },
  { key: 'skills', label: '技能', color: '#0b9c93', icon: Wrench, question: '需要会什么？' },
  { key: 'abilities', label: '能力', color: '#7257c8', icon: BrainCircuit, question: '需要怎样解决问题？' },
  { key: 'scenarios', label: '场景', color: '#df8b2f', icon: Workflow, question: '在哪类业务环境中工作？' },
  { key: 'conditions', label: '条件', color: '#65758b', icon: ShieldCheck, question: '学历、经验与地区要求是什么？' },
]

function ClusterDiscoveryGraph({
  category,
  clusters,
  selected,
  onCluster,
}: {
  category: JobCategory
  clusters: JobCluster[]
  selected: JobCluster | null
  onCluster: (id: string) => void
}) {
  const graph = useMemo(() => {
    const nodes: PositionedNode[] = []
    const edges: PositionedEdge[] = []
    const boundary: PositionedNode = { id: category.id, label: category.name, kind: 'direction', x: 265, y: 335, color: category.color, count: category.jobCount }
    const discovery: PositionedNode = { id: 'class-discovery', label: '类内候选发现', kind: 'root', x: 520, y: 335, color: '#052849', count: clusters.length, unit: '候选簇' }
    const inputs: PositionedNode[] = [
      { id: 'input-title', label: '岗位名称', kind: 'dimension', x: 82, y: 148, color: '#7c91a5', count: category.jobCount, unit: '条' },
      { id: 'input-jd', label: 'JD文本', kind: 'dimension', x: 82, y: 272, color: '#7c91a5', count: category.jobCount, unit: '条' },
      { id: 'input-company', label: '公司实体', kind: 'dimension', x: 82, y: 398, color: '#7c91a5', count: category.jobCount, unit: '条' },
      { id: 'input-skill', label: '技能标签', kind: 'dimension', x: 82, y: 522, color: '#7c91a5', count: category.jobCount, unit: '条' },
    ]
    nodes.push(...inputs, boundary, discovery)
    inputs.forEach((node) => edges.push({ source: node, target: boundary }))
    edges.push({ source: boundary, target: discovery })
    clusters.forEach((cluster, index) => {
      const angle = -Math.PI / 2 + index * Math.PI * 2 / Math.max(1, clusters.length)
      const point = { x: 790 + Math.cos(angle) * 190, y: 335 + Math.sin(angle) * 245 }
      const node: PositionedNode = {
        id: cluster.id, label: cluster.name, kind: 'cluster', ...point, color: category.color,
        count: cluster.jobCount, selected: selected?.id === cluster.id,
      }
      nodes.push(node); edges.push({ source: discovery, target: node })
    })
    return { nodes, edges }
  }, [category, clusters, selected?.id])

  return <div className="job-ecosystem-canvas cluster-discovery-canvas">
    <div className="cluster-discovery-pipeline" aria-label="岗位簇正式生成流程"><span>当前候选证据</span><ChevronRight size={13} /><strong>Embedding</strong><ChevronRight size={13} /><strong>HDBSCAN</strong><ChevronRight size={13} /><strong>专家命名</strong><em>后3步待正式复算/留痕</em></div>
    <svg viewBox="0 0 1040 670" role="img" aria-label={`${category.name}职业种类内部的岗位簇发现图`}>
      <defs><filter id="cluster-discovery-shadow" x="-30%" y="-30%" width="160%" height="160%"><feDropShadow dx="0" dy="3" stdDeviation="4" floodColor="#153452" floodOpacity=".15" /></filter></defs>
      <g className="job-ecosystem-edges">{graph.edges.map((edge) => <path key={`${edge.source.id}-${edge.target.id}`} d={`M ${edge.source.x} ${edge.source.y} L ${edge.target.x} ${edge.target.y}`} />)}</g>
      {graph.nodes.map((node) => <GraphNode key={node.id} node={node} onClick={() => node.kind === 'cluster' ? onCluster(node.id) : undefined} />)}
    </svg>
    <div className="job-ecosystem-canvas-hint"><BrainCircuit size={14} />固定职业种类边界后再做类内发现，避免跨职业混聚</div>
  </div>
}

function DiscoveryDetail({ cluster, roles, onRole }: { cluster: JobCluster; roles: StandardRole[]; onRole: (id: string) => void }) {
  return <div className="job-cluster-detail discovery-detail">
    <div className="job-cluster-detail-head"><div><StatusTag tone="warning">候选簇 · 未正式发布</StatusTag><h3>{cluster.name}</h3><p>{cluster.code} · 专家建议名称</p></div><span className="job-cluster-total">{cluster.jobCount}<small>岗位</small></span></div>
    <div className="discovery-quality-grid">
      <div><span>JD覆盖</span><strong>{Math.round(cluster.jdCoverageRate * 100)}%</strong></div>
      <div><span>技能覆盖</span><strong>{Math.round(cluster.skillCoverageRate * 100)}%</strong></div>
      <div><span>岗位名称</span><strong>{cluster.uniqueTitleCount}</strong></div>
      <div><span>头部企业占比</span><strong>{Math.round(cluster.topCompanyShare * 100)}%</strong></div>
    </div>
    <section><h4><Tags size={15} />命名证据</h4><div className="job-cluster-skill-tags">{cluster.topKeywords.length ? cluster.topKeywords.map((keyword) => <span key={keyword}>{keyword}</span>) : <span>通用类候选 · 关键词覆盖不足</span>}</div></section>
    <section><h4><BriefcaseBusiness size={15} />簇内标准岗位 · 图谱业务落点</h4>{roles.length ? <ul className="job-cluster-job-list">{roles.slice(0, 12).map((role) => <li key={role.id}><button type="button" className="job-landing-link" onClick={() => onRole(role.id)}><strong>{role.name}</strong><span>{role.jobCount}条JD证据<ChevronRight size={13} /></span></button></li>)}</ul> : <p className="job-cluster-muted">当前搜索词包尚未映射到该候选簇，保留为待专家校准。</p>}</section>
    <section className="discovery-method-card"><h4><Layers3 size={15} />方法与发布闸门</h4><p><strong>当前结果</strong>{cluster.currentDiscoveryMethod}</p><p><strong>正式复算</strong>{cluster.targetDiscoveryMethod}</p><p><strong>专家校准</strong>核对关键词、代表岗位、异常率与公司集中度，签名后才作为正式岗位簇。</p></section>
  </div>
}

function JobLandingGraph({
  cluster,
  job,
  dimension,
  onDimension,
}: {
  cluster: JobCluster | null
  job: RepresentativeJob
  dimension: PortraitDimension
  onDimension: (dimension: PortraitDimension) => void
}) {
  const evidenceCount = PORTRAIT_DIMENSIONS.reduce((sum, item) => sum + job.profile[item.key].length, 0)
  const center: PositionedNode = { id: 'portrait-job', label: job.title, kind: 'root', x: 520, y: 335, color: '#112f53', count: evidenceCount, unit: '项JD证据' }
  const nodes: PositionedNode[] = [center]
  const edges: PositionedEdge[] = []
  PORTRAIT_DIMENSIONS.forEach((item, index) => {
    const angle = -Math.PI / 2 + index * Math.PI * 2 / PORTRAIT_DIMENSIONS.length
    const point = polar(520, 335, 176, angle)
    const node: PositionedNode = {
      id: item.key, label: item.label, kind: 'capability', ...point, color: item.color,
      count: job.profile[item.key].length, unit: '项能力', selected: dimension === item.key,
    }
    nodes.push(node); edges.push({ source: center, target: node })
    job.profile[item.key].slice(0, 3).forEach((value, evidenceIndex, evidenceItems) => {
      const spread = evidenceItems.length === 1 ? 0 : (evidenceIndex - (evidenceItems.length - 1) / 2) * 0.15
      const evidenceAngle = angle + spread
      const evidenceNode: PositionedNode = {
        id: `${item.key}-${evidenceIndex}`,
        label: value,
        kind: 'evidence',
        x: 520 + Math.cos(evidenceAngle) * 435,
        y: 335 + Math.sin(evidenceAngle) * 285,
        color: item.color,
        count: 1,
        unit: '条JD证据',
      }
      nodes.push(evidenceNode); edges.push({ source: node, target: evidenceNode })
    })
  })
  return <div className="job-ecosystem-canvas job-portrait-canvas job-landing-canvas">
    <svg viewBox="0 0 1040 670" role="img" aria-label={`${job.title}岗位技能与画像证据图`}>
      <defs><filter id="portrait-node-shadow" x="-30%" y="-30%" width="160%" height="160%"><feDropShadow dx="0" dy="3" stdDeviation="4" floodColor="#153452" floodOpacity=".15" /></filter></defs>
      <g className="job-ecosystem-edges">{edges.map((edge) => <path key={`${edge.source.id}-${edge.target.id}`} d={`M ${edge.source.x} ${edge.source.y} L ${edge.target.x} ${edge.target.y}`} />)}</g>
      {nodes.map((node) => <GraphNode key={node.id} node={node} onClick={() => PORTRAIT_DIMENSIONS.some((item) => item.key === node.id) ? onDimension(node.id as PortraitDimension) : undefined} />)}
    </svg>
    <div className="job-ecosystem-canvas-hint"><FileText size={14} />中心是具体岗位；内圈是能力类别；外圈是该岗位的JD技能与证据</div>
  </div>
}

function PortraitDetail({ job, cluster, dimension }: { job: RepresentativeJob; cluster: JobCluster | null; dimension: PortraitDimension }) {
  const config = PORTRAIT_DIMENSIONS.find((item) => item.key === dimension) ?? PORTRAIT_DIMENSIONS[0]
  const Icon = config.icon
  const values = job.profile[dimension]
  return <div className="job-cluster-detail portrait-detail">
    <div className="job-cluster-detail-head"><div><StatusTag tone="success">具体岗位落点</StatusTag><h3>{job.title}</h3><p>{job.company || '公司未说明'} · {cluster?.name || job.clusterName || '岗位簇待定位'}</p></div><span className="job-cluster-total">{values.length}<small>{config.label}证据</small></span></div>
    <section className="portrait-question"><Icon size={18} /><div><strong>{config.label}</strong><p>{config.question}</p></div></section>
    <section><h4><CheckCircle2 size={15} />结构化结果</h4>{values.length ? <ul className="portrait-evidence-list">{values.map((value) => <li key={value}>{value}</li>)}</ul> : <p className="job-cluster-muted">当前JD未提取到该维度，保留为空，不推测补值。</p>}</section>
    <section><h4><FileText size={15} />原始JD证据</h4>{job.profile.jdEvidence.length ? <blockquote>{job.profile.jdEvidence.map((value) => <p key={value}>{value}</p>)}</blockquote> : <p className="job-cluster-muted">该岗位暂无可展示的JD原文。</p>}</section>
    <section className="portrait-jd-snippet"><h4>JD摘要</h4><p>{job.jdSnippet || '暂无JD摘要'}</p>{job.url ? <a href={job.url} target="_blank" rel="noreferrer">查看岗位来源</a> : null}</section>
  </div>
}

export function JobEcosystemPage({ fixedView, onNavigate, focusCandidateCode }: { fixedView?: ViewMode; onNavigate?: (page: PageId, param?: string | null) => void; focusCandidateCode?: string | null }) {
  const routeParams = jobGraphRouteParams()
  const routeView = routeParams.get('view')
  const routeRoleId = routeParams.get('role')
  const routeJobId = routeParams.get('job')
  const routeDimension = routeParams.get('dimension') as PortraitDimension | null
  const initialView: ViewMode = routeView === 'technology' ? 'technology' : routeView === 'portrait' || routeView === 'ecosystem' || routeView === 'discovery' ? 'portrait' : 'industry'
  const [data, setData] = useState<JobEcosystemGraph | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [selectedView, setSelectedView] = useState<ViewMode>(initialView)
  const viewMode = fixedView ?? selectedView
  const [directionId, setDirectionId] = useState<string | null>(null)
  const [categoryId, setCategoryId] = useState<string | null>(null)
  const [clusterId, setClusterId] = useState<string | null>(null)
  const [standardRoleId, setStandardRoleId] = useState<string | null>(routeRoleId)
  const [selectedProfilePoint, setSelectedProfilePoint] = useState<string | null>(null)
  const [evidenceJobId, setEvidenceJobId] = useState<string | null>(routeJobId)
  const [clusterJobPage, setClusterJobPage] = useState(0)
  const [clusterJobQuery, setClusterJobQuery] = useState('')
  const [portraitDimension, setPortraitDimension] = useState<PortraitDimension>(routeDimension === 'skills' || routeDimension === 'abilities' || routeDimension === 'scenarios' || routeDimension === 'conditions' ? routeDimension : 'responsibilities')
  const [enterpriseDimension, setEnterpriseDimension] = useState<EnterpriseDimensionKey>('industryStage')
  const [enterpriseValue, setEnterpriseValue] = useState<string | null>(null)
  const [enterpriseId, setEnterpriseId] = useState<string | null>(null)
  const [industryReset, setIndustryReset] = useState(0)
  const [technologyId, setTechnologyId] = useState<string | null>(null)
  const [technologyQuery, setTechnologyQuery] = useState('')
  const [technologyTreeExpanded, setTechnologyTreeExpanded] = useState<Set<string>>(new Set())
  const [query, setQuery] = useState('')
  const [portraitTreeExpanded, setPortraitTreeExpanded] = useState<Set<string>>(new Set())
  const togglePortraitTree = (id: string) => setPortraitTreeExpanded((prev) => {
    const next = new Set(prev)
    if (next.has(id)) next.delete(id); else next.add(id)
    return next
  })
  const expandPortraitTreeTo = (ids: (string | null | undefined)[]) => {
    const valid = ids.filter((x): x is string => Boolean(x))
    if (!valid.length) return
    setPortraitTreeExpanded((prev) => {
      const next = new Set(prev)
      valid.forEach((id) => next.add(id))
      return next
    })
  }
  const toggleTechnologyTree = (id: string) => setTechnologyTreeExpanded((prev) => {
    const next = new Set(prev)
    if (next.has(id)) next.delete(id); else next.add(id)
    return next
  })

  // 顶部筛选栏 / 左树节点选中 → 自动把该路径上的层级全部展开
  useEffect(() => { expandPortraitTreeTo([directionId, categoryId, clusterId]) }, [directionId, categoryId, clusterId])
  useEffect(() => {
    if (!standardRoleId) return
    const role = data?.standardRoles.find((r) => r.id === standardRoleId)
    if (role) expandPortraitTreeTo([role.directionId, role.categoryId, role.clusterId])
  }, [standardRoleId, data])
  useEffect(() => {
    if (!data || !technologyId) return
    const selected = data.technologyNodes.find((node) => node.id === technologyId) ?? null
    const path = technologyPath(data.technologyNodes, selected)
    setTechnologyTreeExpanded((prev) => {
      const next = new Set(prev)
      path.forEach((node) => next.add(node.id))
      return next
    })
  }, [data, technologyId])

  useEffect(() => {
    const controller = new AbortController()
    // 推演派生岗位在装配阶段就并进 standardRoles，下游的分层树、岗位列表与五维圆图
    // 因此无需各自判断来源；它们的 jobCount / jdCount 都是 0，不会影响任何计数口径。
    // 画像内容以后端为准、静态文件为兜底：画像由 LLM 生成后写在标准 JD 里，重跑一次
    // 就该在图上更新，不应再要求手工改前端文件。而落位（方向/种类/簇）仍取自静态文件——
    // 那是 Excel 图谱的命名空间，后端的聚类不是同一套 id，换不过来。
    Promise.all([
      loadJobEcosystemGraph(controller.signal),
      loadDiscoveryRolePortraits(controller.signal),
      discoveryApi.rolePortraits(controller.signal).catch(() => ({ total: 0, items: [] })),
    ])
      .then(([graph, inferredRoles, served]) => {
        const byCandidate = new Map(served.items.map((item) => [item.candidate_code, item.portrait]))
        const merged = inferredRoles.map((role) => {
          const portrait = role.candidateCode ? byCandidate.get(role.candidateCode) : undefined
          if (!portrait) return role
          return {
            ...role,
            profileMethod: `${portrait.provenance.generated_by} · ${portrait.provenance.prompt_version} · 无 JD 证据支撑`,
            standardProfile: {
              responsibilities: portrait.responsibilities.map(toProfilePoint),
              skills: portrait.skills.map(toProfilePoint),
              abilities: portrait.abilities.map(toProfilePoint),
              scenarios: portrait.scenarios.map(toProfilePoint),
              conditions: portrait.conditions.map(toProfilePoint),
            },
          }
        })
        setData(merged.length ? { ...graph, standardRoles: [...graph.standardRoles, ...merged] } : graph)
      })
      .catch((reason: Error) => { if (reason.name !== 'AbortError') setError(reason.message) })
    return () => controller.abort()
  }, [])

  useEffect(() => {
    if (!data || !routeJobId || standardRoleId) return
    const nextJob = data.jobs.find((job) => job.id === routeJobId)
    if (!nextJob) return
    setStandardRoleId(nextJob.standardRoleId)
    setDirectionId(nextJob.directionId)
    setCategoryId(nextJob.categoryId)
    setClusterId(nextJob.clusterId)
    setEvidenceJobId(nextJob.id)
  }, [data, routeJobId, standardRoleId])

  const direction = data?.directions.find((item) => item.id === directionId) ?? null
  const category = data?.categories.find((item) => item.id === categoryId) ?? null
  const cluster = data?.clusters.find((item) => item.id === clusterId) ?? null
  const standardRole = data?.standardRoles.find((item) => item.id === standardRoleId) ?? null
  const enterprise = data?.enterprises.find((item) => item.id === enterpriseId) ?? null
  const selectedTechnology = data?.technologyNodes.find((item) => item.id === technologyId) ?? null
  const clusterJobs = useMemo(() => data && clusterId ? data.jobs.filter((job) => job.clusterId === clusterId) : [], [clusterId, data])
  const filteredClusterJobs = useMemo(() => {
    const value = clusterJobQuery.trim().toLowerCase()
    if (!value) return clusterJobs
    return clusterJobs.filter((job) => [job.title, job.company, ...job.skills, ...job.profile.skills].some((text) => text.toLowerCase().includes(value)))
  }, [clusterJobQuery, clusterJobs])
  const matches = useMemo(() => {
    if (!data || !query.trim()) return []
    const value = query.trim().toLowerCase()
    const roleMatches = data.standardRoles
      .filter((item) => [item.name, item.clusterName, item.categoryName, item.directionName, ...item.seedVariants, ...item.observedVariants.map((variant) => variant.name)].some((text) => text.toLowerCase().includes(value)))
      .map((item) => ({ ...item, searchKind: 'standardRole' as const }))
    const clusterMatches = data.clusters
      .filter((item) => [item.name, item.categoryName, item.directionName, ...item.topKeywords, ...item.topSkills.map((skill) => skill.name)].some((text) => text.toLowerCase().includes(value)))
      .map((item) => ({ ...item, searchKind: 'cluster' as const }))
    return [...roleMatches, ...clusterMatches].slice(0, 8)
  }, [data, query])
  const technologyJobs = useMemo(() => {
    if (!data || !technologyId) return []
    const ids = technologyDescendantIds(data.technologyNodes, technologyId)
    return data.jobs.filter((job) => job.technologyTermIds.some((id) => ids.has(id)))
  }, [data, technologyId])
  // 新岗位发现叠加：默认关闭，打开时才去取。候选是未入库的提议，与图谱里
  // 已观测的标准岗位不同级，混在一起看会把"提议"读成"既有事实"。
  const [showDiscovery, setShowDiscovery] = useState(false)
  const [discovery, setDiscovery] = useState<DiscoveryOverlay | null>(null)
  const [discoveryError, setDiscoveryError] = useState('')
  /** 清单点选后要在叠加面板里定位到的候选。 */
  const [highlightedCandidate, setHighlightedCandidate] = useState<string | null>(null)
  useEffect(() => {
    // 画像视图的分层导航下常驻一份新岗位发现清单，因此进入该视图就要取数，
    // 不能只在勾选叠加时才取——否则那份清单会一直停在「正在加载推演结果…」。
    if ((!showDiscovery && viewMode !== 'portrait') || discovery) return
    const controller = new AbortController()
    fetchDiscoveryOverlay(controller.signal)
      .then(setDiscovery)
      .catch((reason: Error) => { if (reason.name !== 'AbortError') setDiscoveryError(reason.message) })
    return () => controller.abort()
  }, [showDiscovery, discovery, viewMode])

  /** 画像视图：按当前方向 / 岗位簇筛出候选。 */
  const portraitCandidates = useMemo<DiscoveryCandidate[]>(() => {
    if (!data || !discovery || !showDiscovery) return []
    const placed = discovery.candidates.filter((item) => item.portraitClusterName)
    const clusterName = data.clusters.find((item) => item.id === clusterId)?.name
    if (clusterName) return placed.filter((item) => item.portraitClusterName === clusterName)
    const directionName = data.directions.find((item) => item.id === directionId)?.name
    if (directionName) return placed.filter((item) => item.portraitDirectionName === directionName)
    return placed
  }, [data, discovery, showDiscovery, clusterId, directionId])

  /**
   * 分层导航下方那份新岗位发现清单。
   *
   * **不跟随「叠加新岗位发现」开关。** 那个开关控制的是图上要不要画候选，而这里是
   * 一个跳转入口——开关关着时列表也该在，否则用户得先想起去勾一个图层开关才能找到
   * 新岗位。选中方向或岗位簇时按同一套落位规则收窄，未选则给全量。
   *
   * 排序把外部证据类（研究侧 / 产业里程碑）放前面：它们才是「招聘市场上还没有」的
   * 提议，也是这个入口要让人一眼看到的东西；库内四类同分时按证据分降序。
   */
  const discoveryNavItems = useMemo<DiscoveryCandidate[]>(() => {
    if (!data || !discovery) return []
    const clusterName = data.clusters.find((item) => item.id === clusterId)?.name
    const directionName = data.directions.find((item) => item.id === directionId)?.name
    const scoped = clusterName
      ? discovery.candidates.filter((item) => item.portraitClusterName === clusterName)
      : directionName
        ? discovery.candidates.filter((item) => item.portraitDirectionName === directionName)
        : discovery.candidates
    const externalFirst = (item: DiscoveryCandidate) =>
      item.classificationCode === 'upstream_signal' || item.classificationCode === 'milestone_signal' ? 0 : 1
    return [...scoped].sort((a, b) => externalFirst(a) - externalFirst(b) || b.score - a.score)
  }, [data, discovery, clusterId, directionId])

  /** 当前技术节点（含其所有下级）名下的候选。 */
  const technologyCandidates = useMemo<DiscoveryCandidate[]>(() => {
    if (!data || !discovery || !showDiscovery) return []
    if (!technologyId) return discovery.candidates
    const ids = technologyDescendantIds(data.technologyNodes, technologyId)
    return discovery.candidates.filter((item) => item.technologyNodeIds.some((id) => ids.has(id)))
  }, [data, discovery, showDiscovery, technologyId])

  const technologyMatches = useMemo(() => {
    if (!data || !technologyQuery.trim()) return []
    const value = technologyQuery.trim().toLowerCase()
    return data.technologyNodes
      .filter((item) => item.name.toLowerCase().includes(value) || item.code.toLowerCase().includes(value))
      .sort((a, b) => b.jobCount - a.jobCount || a.level.localeCompare(b.level))
      .slice(0, 10)
  }, [data, technologyQuery])

  const selectDirection = (id: string | null) => { setDirectionId(id); setCategoryId(null); setClusterId(null); setStandardRoleId(null); setSelectedProfilePoint(null); setEvidenceJobId(null); setClusterJobPage(0); setClusterJobQuery('') }
  const selectCategory = (id: string | null) => {
    const next = data?.categories.find((item) => item.id === id)
    if (next) setDirectionId(next.directionId)
    setCategoryId(id); setClusterId(null); setStandardRoleId(null); setSelectedProfilePoint(null); setEvidenceJobId(null); setClusterJobPage(0); setClusterJobQuery('')
  }
  const selectCluster = (id: string | null) => {
    const next = data?.clusters.find((item) => item.id === id)
    if (next) { setDirectionId(next.directionId); setCategoryId(next.categoryId) }
    setClusterId(id); setStandardRoleId(null); setSelectedProfilePoint(null); setEvidenceJobId(null); setClusterJobPage(0); setClusterJobQuery('')
  }
  /**
   * 从分层导航下的清单点进某条候选：留在本图定位，而不是跳去别的页面。
   *
   * 三步——打开叠加（否则候选在图上和面板里都不出现）、按落位名把图钻到对应
   * 岗位簇或方向、把该条标为高亮供叠加面板滚动定位。未落位的候选（招聘市场上
   * 没有同时命中其全部技术点的 JD）没有对应簇，此时清空层级筛选回到全量，
   * 由叠加面板说明它为什么不在图上，而不是静默什么都不发生。
   */
  const locateCandidateInPortrait = (item: DiscoveryCandidate) => {
    setShowDiscovery(true)
    setHighlightedCandidate(item.candidateCode)
    const cluster = item.portraitClusterName
      ? data?.clusters.find((entry) => entry.name === item.portraitClusterName)
      : undefined
    if (cluster) { selectCluster(cluster.id); return }
    const direction = item.portraitDirectionName
      ? data?.directions.find((entry) => entry.name === item.portraitDirectionName)
      : undefined
    if (direction) { selectDirection(direction.id); return }
    selectDirection(null)
  }

  /*
    从候选数据卡带着候选编码跳进来时，直接把图落到这条候选上。

    首选按 candidateCode 找到已并进 standardRoles 的推演岗位并选中它——那样右侧
    直接就是它的五维圆图，正是按钮承诺的「查看画像」。找不到（画像还没并进来，
    或该候选本就没落位）才退回 locateCandidateInPortrait 的层级定位。

    只跑一次：跑完清掉 param，否则使用者在页内再点别的岗位会被这里拽回来。
  */
  const focusedCandidateRef = useRef<string | null>(null)
  useEffect(() => {
    if (!focusCandidateCode || !data || !discovery) return
    if (focusedCandidateRef.current === focusCandidateCode) return
    focusedCandidateRef.current = focusCandidateCode
    setShowDiscovery(true)
    setHighlightedCandidate(focusCandidateCode)
    const role = data.standardRoles.find((item) => item.candidateCode === focusCandidateCode)
    if (role) { selectStandardRole(role.id); return }
    const item = discovery.candidates.find((entry) => entry.candidateCode === focusCandidateCode)
    if (item) locateCandidateInPortrait(item)
  }, [focusCandidateCode, data, discovery])

  const selectStandardRole = (id: string | null) => {
    const next = data?.standardRoles.find((item) => item.id === id)
    if (next) {
      setDirectionId(next.directionId)
      setCategoryId(next.categoryId)
      setClusterId(next.clusterId)
    }
    setStandardRoleId(id); setSelectedProfilePoint(null); setEvidenceJobId(null); setPortraitDimension('responsibilities')
  }
  const selectTechnology = (id: string | null) => {
    setTechnologyId(id); setEvidenceJobId(null)
  }
  const openJobEvidence = (job: JobRecord) => {
    if (job.standardRoleId) selectStandardRole(job.standardRoleId)
    setEvidenceJobId(job.id)
  }
  const openJobPortrait = (job: JobRecord) => {
    window.location.hash = `/job-portrait-graph?job=${encodeURIComponent(job.id)}`
  }
  const openRoleProfile = (role: StandardRole) => {
    if (fixedView && fixedView !== 'portrait') {
      window.location.hash = `/job-portrait-graph?role=${encodeURIComponent(role.id)}`
      return
    }
    selectStandardRole(role.id)
    if (!fixedView) {
      setSelectedView('portrait')
      window.history.replaceState(null, '', `#/job-graph?view=portrait&role=${encodeURIComponent(role.id)}`)
    }
  }
  const reset = () => {
    setIndustryReset(value => value + 1)
    setDirectionId(null); setCategoryId(null); setClusterId(null); setQuery('')
    setStandardRoleId(null); setSelectedProfilePoint(null); setEvidenceJobId(null); setPortraitDimension('responsibilities'); setClusterJobPage(0); setClusterJobQuery('')
    setEnterpriseValue(null); setEnterpriseId(null)
    setTechnologyId(null); setTechnologyQuery(''); setTechnologyTreeExpanded(new Set())
  }
  const switchView = (mode: ViewMode) => {
    setSelectedView(mode); reset()
    window.history.replaceState(null, '', `#/job-graph?view=${mode}`)
  }

  if (error) return <div className="empty-state"><strong>岗位图谱加载失败</strong><span>{error}</span></div>
  if (!data) return <div className="empty-state"><strong>正在生成岗位生态视图</strong><span>读取6方向、17职业种类与候选岗位簇证据。</span></div>

  const dimensionConfig = ENTERPRISE_DIMENSIONS.find((item) => item.key === enterpriseDimension) ?? ENTERPRISE_DIMENSIONS[0]
  const enterpriseGroup = enterpriseValue
    ? data.enterprises.filter((item) => item[enterpriseDimension] === enterpriseValue).sort((a, b) => b.jobCount - a.jobCount)
    : []
  // 跟随层级的作用域：方向 → 种类 → 簇 → 标准岗位，逐级收缩
  const portraitScopedRoles = standardRoleId
    ? data.standardRoles.filter((r) => r.id === standardRoleId)
    : clusterId
      ? data.standardRoles.filter((r) => r.clusterId === clusterId)
      : categoryId
        ? data.standardRoles.filter((r) => r.categoryId === categoryId)
        : directionId
          ? data.standardRoles.filter((r) => r.directionId === directionId)
          : data.standardRoles
  const portraitScopedClusters = clusterId
    ? data.clusters.filter((c) => c.id === clusterId)
    : categoryId
      ? data.clusters.filter((c) => c.categoryId === categoryId)
      : directionId
        ? data.clusters.filter((c) => c.directionId === directionId)
        : data.clusters
  const portraitScopedCategories = categoryId
    ? data.categories.filter((c) => c.id === categoryId)
    : directionId
      ? data.categories.filter((c) => c.directionId === directionId)
      : data.categories
  const portraitScopedJobCount = directionId
    ? (categoryId
        ? (clusterId ? portraitScopedRoles.reduce((s, r) => s + r.jobCount, 0) : portraitScopedClusters.reduce((s, c) => s + c.jobCount, 0))
        : data.directions.find((d) => d.id === directionId)?.jobCount ?? 0)
    : data.metadata.jobCount
  // 不管选到哪一层（方向/种类/簇/标准岗位），都取该层级下 JD 支撑最多、且有完整五维画像数据的标准岗位
  // 关键兜底：没有 standardProfile 或画像维度数组残缺的角色，永远不会被选作 displayRole → 防止渲染抛错整页空白
  const hasValidProfile = (role: StandardRole) => {
    if (!role || !role.standardProfile) return false
    return PORTRAIT_DIMENSIONS.every((dim) => Array.isArray(role.standardProfile[dim.key]) && role.standardProfile[dim.key].length > 0)
  }
  const scopedRolesSorted = [...portraitScopedRoles].sort((a, b) => b.jobCount - a.jobCount)
  const scopedRolesWithProfile = scopedRolesSorted.filter(hasValidProfile)
  const explicitlySelectedRole = standardRoleId ? data.standardRoles.find((r) => r.id === standardRoleId) ?? null : null
  const displayRole = explicitlySelectedRole
    ? (hasValidProfile(explicitlySelectedRole) ? explicitlySelectedRole : scopedRolesWithProfile[0] ?? explicitlySelectedRole)
    : (scopedRolesWithProfile[0] ?? scopedRolesSorted[0] ?? null)
  const canRenderGraph = displayRole && hasValidProfile(displayRole)
  const activeRole = canRenderGraph ? displayRole : null
  const selectedClusterRole = standardRoleId ? data.standardRoles.find((r) => r.id === standardRoleId) ?? null : null
  const clusterFocusedRoles = cluster ? data.standardRoles.filter((r) => r.clusterId === cluster.id).sort((a, b) => b.jobCount - a.jobCount) : []
  const roleJobs = activeRole ? data.jobs.filter((job) => job.standardRoleId === activeRole.id) : []
  const selectedEvidenceJob = evidenceJobId ? data.jobs.find((job) => job.id === evidenceJobId) ?? null : null
  const selectedJob = selectedEvidenceJob
  const currentProfilePoint = activeRole?.standardProfile?.[portraitDimension]?.find((point) => point.name === selectedProfilePoint) ?? null
  const profileEvidenceJobs = currentProfilePoint
    ? roleJobs.filter((job) => currentProfilePoint.evidenceOccIds.includes(job.occId))
    : roleJobs
  const portraitMiddleGraph = standardRoleId
    ? (activeRole
        ? <StandardRoleCapabilityGraph role={activeRole} dimension={portraitDimension} selectedPoint={selectedProfilePoint} onDimension={(next) => { setPortraitDimension(next); setSelectedProfilePoint(null); setEvidenceJobId(null) }} onPoint={(next, point) => { setPortraitDimension(next); setSelectedProfilePoint(point.name); setEvidenceJobId(null) }} />
        : cluster
          ? <StandardRoleGraph cluster={cluster} roles={clusterFocusedRoles} selected={selectedClusterRole && selectedClusterRole.clusterId === cluster.id ? selectedClusterRole : null} onRole={selectStandardRole} />
          : <div className="empty-state"><UserRound size={34} /><strong>该标准岗位暂未形成完整画像</strong><span>这个标准岗位已有名称和证据，但五维画像还没入库完成。可以先看右侧的岗位证据，再切换到其他已有画像的岗位。</span></div>)
    : cluster
      ? <StandardRoleGraph cluster={cluster} roles={clusterFocusedRoles} selected={null} onRole={selectStandardRole} />
      : <JobHierarchyGraph data={data} direction={direction} category={category} cluster={cluster} onDirection={selectDirection} onCategory={selectCategory} onCluster={selectCluster} />
  const enterpriseJobs = enterprise
    ? data.jobs.filter((job) => job.enterpriseName === enterprise.name || job.company === enterprise.name)
    : []

  const methodChain = viewMode === 'industry'
    ? [`${data.enterpriseAnalysis.enterpriseLibraryRecordCount}条企业库`, '产业链/细分领域/融资/地区/城市', '企业', '标准岗位', '具体岗位/JD']
    : viewMode === 'technology'
      ? ['技术主数据', '7个L1域', '43个L2类', '229个L3点', '1,872个L4词', '标准岗位/具体JD']
      : ['6职业方向', '17职业种类', `${data.metadata.clusterCount}候选岗位簇`, `${data.standardRoleAudit.seedRoleCount}标准岗位`, '多JD五维画像', '演化/匹配解释']

  const industryContent = viewMode === 'industry' ? <IndustryJobGraph key={industryReset} graph={data} onRole={openRoleProfile} onOpenPortrait={openJobPortrait} /> : null

  return <div className="page-stack job-ecosystem-page">
    <div className="page-intro"><div><h2>{viewMode === 'industry' ? '产业—岗位图谱' : viewMode === 'technology' ? '技术—岗位图谱' : '岗位画像图谱'}</h2><p>{viewMode === 'industry' ? '以完整企业库展开产业全景：产业链层级 → 产业类别 → 企业 → 标准岗位 → 具体岗位/JD。' : viewMode === 'technology' ? '沿技术主数据逐层下钻：L1技术域 → L2技术类 → L3技术点 → L4技术词 → 标准岗位 → 具体JD。' : '从职业方向逐层定位到具体岗位：职业方向 → 职业种类 → 岗位簇 → 标准岗位 → 五维画像与JD证据。'}</p></div><div className="job-ecosystem-intro-actions"><StatusTag tone={viewMode === 'industry' ? 'info' : 'warning'}>{viewMode === 'industry' ? '企业全景 v0.6' : '证据候选版 v0.5'}</StatusTag><button className="secondary-button" onClick={reset}><RotateCcw size={15} />重置当前图</button></div></div>
    {!fixedView ? <div className="job-three-graph-switch" aria-label="岗位三图谱切换">
      <button className={viewMode === 'industry' ? 'active' : ''} onClick={() => switchView('industry')}><span>01</span><Building2 size={17} /><div><strong>产业—岗位图谱</strong><small>企业库 → 产业类别 → 企业 → 岗位/招聘</small></div></button>
      <button className={viewMode === 'technology' ? 'active' : ''} onClick={() => switchView('technology')}><span>02</span><Wrench size={17} /><div><strong>技术—岗位图谱</strong><small>L1–L4技术词 → 标准岗位 → JD</small></div></button>
      <button className={viewMode === 'portrait' ? 'active' : ''} onClick={() => switchView('portrait')}><span>03</span><UserRound size={17} /><div><strong>岗位画像与演化图谱</strong><small>6→17→岗位簇→标准岗位→五维画像</small></div></button>
    </div> : null}
    {industryContent || <><MetricStrip items={[
      { label: '岗位事实', value: data.metadata.jobCount.toLocaleString(), delta: 'v4统一底座' },
      { label: '企业映射覆盖', value: `${Math.round(data.enterpriseAnalysis.matchedJobRate * 1000) / 10}%`, delta: `${data.enterpriseAnalysis.pendingJobCount}条待补` },
      { label: '技术映射覆盖', value: `${(data.technologyAudit.mappedJobRate * 100).toFixed(1)}%`, delta: `${data.technologyAudit.pendingJobCount}条待补` },
      // rolesWithEvidence 在图谱产物里根本不存在，此处一直显示成「undefined个已有JD证据」。
      // 改用产物里确有的归属量：4,655 条 JD 已落到标准岗位上，这也正是这一格该说明的事。
      { label: '标准岗位', value: String(data.standardRoleAudit.seedRoleCount), delta: `${data.standardRoleAudit.mappedJobCount.toLocaleString()}条JD已归属` },
    ]} />
    {viewMode === 'portrait' ? <div className="portrait-overview-strip" aria-label="岗位分层总览">
      <div className="portrait-overview-item"><i style={{background: data.directions[0]?.color ?? '#1769e0'}} /><strong>{data.directions.length}</strong><span>职业方向</span></div>
      <ChevronRight size={18} className="portrait-overview-chevron" />
      <div className="portrait-overview-item"><i style={{background: '#0e8f88'}} /><strong>{data.categories.length}</strong><span>职业种类</span></div>
      <ChevronRight size={18} className="portrait-overview-chevron" />
      <div className="portrait-overview-item"><i style={{background: '#df645e'}} /><strong>{data.clusters.length}</strong><span>岗位簇</span></div>
      <ChevronRight size={18} className="portrait-overview-chevron" />
      <div className="portrait-overview-item"><i style={{background: '#7257c8'}} /><strong>{data.standardRoles.length}</strong><span>标准岗位</span></div>
      <ChevronRight size={18} className="portrait-overview-chevron" />
      <div className="portrait-overview-item"><i style={{background: '#65758b'}} /><strong>{data.jobs.length.toLocaleString()}</strong><span>具体岗位JD</span></div>
      <p className="portrait-overview-note">{data.metadata.releaseNote}</p>
    </div> : <div className="job-ecosystem-method"><div><strong>本图主链</strong>{methodChain.map((item, index) => <span key={item} className="job-method-step">{index ? <ChevronRight size={14} /> : null}<b>{item}</b></span>)}</div><p>{viewMode === 'industry' ? '企业属性只认企业库主数据，岗位需求只认v4岗位事实；两者通过治理后的企业实体关联。' : data.technologyAudit.mappingRule}</p></div>}
    <div className="job-ecosystem-toolbar">
      {viewMode === 'industry' ? <><div className="job-ecosystem-breadcrumb"><button onClick={reset}>企业库</button><ChevronRight size={14} /><span>{dimensionConfig.label}</span>{enterpriseValue ? <><ChevronRight size={14} /><button onClick={() => { setEnterpriseValue(enterpriseValue); setEnterpriseId(null) }}>{enterpriseValue}</button></> : null}{enterprise ? <><ChevronRight size={14} /><span>{enterprise.name}</span></> : null}</div><div className="enterprise-dimension-tabs">{ENTERPRISE_DIMENSIONS.map((item) => { const Icon = item.icon; return <button key={item.key} className={enterpriseDimension === item.key ? 'active' : ''} onClick={() => { setEnterpriseDimension(item.key); setEnterpriseValue(null); setEnterpriseId(null); setEvidenceJobId(null) }}><Icon size={14} />{item.label}</button> })}</div></> : viewMode === 'technology' ? <><div className="job-ecosystem-breadcrumb"><button onClick={() => selectTechnology(null)}>技术主数据</button>{technologyPath(data.technologyNodes, selectedTechnology).map((item) => <span key={item.id} className="technology-crumb"><ChevronRight size={14} /><button onClick={() => selectTechnology(item.id)}>{item.name}</button></span>)}</div><div className="job-ecosystem-search"><Search size={15} /><input value={technologyQuery} onChange={(event) => setTechnologyQuery(event.target.value)} placeholder="搜索L1–L4技术词" aria-label="搜索L1到L4技术词" />{technologyQuery ? <button onClick={() => setTechnologyQuery('')}>清空</button> : null}</div><label className="discovery-overlay-toggle"><input type="checkbox" checked={showDiscovery} onChange={(event) => setShowDiscovery(event.target.checked)} />叠加新岗位发现{showDiscovery && discovery ? <em>{technologyCandidates.length}</em> : null}</label></> : <div className="graph-scope-selectors portrait-toolbar-tight"><label>方向<select value={direction?.id ?? ''} onChange={(e) => selectDirection(e.target.value || null)}><option value="">全部{data.directions.reduce((s, d) => s + d.jobCount, 0).toLocaleString()}</option>{data.directions.map((item) => <option key={item.id} value={item.id}>{item.name} · {item.jobCount}</option>)}</select></label><label>种类<select value={category?.id ?? ''} onChange={(e) => selectCategory(e.target.value || null)}><option value="">全部{(directionId ? data.categories.filter(c => c.directionId === directionId) : data.categories).reduce((s, c) => s + c.jobCount, 0).toLocaleString()}</option>{(directionId ? data.categories.filter(c => c.directionId === directionId) : data.categories).map((item) => <option key={item.id} value={item.id}>{item.name} · {item.jobCount}</option>)}</select></label><label>岗位簇<select value={cluster?.id ?? ''} onChange={(e) => selectCluster(e.target.value || null)}><option value="">全部{data.clusters.filter(c => (!directionId || c.directionId === directionId) && (!categoryId || c.categoryId === categoryId)).reduce((s, c) => s + c.jobCount, 0).toLocaleString()}</option>{data.clusters.filter(c => (!directionId || c.directionId === directionId) && (!categoryId || c.categoryId === categoryId)).map((item) => <option key={item.id} value={item.id}>{item.name} · {item.jobCount}</option>)}</select></label><label>标准岗位<select value={standardRole?.id ?? ''} onChange={(e) => selectStandardRole(e.target.value || null)}><option value="">全部{data.standardRoles.filter(r => (!directionId || r.directionId === directionId) && (!categoryId || r.categoryId === categoryId) && (!clusterId || r.clusterId === clusterId)).reduce((s, r) => s + r.jobCount, 0).toLocaleString()}</option>{data.standardRoles.filter(r => (!directionId || r.directionId === directionId) && (!categoryId || r.categoryId === categoryId) && (!clusterId || r.clusterId === clusterId)).map((item) => <option key={item.id} value={item.id}>{item.name} · {item.jobCount}条JD</option>)}</select></label><label className="discovery-overlay-toggle"><input type="checkbox" checked={showDiscovery} onChange={(event) => setShowDiscovery(event.target.checked)} />叠加新岗位发现{showDiscovery && discovery ? <em>{portraitCandidates.length}</em> : null}</label></div>}
    </div>
    {viewMode === 'technology' && technologyQuery ? <Panel title={`技术词搜索结果 · ${technologyMatches.length}`} subtitle="只搜索技术主数据节点，点击后按L1–L4层级定位"><div className="job-ecosystem-search-results">{technologyMatches.length ? technologyMatches.map((item) => <button key={item.id} onClick={() => { selectTechnology(item.id); setTechnologyQuery('') }}><i style={{ background: item.level === 'L4' ? '#6b4fc2' : '#0e8f88' }} /><div><strong>{item.name}</strong><span>{item.code || item.level} · {item.level}</span></div><em>{item.jobCount} 岗位</em><ChevronRight size={15} /></button>) : <div className="empty-state"><span>没有找到匹配的L1–L4技术节点。</span></div>}</div></Panel> : null}
    {viewMode === 'industry' ? <div className="job-ecosystem-workspace industry-workspace">
        <Panel title={enterprise ? `${enterprise.name} · 企业信息与岗位` : enterpriseValue ? `${enterpriseValue} · 重点企业` : `${dimensionConfig.label} · 企业岗位分布`} subtitle={enterprise ? '企业信息直接展示在图下方；点击岗位右侧查看JD' : enterpriseValue ? '图中展示该维度岗位量靠前的企业' : '点击属性值继续下钻'} className="job-ecosystem-graph-panel industry-main-panel">
          {enterpriseValue ? <button className="job-ecosystem-back" onClick={() => enterprise ? setEnterpriseId(null) : setEnterpriseValue(null)}><ArrowLeft size={14} />返回上一层</button> : null}
          <EnterpriseDimensionGraph data={data} dimension={enterpriseDimension} selectedValue={enterpriseValue} selectedEnterprise={enterprise} onValue={(value) => { setEnterpriseValue(value); setEnterpriseId(null); setEvidenceJobId(null) }} onEnterprise={(id) => { setEnterpriseId(id); setEvidenceJobId(null) }} onRole={(id) => { const role = data.standardRoles.find((item) => item.id === id); if (role) openRoleProfile(role) }} />
          {enterprise ? <EnterpriseDetail enterprise={enterprise} jobs={enterpriseJobs} onJob={openJobEvidence} selectedJobId={evidenceJobId} /> : enterpriseValue ? <div className="job-direction-detail enterprise-group-detail"><i style={{ background: dimensionConfig.color }} /><h3>{enterpriseValue}</h3><p>共{enterpriseGroup.reduce((sum, item) => sum + item.jobCount, 0).toLocaleString()}个已关联岗位，覆盖{enterpriseGroup.length}家企业；图中展示岗位量靠前的18家。</p><div>{enterpriseGroup.slice(0, 10).map((item) => <button key={item.id} onClick={() => { setEnterpriseId(item.id); setEvidenceJobId(null) }}><span>{item.name}</span><strong>{item.jobCount}</strong><em>{item.headquartersCity || '城市待补'}</em><ChevronRight size={14} /></button>)}</div></div> : <div className="job-ecosystem-guide enterprise-guide"><div><span>01</span><p><strong>企业库主数据</strong>{data.enterpriseAnalysis.enterpriseLibraryRecordCount}条企业记录是产业链、细分领域、融资、地区和总部城市的唯一口径。</p></div><div><span>02</span><p><strong>岗位覆盖</strong>{data.enterpriseAnalysis.matchedJobCount.toLocaleString()}条岗位已关联{data.enterpriseAnalysis.matchedEnterpriseCount}个企业实体，覆盖率{Math.round(data.enterpriseAnalysis.matchedJobRate * 1000) / 10}%。</p></div><div><span>03</span><p><strong>不强行补全</strong>{data.enterpriseAnalysis.pendingJobCount}条未匹配或多候选岗位保留空值。</p></div><div><span>04</span><p><strong>统一落点</strong>企业 → 标准岗位 → 具体招聘岗位/JD，回答“谁在招、招什么”。</p></div></div>}
        </Panel>
        <Panel title={selectedEvidenceJob ? `${selectedEvidenceJob.title} · JD详情` : '具体JD详情'} subtitle={selectedEvidenceJob ? '点击岗位列表中的条目可查看完整JD' : '点击左侧企业下的岗位查看JD'} className="industry-jd-panel">
          {selectedEvidenceJob ? <JobEvidenceDetail job={selectedEvidenceJob} onBack={() => setEvidenceJobId(null)} onOpenPortrait={() => { window.location.hash = `/job-portrait-graph?job=${encodeURIComponent(selectedEvidenceJob.id)}` }} /> : <div className="empty-state"><FileText size={26} /><strong>点击左侧具体岗位查看JD</strong><span>在企业信息区域的岗位列表中点击任意岗位，这里会显示完整的JD详情。</span></div>}
        </Panel>
      </div> : viewMode === 'technology' ? <div className="job-ecosystem-workspace portrait-three-column technology-three-column">
        <Panel title="技术分层导航" subtitle="技术词主数据：L1 技术域 → L2 技术类 → L3 技术点 → L4 技术词" className="portrait-hierarchy-tree-panel technology-hierarchy-tree-panel">
          <TechnologyLayeredTree nodes={data.technologyNodes} selected={selectedTechnology} expanded={technologyTreeExpanded} onToggle={toggleTechnologyTree} onTechnology={selectTechnology} />
        </Panel>
        <Panel title={selectedTechnology ? `${selectedTechnology.name} · ${selectedTechnology.level}技术节点` : 'L1–L4技术主数据全景'} subtitle={selectedTechnology?.level === 'L4' ? '技术词尾端落到标准岗位；具体招聘岗位与完整JD在右侧' : '中间图展示当前节点及其下一层，点击继续下钻'} className="job-ecosystem-graph-panel portrait-graph-panel technology-graph-panel"><TechnologyHierarchyGraph data={data} selected={selectedTechnology} jobs={technologyJobs} onTechnology={selectTechnology} onRole={(id) => { const role = data.standardRoles.find((item) => item.id === id); if (role) openRoleProfile(role) }} /></Panel>
        <Panel title={selectedTechnology ? '技术节点的岗位证据' : '技术图谱说明'} subtitle={selectedTechnology ? '标准岗位负责聚合，具体岗位与完整JD负责举证' : '技术层级来自主数据，不由页面临时造词'} className="portrait-detail-panel technology-detail-panel"><TechnologyDetail data={data} selected={selectedTechnology} jobs={technologyJobs} selectedJob={selectedEvidenceJob && technologyJobs.some((job) => job.id === selectedEvidenceJob.id) ? selectedEvidenceJob : null} onTechnology={(id) => selectTechnology(id)} onJob={openJobEvidence} onBackJob={() => setEvidenceJobId(null)} /></Panel>
        {showDiscovery ? (
          <DiscoveryOverlayPanel
            title={selectedTechnology ? `${selectedTechnology.name} · 新岗位发现 ${technologyCandidates.length}` : `新岗位发现 ${technologyCandidates.length}`}
            subtitle={selectedTechnology ? '该技术节点及其下级技术点上的岗位提议' : '选中左侧技术节点可只看该方向的提议'}
            footnote={discovery && discovery.metadata.unmatchedTechnologyCodes.length > 0
              ? `另有 ${discovery.metadata.unmatchedTechnologyCodes.length} 个技术编码晚于本图谱的技术主数据快照，尚无对应节点：${discovery.metadata.unmatchedTechnologyCodes.join('、')}`
              : undefined}
            items={technologyCandidates}
            loading={!discovery}
            error={discoveryError}
            empty="该技术方向下暂无岗位提议。"
          />
        ) : null}
      </div> : viewMode === 'portrait' ? <div className="job-ecosystem-workspace portrait-three-column">
        <Panel title="岗位分层导航" subtitle="从6方向一层一层展开，最终落到标准岗位" className="portrait-hierarchy-tree-panel">
          <div className="portrait-layered-tree">
            {data.directions.map((dir) => {
              const dirOpen = portraitTreeExpanded.has(dir.id)
              const childCategories = data.categories.filter((c) => c.directionId === dir.id)
              return <div key={dir.id} className="tree-node tree-dir">
                <div className={`tree-row ${directionId === dir.id ? 'active' : ''}`}>
                  <button className="tree-toggle" onClick={(e) => { e.stopPropagation(); togglePortraitTree(dir.id) }}>
                    {dirOpen ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
                  </button>
                  <button className="tree-label" onClick={() => selectDirection(dir.id)}>
                    <i style={{ background: dir.color }} />
                    <span>{dir.name}</span>
                    <em>{dir.jobCount.toLocaleString()}</em>
                  </button>
                </div>
                {dirOpen ? <div className="tree-children">
                  {childCategories.map((cat) => {
                    const catOpen = portraitTreeExpanded.has(cat.id)
                    const childClusters = data.clusters.filter((cl) => cl.categoryId === cat.id)
                    return <div key={cat.id} className="tree-node tree-cat">
                      <div className={`tree-row ${categoryId === cat.id ? 'active' : ''}`}>
                        <button className="tree-toggle" onClick={(e) => { e.stopPropagation(); togglePortraitTree(cat.id) }}>
                          {catOpen ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
                        </button>
                        <button className="tree-label" onClick={() => selectCategory(cat.id)}>
                          <i style={{ background: dir.color, opacity: 0.7 }} />
                          <span>{cat.name}</span>
                          <em>{cat.jobCount.toLocaleString()}</em>
                        </button>
                      </div>
                      {catOpen ? <div className="tree-children">
                        {childClusters.map((cl) => {
                          const clOpen = portraitTreeExpanded.has(cl.id)
                          const childRoles = data.standardRoles.filter((r) => r.clusterId === cl.id)
                          return <div key={cl.id} className="tree-node tree-cluster">
                            <div className={`tree-row ${clusterId === cl.id ? 'active' : ''}`}>
                              <button className="tree-toggle" onClick={(e) => { e.stopPropagation(); togglePortraitTree(cl.id) }}>
                                {clOpen ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
                              </button>
                              <button className="tree-label" onClick={() => selectCluster(cl.id)}>
                                <i style={{ background: cl.color, opacity: 0.5 }} />
                                <span>{cl.name}</span>
                                <em>{cl.jobCount.toLocaleString()}</em>
                              </button>
                            </div>
                            {clOpen ? <div className="tree-children tree-role-children">
                              {childRoles.length ? childRoles.sort((a, b) => b.jobCount - a.jobCount).map((role) => (
                                <div key={role.id} className={`tree-node tree-role ${standardRoleId === role.id ? 'active' : ''}`}>
                                  <div className="tree-row">
                                    <span className="tree-toggle tree-spacer" />
                                    <button className="tree-label" onClick={() => selectStandardRole(role.id)}>
                                      <i style={{ background: '#7257c8' }} />
                                      <span className="tree-role-name" title={role.name}>{role.name}</span>
                                      <em>{role.jobCount}JD</em>
                                    </button>
                                  </div>
                                </div>
                              )) : <div className="tree-empty">该簇暂无标准岗位画像</div>}
                            </div> : null}
                          </div>
                        })}
                        {childClusters.length === 0 ? <div className="tree-empty">该职业种类下暂无岗位簇数据</div> : null}
                      </div> : null}
                    </div>
                  })}
                </div> : null}
              </div>
            })}
          </div>
          {/* 新岗位发现清单与上方分层导航同列但明确隔开：分层导航是已观测到的岗位事实，
              这里是尚未入库的推演提议，两者不能混进同一棵树，否则读者分不清哪个是事实。 */}
          <div className="portrait-discovery-nav">
            <div className="portrait-discovery-nav-heading">
              <strong>新岗位发现</strong>
              <span>{discovery ? `${discoveryNavItems.length} 条 · 点击在本图定位` : '正在加载推演结果…'}</span>
            </div>
            {discovery && discoveryNavItems.length ? <div className="portrait-discovery-nav-list">
              {discoveryNavItems.map((item) => (
                <button
                  key={item.candidateCode}
                  className={`${highlightedCandidate === item.candidateCode ? 'active' : ''}${item.portraitClusterName ? '' : ' unplaced'}`}
                  onClick={() => locateCandidateInPortrait(item)}
                  title={item.portraitClusterName ? item.definition || item.name : `${item.name}（未归位：招聘市场中没有同时命中其全部技术点的 JD）`}
                >
                  <i style={{ background: classificationColor[item.classificationCode]?.dot ?? '#94a3b8' }} />
                  <span>{item.name}<small>{item.classification}{item.gapGrade ? ` · ${item.gapGrade === 'A' ? '缺口显著' : '缺口存疑'}` : ''}</small></span>
                  <em>{item.score.toFixed(2)}</em>
                </button>
              ))}
            </div> : discovery ? <div className="tree-empty">当前方向或岗位簇下没有推演候选</div> : null}
          </div>
        </Panel>
        <Panel
          title={
            selectedJob
              ? `${selectedJob.title} · 具体岗位能力图谱`
              : activeRole
                ? `${activeRole.name} · 标准岗位五维画像`
                : selectedClusterRole
                  ? `${selectedClusterRole.name} · 标准岗位层`
                  : cluster
                    ? `${cluster.name} · 岗位簇层`
                    : category
                      ? `${category.name} · 岗位簇层`
                      : direction
                        ? `${direction.name} · 岗位分层图`
                        : '岗位分层导览'
          }
          subtitle={
            selectedJob
              ? '中心是具体岗位；外圈是该岗位的职责、技能、能力、场景与条件'
              : activeRole
                ? '中心是标准岗位；外圈画像点由同类多条JD归纳，不由单条JD生成'
                : standardRoleId
                  ? '当前标准岗位画像尚未完全入库，先用岗位簇或层级图继续浏览'
                  : cluster
                    ? '展示该岗位簇下的标准岗位；继续点选可进入岗位能力图谱'
                    : directionId
                      ? '展示当前层级的下一层节点，便于一级一级下钻'
                      : '从左侧分层导览开始，逐级筛选到岗位簇和具体岗位'
          }
          className="job-ecosystem-graph-panel portrait-graph-panel"
        >
          {activeRole?.origin === 'inference_derived' ? <div className="inferred-role-banner">
            <strong>{activeRole.classification} · 推演派生岗位</strong>
            <p>本岗位来自新岗位发现，画像由 LLM 依候选数据卡生成，<b>没有 JD 证据支撑</b>——招聘市场上从未出现该技术组合，这正是它作为缺口信号的前提，不是数据缺失。画像点不计入市场热度与岗位证据。</p>
            <span>{activeRole.evidenceSummary}</span>
            <button className="secondary-button" onClick={() => activeRole.candidateCode && onNavigate?.('candidate', activeRole.candidateCode)}>查看候选数据卡</button>
          </div> : null}
          {portraitMiddleGraph}
        </Panel>
        <Panel title={`${standardRoleId ? '多JD证据下钻' : `当前层级 ${portraitScopedRoles.length} 个标准岗位导航`} & 具体岗位列表`} subtitle={standardRoleId ? '点击画像点筛选支持它的岗位，再打开完整JD' : '点击上方岗位可切换中心圆形画像；下方显示当前展示岗位的证据与具体JD（若无画像则只展示导航）'} className="portrait-detail-panel">
          {!standardRoleId || portraitScopedRoles.length > 1 ? <>
            <div className="portrait-role-jobs-table" style={{ marginTop: 6, borderTop: 0, paddingTop: 0 }}>
              <div className="role-jobs-head"><h4>{directionId ? (categoryId ? (clusterId ? '该簇下' : '该种类下') : '该方向下') : '全量'}标准岗位（{portraitScopedRoles.length.toLocaleString()}个）</h4><span>{scopedRolesWithProfile.length} 个有完整画像可点查看圆形</span></div>
              <div className="role-jobs-list">
                {scopedRolesSorted.slice(0, 60).map((role) => (
                  <button key={role.id} className={`role-job-item ${activeRole?.id === role.id ? 'active' : ''}`} onClick={() => selectStandardRole(role.id)}>
                    <span className="role-job-title">{role.name}</span>
                    <span className="role-job-company">{role.directionName} · {role.categoryName}</span>
                    <span className="role-job-count">{role.origin === 'inference_derived' ? '推演派生 · 无 JD 支撑' : hasValidProfile(role) ? `${role.jobCount} JD · 有画像` : `${role.jobCount} JD`}</span>
                  </button>
                ))}
                {portraitScopedRoles.length > 60 ? <div className="role-jobs-more">剩余 {portraitScopedRoles.length - 60} 个请用左侧分层树或顶部筛选定位。</div> : null}
              </div>
            </div>
          </> : null}
          {canRenderGraph && activeRole ? <>
            {!selectedEvidenceJob ? <div style={{ borderTop: '1px dashed #dbe5f1', margin: '10px 0 6px', paddingTop: 8 }}>
              <div className="role-jobs-head" style={{ marginTop: 0 }}><h4>当前展示 · {activeRole.name} 的五维画像证据</h4><span>上方切换岗位可查看不同画像</span></div>
            </div> : null}
            <StandardRoleEvidenceDetail role={activeRole} cluster={cluster} dimension={portraitDimension} selectedPoint={selectedProfilePoint} jobs={profileEvidenceJobs} selectedJob={selectedEvidenceJob} onPoint={(point) => { setSelectedProfilePoint(point.name); setEvidenceJobId(null) }} onJob={openJobEvidence} onBackJob={() => setEvidenceJobId(null)} />
            <div className="portrait-role-jobs-table">
              <div className="role-jobs-head"><h4>该标准岗位下的具体岗位（{roleJobs.length.toLocaleString()}条）</h4><span>点击岗位标题查看完整JD</span></div>
              <div className="role-jobs-list">
                {roleJobs.slice(0, 80).map((job) => (
                  <button key={job.id} className={`role-job-item ${evidenceJobId === job.id ? 'active' : ''}`} onClick={() => openJobEvidence(job)}>
                    <span className="role-job-title" title={job.title}>{job.title}</span>
                    <span className="role-job-company" title={job.company}>{job.company || '公司未公开'}</span>
                    <span className="role-job-count">· {job.abilityLevel || job.headquartersCity || '详情'}</span>
                  </button>
                ))}
                {roleJobs.length > 80 ? <div className="role-jobs-more">剩余 {roleJobs.length - 80} 条请使用顶部搜索或画像点筛选定位。</div> : null}
              </div>
            </div>
          </> : !standardRoleId && portraitScopedRoles.length ? <>
            <div style={{ borderTop: '1px dashed #dbe5f1', margin: '10px 0 6px', paddingTop: 8 }}>
              <div className="role-jobs-head" style={{ marginTop: 0 }}><h4>当前层级画像状态</h4><span>有完整画像：{scopedRolesWithProfile.length} / {portraitScopedRoles.length}</span></div>
              <div className="role-jobs-more" style={{ marginTop: 0 }}>该层级选到的标准岗位（{displayRole?.name ?? '—'}）暂无完整五维画像，请在上方列表中点击带「有画像」标记的岗位查看圆形图谱。</div>
            </div>
          </> : null}
        </Panel>
        {showDiscovery ? (
          <DiscoveryOverlayPanel
            title={`新岗位发现 ${portraitCandidates.length}`}
            subtitle="按招聘文本证据归入岗位簇；上方选择方向或岗位簇可收窄"
            footnote={discovery
              ? `岗位簇由招聘文本反推：只有同时命中候选全部技术点的 JD 才计入，据此定位到 ${discovery.metadata.portraitPlacedCount} 条候选。放宽到命中任意一个技术点会让结果失去意义——泛泛提及大量技术词的 JD 会主导匹配。其余 ${discovery.metadata.candidateCount - discovery.metadata.portraitPlacedCount} 条没有这样的 JD，不做归位。`
              : undefined}
            items={portraitCandidates}
            highlightCode={highlightedCandidate}
            unplacedNote="该候选没有归位到任何岗位簇：招聘市场中没有同时命中其全部技术点的 JD——这正是它作为缺口信号的前提。"
            loading={!discovery}
            error={discoveryError}
            empty="该范围内暂无可归位的岗位提议。"
          />
        ) : null}
      </div> : <div className="job-ecosystem-workspace">
        <Panel title={enterpriseValue ? `${enterpriseValue} · 重点企业` : `${dimensionConfig.label} · 企业岗位分布`} subtitle={enterpriseValue ? '图中展示该维度岗位量靠前的企业' : '点击属性值继续下钻'} className="job-ecosystem-graph-panel">
          {enterpriseValue ? <button className="job-ecosystem-back" onClick={() => { setEnterpriseValue(null); setEnterpriseId(null) }}><ArrowLeft size={14} />返回属性分布</button> : null}
          <EnterpriseDimensionGraph data={data} dimension={enterpriseDimension} selectedValue={enterpriseValue} selectedEnterprise={enterprise} onValue={(value) => { setEnterpriseValue(value); setEnterpriseId(null); setEvidenceJobId(null) }} onEnterprise={(id) => { setEnterpriseId(id); setEvidenceJobId(null) }} onRole={(id) => { const role = data.standardRoles.find((item) => item.id === id); if (role) openRoleProfile(role) }} />
        </Panel>
        <Panel title={enterprise ? '企业岗位画像' : enterpriseValue ? `${enterpriseValue} · 企业排行` : '企业库关联说明'} subtitle={enterprise ? '企业属性与岗位需求来自同一实体' : '空白项不推测，保留治理状态'}>
          {enterprise ? <EnterpriseDetail enterprise={enterprise} jobs={enterpriseJobs} selectedJobId={evidenceJobId} onJob={openJobEvidence} /> : enterpriseValue ? <div className="job-direction-detail enterprise-group-detail"><i style={{ background: dimensionConfig.color }} /><h3>{enterpriseValue}</h3><p>共{enterpriseGroup.reduce((sum, item) => sum + item.jobCount, 0).toLocaleString()}个已关联岗位，覆盖{enterpriseGroup.length}家企业；图中展示岗位量靠前的18家。</p><div>{enterpriseGroup.slice(0, 10).map((item) => <button key={item.id} onClick={() => { setEnterpriseId(item.id); setEvidenceJobId(null) }}><span>{item.name}</span><strong>{item.jobCount}</strong><em>{item.headquartersCity || '城市待补'}</em><ChevronRight size={14} /></button>)}</div></div> : <div className="job-ecosystem-guide enterprise-guide"><div><span>01</span><p><strong>企业库主数据</strong>{data.enterpriseAnalysis.enterpriseLibraryRecordCount}条企业记录是产业链、细分领域、融资和总部属性的唯一口径。</p></div><div><span>02</span><p><strong>岗位覆盖</strong>{data.enterpriseAnalysis.matchedJobCount.toLocaleString()}条岗位已关联{data.enterpriseAnalysis.matchedEnterpriseCount}个企业实体，覆盖率{Math.round(data.enterpriseAnalysis.matchedJobRate * 1000) / 10}%。</p></div><div><span>03</span><p><strong>不强行补全</strong>{data.enterpriseAnalysis.pendingJobCount}条未匹配或多候选岗位保留空值，进入企业待补全清单。</p></div><div><span>04</span><p><strong>统一落点</strong>企业 → 标准岗位 → 具体招聘岗位/JD，企业偏好与岗位能力在标准岗位画像中汇合。</p></div></div>}
        </Panel>
      </div>}
    <div className="job-ecosystem-notes"><StatusTag tone="info">数据口径</StatusTag><p>岗位源：{data.metadata.sourceFile}；企业属性源：{data.enterpriseAnalysis.enterpriseLibraryFile}；{data.metadata.portraitExcelOverride ? `标准岗位源：标准岗位五维能力画像.xlsx（${data.standardRoleAudit.seedRoleCount}岗、${data.standardRoleAudit.seedVariantCount}个名称变体）；层级归属：四层聚类结果 岗位明细 sheet；方向/类别/簇：分层聚类图谱 nodes+edges。` : `标准岗位源：搜索词包（${data.standardRoleAudit.seedRoleCount}岗、${data.standardRoleAudit.seedVariantCount}个名称变体）。`} 当前{data.standardRoleAudit.mappedJobCount}条JD通过人工层级与标题置信闸门，{data.standardRoleAudit.pendingJobCount}条保留待专家映射；岗位簇仍是候选层，画像点至少由2条JD共同支持，证据不足不推测补值。</p></div>
    </>}
  </div>
}
