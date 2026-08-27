const API_BASE = import.meta.env.VITE_API_BASE_URL ?? '/api/v1'

async function getJson<T>(path: string, signal?: AbortSignal): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, { signal })
  if (!response.ok) {
    const payload = await response.json().catch(() => null)
    throw new Error(payload?.detail ?? `请求失败（${response.status}）`)
  }
  return response.json() as Promise<T>
}

const MISSING_VERSION_MESSAGE = '技术体系版本不存在'

/**
 * A fresh local database is valid before the first taxonomy workbook is
 * published. The backend keeps the precise 404 contract for API consumers;
 * the UI treats that initialization state as an empty dataset instead of a
 * page-level failure.
 */
async function getTaxonomyOrEmpty<T>(path: string, empty: T, signal?: AbortSignal): Promise<T> {
  try {
    return await getJson<T>(path, signal)
  } catch (error) {
    if (error instanceof Error && error.message === MISSING_VERSION_MESSAGE) return empty
    throw error
  }
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

export interface TechnologyNodeDetail {
  node_id: number
  code: string
  name: string
  level_code: string
  definition_text: string | null
  alias_text: string[]
  deprecated: boolean
  replaced_by_code: string | null
  review_status_code: string
  referenced_job_count: number
  referenced_organization_count: number
  referenced_role_cluster_count: number
  source_sheet: string | null
  source_row_number: number | null
  alias_count: number
  source_job_count: number
  role_cluster_requirement_count: number
}

export interface TaxonomyTreeNode {
  node_id: number
  code: string
  name: string
  level_code: string
  domain_code: string
  parent_code: string | null
  referenced_job_count: number
  referenced_organization_count: number
  referenced_role_cluster_count: number
  children: TaxonomyTreeNode[]
}

export interface TaxonomyTreeResponse {
  version_code: string
  max_depth: string
  total_nodes: number
  root_count: number
  roots: TaxonomyTreeNode[]
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
    return getTaxonomyOrEmpty<TechnologyDomain[]>(`/taxonomy/domains?${query}`, [], signal)
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
    return getTaxonomyOrEmpty<TechnologyNodePage>(
      `/taxonomy/nodes?${query}`,
      { total: 0, limit: params.limit ?? 100, offset: params.offset ?? 0, items: [] },
      signal,
    )
  },
  nodeDetail(code: string, signal?: AbortSignal) {
    return getJson<TechnologyNodeDetail>(`/taxonomy/nodes/${encodeURIComponent(code)}/detail`, signal)
  },
  tree(maxDepth: 'L1' | 'L2' | 'L3' | 'L4' = 'L3', versionCode?: string | null, signal?: AbortSignal) {
    const query = new URLSearchParams({ max_depth: maxDepth })
    if (versionCode) query.set('version_code', versionCode)
    return getJson<TaxonomyTreeResponse>(`/taxonomy/tree?${query}`, signal)
  },
}
