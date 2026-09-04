const API_BASE = import.meta.env.VITE_API_BASE_URL ?? '/api/v1'

async function getJson<T>(path: string, signal?: AbortSignal): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, { signal })
  if (!response.ok) {
    const payload = await response.json().catch(() => null)
    throw new Error(payload?.detail ?? `请求失败（${response.status}）`)
  }
  return response.json() as Promise<T>
}

export interface OrganizationSummary {
  total: number
  enterprise_count: number
  university_count: number
  research_institute_count: number
  government_public_count: number
  job_linked_count: number
}

export interface OrganizationListItem {
  organization_code: string
  institution_ids: string[]
  name: string
  organization_type: string
  country: string | null
  province: string | null
  city: string | null
  website_url: string | null
  recruitment_url: string | null
  industry: string | null
  source: string | null
  job_count: number
}

export interface OrganizationPage {
  total: number
  limit: number
  offset: number
  items: OrganizationListItem[]
}

export const organizationsApi = {
  summary(signal?: AbortSignal) {
    return getJson<OrganizationSummary>('/organizations/summary', signal)
  },
  list(params: { search?: string; limit?: number; offset?: number } = {}, signal?: AbortSignal) {
    const query = new URLSearchParams()
    if (params.search) query.set('search', params.search)
    query.set('limit', String(params.limit ?? 50))
    query.set('offset', String(params.offset ?? 0))
    return getJson<OrganizationPage>(`/organizations?${query}`, signal)
  },
}
