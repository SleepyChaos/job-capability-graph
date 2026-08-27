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

export const clusteringApi = {
  clusters(params: { limit?: number; offset?: number } = {}, signal?: AbortSignal) {
    const query = new URLSearchParams()
    const limit = params.limit ?? 50
    const offset = params.offset ?? 0
    query.set('limit', String(limit))
    query.set('offset', String(offset))
    return getJson<ClusterPage>(`/job-clusters?${query}`, signal).catch((error: Error) => {
      // A fresh runtime database has no successful clustering snapshot yet;
      // keep overview cards usable while preserving other API failures.
      if (NO_CLUSTERING_RUN_MESSAGES.has(error.message)) return { total: 0, limit, offset, items: [] }
      throw error
    })
  },
}
