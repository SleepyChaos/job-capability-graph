const API_BASE = import.meta.env.VITE_API_BASE_URL ?? '/api/v1'

async function getJson<T>(path: string, signal?: AbortSignal): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, { signal })
  if (!response.ok) {
    const payload = await response.json().catch(() => null)
    throw new Error(payload?.detail ?? `请求失败（${response.status}）`)
  }
  return response.json() as Promise<T>
}

export interface TaxonomyVersion {
  version_code: string
  version_name: string
  effective_date: string
  status: string
  node_count: number
}

export interface TechnologyDomain {
  code: string
  name: string
  definition: string | null
  color: string | null
  sort_order: number
  node_count: number
}

export interface TechnologyNode {
  node_id: number
  code: string
  name: string
  normalized_name: string
  level: string
  parent_code: string | null
  domain_code: string
  domain_name: string
  domain_color: string | null
  semantic_role: string | null
  alias_count: number
  source_sheet: string
  source_row_number: number
}

export interface TechnologyNodePage {
  total: number
  limit: number
  offset: number
  items: TechnologyNode[]
}

let domainCache: Promise<TechnologyDomain[]> | null = null

/** 模块级缓存的领域列表，供图例/筛选等轻量组件复用。 */
export function cachedDomains(): Promise<TechnologyDomain[]> {
  if (!domainCache) {
    domainCache = taxonomyApi.domains(null).catch((error) => {
      domainCache = null
      throw error
    })
  }
  return domainCache
}

export const taxonomyApi = {
  versions(signal?: AbortSignal) {
    return getJson<TaxonomyVersion[]>('/taxonomy/versions', signal)
  },
  domains(versionCode: string | null, signal?: AbortSignal) {
    const query = new URLSearchParams()
    if (versionCode) query.set('version_code', versionCode)
    return getJson<TechnologyDomain[]>(`/taxonomy/domains?${query}`, signal)
  },
  nodes(
    params: { level?: string; domainCode?: string | null; search?: string; limit?: number; offset?: number } = {},
    signal?: AbortSignal,
  ) {
    const query = new URLSearchParams()
    if (params.level) query.set('level', params.level)
    if (params.domainCode) query.set('domain_code', params.domainCode)
    if (params.search) query.set('search', params.search)
    query.set('limit', String(params.limit ?? 100))
    query.set('offset', String(params.offset ?? 0))
    return getJson<TechnologyNodePage>(`/taxonomy/nodes?${query}`, signal)
  },
}
