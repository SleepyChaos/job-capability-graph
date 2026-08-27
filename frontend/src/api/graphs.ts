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
  type: 'job_cluster' | 'technology'
  label: string
  domain_code: string
  level_code?: string
  metrics: Record<string, number | null>
  evidence_count: number
}

export interface RelationEdge {
  id: string
  source: string
  target: string
  relation_type: string
  importance: number
  recent_activity: number
  supporting_job_count: number
  coverage_rate: number
  evidence_job_codes: string[]
}

export interface RelationGraphResponse extends GraphMetadata {
  role_nodes: RelationNode[]
  capability_nodes: RelationNode[]
  edges: RelationEdge[]
  filters: {
    cluster_domain_code: string | null
    capability_domain_code: string | null
    capability_level_code: string
    cluster_limit: number
    capabilities_per_cluster: number
    node_budget: number
    min_supporting_job_count: number
    mode: 'overview' | 'focus'
    focus_node_id: string | null
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

export interface JobArchitectureRole {
  role_code: string
  name: string
  direction: string | null
  category: string | null
  cluster_code: string | null
  cluster_name: string | null
  job_count: number
}

export interface JobArchitectureTechnology {
  code: string
  name: string
  level: string
  path: Array<{ level: string; code: string; name: string }>
  job_count: number
  exact_evidence_count: number
  evidence_rate: number
  role_codes: string[]
}

export interface JobArchitectureCompany {
  name: string
  job_count: number
  role_codes: string[]
}

export interface JobArchitectureOverview {
  schema_version: string
  source_version: string
  metadata: {
    job_count: number
    standard_role_count: number
    direction_count: number
    category_count: number
    cluster_count: number
    technology_count: number
    company_count: number
    join_key: string
    hierarchy: string[]
  }
  hierarchy: Record<string, Record<string, Record<string, string[]>>>
  roles: JobArchitectureRole[]
  technologies: JobArchitectureTechnology[]
  companies: JobArchitectureCompany[]
}

export interface JobArchitectureRoleDetail {
  role: JobArchitectureRole & {
    portrait: {
      responsibilities: string[]
      skills: string[]
      capabilities: string[]
      scenarios: string[]
      conditions: string[]
    }
  }
  technologies: Array<JobArchitectureTechnology & { hit_terms: string[] }>
  companies: Array<{ name: string; job_count: number }>
  jobs: Array<{
    occ_id: string
    title: string | null
    company: string | null
    match_confidence: string | null
    match_method: string | null
  }>
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
  jobArchitecture(signal?: AbortSignal) {
    return getJson<JobArchitectureOverview>('/graphs/job-architecture', signal)
  },
  jobArchitectureRole(roleCode: string, signal?: AbortSignal) {
    return getJson<JobArchitectureRoleDetail>(
      `/graphs/job-architecture/roles/${encodeURIComponent(roleCode)}`,
      signal,
    )
  },
  relations(filters: RelationGraphQuery, signal?: AbortSignal) {
    const query = new URLSearchParams({ capability_level_code: filters.capabilityLevelCode ?? 'L2' })
    if (filters.clusterDomainCode) query.set('cluster_domain_code', filters.clusterDomainCode)
    if (filters.capabilityDomainCode) query.set('capability_domain_code', filters.capabilityDomainCode)
    if (filters.clusterLimit) query.set('cluster_limit', String(filters.clusterLimit))
    if (filters.nodeBudget) query.set('node_budget', String(filters.nodeBudget))
    if (filters.minSupportingJobCount) query.set('min_supporting_job_count', String(filters.minSupportingJobCount))
    if (filters.mode) query.set('mode', filters.mode)
    if (filters.focusNodeId) query.set('focus_node_id', filters.focusNodeId)
    return getGraphOrEmpty<RelationGraphResponse>(`/graphs/relations?${query}`, {
      ...emptyMetadata(),
      role_nodes: [],
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
}

export function graphDomainCode(value: string): string | null {
  return value.startsWith('T') ? value.slice(0, 2) : null
}

export function graphLevelCode(value: string): string {
  return value.slice(0, 2)
}
