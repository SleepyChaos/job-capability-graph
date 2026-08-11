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

export const graphApi = {
  relations(domainCode: string | null, levelCode: string, signal?: AbortSignal) {
    const query = new URLSearchParams({ level_code: levelCode })
    if (domainCode) query.set('domain_code', domainCode)
    return getJson<RelationGraphResponse>(`/graphs/relations?${query}`, signal)
  },
  clusters(signal?: AbortSignal) {
    return getJson<ClusterListResponse>('/graphs/clusters?limit=30', signal)
  },
  clusterDetail(clusterCode: string, levelCode: string, signal?: AbortSignal) {
    const query = new URLSearchParams({ level_code: levelCode, capability_limit: '20' })
    return getJson<ClusterGraphResponse>(
      `/graphs/clusters/${encodeURIComponent(clusterCode)}?${query}`,
      signal,
    )
  },
  heatmap(domainCode: string | null, levelCode: string, signal?: AbortSignal) {
    const query = new URLSearchParams({ level_code: levelCode })
    if (domainCode) query.set('domain_code', domainCode)
    return getJson<HeatmapResponse>(`/graphs/heatmap?${query}`, signal)
  },
}

export function graphDomainCode(value: string): string | null {
  return value.startsWith('T') ? value.slice(0, 2) : null
}

export function graphLevelCode(value: string): string {
  return value.slice(0, 2)
}
