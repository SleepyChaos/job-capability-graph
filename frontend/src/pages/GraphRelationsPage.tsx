import { classificationColor, classificationLabels } from '../api/discovery'
import { AlertTriangle, BadgeDollarSign, Building2, ChevronDown, ChevronRight, Eye, GitBranch, Layers, Network, RefreshCw, RotateCcw, Table2, TreePine, Undo2, Zap } from 'lucide-react'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { graphApi, type CapabilityToClusterRanking, type IndustryChainSummary, type OrgTechGraphResponse, type RelationGraphExpansion, type RelationGraphResponse, type RelationNode, type TripleAuditResponse } from '../api/graphs'
import { jobsApi, type JobDetail } from '../api/jobs'
import { organizationsApi, type CrossValidationReport, type OrganizationDetail, type OrganizationListItem } from '../api/organizations'
import { taxonomyApi, type TaxonomyTreeResponse, type TechnologyNodeDetail } from '../api/taxonomy'
import { DomainLegend } from '../components/DomainLegend'
import { RelationGraphFilters, type RelationGraphFilterState } from '../components/GraphFilters'
import { RelationForceGraph } from '../components/RelationForceGraph'
import { Modal, StatusTag } from '../components/ui'
import { domainColors } from '../data/graphData'

type TabId = 'global' | 'capability_to_cluster' | 'org_tech' | 'enterprise_cards' | 'skill_tree' | 'cross_validation' | 'triple_audit'
type LayoutMode = 'force' | 'dagre_lr'

const densityOptions = [80, 240, 400, 720, 1000]
const supportOptions = [1, 2, 3, 5]
const topNOptions = [20, 50, 100, 0]
const MAX_RENDERED_NODES = 1000
const FULL_CLUSTER_LIMIT = 1000
const DEFAULT_NODE_BUDGET = 240
const DEFAULT_RELATION_FILTERS: RelationGraphFilterState = { clusterDomain: '', capabilityDomain: '', capabilityLevel: 'L2' }
const industryStageOrder = ['upstream', 'midstream', 'downstream', 'support', 'unclassified'] as const

interface GraphQuerySnapshot {
  filters: RelationGraphFilterState
  nodeBudget: number
  minSupportingJobCount: number
  focusNodeId: string | null
  industryStage: string
}

function graphRouteParams() {
  const query = window.location.hash.split('?')[1] ?? ''
  return new URLSearchParams(query)
}

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
    domain_group_nodes: base.domain_group_nodes,
    capability_nodes: mergeNodes(base.capability_nodes, expansion.capability_nodes),
    edges: [...edges.values()],
  }
}

/** 图例里列出的候选分类，与候选墙同序：外部证据在前，库内分类在后。 */
const CANDIDATE_LEGEND_ORDER = [
  'milestone_signal',
  'upstream_signal',
  'potential_new_role',
  'library_gap',
  'role_evolution',
  'existing_role',
]
function SkillTreeRenderer({ nodes, collapsed, toggle, onDrill, depth = 0 }: {
  nodes: TaxonomyTreeResponse['roots']
  collapsed: Set<string>
  toggle: (code: string) => void
  onDrill: (code: string) => void
  depth?: number
}) {
  const itemStyle: React.CSSProperties = {
    display: 'flex',
    flexDirection: 'column',
    gap: '6px',
    padding: '8px 12px',
    background: depth === 0 ? '#0f172a' : depth === 1 ? '#1e293b' : '#f8fafc',
    color: depth <= 1 ? '#f8fafc' : '#0f172a',
    border: `1px solid ${depth === 0 ? '#020617' : depth === 1 ? '#334155' : '#e2e8f0'}`,
    borderRadius: '8px',
    minWidth: '190px',
    maxWidth: '260px',
    boxShadow: depth <= 1 ? '0 4px 12px rgba(15,23,42,.24)' : '0 1px 2px rgba(0,0,0,.04)',
  }
  const rowStyle: React.CSSProperties = { display: 'flex', alignItems: 'flex-start', gap: '14px' }
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
      {nodes.map((node) => {
        const isCollapsed = collapsed.has(node.code)
        const hasChildren = node.children.length > 0
        return (
          <div key={node.code} style={rowStyle}>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
              <div style={itemStyle}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                  {hasChildren ? (
                    <button
                      onClick={() => toggle(node.code)}
                      style={{ background: 'none', border: 'none', cursor: 'pointer', padding: 0, color: 'inherit', display: 'inline-flex' }}
                      aria-label={isCollapsed ? '展开' : '折叠'}
                    >{isCollapsed ? <ChevronRight size={14} /> : <ChevronDown size={14} />}</button>
                  ) : <span style={{ width: '14px' }} />}
                  <div style={{ fontWeight: 700, fontSize: '13px' }}>{node.name}</div>
                </div>
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '6px', fontSize: '11px', opacity: depth <= 1 ? 0.8 : 0.7 }}>
                  <span style={{ fontWeight: 600 }}>{node.code} · {node.level_code}</span>
                  <span style={{ cursor: 'pointer', textDecoration: 'underline' }} onClick={() => onDrill(node.code)} title="打开详情 + 下钻">
                    <GitBranch size={11} style={{ display: 'inline', verticalAlign: '-2px' }} /> 下钻
                  </span>
                </div>
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '4px', marginTop: '2px', fontSize: '10px', opacity: depth <= 1 ? 0.85 : 1 }}>
                  <div>JD <strong>{node.referenced_job_count}</strong></div>
                  <div>企业 <strong>{node.referenced_organization_count}</strong></div>
                  <div>岗位簇 <strong>{node.referenced_role_cluster_count}</strong></div>
                </div>
              </div>
            </div>
            {hasChildren && !isCollapsed ? (
              <SkillTreeRenderer
                nodes={node.children}
                collapsed={collapsed}
                toggle={toggle}
                onDrill={onDrill}
                depth={depth + 1}
              />
            ) : null}
          </div>
        )
      })}
    </div>
  )
}

export function GraphRelationsPage({ notify }: { notify: (message: string) => void }) {
  const initialRoute = graphRouteParams()
  const [activeTab, setActiveTab] = useState<TabId>((initialRoute.get('view') as TabId) || 'global')
  const [industryStage, setIndustryStage] = useState(initialRoute.get('stage') ?? '')
  const [industrySummary, setIndustrySummary] = useState<IndustryChainSummary | null>(null)
  const [filters, setFilters] = useState<RelationGraphFilterState>(DEFAULT_RELATION_FILTERS)
  const [nodeBudget, setNodeBudget] = useState(DEFAULT_NODE_BUDGET)
  const [minSupportingJobCount, setMinSupportingJobCount] = useState(1)
  const [focusNodeId, setFocusNodeId] = useState<string | null>(null)
  // 候选默认不进图：它们是未入库的提议，与观测到的聚类混排会让读者分不清
  // 哪些是既有事实。由用户显式打开。
  const [includeCandidates, setIncludeCandidates] = useState(false)
  const [data, setData] = useState<RelationGraphResponse | null>(null)
  const [graphLoading, setGraphLoading] = useState(false)
  const [graphReloadKey, setGraphReloadKey] = useState(0)
  const [lastSuccessfulSnapshot, setLastSuccessfulSnapshot] = useState<GraphQuerySnapshot | null>(null)
  const graphRequestRef = useRef(0)
  const [selected, setSelected] = useState<string | null>(initialRoute.get('node'))
  const [expandedNodeIds, setExpandedNodeIds] = useState<Set<string>>(() => new Set())
  const [expandingNodeId, setExpandingNodeId] = useState<string | null>(null)
  const [tableView, setTableView] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [revDomainCode, setRevDomainCode] = useState<string>('')
  const [revLevelCode, setRevLevelCode] = useState<'L2' | 'L3'>('L2')
  const [revTopN, setRevTopN] = useState<number>(20)
  const [capRanking, setCapRanking] = useState<CapabilityToClusterRanking | null>(null)
  const [revLoading, setRevLoading] = useState(false)
  const [revError, setRevError] = useState<string | null>(null)
  const [orgTechData, setOrgTechData] = useState<OrgTechGraphResponse | null>(null)
  const [orgLoading, setOrgLoading] = useState(false)
  const [orgError, setOrgError] = useState<string | null>(null)
  const [orgDomain, setOrgDomain] = useState<string>('')
  const [orgLevel, setOrgLevel] = useState<'L2' | 'L3'>('L2')
  const [orgLimit, setOrgLimit] = useState<number>(40)
  const [capabilityDetail, setCapabilityDetail] = useState<TechnologyNodeDetail | null>(null)
  const [detailLoading, setDetailLoading] = useState(false)
  const [layoutMode, setLayoutMode] = useState<LayoutMode>('force')
  const [selectedJobCode, setSelectedJobCode] = useState<string | null>(null)
  const [selectedJob, setSelectedJob] = useState<JobDetail | null>(null)
  const [jobDetailLoading, setJobDetailLoading] = useState(false)
  // Enterprise cards tab
  const [entSearch, setEntSearch] = useState('')
  const [entType, setEntType] = useState('')
  const [entOnlyReview, setEntOnlyReview] = useState(false)
  const [entOnlyWithJobs, setEntOnlyWithJobs] = useState(true)
  const [entPage, setEntPage] = useState(0)
  const [entPageSize, setEntPageSize] = useState(50)
  const [entItems, setEntItems] = useState<OrganizationListItem[]>([])
  const [entTotal, setEntTotal] = useState(0)
  const [entLoading, setEntLoading] = useState(false)
  const [entError, setEntError] = useState<string | null>(null)
  const [entTypes, setEntTypes] = useState<string[]>([])
  const [entSelected, setEntSelected] = useState<OrganizationDetail | null>(null)
  const [entDetailLoading, setEntDetailLoading] = useState(false)
  // Skill tree tab
  const [skillMaxDepth, setSkillMaxDepth] = useState<'L2' | 'L3' | 'L4'>('L3')
  const [skillTree, setSkillTree] = useState<TaxonomyTreeResponse | null>(null)
  const [skillLoading, setSkillLoading] = useState(false)
  const [skillError, setSkillError] = useState<string | null>(null)
  const [skillCollapsed, setSkillCollapsed] = useState<Set<string>>(() => new Set())
  const [skillDetailCode, setSkillDetailCode] = useState<string | null>(null)
  // Cross-source validation tab
  const [cvData, setCvData] = useState<CrossValidationReport | null>(null)
  const [cvStatus, setCvStatus] = useState('')
  const [cvLoading, setCvLoading] = useState(false)
  const [cvError, setCvError] = useState<string | null>(null)
  // Triple audit tab
  const [auditData, setAuditData] = useState<TripleAuditResponse | null>(null)
  const [auditLoading, setAuditLoading] = useState(false)
  const [auditError, setAuditError] = useState<string | null>(null)
  const [auditRunCode, setAuditRunCode] = useState<string | undefined>(undefined)
  const selectNode = useCallback((id: string) => setSelected(id), [])
  const changeFilters = useCallback((next: RelationGraphFilterState) => {
    setFocusNodeId(null)
    if (next.capabilityDomain) setLayoutMode('force')
    setFilters(next)
  }, [])

  const updateGraphRoute = useCallback((next: { stage?: string; view?: TabId; node?: string | null }) => {
    const params = graphRouteParams()
    const values = { stage: industryStage, view: activeTab, node: selected, ...next }
    if (values.stage) params.set('stage', values.stage); else params.delete('stage')
    if (values.view && values.view !== 'global') params.set('view', values.view); else params.delete('view')
    if (values.node) params.set('node', values.node); else params.delete('node')
    const suffix = params.toString()
    window.history.replaceState(null, '', `#/graph-relations${suffix ? `?${suffix}` : ''}`)
  }, [activeTab, industryStage, selected])

  const changeIndustryStage = useCallback((stage: string) => {
    setIndustryStage(stage)
    setFocusNodeId(null)
    updateGraphRoute({ stage, node: null })
  }, [updateGraphRoute])

  const changeTab = useCallback((tab: TabId) => {
    setActiveTab(tab)
    updateGraphRoute({ view: tab })
  }, [updateGraphRoute])

  useEffect(() => {
    updateGraphRoute({ node: selected })
  }, [selected, updateGraphRoute])

  useEffect(() => {
    const controller = new AbortController()
    graphApi.industryChain(controller.signal).then(setIndustrySummary).catch((reason: Error) => {
      if (reason.name !== 'AbortError') notify(`产业链总览加载失败：${reason.message}`)
    })
    return () => controller.abort()
  }, [notify])

  useEffect(() => {
    const controller = new AbortController()
    const requestId = ++graphRequestRef.current
    const requestSnapshot: GraphQuerySnapshot = {
      filters: { ...filters },
      nodeBudget,
      minSupportingJobCount,
      focusNodeId,
      industryStage,
    }
    setGraphLoading(true)
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
      includeCandidates,
      industryStage: industryStage || null,
    }, controller.signal)
      .then((response) => {
        setData(response)
        if (response.edges.some((edge) => edge.relation_type === 'important_technology')) {
          setLastSuccessfulSnapshot(requestSnapshot)
        }
        setExpandedNodeIds(new Set())
        setSelected((current) => {
          const ids = new Set([...response.role_nodes, ...response.domain_group_nodes, ...response.capability_nodes].map((node) => node.id))
          return current && ids.has(current) ? current : response.role_nodes[0]?.id ?? response.capability_nodes[0]?.id ?? null
        })
      })
      .catch((reason: Error) => {
        if (reason.name !== 'AbortError') setError(reason.message)
      })
      .finally(() => { if (graphRequestRef.current === requestId) setGraphLoading(false) })
    return () => controller.abort()
    // includeCandidates 必须在依赖里：它是请求参数的一部分，漏掉会让「叠加岗位候选」
    // 这个勾选框完全不生效——状态翻了，但不重新取数，图上永远看不到候选节点。
  }, [filters.clusterDomain, filters.capabilityDomain, filters.capabilityLevel, focusNodeId, graphReloadKey, includeCandidates, industryStage, minSupportingJobCount, nodeBudget])

  const nodeMap = useMemo(
    () => new Map<string, RelationNode>(data ? [...data.role_nodes, ...data.domain_group_nodes, ...data.capability_nodes].map((node) => [node.id, node]) : []),
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
  const evidenceJobCodes = useMemo(() => Array.from(new Set(connections.flatMap((edge) => edge.evidence_job_codes))).slice(0, 30), [connections])

  useEffect(() => {
    const nextCode = evidenceJobCodes.includes(selectedJobCode ?? '') ? selectedJobCode : evidenceJobCodes[0] ?? null
    setSelectedJobCode(nextCode)
    if (!nextCode) {
      setSelectedJob(null)
      return
    }
    const controller = new AbortController()
    setJobDetailLoading(true)
    jobsApi.detail(nextCode, controller.signal)
      .then(setSelectedJob)
      .catch((reason: Error) => { if (reason.name !== 'AbortError') notify(`JD 详情加载失败：${reason.message}`) })
      .finally(() => setJobDetailLoading(false))
    return () => controller.abort()
  }, [evidenceJobCodes, notify, selectedJobCode])
  const hasProjection = Boolean(data && data.data_version !== 'uninitialized')
  const businessEdges = useMemo(
    () => data?.edges.filter((edge) => edge.relation_type === 'important_technology') ?? [],
    [data],
  )
  const totalNodeCount = data ? data.role_nodes.length + data.domain_group_nodes.length + data.capability_nodes.length : 0
  const displayedNodeCount = useMemo(() => {
    if (!data) return 0
    if (!filters.capabilityDomain) return totalNodeCount
    const connectedRoleIds = new Set(businessEdges.map((edge) => edge.source))
    return connectedRoleIds.size
      + data.capability_nodes.filter((node) => node.domain_code === filters.capabilityDomain).length
      + data.domain_group_nodes.filter((node) => node.domain_code === filters.capabilityDomain).length
  }, [businessEdges, data, filters.capabilityDomain, totalNodeCount])
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

  useEffect(() => {
    if (activeTab !== 'capability_to_cluster') return
    const controller = new AbortController()
    setRevLoading(true)
    setRevError(null)
    graphApi.capabilityToClusters({
      capabilityDomainCode: revDomainCode || null,
      capabilityLevelCode: revLevelCode,
      minSupportingJobCount: 1,
      limit: 1000,
    }, controller.signal)
      .then((response) => setCapRanking(response))
      .catch((reason: Error) => {
        if (reason.name !== 'AbortError') setRevError(reason.message)
      })
      .finally(() => setRevLoading(false))
    return () => controller.abort()
  }, [activeTab, revDomainCode, revLevelCode])

  useEffect(() => {
    if (activeTab !== 'org_tech') return
    const controller = new AbortController()
    setOrgLoading(true)
    setOrgError(null)
    graphApi.orgTechGraph({
      capabilityDomainCode: orgDomain || null,
      capabilityLevelCode: orgLevel,
      orgLimit,
      capabilitiesPerOrg: 20,
      minSupportingJobCount: 1,
      industryStage: industryStage || null,
    }, controller.signal)
      .then((response) => setOrgTechData(response))
      .catch((reason: Error) => {
        if (reason.name !== 'AbortError') setOrgError(reason.message)
      })
      .finally(() => setOrgLoading(false))
    return () => controller.abort()
  }, [activeTab, industryStage, orgDomain, orgLevel, orgLimit])

  // Enterprise cards fetch
  useEffect(() => {
    if (activeTab !== 'enterprise_cards') return
    const controller = new AbortController()
    setEntLoading(true)
    setEntError(null)
    organizationsApi.list({
      search: entSearch || undefined,
      orgType: entType || undefined,
      onlyNeedsReview: entOnlyReview,
      withJobsOnly: entOnlyWithJobs,
      limit: entPageSize,
      offset: entPage * entPageSize,
    }, controller.signal)
      .then((response) => {
        setEntItems(response.items)
        setEntTotal(response.total)
        setEntTypes((prev) => prev.length ? prev : Array.from(new Set(response.items.map((i) => i.type).filter(Boolean))).sort())
      })
      .catch((reason: Error) => {
        if (reason.name !== 'AbortError') setEntError(reason.message)
      })
      .finally(() => setEntLoading(false))
    return () => controller.abort()
  }, [activeTab, entSearch, entType, entOnlyReview, entOnlyWithJobs, entPageSize, entPage])

  // Skill tree fetch
  useEffect(() => {
    if (activeTab !== 'skill_tree') return
    const controller = new AbortController()
    setSkillLoading(true)
    setSkillError(null)
    taxonomyApi.tree(skillMaxDepth, undefined, controller.signal)
      .then((response) => setSkillTree(response))
      .catch((reason: Error) => {
        if (reason.name !== 'AbortError') setSkillError(reason.message)
      })
      .finally(() => setSkillLoading(false))
    return () => controller.abort()
  }, [activeTab, skillMaxDepth])

  // Triple audit fetch
  useEffect(() => {
    if (activeTab !== 'cross_validation') return
    const controller = new AbortController()
    setCvLoading(true)
    setCvError(null)
    organizationsApi.crossValidation({ status: cvStatus || undefined, limit: 500 }, controller.signal)
      .then(setCvData)
      .catch((reason: Error) => { if (reason.name !== 'AbortError') setCvError(reason.message) })
      .finally(() => setCvLoading(false))
    return () => controller.abort()
  }, [activeTab, cvStatus])

  useEffect(() => {
    if (activeTab !== 'triple_audit') return
    const controller = new AbortController()
    setAuditLoading(true)
    setAuditError(null)
    graphApi.tripleAuditLatest(auditRunCode, controller.signal)
      .then((response) => setAuditData(response))
      .catch((reason: Error) => {
        if (reason.name !== 'AbortError') setAuditError(reason.message)
      })
      .finally(() => setAuditLoading(false))
    return () => controller.abort()
  }, [activeTab, auditRunCode])

  const exportCrossValidationCsv = () => {
    if (!cvData?.rows.length) return
    const header = ['机构编码', '机构名称', '类别', '地区', '状态', '一致性分', 'Splink置信度', '外部佐证率', '业务链', '专利技术域', 'JD产业链', '缺失维度']
    const quote = (value: unknown) => `"${String(value ?? '').replaceAll('"', '""')}"`
    const lines = cvData.rows.map((row) => [
      row.org_code, row.org_name, row.org_category, [row.province, row.city].filter(Boolean).join('/'),
      row.status, row.consistency_score, row.splink_match_score, row.external_alignment_rate,
      row.business_chain, row.patent_domain_codes, row.jd_chain, row.missing_dimensions.join('|'),
    ].map(quote).join(','))
    const blob = new Blob([`\uFEFF${header.map(quote).join(',')}\n${lines.join('\n')}`], { type: 'text/csv;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const anchor = document.createElement('a')
    anchor.href = url
    anchor.download = `cross-validation-${new Date().toISOString().slice(0, 10)}.csv`
    anchor.click()
    URL.revokeObjectURL(url)
  }

  const openOrgDetail = async (code: string) => {
    try {
      setEntDetailLoading(true)
      setEntSelected(await organizationsApi.detail(code))
    } catch (reason) {
      notify(`企业详情加载失败：${(reason as Error).message}`)
    } finally {
      setEntDetailLoading(false)
    }
  }

  const reverseTableRows = useMemo<CapabilityToClusterRanking['rows']>(() => {
    if (!capRanking) return []
    const rows = [...capRanking.rows]
    if (revTopN > 0 && rows.length > revTopN) return rows.slice(0, revTopN)
    return rows
  }, [capRanking, revTopN])

  const openCapabilityDetail = async (code: string) => {
    try {
      setDetailLoading(true)
      setCapabilityDetail(await taxonomyApi.nodeDetail(code))
    } catch (reason) {
      notify(`技术词详情加载失败：${(reason as Error).message}`)
    } finally {
      setDetailLoading(false)
    }
  }

  const openClusterStar = (nodeId: string) => {
    const clusterCode = nodeId.replace(/^cluster:/, '')
    window.location.hash = `/graph-clusters?cluster=${encodeURIComponent(clusterCode)}&stage=${encodeURIComponent(industryStage)}`
  }

  const applyGraphSnapshot = useCallback((snapshot: GraphQuerySnapshot) => {
    setFilters({ ...snapshot.filters })
    setNodeBudget(snapshot.nodeBudget)
    setMinSupportingJobCount(snapshot.minSupportingJobCount)
    setFocusNodeId(snapshot.focusNodeId)
    setIndustryStage(snapshot.industryStage)
    setSelected(null)
    setError(null)
    updateGraphRoute({ stage: snapshot.industryStage, node: null })
  }, [updateGraphRoute])

  const restoreDefaultGraph = useCallback(() => {
    applyGraphSnapshot({
      filters: DEFAULT_RELATION_FILTERS,
      nodeBudget: DEFAULT_NODE_BUDGET,
      minSupportingJobCount: 1,
      focusNodeId: null,
      industryStage: '',
    })
    setLayoutMode('force')
    notify('已恢复默认图谱筛选。')
  }, [applyGraphSnapshot, notify])

  const hasActiveGraphFilters = Boolean(
    filters.clusterDomain
    || filters.capabilityDomain
    || filters.capabilityLevel !== 'L2'
    || industryStage
    || focusNodeId
    || minSupportingJobCount !== 1
  )
  const hasBusinessRelations = businessEdges.length > 0
  const noFilterIntersection = Boolean(!error && data && hasProjection && !graphLoading && !hasBusinessRelations && hasActiveGraphFilters)
  const noAcceptedEvidence = Boolean(!error && data && hasProjection && !graphLoading && !hasBusinessRelations && !hasActiveGraphFilters)
  const canRestorePrevious = Boolean(lastSuccessfulSnapshot && (
    lastSuccessfulSnapshot.filters.clusterDomain !== filters.clusterDomain
    || lastSuccessfulSnapshot.filters.capabilityDomain !== filters.capabilityDomain
    || lastSuccessfulSnapshot.filters.capabilityLevel !== filters.capabilityLevel
    || lastSuccessfulSnapshot.nodeBudget !== nodeBudget
    || lastSuccessfulSnapshot.minSupportingJobCount !== minSupportingJobCount
    || lastSuccessfulSnapshot.focusNodeId !== focusNodeId
    || lastSuccessfulSnapshot.industryStage !== industryStage
  ))

  return (
    <div className="graph-page graph-subpage">
      <div className="graph-subpage-intro">
        <div><h2>岗位—能力关联图</h2><p>展示当前岗位聚类及其高频标准技术能力；仅使用通过语境校验的真实 JD 证据。</p></div>
        <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: '8px' }}>
          <StatusTag tone={hasProjection ? 'success' : 'info'}>{data ? (hasProjection ? `数据版本 ${data.data_version.slice(0, 8)}` : '暂无图谱快照') : '加载中'}</StatusTag>
          <div className="tab-row" style={{ display: 'flex', flexWrap: 'wrap', gap: '4px', padding: '4px', background: '#f1f5f9', borderRadius: '8px' }}>
            <button
              onClick={() => changeTab('global')}
              style={{ padding: '6px 12px', borderRadius: '6px', border: 'none', cursor: 'pointer', fontWeight: 600, background: activeTab === 'global' ? '#ffffff' : 'transparent', color: activeTab === 'global' ? '#0f172a' : '#64748b', boxShadow: activeTab === 'global' ? '0 1px 2px rgba(0,0,0,.06)' : 'none' }}
            ><Network size={14} style={{ display: 'inline', verticalAlign: '-2px', marginRight: '4px' }} />全局关系图</button>
            <button
              onClick={() => changeTab('capability_to_cluster')}
              style={{ padding: '6px 12px', borderRadius: '6px', border: 'none', cursor: 'pointer', fontWeight: 600, background: activeTab === 'capability_to_cluster' ? '#ffffff' : 'transparent', color: activeTab === 'capability_to_cluster' ? '#0f172a' : '#64748b', boxShadow: activeTab === 'capability_to_cluster' ? '0 1px 2px rgba(0,0,0,.06)' : 'none' }}
            ><Zap size={14} style={{ display: 'inline', verticalAlign: '-2px', marginRight: '4px' }} />能力→岗位簇</button>
            <button
              onClick={() => changeTab('org_tech')}
              style={{ padding: '6px 12px', borderRadius: '6px', border: 'none', cursor: 'pointer', fontWeight: 600, background: activeTab === 'org_tech' ? '#ffffff' : 'transparent', color: activeTab === 'org_tech' ? '#0f172a' : '#64748b', boxShadow: activeTab === 'org_tech' ? '0 1px 2px rgba(0,0,0,.06)' : 'none' }}
            ><Building2 size={14} style={{ display: 'inline', verticalAlign: '-2px', marginRight: '4px' }} />企业↔技术</button>
            <button
              onClick={() => changeTab('enterprise_cards')}
              style={{ padding: '6px 12px', borderRadius: '6px', border: 'none', cursor: 'pointer', fontWeight: 600, background: activeTab === 'enterprise_cards' ? '#ffffff' : 'transparent', color: activeTab === 'enterprise_cards' ? '#0f172a' : '#64748b', boxShadow: activeTab === 'enterprise_cards' ? '0 1px 2px rgba(0,0,0,.06)' : 'none' }}
            ><BadgeDollarSign size={14} style={{ display: 'inline', verticalAlign: '-2px', marginRight: '4px' }} />企业图谱卡片</button>
            <button
              onClick={() => changeTab('skill_tree')}
              style={{ padding: '6px 12px', borderRadius: '6px', border: 'none', cursor: 'pointer', fontWeight: 600, background: activeTab === 'skill_tree' ? '#ffffff' : 'transparent', color: activeTab === 'skill_tree' ? '#0f172a' : '#64748b', boxShadow: activeTab === 'skill_tree' ? '0 1px 2px rgba(0,0,0,.06)' : 'none' }}
            ><TreePine size={14} style={{ display: 'inline', verticalAlign: '-2px', marginRight: '4px' }} />技能树</button>
            <button
              onClick={() => changeTab('cross_validation')}
              style={{ padding: '6px 12px', borderRadius: '6px', border: 'none', cursor: 'pointer', fontWeight: 600, background: activeTab === 'cross_validation' ? '#ffffff' : 'transparent', color: activeTab === 'cross_validation' ? '#0f172a' : '#64748b', boxShadow: activeTab === 'cross_validation' ? '0 1px 2px rgba(0,0,0,.06)' : 'none' }}
            ><GitBranch size={14} style={{ display: 'inline', verticalAlign: '-2px', marginRight: '4px' }} />交叉验证</button>
            <button
              onClick={() => changeTab('triple_audit')}
              style={{ padding: '6px 12px', borderRadius: '6px', border: 'none', cursor: 'pointer', fontWeight: 600, background: activeTab === 'triple_audit' ? '#ffffff' : 'transparent', color: activeTab === 'triple_audit' ? '#0f172a' : '#64748b', boxShadow: activeTab === 'triple_audit' ? '0 1px 2px rgba(0,0,0,.06)' : 'none' }}
            ><AlertTriangle size={14} style={{ display: 'inline', verticalAlign: '-2px', marginRight: '4px' }} />矛盾打分审核</button>
          </div>
        </div>
      </div>

      {industrySummary ? <section className="industry-chain-navigator" aria-label="产业链图谱导航">
        <div className="industry-chain-heading"><div><span>统一图谱入口</span><h3>按产业链探索岗位、企业与技能</h3></div><button className={!industryStage ? 'selected' : ''} onClick={() => changeIndustryStage('')}>全部产业链</button></div>
        <div className="industry-stage-grid">{industryStageOrder.map((code) => industrySummary.stages.find((stage) => stage.code === code)).filter((stage): stage is NonNullable<typeof stage> => Boolean(stage)).map((stage) => <button key={stage.code} className={industryStage === stage.code ? 'selected' : ''} style={{ '--stage-color': stage.color } as React.CSSProperties} onClick={() => { changeIndustryStage(stage.code); changeTab('global') }}><i /><div><strong>{stage.name}</strong><span>{stage.categories.slice(0, 3).map((item) => item.name).join(' · ') || '等待分类'}</span></div><dl><div><dt>岗位</dt><dd>{stage.job_count}</dd></div><div><dt>企业</dt><dd>{stage.organization_count}</dd></div><div><dt>岗位簇</dt><dd>{stage.cluster_count}</dd></div><div><dt>技能</dt><dd>{stage.technology_count}</dd></div></dl></button>)}</div>
        {industryStage ? <div className="industry-category-strip"><strong>{industrySummary.stages.find((stage) => stage.code === industryStage)?.name}细分</strong>{industrySummary.stages.find((stage) => stage.code === industryStage)?.categories.slice(0, 12).map((category) => <span key={category.name}>{category.name}<b>{category.job_count}</b></span>)}</div> : null}
      </section> : null}

      {activeTab === 'global' && (
        <>
          <RelationGraphFilters values={filters} onChange={changeFilters} onApply={(summary) => notify(`关联图筛选已更新：${summary}`)} />

          {/*
            候选与岗位聚类同级——都属于 role 一侧、连的是同一批能力节点，指标也一一对应
            （成员数↔支撑 JD 数、独立企业数↔独立企业数、簇内聚度↔候选评分）。但候选是
            **未入库的提议**，默认不进图，打开后以虚线边区分。
          */}
          <label className="graph-candidate-toggle">
            <input
              type="checkbox"
              checked={includeCandidates}
              onChange={(event) => setIncludeCandidates(event.target.checked)}
            />
            <span>
              <strong>叠加新岗位候选</strong>
              候选与岗位聚类同级，但属于未入库的提议，以虚线连接其能力节点
              {data?.filters?.candidate_node_count
                ? `（当前 ${data.filters.candidate_node_count} 个）`
                : ''}
            </span>
          </label>
          {hasProjection ? <div className="relation-density-toolbar" aria-label="图谱展示密度">
            <label>节点预算<select value={nodeBudget} onChange={(event) => setNodeBudget(Number(event.target.value))}>{densityOptions.map((value) => <option key={value} value={value}>{value} 个节点</option>)}</select></label>
            <label>最小支持 JD<select value={minSupportingJobCount} onChange={(event) => setMinSupportingJobCount(Number(event.target.value))}>{supportOptions.map((value) => <option key={value} value={value}>{value} 条</option>)}</select></label>
            <label>布局模式
              <select value={layoutMode} onChange={(event) => setLayoutMode(event.target.value as LayoutMode)}>
                <option value="force">{filters.capabilityDomain ? '领域 → L2 能力 → 岗位同心环' : '岗位环绕技能（推荐）'}</option>
                <option value="dagre_lr">岗位 → 能力分层</option>
              </select>
            </label>
            <span>当前展示 {displayedNodeCount} 个节点 · {businessEdges.length} 条岗位—能力关系{expandedNodeIds.size ? ` · 已展开 ${expandedNodeIds.size} 处邻居` : ''}</span>
            {focusNodeId ? <button className="secondary-button relation-focus-exit" onClick={() => setFocusNodeId(null)}>返回全局图</button> : null}
          </div> : null}
          {error && data ? <div className="graph-state-banner graph-state-banner--error" role="alert"><AlertTriangle size={18} /><div><strong>筛选请求失败，已保留上一版图谱</strong><span>{error}</span></div><div><button className="secondary-button" onClick={() => setGraphReloadKey((value) => value + 1)}><RefreshCw size={14} />重试</button>{canRestorePrevious && lastSuccessfulSnapshot ? <button className="secondary-button" onClick={() => applyGraphSnapshot(lastSuccessfulSnapshot)}><Undo2 size={14} />返回上一组有效筛选</button> : null}<button className="secondary-button" onClick={restoreDefaultGraph}><RotateCcw size={14} />恢复默认</button></div></div> : null}
          {error && !data ? <div className="empty-state graph-state-card graph-state-card--error"><AlertTriangle size={26} /><strong>图谱接口连接失败</strong><span>{error}</span><div className="graph-state-actions"><button className="primary-button" onClick={() => setGraphReloadKey((value) => value + 1)}><RefreshCw size={14} />重新连接</button><button className="secondary-button" onClick={restoreDefaultGraph}><RotateCcw size={14} />恢复默认筛选</button></div></div> : null}
          {!error && !data ? <div className="empty-state graph-state-card"><Network className="spin" size={26} /><strong>正在加载岗位—能力关系</strong><span>正在读取最新岗位聚类和通过语境校验的 JD 证据，请稍候。</span></div> : null}
          {data && !hasProjection ? <div className="empty-state graph-state-card"><Layers size={26} /><strong>当前还没有可用图谱数据</strong><span>数据库尚未生成成功的岗位聚类快照。请先完成 JD 导入、解析和聚类，再刷新本页。</span><div className="graph-state-actions"><button className="primary-button" onClick={() => setGraphReloadKey((value) => value + 1)}><RefreshCw size={14} />刷新数据状态</button><button className="secondary-button" onClick={restoreDefaultGraph}><RotateCcw size={14} />恢复默认筛选</button></div></div> : null}
          {noFilterIntersection ? <div className="empty-state graph-state-card graph-state-card--intersection"><Network size={26} /><strong>当前筛选条件没有岗位—能力交集</strong><span>这不是系统故障。可返回上一组有效筛选，降低“最小支持 JD”，或恢复默认图谱。</span><div className="graph-filter-summary"><span>岗位领域：{filters.clusterDomain || '全部'}</span><span>能力领域：{filters.capabilityDomain || '全部'}</span><span>能力层级：{filters.capabilityLevel}</span><span>产业链：{industryStage || '全部'}</span><span>最小支持：{minSupportingJobCount} 条 JD</span></div><div className="graph-state-actions">{canRestorePrevious && lastSuccessfulSnapshot ? <button className="primary-button" onClick={() => applyGraphSnapshot(lastSuccessfulSnapshot)}><Undo2 size={14} />返回上一组有效筛选</button> : null}{minSupportingJobCount > 1 ? <button className="secondary-button" onClick={() => setMinSupportingJobCount(1)}>放宽为 1 条 JD</button> : null}<button className="secondary-button" onClick={restoreDefaultGraph}><RotateCcw size={14} />恢复默认图谱</button></div></div> : null}
          {noAcceptedEvidence ? <div className="empty-state graph-state-card"><Layers size={26} /><strong>当前快照没有通过校验的岗位—能力关系</strong><span>岗位簇和技术体系已经存在，但还没有可用于连边的有效 JD 证据。</span><div className="graph-state-actions"><button className="primary-button" onClick={() => setGraphReloadKey((value) => value + 1)}><RefreshCw size={14} />重新读取</button><button className="secondary-button" onClick={restoreDefaultGraph}><RotateCcw size={14} />恢复默认图谱</button></div></div> : null}
          {data && hasProjection && hasBusinessRelations ? <div className={`graph-workspace graph-workspace--global${graphLoading ? ' is-refreshing' : ''}`}>
            {graphLoading ? <div className="graph-refresh-indicator"><Network size={13} />正在应用筛选，保留当前图谱…</div> : null}
            <div className="graph-legend"><strong>节点类型</strong><span><i className="legend-cluster" />岗位聚类</span><span><i className="legend-domain" />T1 技术领域</span><span><i className="legend-skill" />标准技术能力</span><hr /><strong>T1–T7 领域色</strong><DomainLegend compact /><hr /><strong>新岗位候选 · 按分类着色</strong><div className="graph-candidate-legend">{CANDIDATE_LEGEND_ORDER.map((code) => (<span key={code}><i style={{ borderColor: classificationColor[code]?.dot }} />{classificationLabels[code] ?? code}</span>))}</div><p className="graph-legend-note">候选为空心虚线圈，与实心的岗位聚类区分——它们同级，但还没入库。着色按分类而非技术域：图上要回答的是「这条提议哪来的」。</p><hr /><p>{focusNodeId ? '当前为单岗位聚类局部图；返回全局图可继续浏览其他聚类。' : filters.capabilityDomain ? `${filters.capabilityDomain} 领域位于中心，L2 能力构成内环，相关岗位簇按最强能力关系分布在外环。` : '岗位聚类按 T1–T7 技术域分散，领域节点连接本域能力，能力节点位于关联岗位簇的加权中心。'}</p><button onClick={() => setTableView((value) => !value)}><Table2 size={15} />{tableView ? '图谱视图' : '表格视图'}</button></div>
            {tableView ? <div className="relation-table-view"><table><thead><tr><th>岗位聚类</th><th>重要能力</th><th>覆盖率</th><th>支持 JD</th></tr></thead><tbody>{businessEdges.map((edge) => <tr key={edge.id}><td><button onClick={() => selectNode(edge.source)}>{nodeMap.get(edge.source)?.label}</button></td><td><button onClick={() => selectNode(edge.target)}>{nodeMap.get(edge.target)?.label}</button></td><td>{Math.round((edge.coverage_rate ?? 0) * 100)}%</td><td>{edge.supporting_job_count}</td></tr>)}</tbody></table></div> : <RelationForceGraph graph={data} selectedId={selected} onSelect={selectNode} onExpand={expandNode} layoutMode={layoutMode} />}
            <aside className="evidence-inspector relation-job-inspector">{selectedNode ? <>
              <div className="inspector-title"><div><span>{selectedNode.type === 'job_cluster' ? '岗位聚类详情' : selectedNode.type === 'technology_domain' ? '技术领域导航' : '标准技术能力'}</span><h3>{selectedNode.label}</h3></div><StatusTag tone={selectedNode.type === 'job_cluster' ? 'info' : 'success'}>{selectedNode.domain_code}</StatusTag></div>
              <div className="inspector-metric-grid"><div><span>证据 JD</span><strong>{selectedNode.evidence_count}</strong></div><div><span>关联节点</span><strong>{connectedNodes.length}</strong></div><div><span>可查看 JD</span><strong>{evidenceJobCodes.length}</strong></div></div>
              <div className="inspector-actions">{selectedNode.type === 'job_cluster' ? <button className="secondary-button" onClick={() => openClusterStar(selectedNode.id)}>技能星图</button> : selectedNode.type === 'technology' ? <button className="secondary-button" onClick={() => changeTab('capability_to_cluster')}>相关岗位簇</button> : <button className="secondary-button" onClick={() => changeFilters({ ...filters, capabilityDomain: selectedNode.domain_code })}>筛选本领域</button>}{selectedNode.type === 'job_cluster' && !focusNodeId ? <button className="secondary-button" onClick={() => setFocusNodeId(selectedNode.id)}>局部聚焦</button> : selectedNode.type !== 'technology_domain' ? <button className="secondary-button" onClick={() => expandNode(selectedNode.id)} disabled={Boolean(expandingNodeId) || expandedNodeIds.has(selectedNode.id)}>{expandingNodeId === selectedNode.id ? '展开中…' : expandedNodeIds.has(selectedNode.id) ? '已展开' : '展开邻居'}</button> : <button className="secondary-button" onClick={restoreDefaultGraph}>查看全部领域</button>}</div>
              {evidenceJobCodes.length ? <section className="job-evidence-section"><div className="section-heading"><h4>真实岗位与完整 JD</h4><span>{evidenceJobCodes.length} 条证据</span></div><select value={selectedJobCode ?? ''} onChange={(event) => setSelectedJobCode(event.target.value)}>{evidenceJobCodes.map((code, index) => <option key={code} value={code}>证据 {index + 1} · {code}</option>)}</select>{jobDetailLoading ? <div className="job-detail-loading">正在加载岗位详情…</div> : selectedJob ? <div className="job-detail-card"><h4>{selectedJob.title}</h4><p className="job-company">{selectedJob.company ?? '企业未标注'} · {selectedJob.region ?? selectedJob.company_region ?? '地区未标注'}</p><dl className="job-field-grid"><div><dt>岗位编号</dt><dd>{selectedJob.source_job_id ?? selectedJob.job_code}</dd></div><div><dt>薪资</dt><dd>{selectedJob.salary ?? '—'}</dd></div><div><dt>经验</dt><dd>{selectedJob.experience ?? '—'}</dd></div><div><dt>学历</dt><dd>{selectedJob.education ?? '—'}</dd></div><div><dt>能力等级</dt><dd>{selectedJob.level ?? '—'}</dd></div><div><dt>职业方向</dt><dd>{selectedJob.career_direction ?? '—'}</dd></div><div><dt>职业种类</dt><dd>{selectedJob.career_type ?? '—'}</dd></div><div><dt>产业链层级</dt><dd>{selectedJob.industry_chain_level ?? '—'}</dd></div><div><dt>公司细分领域</dt><dd>{selectedJob.company_subfield ?? '—'}</dd></div><div><dt>融资轮次</dt><dd>{selectedJob.funding_round ?? '—'}</dd></div><div><dt>公司所属地区</dt><dd>{selectedJob.company_region ?? '—'}</dd></div><div><dt>公司总部城市</dt><dd>{selectedJob.company_headquarters_city ?? '—'}</dd></div><div><dt>收录/发布时间</dt><dd>{selectedJob.published_at_date ?? selectedJob.source_collected_at_date ?? '—'}</dd></div><div><dt>来源列表</dt><dd>{selectedJob.source_codes.join('、') || '—'}</dd></div></dl>{selectedJob.source_url ? <a className="job-source-link" href={selectedJob.source_url} target="_blank" rel="noreferrer">打开原始招聘链接</a> : null}{selectedJob.source_skill_tags ? <><h5>原表技能标签</h5><div className="job-tag-list">{selectedJob.source_skill_tags.split(';').map((item) => item.trim()).filter(Boolean).map((item) => <span key={item}>{item}</span>)}</div></> : null}{selectedJob.scenarios.length ? <><h5>工作场景</h5><div className="job-tag-list">{selectedJob.scenarios.map((item) => <span key={item}>{item}</span>)}</div></> : null}<h5>清洗 JD 描述（全文）</h5><div className="job-jd-full">{selectedJob.jd_text || '暂无 JD 正文'}</div>{selectedJob.technologies.length ? <><h5>系统识别的重点能力</h5><div className="job-tag-list">{selectedJob.technologies.map((item) => <span key={`${item.requirement_no}-${item.technology_code}`}>{item.technology_name}</span>)}</div></> : null}</div> : null}</section> : null}
              <details className="connected-node-details"><summary>{selectedNode.type === 'job_cluster' ? '重要能力' : selectedNode.type === 'technology_domain' ? '领域内能力' : '关联岗位聚类'}（{connectedNodes.length}）</summary><div className="connected-node-list">{connections.map((edge) => { const node = nodeMap.get(edge.source === selectedNode.id ? edge.target : edge.source); return node ? <button key={edge.id} onClick={() => selectNode(node.id)}><i style={{ background: domainColors[node.domain_code] }} /><span>{node.label}<small>{edge.supporting_job_count ? `${edge.supporting_job_count} 条 JD · 覆盖 ${Math.round((edge.coverage_rate ?? 0) * 100)}%` : '分类关系'}</small></span><strong>{Math.round(edge.importance)}</strong></button> : null })}</div></details>
            </> : <div className="empty-state"><strong>当前筛选没有关系</strong><span>该岗位领域与能力领域可能没有交集；可降低“最小支持 JD”或重置筛选。</span><button className="secondary-button" onClick={() => changeFilters({ clusterDomain: '', capabilityDomain: '', capabilityLevel: 'L2' })}>恢复默认图谱</button></div>}</aside>
          </div> : null}
        </>
      )}

      {activeTab === 'capability_to_cluster' && (
        <>
          <div className="relation-density-toolbar" aria-label="反向视图筛选">
            <label>技术域 T1<select value={revDomainCode} onChange={(event) => setRevDomainCode(event.target.value)}><option value="">全部 T1</option>{Array.from(new Set(capRanking?.rows.map((r) => r.domain_code) ?? [])).filter(Boolean).sort().map((code) => <option key={code} value={code}>{code}</option>)}</select></label>
            <label>能力层级<select value={revLevelCode} onChange={(event) => setRevLevelCode(event.target.value as 'L2' | 'L3')}><option value="L2">L2 能力组</option><option value="L3">L3 具体能力</option></select></label>
            <label>TOP-N<select value={revTopN} onChange={(event) => setRevTopN(Number(event.target.value))}>{topNOptions.map((value) => <option key={value} value={value}>{value === 0 ? '全部' : `Top ${value}`}</option>)}</select></label>
            <span>共 {reverseTableRows.length} 个能力 · 共 {capRanking?.total ?? 0} 条聚合</span>
          </div>
          {revLoading ? <div className="empty-state"><Network size={24} /><strong>正在加载反向关系…</strong><span>按证据数排序聚合能力与岗位簇的关系。</span></div> : null}
          {revError ? <div className="empty-state"><Network size={24} /><strong>反向关系加载失败</strong><span>{revError}</span></div> : null}
          {!revLoading && !revError && reverseTableRows.length === 0 ? <div className="empty-state"><Network size={24} /><strong>暂无匹配的能力</strong><span>调整 T1 领域或层级筛选。</span></div> : null}
          {!revLoading && !revError && reverseTableRows.length > 0 ? (
            <div className="table-wrap">
              <table className="data-table">
                <thead><tr><th style={{ width: '42%' }}>能力 + 编码 + 定义 + T 域</th><th>引用该能力的岗位簇列表（按权重降序）</th></tr></thead>
                <tbody>{reverseTableRows.map((row) => (
                  <tr key={row.technology_node_id}>
                    <td>
                      <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                          <strong>{row.technology_name}</strong>
                          <small style={{ color: '#64748b' }}>{row.technology_code}</small>
                          <button title="查看详情" onClick={() => openCapabilityDetail(row.technology_code)} style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#64748b', padding: 0 }}><Eye size={13} /></button>
                          <StatusTag tone="info" style={{ fontSize: '11px' }}>{row.domain_code} {row.domain_name ?? ''}</StatusTag>
                          <StatusTag tone="warning" style={{ fontSize: '11px' }}>{row.level_code}</StatusTag>
                        </div>
                        <div style={{ color: '#475569', fontSize: '13px' }}>支持 JD {row.supporting_job_count}</div>
                      </div>
                    </td>
                    <td>
                      <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px' }}>
                        {row.ranked_clusters.slice(0, 20).map((cluster) => (
                          <div key={cluster.code} style={{ background: '#f8fafc', border: '1px solid #e2e8f0', borderRadius: '6px', padding: '6px 8px', minWidth: '150px' }}>
                            <div style={{ fontWeight: 600, fontSize: '13px' }}>{cluster.label}</div>
                            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', fontSize: '11px', color: '#64748b', marginTop: '2px' }}>
                              <span>JD {cluster.supporting_job_count}</span>
                              <span style={{ color: '#0f172a', fontWeight: 600 }}>覆盖率 {Math.round(cluster.coverage_rate * 100)}%</span>
                              <span style={{ fontWeight: 700, color: '#1769e0' }}>{cluster.importance.toFixed(1)}</span>
                            </div>
                          </div>
                        ))}
                        {row.ranked_clusters.length > 20 ? <span style={{ fontSize: '12px', color: '#64748b', alignSelf: 'center' }}>+{row.ranked_clusters.length - 20} 个</span> : null}
                      </div>
                    </td>
                  </tr>
                ))}</tbody>
              </table>
            </div>
          ) : null}
        </>
      )}

      {activeTab === 'org_tech' && (
        <>
          <div className="relation-density-toolbar" aria-label="企业技术图筛选">
            <label>技术域 T1<select value={orgDomain} onChange={(event) => setOrgDomain(event.target.value)}><option value="">全部 T1</option>{Array.from(new Set(orgTechData?.domain_group_nodes.map((d) => d.code) ?? [])).filter(Boolean).sort().map((code) => <option key={code} value={code}>{code}</option>)}</select></label>
            <label>能力层级<select value={orgLevel} onChange={(event) => setOrgLevel(event.target.value as 'L2' | 'L3')}><option value="L2">L2 能力组</option><option value="L3">L3 具体能力</option></select></label>
            <label>企业 Top-N<select value={orgLimit} onChange={(event) => setOrgLimit(Number(event.target.value))}>{[20, 40, 100, 200].map((v) => <option key={v} value={v}>Top {v}</option>)}</select></label>
            <span>机构 {orgTechData?.org_nodes.length ?? 0} · 技术 {orgTechData?.capability_nodes.length ?? 0} · 边 {orgTechData?.edges.length ?? 0}</span>
          </div>
          {orgLoading ? <div className="empty-state"><Network size={24} /><strong>企业↔技术图加载中…</strong><span>根据 Layer A 的 Splink 归并机构聚合技术需求。</span></div> : null}
          {orgError ? <div className="empty-state"><Network size={24} /><strong>加载失败</strong><span>{orgError}</span></div> : null}
          {!orgLoading && !orgError && orgTechData ? (
            orgTechData.org_nodes.length === 0 ? (
              <div className="empty-state" style={{ minHeight: '400px' }}>
                <Layers size={32} />
                <strong>暂无机构数据</strong>
                <span style={{ maxWidth: '420px' }}>请先运行 Layer A Splink 归并脚本写入 md_organization，或放宽「最小支持 JD 数」。</span>
              </div>
            ) : (
              <div className="table-wrap">
                <table className="data-table">
                  <thead><tr><th style={{ width: '38%' }}>企业（机构编码 + 地区 + 类型）</th><th>核心技术栈（按 JD 数排序）</th></tr></thead>
                  <tbody>{orgTechData.org_nodes.map((org) => {
                    const edges = orgTechData.edges.filter((e) => e.source === org.id && e.relation_type === 'org_adopts_tech')
                    const techMap = new Map(orgTechData.capability_nodes.map((n) => [n.id, n]))
                    const rowTechs = edges
                      .sort((a, b) => (b.job_count ?? 0) - (a.job_count ?? 0))
                      .slice(0, 15)
                      .map((e) => ({ node: techMap.get(e.target), count: e.job_count ?? 0 }))
                      .filter((t) => Boolean(t.node))
                    return (
                      <tr key={org.id}>
                        <td>
                          <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                              <strong>{org.label}</strong>
                              <small style={{ color: '#64748b' }}>{org.code}</small>
                              <StatusTag tone={org.status === 'active' ? 'success' : 'warning'} style={{ fontSize: '11px' }}>{org.status}</StatusTag>
                              <StatusTag tone="info" style={{ fontSize: '11px' }}>{org.org_type}</StatusTag>
                            </div>
                            <div style={{ color: '#475569', fontSize: '13px' }}>
                              地区 {org.province ?? '—'}{org.city ? ` · ${org.city}` : ''} · 技术覆盖 {org.metrics.technology_count} · JD {org.metrics.job_count}
                            </div>
                          </div>
                        </td>
                        <td>
                          <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px' }}>
                            {rowTechs.map((t) => t.node && (
                              <div key={t.node.id} style={{ background: t.node.domain_code ? (domainColors as Record<string, string>)[t.node.domain_code] + '22' : '#f8fafc', border: `1px solid ${(domainColors as Record<string, string>)[t.node.domain_code] ?? '#e2e8f0'}`, borderRadius: '6px', padding: '6px 8px' }}>
                                <div style={{ fontWeight: 600, fontSize: '13px' }}>{t.node.label}</div>
                                <div style={{ fontSize: '11px', color: '#64748b', marginTop: '2px' }}>
                                  <StatusTag tone="warning" style={{ fontSize: '11px' }}>{t.node.level_code}</StatusTag>{' '}JD {t.count}
                                </div>
                              </div>
                            ))}
                            {edges.length > 15 ? <span style={{ fontSize: '12px', color: '#64748b', alignSelf: 'center' }}>+{edges.length - 15} 个</span> : null}
                          </div>
                        </td>
                      </tr>
                    )
                  })}</tbody>
                </table>
              </div>
            )
          ) : null}
        </>
      )}

      {activeTab === 'enterprise_cards' && (
        <>
          <div className="relation-density-toolbar" aria-label="企业卡片筛选">
            <label>搜索<input type="search" value={entSearch} onChange={(event) => { setEntSearch(event.target.value); setEntPage(0) }} placeholder="企业名称 / 编码 / 别名" /></label>
            <label>类型
              <select value={entType} onChange={(event) => { setEntType(event.target.value); setEntPage(0) }}>
                <option value="">全部</option>
                {entTypes.map((t) => <option key={t} value={t}>{t}</option>)}
              </select>
            </label>
            <label><input type="checkbox" checked={entOnlyWithJobs} onChange={(event) => { setEntOnlyWithJobs(event.target.checked); setEntPage(0) }} />有 JD 数据</label>
            <label><input type="checkbox" checked={entOnlyReview} onChange={(event) => { setEntOnlyReview(event.target.checked); setEntPage(0) }} />需人工复核</label>
            <label>每页
              <select value={entPageSize} onChange={(event) => { setEntPageSize(Number(event.target.value)); setEntPage(0) }}>
                {[24, 48, 96].map((n) => <option key={n} value={n}>{n} 条</option>)}
              </select>
            </label>
            <span>共 {entTotal} 家机构 · 当前第 {entPage + 1} / {Math.max(1, Math.ceil(entTotal / entPageSize))} 页</span>
          </div>
          {entLoading ? <div className="empty-state"><Building2 size={24} /><strong>加载中…</strong><span>从机构库读取企业卡片数据。</span></div> : null}
          {entError ? <div className="empty-state"><Building2 size={24} /><strong>加载失败</strong><span>{entError}</span></div> : null}
          {!entLoading && !entError && entItems.length === 0 ? (
            <div className="empty-state" style={{ minHeight: '400px' }}>
              <Building2 size={32} />
              <strong>暂无匹配的企业</strong>
              <span style={{ maxWidth: '420px' }}>可放宽「有 JD 数据」或取消「需人工复核」筛选。</span>
            </div>
          ) : null}
          {!entLoading && !entError && entItems.length > 0 ? (
            <>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(260px, 1fr))', gap: '12px', padding: '12px 16px 24px' }}>
                {entItems.map((org) => (
                  <button
                    key={org.code}
                    onClick={() => openOrgDetail(org.code)}
                    style={{
                      textAlign: 'left',
                      background: '#ffffff',
                      border: `1px solid ${org.needs_review ? '#fca5a5' : '#e2e8f0'}`,
                      borderRadius: '10px',
                      padding: '14px',
                      cursor: 'pointer',
                      boxShadow: '0 1px 2px rgba(0,0,0,.04)',
                      display: 'flex',
                      flexDirection: 'column',
                      gap: '8px',
                    }}
                  >
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'start', gap: '8px' }}>
                      <div style={{ minWidth: 0 }}>
                        <div style={{ fontWeight: 700, fontSize: '15px', color: '#0f172a', whiteSpace: 'nowrap', textOverflow: 'ellipsis', overflow: 'hidden' }}>{org.name}</div>
                        <div style={{ fontSize: '11px', color: '#64748b' }}>{org.code}</div>
                      </div>
                      <StatusTag tone={org.status === 'active' ? 'success' : 'warning'} style={{ fontSize: '11px', flexShrink: 0 }}>{org.status}</StatusTag>
                    </div>
                    <div style={{ display: 'flex', flexWrap: 'wrap', gap: '4px', alignItems: 'center' }}>
                      <StatusTag tone="info" style={{ fontSize: '11px' }}>{org.type}</StatusTag>
                      {org.needs_review ? <StatusTag tone="danger" style={{ fontSize: '11px' }}>待复核</StatusTag> : null}
                      <span style={{ color: '#475569', fontSize: '12px' }}>{org.province ?? '—'}{org.city ? ` · ${org.city}` : ''}</span>
                    </div>
                    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '6px', padding: '8px 6px', background: '#f8fafc', borderRadius: '6px', marginTop: '2px' }}>
                      <div><small style={{ color: '#64748b' }}>JD</small><div style={{ fontWeight: 700 }}>{org.job_count}</div></div>
                      <div><small style={{ color: '#64748b' }}>技术</small><div style={{ fontWeight: 700 }}>{org.referenced_technology_count}</div></div>
                      <div><small style={{ color: '#64748b' }}>岗位簇</small><div style={{ fontWeight: 700 }}>{org.cluster_count}</div></div>
                    </div>
                    {org.aliases_preview.length > 0 ? (
                      <div style={{ display: 'flex', flexWrap: 'wrap', gap: '4px' }}>
                        {org.aliases_preview.slice(0, 3).map((a, i) => (
                          <span key={i} style={{ background: '#f1f5f9', color: '#475569', fontSize: '11px', padding: '2px 8px', borderRadius: '10px' }}>{a}</span>
                        ))}
                        {org.aliases_preview.length > 3 ? <span style={{ fontSize: '11px', color: '#94a3b8' }}>+{org.aliases_preview.length - 3}</span> : null}
                      </div>
                    ) : null}
                    {org.min_match_score != null ? (
                      <div style={{ fontSize: '11px', color: '#64748b' }}>最低置信度 <strong style={{ color: '#0f172a' }}>{(org.min_match_score * 100).toFixed(0)}%</strong></div>
                    ) : null}
                  </button>
                ))}
              </div>
              <div style={{ display: 'flex', justifyContent: 'center', gap: '8px', padding: '8px 0 24px' }}>
                <button
                  className="secondary-button"
                  onClick={() => setEntPage((p) => Math.max(0, p - 1))}
                  disabled={entPage === 0 || entLoading}
                >上一页</button>
                <span style={{ alignSelf: 'center', color: '#64748b' }}>{entPage + 1} / {Math.max(1, Math.ceil(entTotal / entPageSize))}</span>
                <button
                  className="secondary-button"
                  onClick={() => setEntPage((p) => p + 1)}
                  disabled={(entPage + 1) * entPageSize >= entTotal || entLoading}
                >下一页</button>
              </div>
            </>
          ) : null}
        </>
      )}

      {activeTab === 'skill_tree' && (
        <>
          <div className="relation-density-toolbar" aria-label="技能树层级">
            <label>最大层级
              <select value={skillMaxDepth} onChange={(event) => { setSkillMaxDepth(event.target.value as 'L2' | 'L3' | 'L4'); setSkillCollapsed(new Set()) }}>
                <option value="L2">T1 → L2</option>
                <option value="L3">T1 → L3（推荐）</option>
                <option value="L4">T1 → L4（全量）</option>
              </select>
            </label>
            <span>{skillTree ? `共 ${skillTree.total_nodes} 个节点 · ${skillTree.root_count} 个 T1 根` : '加载中…'}</span>
            <button className="secondary-button" onClick={() => setSkillCollapsed(new Set())}>全部展开</button>
            <button className="secondary-button" onClick={() => {
              if (!skillTree) return
              const all = new Set<string>()
              const walk = (n: TaxonomyTreeResponse['roots'][number]) => {
                if (n.children.length) all.add(n.code)
                n.children.forEach(walk)
              }
              skillTree.roots.forEach(walk)
              setSkillCollapsed(all)
            }}>全部折叠</button>
          </div>
          {skillLoading ? <div className="empty-state"><TreePine size={24} /><strong>技能树加载中…</strong><span>基于 T1→L4 技术体系与引用计数生成。</span></div> : null}
          {skillError ? <div className="empty-state"><TreePine size={24} /><strong>技能树加载失败</strong><span>{skillError}</span></div> : null}
          {!skillLoading && !skillError && skillTree && skillTree.roots.length === 0 ? (
            <div className="empty-state" style={{ minHeight: '400px' }}>
              <TreePine size={32} />
              <strong>暂无技术树数据</strong>
              <span style={{ maxWidth: '420px' }}>请先导入技术体系 Excel 或发布技术体系版本。</span>
            </div>
          ) : null}
          {!skillLoading && !skillError && skillTree && skillTree.roots.length > 0 ? (
            <div style={{ padding: '16px', overflowX: 'auto' }}>
              <SkillTreeRenderer
                nodes={skillTree.roots}
                collapsed={skillCollapsed}
                toggle={(code) => {
                  setSkillCollapsed((prev) => {
                    const next = new Set(prev)
                    if (next.has(code)) next.delete(code)
                    else next.add(code)
                    return next
                  })
                }}
                onDrill={(code) => openCapabilityDetail(code)}
              />
            </div>
          ) : null}
          {skillDetailCode ? null : null}
        </>
      )}

      {activeTab === 'cross_validation' && (
        <>
          <div className="relation-density-toolbar" aria-label="多源交叉验证筛选">
            <label>验证状态
              <select value={cvStatus} onChange={(event) => setCvStatus(event.target.value)}>
                <option value="">全部</option>
                <option value="verified">已验证</option>
                <option value="partial">部分验证</option>
                <option value="unverified">未验证</option>
              </select>
            </label>
            <span>{cvData ? `机构 ${cvData.summary.entity_count} · 人才 ${cvData.summary.talent_count} · 机构—人才边 ${cvData.summary.organization_talent_edges} · 机构—技术边 ${cvData.summary.organization_technology_edges}` : '加载中…'}</span>
            <button className="secondary-button" onClick={exportCrossValidationCsv} disabled={!cvData?.rows.length}><Table2 size={14} />导出当前 CSV</button>
          </div>
          {cvLoading ? <div className="empty-state"><GitBranch size={24} /><strong>正在计算交叉验证视图…</strong><span>汇总高校、机构、企业、人才、岗位与技术之间的关系。</span></div> : null}
          {cvError ? <div className="empty-state"><GitBranch size={24} /><strong>交叉验证数据不可用</strong><span>{cvError}</span></div> : null}
          {!cvLoading && !cvError && cvData ? (
            <>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))', gap: '12px', padding: '12px 16px' }}>
                {Object.entries(cvData.summary.category_counts).map(([key, value]) => (
                  <div key={key} style={{ background: '#f8fafc', border: '1px solid #e2e8f0', borderRadius: '8px', padding: '12px' }}><small style={{ color: '#64748b' }}>{key}</small><div style={{ fontWeight: 800, fontSize: '22px' }}>{value}</div></div>
                ))}
                {Object.entries(cvData.summary.status_counts).map(([key, value]) => (
                  <div key={key} style={{ background: key === 'verified' ? '#f0fdf4' : key === 'partial' ? '#fff7ed' : '#fef2f2', border: '1px solid #e2e8f0', borderRadius: '8px', padding: '12px' }}><small style={{ color: '#64748b' }}>{key}</small><div style={{ fontWeight: 800, fontSize: '22px' }}>{value}</div></div>
                ))}
              </div>
              <div className="table-wrap">
                <table className="data-table">
                  <thead><tr><th>机构</th><th>来源归并</th><th>三方一致性</th><th>外部佐证</th><th>业务/JD/专利维度</th><th>缺失或冲突</th></tr></thead>
                  <tbody>{cvData.rows.map((row) => (
                    <tr key={row.org_code} style={row.status === 'unverified' ? { background: '#fef2f2' } : undefined}>
                      <td><strong>{row.org_name}</strong><div style={{ color: '#64748b', fontSize: '11px' }}>{row.org_code} · {row.org_category} · {row.province ?? '—'}{row.city ? `/${row.city}` : ''}</div></td>
                      <td><div>来源键 {row.source_count}</div><small>Splink {(row.splink_match_score * 100).toFixed(1)}%</small></td>
                      <td><StatusTag tone={row.status === 'verified' ? 'success' : row.status === 'partial' ? 'warning' : 'danger'}>{row.status}</StatusTag><div style={{ marginTop: '4px', fontWeight: 700 }}>{row.consistency_score} 分 · {row.matched_dimensions} 维命中</div></td>
                      <td><strong>{(row.external_alignment_rate * 100).toFixed(1)}%</strong><div style={{ color: '#64748b', fontSize: '11px' }}>ESCO/外部技能体系</div></td>
                      <td><div>业务：{row.business_chain ?? '—'}</div><div>JD：{row.jd_chain ?? '—'}</div><div>专利：{row.patent_domain_codes ?? '—'}</div></td>
                      <td>{row.missing_dimensions.length ? row.missing_dimensions.map((item) => <StatusTag key={item} tone="danger" style={{ margin: '2px', fontSize: '11px' }}>{item}</StatusTag>) : <StatusTag tone="success">完整</StatusTag>}</td>
                    </tr>
                  ))}</tbody>
                </table>
              </div>
            </>
          ) : null}
        </>
      )}

      {activeTab === 'triple_audit' && (
        <>
          <div className="relation-density-toolbar" aria-label="矛盾审核筛选">
            <label>审计批次
              <input value={auditRunCode ?? ''} onChange={(event) => setAuditRunCode(event.target.value || undefined)} placeholder="留空=最新批次" />
            </label>
            <span>{auditData ? `批次 ${auditData.summary.audit_run_code} · 三元组 ${auditData.summary.total_triples} · 低可信 ${auditData.summary.low_plausibility}` : '加载中…'}</span>
          </div>
          {auditLoading ? <div className="empty-state"><AlertTriangle size={24} /><strong>加载中…</strong><span>读取 Layer C 三元组矛盾打分结果。</span></div> : null}
          {auditError ? <div className="empty-state"><AlertTriangle size={24} /><strong>加载失败</strong><span>{auditError}</span></div> : null}
          {!auditLoading && !auditError && auditData ? (
            <>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '12px', padding: '12px 16px' }}>
                <div style={{ background: '#f8fafc', border: '1px solid #e2e8f0', borderRadius: '8px', padding: '12px' }}>
                  <small style={{ color: '#64748b' }}>抽样数</small>
                  <div style={{ fontWeight: 800, fontSize: '22px' }}>{auditData.summary.total_triples}</div>
                </div>
                <div style={{ background: '#fff7ed', border: '1px solid #fed7aa', borderRadius: '8px', padding: '12px' }}>
                  <small style={{ color: '#92400e' }}>低可信</small>
                  <div style={{ fontWeight: 800, fontSize: '22px', color: '#9a3412' }}>{auditData.summary.low_plausibility}</div>
                </div>
                <div style={{ background: '#f1f5f9', border: '1px solid #e2e8f0', borderRadius: '8px', padding: '12px' }}>
                  <small style={{ color: '#64748b' }}>中可信</small>
                  <div style={{ fontWeight: 800, fontSize: '22px' }}>{auditData.summary.medium_plausibility}</div>
                </div>
                <div style={{ background: '#f1f5f9', border: '1px solid #e2e8f0', borderRadius: '8px', padding: '12px' }}>
                  <small style={{ color: '#64748b' }}>高可信</small>
                  <div style={{ fontWeight: 800, fontSize: '22px', color: '#166534' }}>{auditData.summary.high_plausibility}</div>
                </div>
              </div>
              <div className="table-wrap">
                <table className="data-table">
                  <thead><tr>
                    <th style={{ width: '80px' }}>得分</th>
                    <th style={{ width: '12%' }}>主体 + 客体</th>
                    <th style={{ width: '8%' }}>支持 JD</th>
                    <th style={{ width: '10%' }}>支持度 CDF</th>
                    <th style={{ width: '10%' }}>Jaccard 相似度</th>
                    <th style={{ width: '14%' }}>规则标志</th>
                    <th>说明</th>
                  </tr></thead>
                  <tbody>
                    {auditData.low_plausibility_rows.length === 0 ? (
                      <tr><td colSpan={7} style={{ textAlign: 'center', padding: '24px', color: '#64748b' }}>暂无低分数待复核条目。</td></tr>
                    ) : null}
                    {auditData.low_plausibility_rows.map((row) => {
                      const flags = Object.entries(row.rule_flags).filter(([, value]) => Boolean(value))
                      return (
                        <tr key={row.triple_id} style={row.plausibility_score < 0.35 ? { background: '#fef2f2' } : undefined}>
                          <td>
                            <div style={{ fontWeight: 800, color: row.plausibility_score < 0.2 ? '#b91c1c' : row.plausibility_score < 0.35 ? '#9a3412' : '#1e293b' }}>
                              {(row.plausibility_score * 100).toFixed(1)}%
                            </div>
                          </td>
                          <td>
                            <div style={{ fontSize: '12px', fontWeight: 700 }}>{row.subject_label}</div>
                            <div style={{ fontSize: '11px', color: '#64748b' }}>{row.subject_id} · {row.subject_kind}</div>
                            <hr style={{ margin: '4px 0', borderColor: '#e2e8f0' }} />
                            <div style={{ fontSize: '12px', fontWeight: 700 }}>{row.object_label}</div>
                            <div style={{ fontSize: '11px', color: '#64748b' }}>{row.object_id} · {row.object_kind}</div>
                          </td>
                          <td style={{ fontWeight: 700 }}>{row.supporting_job_count}</td>
                          <td>{((row.component_scores.support ?? 0) * 100).toFixed(0)}%</td>
                          <td>{((row.component_scores.jaccard ?? 0) * 100).toFixed(0)}%</td>
                          <td>
                            <div style={{ display: 'flex', flexWrap: 'wrap', gap: '4px' }}>
                              {flags.length === 0 ? <StatusTag tone="success" style={{ fontSize: '11px' }}>no_flag</StatusTag> : flags.map(([key, value]) => (
                                <StatusTag key={key} tone="danger" style={{ fontSize: '11px' }}>{key}:{String(value)}</StatusTag>
                              ))}
                            </div>
                          </td>
                          <td style={{ color: '#475569', fontSize: '13px' }}>{row.subject_label} —[{row.predicate}]→ {row.object_label}；状态：{row.review_status_code}</td>
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
              </div>
            </>
          ) : null}
        </>
      )}

      {entSelected ? (
        <Modal title={`企业详情 · ${entSelected.name}`} onClose={() => setEntSelected(null)}>
          {entDetailLoading ? <div className="empty-state"><Building2 className="spin" size={22} /><strong>正在加载…</strong></div> : (
            <div className="record-detail-form">
              <div className="record-meta">
                <StatusTag tone="success">{entSelected.name}</StatusTag>
                <span>{entSelected.type}</span>
                <span>{entSelected.status}</span>
                <span>{entSelected.code}</span>
              </div>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px 20px', marginBottom: '16px' }}>
                <div><small style={{ color: '#64748b' }}>地区</small><div style={{ fontWeight: 600 }}>{entSelected.province ?? '—'}{entSelected.city ? ` · ${entSelected.city}` : ''}</div></div>
                <div><small style={{ color: '#64748b' }}>行业标签</small><div style={{ fontWeight: 600 }}>{entSelected.industry_text ?? '—'}</div></div>
                <div><small style={{ color: '#64748b' }}>官网</small><div style={{ fontWeight: 600 }}>{entSelected.website ?? '—'}</div></div>
                <div><small style={{ color: '#64748b' }}>别名</small><div style={{ fontWeight: 600 }}>{entSelected.aliases.length ? entSelected.aliases.join('、') : '—'}</div></div>
              </div>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '12px 20px', padding: '12px', background: '#f8fafc', borderRadius: '8px', marginBottom: '12px' }}>
                <div><small style={{ color: '#64748b' }}>JD 总数</small><div style={{ fontWeight: 700, fontSize: '18px' }}>{entSelected.job_count}</div></div>
                <div><small style={{ color: '#64748b' }}>技术维度</small><div style={{ fontWeight: 700, fontSize: '18px' }}>{entSelected.referenced_technology_count}</div></div>
                <div><small style={{ color: '#64748b' }}>关联岗位簇</small><div style={{ fontWeight: 700, fontSize: '18px' }}>{entSelected.cluster_count}</div></div>
              </div>
              <h4 style={{ marginBottom: '8px' }}>高频技术栈（Top {entSelected.top_technologies.length}）</h4>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(150px, 1fr))', gap: '6px', marginBottom: '16px' }}>
                {entSelected.top_technologies.map((t) => (
                  <div key={t.code} style={{ background: t.code ? ((domainColors as Record<string, string>)[t.code.slice(0, 2)] ?? '#f1f5f9') + '22' : '#f8fafc', border: `1px solid ${(domainColors as Record<string, string>)[t.code.slice(0, 2)] ?? '#e2e8f0'}`, borderRadius: '6px', padding: '6px 10px' }}>
                    <div style={{ fontWeight: 600, fontSize: '13px' }}>{t.name}</div>
                    <div style={{ fontSize: '11px', color: '#64748b' }}>{t.code} · JD {t.count}</div>
                  </div>
                ))}
                {entSelected.top_technologies.length === 0 ? <div style={{ color: '#94a3b8' }}>暂无技术维度记录</div> : null}
              </div>
              <h4 style={{ marginBottom: '8px' }}>核心岗位簇（Top {entSelected.top_clusters.length}）</h4>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(200px, 1fr))', gap: '6px' }}>
                {entSelected.top_clusters.map((c) => (
                  <div key={c.code} style={{ background: '#f8fafc', border: '1px solid #e2e8f0', borderRadius: '6px', padding: '6px 10px' }}>
                    <div style={{ fontWeight: 600, fontSize: '13px' }}>{c.label}</div>
                    <div style={{ fontSize: '11px', color: '#64748b' }}>{c.code} · JD {c.job_count}</div>
                  </div>
                ))}
                {entSelected.top_clusters.length === 0 ? <div style={{ color: '#94a3b8' }}>暂无岗位簇记录</div> : null}
              </div>
              <div className="modal-actions"><button type="button" className="secondary-button" onClick={() => setEntSelected(null)}>关闭</button></div>
            </div>
          )}
        </Modal>
      ) : null}

      {capabilityDetail ? (
        <Modal title={`技术词详情 · ${capabilityDetail.code}`} onClose={() => setCapabilityDetail(null)}>
          {detailLoading ? <div className="empty-state"><Network className="spin" size={22} /><strong>正在加载…</strong></div> : (
            <div className="record-detail-form">
              <div className="record-meta">
                <StatusTag tone="success">{capabilityDetail.name}</StatusTag>
                <span>{capabilityDetail.level_code}</span>
                <span>复核状态 {capabilityDetail.review_status_code}</span>
                {capabilityDetail.deprecated ? (
                  <span title="冷门类" style={{ color: '#64748b', fontSize: '12px' }}>
                    <StatusTag tone="danger">冷门类</StatusTag>
                    {capabilityDetail.replaced_by_code ? `替代编码: ${capabilityDetail.replaced_by_code}` : ''}
                  </span>
                ) : null}
              </div>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px 20px', marginBottom: '16px' }}>
                <div><small style={{ color: '#64748b' }}>层级编码</small><div style={{ fontWeight: 600 }}>{capabilityDetail.level_code}</div></div>
                <div><small style={{ color: '#64748b' }}>复核状态</small><div style={{ fontWeight: 600 }}>{capabilityDetail.review_status_code}</div></div>
                <div style={{ gridColumn: '1 / -1' }}>
                  <small style={{ color: '#64748b' }}>定义</small>
                  <div style={{ fontWeight: 500, whiteSpace: 'pre-wrap' }}>{capabilityDetail.definition_text ?? '—'}</div>
                </div>
                <div style={{ gridColumn: '1 / -1' }}>
                  <small style={{ color: '#64748b' }}>别名列表</small>
                  <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px', marginTop: '4px' }}>
                    {capabilityDetail.alias_text.length > 0
                      ? capabilityDetail.alias_text.map((alias, idx) => (
                          <span key={idx} style={{ background: '#f1f5f9', padding: '3px 10px', borderRadius: '12px', fontSize: '13px' }}>{alias}</span>
                        ))
                      : <span style={{ color: '#94a3b8' }}>—</span>}
                  </div>
                </div>
              </div>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '12px 20px', padding: '12px', background: '#f8fafc', borderRadius: '8px', marginBottom: '12px' }}>
                <div><small style={{ color: '#64748b' }}>引用岗位数</small><div style={{ fontWeight: 700, fontSize: '18px' }}>{capabilityDetail.referenced_job_count}</div></div>
                <div><small style={{ color: '#64748b' }}>引用企业数</small><div style={{ fontWeight: 700, fontSize: '18px' }}>{capabilityDetail.referenced_organization_count}</div></div>
                <div><small style={{ color: '#64748b' }}>引用岗位簇数</small><div style={{ fontWeight: 700, fontSize: '18px' }}>{capabilityDetail.referenced_role_cluster_count}</div></div>
              </div>
              <div className="modal-actions"><button type="button" className="secondary-button" onClick={() => setCapabilityDetail(null)}>关闭</button></div>
            </div>
          )}
        </Modal>
      ) : null}
    </div>
  )
}
