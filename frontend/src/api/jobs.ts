const API_BASE = import.meta.env.VITE_API_BASE_URL ?? '/api/v1'

async function getJson<T>(path: string, signal?: AbortSignal): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, { signal })
  if (!response.ok) {
    const payload = await response.json().catch(() => null)
    throw new Error(payload?.detail ?? `请求失败（${response.status}）`)
  }
  return response.json() as Promise<T>
}

export interface JobSummary {
  total_jobs: number
  organization_count: number
  source_count: number
  unique_content_count: number
  duplicate_group_count: number
  duplicate_member_count: number
  source_timed_count: number
  migration_timed_count: number
  technology_covered_job_count: number
  requirement_count: number
}

export interface JobListItem {
  job_code: string
  source_job_id: string | null
  title: string
  company: string | null
  level: string | null
  region: string | null
  education: string | null
  experience: string | null
  source_collected_at: string | null
  time_quality: string
  evidence_weight: string
  technology_count: number
  duplicate_group_code: string | null
}

export interface JobPage {
  total: number
  limit: number
  offset: number
  items: JobListItem[]
}

export interface JobTechnologyRequirement {
  requirement_no: number
  requirement_type: string
  technology_code: string
  technology_name: string
  raw_term: string | null
  mention_count: number
  confidence: string
  evidence: string[]
  assessment_status: string | null
  ambiguity_reason_label: string | null
}

export interface JobDetail extends JobListItem {
  level_code: string | null
  time_quality_code: string | null
  source_collected_at_date: string | null
  published_at_date: string | null
  duplicate_group_code: string | null
  parse_status_code: string | null
  review_required: boolean
  ambiguity_review_count: number
  salary: string | null
  jd_text: string
  source_codes: string[]
  technologies: JobTechnologyRequirement[]
  scenarios: string[]
  career_direction: string | null
  career_type: string | null
  industry_chain_level: string | null
  company_subfield: string | null
  funding_round: string | null
  company_region: string | null
  company_headquarters_city: string | null
  source_skill_tags: string | null
  source_url: string | null
}

export const jobsApi = {
  summary(signal?: AbortSignal) {
    return getJson<JobSummary>('/jobs/summary', signal)
  },
  list(
    params: { search?: string; level?: string; timeQuality?: string; limit?: number; offset?: number } = {},
    signal?: AbortSignal,
  ) {
    const query = new URLSearchParams()
    if (params.search) query.set('search', params.search)
    if (params.level) query.set('level', params.level)
    if (params.timeQuality) query.set('time_quality', params.timeQuality)
    query.set('limit', String(params.limit ?? 50))
    query.set('offset', String(params.offset ?? 0))
    return getJson<JobPage>(`/jobs?${query}`, signal)
  },
  detail(jobCode: string, signal?: AbortSignal) {
    return getJson<JobDetail>(`/jobs/${encodeURIComponent(jobCode)}`, signal)
  },
}
