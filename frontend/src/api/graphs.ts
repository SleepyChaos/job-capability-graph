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
  rendering: { fallback: string; layout_owner: string }
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
  relations(domainCode: string | null, levelCode: string, signal?: AbortSignal) {
    const query = new URLSearchParams({ level_code: levelCode })
    if (domainCode) query.set('domain_code', domainCode)
    return getGraphOrEmpty<RelationGraphResponse>(`/graphs/relations?${query}`, {
      ...emptyMetadata(),
      role_nodes: [],
      capability_nodes: [],
      edges: [],
      rendering: { fallback: 'edge_table', layout_owner: 'frontend_deterministic_radial' },
    }, signal)
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
