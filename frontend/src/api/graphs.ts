export interface GraphLegendItem {
  domain_code: string
  domain_name: string
  color: string
}

export interface GraphMetadata {
  data_version: string
  projection_version: string
  generated_at: string
  target_date: string
  clustering_run_code: string
  evidence_policy: string
  legend: GraphLegendItem[]
}

export interface RelationNode {
  id: string
  /**
   * emerging_candidate 是未入库的提议，与 job_cluster（观测到的岗位归并）同级但性质不同；
   * technology_domain 是产业链图谱引入的技术域节点。
   */
  type: 'job_cluster' | 'technology_domain' | 'technology' | 'emerging_candidate'
  label: string
  domain_code: string
  level_code?: string
  metrics: Record<string, number | null>
  evidence_count: number
  /** 仅候选节点携带，供前端着色与决定能否下钻到数据卡。 */
  classification_code?: string
  maturity_stage_code?: string
  workflow_status_code?: string
  layer?: number
  parent_ids?: string[]
}

export interface RelationEdge {
  id: string
  source: string
  target: string
  /** important_technology = 聚类的实测关联；proposed_technology = 候选的提议关联。 */
  relation_type: string
  importance: number
  recent_activity: number
  supporting_job_count: number
  /** 提议边（proposed_technology）没有覆盖率，后端下发 null。 */
  coverage_rate: number | null
  evidence_job_codes: string[]
}

export interface RelationGraphResponse extends GraphMetadata {
  role_nodes: RelationNode[]
  domain_group_nodes: RelationNode[]
  capability_nodes: RelationNode[]
  edges: RelationEdge[]
  filters: {
    cluster_domain_code: string | null
    capability_domain_code: string | null
    capability_level_code: string
    cluster_limit: number
    capabilities_per_cluster: number
    node_budget: number
    role_budget?: number
    capability_budget?: number
    min_supporting_job_count: number
    mode: 'overview' | 'focus'
    focus_node_id: string | null
    include_candidates?: boolean
    candidate_node_count?: number
  }
  rendering: {
    primary_route?: string
    fallback: string
    layout_owner: string
    semantic_zoom?: boolean
    neighbor_expansion?: boolean
  }
}

export interface RelationGraphQuery {
  clusterDomainCode?: string | null
  capabilityDomainCode?: string | null
  capabilityLevelCode?: string
  clusterLimit?: number
  nodeBudget?: number
  minSupportingJobCount?: number
  mode?: 'overview' | 'focus'
  focusNodeId?: string | null
  /**
   * 是否把新岗位候选画进图。
   *
   * 默认关闭：候选是**未入库的提议**，与观测到的岗位聚类混在一起会让读者分不清
   * 哪些是既有事实。打开后候选以 `emerging_candidate` 类型出现在 role_nodes 里，
   * 边的 relation_type 是 `proposed_technology`（区别于聚类的 important_technology），
   * 供前端画成虚线。
   */
  includeCandidates?: boolean
  /**
   * 候选取数名额，默认由后端定为 80（按分数取前 80，外部证据与库内各半）。
   * 从岗位数据卡定位某一条候选时必须放开——否则目标候选很可能不在这 80 条里，
   * 跳过去会落到一张没有它的图上。
   */
  candidateLimit?: number
  industryStage?: string | null
}

export interface IndustryChainStage {
  code: 'upstream' | 'midstream' | 'downstream' | 'support' | 'unclassified'
  name: string
  color: string
  job_count: number
  organization_count: number
  cluster_count: number
  technology_count: number
  top_organizations: { code: string; name: string; job_count: number }[]
  top_clusters: { code: string; label: string; job_count: number }[]
  categories: { name: string; job_count: number; organization_count: number; cluster_count: number; technology_count: number }[]
}

export interface IndustryChainSummary {
  data_version: string
  target_date: string
  stages: IndustryChainStage[]
}

export interface RelationGraphExpansion extends GraphMetadata {
  role_nodes: RelationNode[]
  capability_nodes: RelationNode[]
  edges: RelationEdge[]
  filters: {
    cluster_domain_code: string | null
    capability_domain_code: string | null
    capability_level_code: string
    min_supporting_job_count: number
    neighbor_limit: number
  }
  expansion: {
    source_node_id: string
    returned_neighbor_count: number
    neighbor_limit: number
    truncated: boolean
  }
  rendering: RelationGraphResponse['rendering']
}

export interface ClusterListItem {
  stable_cluster_code: string
  label: string
  domain_code: string
  member_count: number
  organization_count: number
  capability_count: number
  coherence_score: number | null
}

export interface ClusterListResponse extends GraphMetadata {
  total_active_cluster_count: number
  items: ClusterListItem[]
}

export interface ClusterCapability {
  technology_node_id: number
  technology_code: string
  technology_name: string
  level_code: string
  domain_code: string
  importance: number
  recent_activity: number
  supporting_job_count: number
  mention_count: number
  coverage_rate: number
  last_seen_at: string | null
  evidence_job_codes: string[]
}

export interface ClusterGraphResponse extends GraphMetadata {
  cluster: ClusterListItem & { description: string | null }
  capabilities: ClusterCapability[]
  encoding: Record<string, string>
}

export interface HeatCell {
  metric_date: string
  trigger_document_count: number
  trigger_mention_count: number
}

export interface HeatSeries {
  domain_code: string
  domain_name: string
  color: string
  total_trigger_documents: number
  values: HeatCell[]
}

export interface TechnologyHeatSeries {
  technology_node_id: number
  technology_code: string
  technology_name: string
  level_code: string
  domain_code: string
  total_trigger_documents: number
  values: HeatCell[]
  rows: HeatCell[][]
}

export interface HeatmapResponse extends GraphMetadata {
  window: {
    start_date: string
    end_date: string
    days: number
    observed_date_count: number
    coverage_ratio: number
    data_status: 'complete' | 'partial'
    warning: string | null
  }
  domain_series: HeatSeries[]
  detail_series: TechnologyHeatSeries[]
}

export interface OrgTechGraphResponse {
  filters: {
    capability_domain_code: string | null
    capability_level_code: string
    org_limit: number
    capabilities_per_org: number
    min_supporting_job_count: number
  }
  org_nodes: {
    id: string
    type: 'organization'
    label: string
    code: string
    province?: string | null
    city?: string | null
    org_type: string
    status: string
    layer: number
    metrics: { technology_count: number; job_count: number; domain_count: number }
  }[]
  domain_group_nodes: { id: string; name: string; code: string; color: string; layer: number }[]
  capability_nodes: {
    id: string
    type: 'technology'
    label: string
    code: string
    level_code: string
    domain_code: string
    layer: number
    metrics: { supporting_org_count: number; job_count: number }
  }[]
  edges: {
    id: string
    source: string
    target: string
    relation_type: string
    style?: string
    job_count?: number
  }[]
  layout: { mode: string; rankdir: string }
  layout_mode: string
}

export interface CapabilityToClusterRanking {
  filters: Record<string, unknown>
  total: number
  rows: {
    technology_node_id: number
    technology_code: string
    technology_name: string
    level_code: string
    domain_code: string
    domain_name: string | null
    supporting_job_count: number
    ranked_clusters: {
      code: string
      label: string
      importance: number
      coverage_rate: number
      supporting_job_count: number
    }[]
  }[]
}

export interface TripleAuditSummary {
  audit_run_code: string
  audit_model: string
  sample_scope: string
  total_triples: number
  low_plausibility: number
  medium_plausibility: number
  high_plausibility: number
  auto_suppressed: number
  pending_review: number
  accepted_as_true: number
  false_positive_edge: number
  redirected_edge: number
}

export interface TripleAuditRow {
  triple_id: number
  subject_kind: string
  subject_id: string
  subject_label: string
  predicate: string
  object_kind: string
  object_id: string
  object_label: string
  plausibility_score: number
  plausibility_level: string
  review_status_code: string
  reviewer_code: string | null
  supporting_job_count: number
  component_scores: Record<string, number>
  rule_flags: Record<string, number | string | boolean>
}

export interface TripleAuditResponse {
  summary: TripleAuditSummary
  low_plausibility_rows: TripleAuditRow[]
}

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? '/api/v1'

async function getJson<T>(path: string, signal?: AbortSignal): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, { signal })
  if (!response.ok) {
    const payload = await response.json().catch(() => null)
    throw new Error(payload?.detail ?? `请求失败（${response.status}）`)
  }
  return response.json() as Promise<T>
}

const NO_CLUSTERING_RUN_MESSAGE = '不存在成功的岗位聚类运行'
const EMPTY_DATA_VERSION = 'uninitialized'

const emptyMetadata = (): GraphMetadata => ({
  data_version: EMPTY_DATA_VERSION,
  projection_version: 'graph_projection_p0_v1',
  generated_at: new Date().toISOString(),
  target_date: '',
  clustering_run_code: '',
  evidence_policy: 'accepted_technology_context_only',
  legend: [],
})

function getGraphOrEmpty<T>(path: string, empty: T, signal?: AbortSignal): Promise<T> {
  return getJson<T>(path, signal).catch((error: Error) => {
    // The first clustering run is an optional data-initialization step. A
    // structured empty projection lets graph pages explain that state instead
    // of showing a transport error to the user.
    if (error.message === NO_CLUSTERING_RUN_MESSAGE) return empty
    throw error
  })
}

export const graphApi = {
  relations(filters: RelationGraphQuery, signal?: AbortSignal) {
    const query = new URLSearchParams({ capability_level_code: filters.capabilityLevelCode ?? 'L2' })
    if (filters.clusterDomainCode) query.set('cluster_domain_code', filters.clusterDomainCode)
    if (filters.capabilityDomainCode) query.set('capability_domain_code', filters.capabilityDomainCode)
    if (filters.clusterLimit) query.set('cluster_limit', String(filters.clusterLimit))
    if (filters.nodeBudget) query.set('node_budget', String(filters.nodeBudget))
    if (filters.minSupportingJobCount) query.set('min_supporting_job_count', String(filters.minSupportingJobCount))
    if (filters.mode) query.set('mode', filters.mode)
    if (filters.focusNodeId) query.set('focus_node_id', filters.focusNodeId)
    if (filters.includeCandidates) query.set('include_candidates', 'true')
    // 候选名额与节点预算分开控制：默认只取分数最高的 80 条，够看格局；
    // 从数据卡定位某一条候选时需要放开，否则目标节点可能根本不在这一批里。
    if (filters.candidateLimit) query.set('candidate_limit', String(filters.candidateLimit))
    if (filters.industryStage) query.set('industry_stage', filters.industryStage)
    return getGraphOrEmpty<RelationGraphResponse>(`/graphs/relations?${query}`, {
      ...emptyMetadata(),
      role_nodes: [],
      domain_group_nodes: [],
      capability_nodes: [],
      edges: [],
      filters: {
        cluster_domain_code: null,
        capability_domain_code: null,
        capability_level_code: filters.capabilityLevelCode ?? 'L2',
        cluster_limit: filters.clusterLimit ?? 1000,
        capabilities_per_cluster: 20,
        node_budget: filters.nodeBudget ?? 240,
        min_supporting_job_count: filters.minSupportingJobCount ?? 1,
        mode: filters.mode ?? 'overview',
        focus_node_id: filters.focusNodeId ?? null,
      },
      rendering: {
        primary_route: 'canvas_force',
        fallback: 'edge_table',
        layout_owner: 'frontend_g6_force_worker',
        semantic_zoom: true,
        neighbor_expansion: true,
      },
    }, signal)
  },
  industryChain(signal?: AbortSignal) {
    return getJson<IndustryChainSummary>('/graphs/industry-chain/summary', signal)
  },
  relationNeighbors(nodeId: string, filters: RelationGraphQuery, neighborLimit: number, signal?: AbortSignal) {
    const query = new URLSearchParams({
      capability_level_code: filters.capabilityLevelCode ?? 'L2',
      neighbor_limit: String(neighborLimit),
      min_supporting_job_count: String(filters.minSupportingJobCount ?? 1),
    })
    if (filters.clusterDomainCode) query.set('cluster_domain_code', filters.clusterDomainCode)
    if (filters.capabilityDomainCode) query.set('capability_domain_code', filters.capabilityDomainCode)
    return getJson<RelationGraphExpansion>(`/graphs/relations/${encodeURIComponent(nodeId)}/neighbors?${query}`, signal)
  },
  clusters(signal?: AbortSignal) {
    return getGraphOrEmpty<ClusterListResponse>('/graphs/clusters?limit=30', {
      ...emptyMetadata(),
      total_active_cluster_count: 0,
      items: [],
    }, signal)
  },
  clusterDetail(clusterCode: string, levelCode: string, signal?: AbortSignal) {
    const query = new URLSearchParams({ level_code: levelCode, capability_limit: '20' })
    return getGraphOrEmpty<ClusterGraphResponse>(
      `/graphs/clusters/${encodeURIComponent(clusterCode)}?${query}`,
      {
        ...emptyMetadata(),
        cluster: {
          stable_cluster_code: clusterCode,
          label: '',
          domain_code: 'T7',
          member_count: 0,
          organization_count: 0,
          capability_count: 0,
          coherence_score: null,
          description: null,
        },
        capabilities: [],
        encoding: {},
      },
      signal,
    )
  },
  heatmap(domainCode: string | null, levelCode: string, signal?: AbortSignal) {
    const query = new URLSearchParams({ level_code: levelCode })
    if (domainCode) query.set('domain_code', domainCode)
    return getGraphOrEmpty<HeatmapResponse>(`/graphs/heatmap?${query}`, {
      ...emptyMetadata(),
      window: {
        start_date: '',
        end_date: '',
        days: 45,
        observed_date_count: 0,
        coverage_ratio: 0,
        data_status: 'partial',
        warning: '尚未生成成功的岗位聚类快照，暂时没有可展示的热力数据。',
      },
      domain_series: [],
      detail_series: [],
    }, signal)
  },
  orgTechGraph(params: {
    capabilityDomainCode?: string | null
    capabilityLevelCode?: string
    orgLimit?: number
    capabilitiesPerOrg?: number
    minSupportingJobCount?: number
    industryStage?: string | null
  }, signal?: AbortSignal) {
    const query = new URLSearchParams({
      capability_level_code: params.capabilityLevelCode ?? 'L2',
      org_limit: String(params.orgLimit ?? 40),
      capabilities_per_org: String(params.capabilitiesPerOrg ?? 20),
      min_supporting_job_count: String(params.minSupportingJobCount ?? 1),
    })
    if (params.capabilityDomainCode) query.set('capability_domain_code', params.capabilityDomainCode)
    if (params.industryStage) query.set('industry_stage', params.industryStage)
    return getJson<OrgTechGraphResponse>(`/graphs/org-tech?${query}`, signal)
  },
  capabilityToClusters(params: {
    capabilityDomainCode?: string | null
    capabilityLevelCode?: string
    minSupportingJobCount?: number
    limit?: number
  }, signal?: AbortSignal) {
    const query = new URLSearchParams({
      capability_level_code: params.capabilityLevelCode ?? 'L2',
      min_supporting_job_count: String(params.minSupportingJobCount ?? 1),
      limit: String(params.limit ?? 300),
    })
    if (params.capabilityDomainCode) query.set('capability_domain_code', params.capabilityDomainCode)
    return getJson<CapabilityToClusterRanking>(`/graphs/capability-to-clusters?${query}`, signal)
  },
  tripleAuditLatest(auditRunCode?: string, signal?: AbortSignal) {
    const query = auditRunCode ? `?audit_run_code=${encodeURIComponent(auditRunCode)}` : ''
    return getJson<TripleAuditResponse>(`/graphs/triple-audit/latest${query}`, signal)
  },
}

export function graphDomainCode(value: string): string | null {
  return value.startsWith('T') ? value.slice(0, 2) : null
}

export function graphLevelCode(value: string): string {
  return value.slice(0, 2)
}
