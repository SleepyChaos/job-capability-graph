const API_BASE = import.meta.env.VITE_API_BASE_URL ?? '/api/v1'

async function getJson<T>(path: string, signal?: AbortSignal): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, { signal })
  if (!response.ok) {
    const payload = await response.json().catch(() => null)
    throw new Error(payload?.detail ?? `请求失败（${response.status}）`)
  }
  return response.json() as Promise<T>
}

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

export const clusteringApi = {
  clusters(params: { limit?: number; offset?: number } = {}, signal?: AbortSignal) {
    const query = new URLSearchParams()
    query.set('limit', String(params.limit ?? 50))
    query.set('offset', String(params.offset ?? 0))
    return getJson<ClusterPage>(`/job-clusters?${query}`, signal)
  },
}
