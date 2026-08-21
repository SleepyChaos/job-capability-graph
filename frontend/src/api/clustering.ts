const API_BASE = import.meta.env.VITE_API_BASE_URL ?? '/api/v1'

async function getJson<T>(path: string, signal?: AbortSignal): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, { signal })
  if (!response.ok) {
    const payload = await response.json().catch(() => null)
    throw new Error(payload?.detail ?? `请求失败（${response.status}）`)
  }
  return response.json() as Promise<T>
}

const NO_CLUSTERING_RUN_MESSAGES = new Set([
  '没有可用的岗位聚类运行',
  '不存在成功的岗位聚类运行',
])

export interface ClusterListItem {
  stable_cluster_code: string
  label: string
  member_count: number
  organization_count: number
  coherence_score: string | null
  status: string
  primary_domain_code: string | null
  candidate_role_code: string | null
}

export interface ClusterPage {
  total: number
  limit: number
  offset: number
  items: ClusterListItem[]
}

export interface ClusterMemberItem {
  job_code: string
  title: string
  company: string | null
  source_collected_at_date: string | null
  technology_evidence_count: number
  similarity_score: string
  assignment_status: string
  assignment_confidence: string | null
  is_representative: boolean
  top_candidates: unknown[]
}

export interface ClusterCapabilityRankingItem {
  technology_code: string
  technology_name: string
  requirement_type: string
  supporting_job_count: number
  organization_count: number
  importance_weight: string
  coverage_rate: string | null
}

export interface ClusterDetail extends ClusterListItem {
  description: string | null
  centroid: Record<string, unknown>
  members: ClusterMemberItem[]
  capability_rankings: ClusterCapabilityRankingItem[]
  grey_zone_member_count: number
  grey_zone_representative_titles: string[]
}

export const clusteringApi = {
  clusters(params: { limit?: number; offset?: number } = {}, signal?: AbortSignal) {
    const query = new URLSearchParams()
    const limit = params.limit ?? 50
    const offset = params.offset ?? 0
    query.set('limit', String(limit))
    query.set('offset', String(offset))
    return getJson<ClusterPage>(`/job-clusters?${query}`, signal).catch((error: Error) => {
      if (NO_CLUSTERING_RUN_MESSAGES.has(error.message)) return { total: 0, limit, offset, items: [] }
      throw error
    })
  },
  clusterDetail(code: string, signal?: AbortSignal) {
    return getJson<ClusterDetail>(`/job-clusters/${encodeURIComponent(code)}`, signal)
  },
}
