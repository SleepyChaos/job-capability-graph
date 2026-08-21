const API_BASE = import.meta.env.VITE_API_BASE_URL ?? '/api/v1'

async function getJson<T>(path: string, signal?: AbortSignal): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, { signal })
  if (!response.ok) {
    const payload = await response.json().catch(() => null)
    throw new Error(payload?.detail ?? `请求失败（${response.status}）`)
  }
  return response.json() as Promise<T>
}

export interface OrganizationListItem {
  code: string
  name: string
  type: string
  province: string | null
  city: string | null
  status: string
  aliases_preview: string[]
  job_count: number
  referenced_technology_count: number
  cluster_count: number
  min_match_score: number | null
  needs_review: boolean
}

export interface OrganizationPage {
  total: number
  limit: number
  offset: number
  items: OrganizationListItem[]
}

export interface OrganizationDetail {
  code: string
  name: string
  normalized_name: string
  type: string
  province: string | null
  city: string | null
  website: string | null
  industry_text: string | null
  status: string
  aliases: string[]
  job_count: number
  cluster_count: number
  referenced_technology_count: number
  top_technologies: { code: string; name: string; count: number }[]
  top_clusters: { code: string; label: string; job_count: number }[]
  splink_meta: Record<string, unknown> | null
}

export interface CrossValidationReport {
  summary: {
    entity_count: number
    matched_entity_count: number
    category_counts: Record<string, number>
    status_counts: Record<string, number>
    talent_count: number
    organization_talent_edges: number
    organization_technology_edges: number
  }
  rows: Array<{
    org_code: string
    org_name: string
    org_category: string
    province: string | null
    city: string | null
    source_count: number
    splink_match_score: number
    external_alignment_rate: number
    status: string
    consistency_score: number
    business_chain: string | null
    patent_domain_codes: string | null
    jd_chain: string | null
    matched_dimensions: number
    missing_dimensions: string[]
    calculated_at: string | null
  }>
  limit: number
  offset: number
}

export const organizationsApi = {
  list(params: {
    search?: string
    orgType?: string
    onlyNeedsReview?: boolean
    withJobsOnly?: boolean
    limit?: number
    offset?: number
  } = {}, signal?: AbortSignal) {
    const query = new URLSearchParams({
      limit: String(params.limit ?? 50),
      offset: String(params.offset ?? 0),
    })
    if (params.search) query.set('search', params.search)
    if (params.orgType) query.set('org_type', params.orgType)
    if (params.onlyNeedsReview) query.set('only_needs_review', '1')
    if (params.withJobsOnly) query.set('with_jobs_only', '1')
    return getJson<OrganizationPage>(`/organizations?${query}`, signal)
  },
  detail(code: string, signal?: AbortSignal) {
    return getJson<OrganizationDetail>(`/organizations/${encodeURIComponent(code)}`, signal)
  },
  crossValidation(params: { status?: string; limit?: number; offset?: number } = {}, signal?: AbortSignal) {
    const query = new URLSearchParams({
      limit: String(params.limit ?? 100),
      offset: String(params.offset ?? 0),
    })
    if (params.status) query.set('status', params.status)
    return getJson<CrossValidationReport>(`/organizations/cross-validation/report?${query}`, signal)
  },
}
