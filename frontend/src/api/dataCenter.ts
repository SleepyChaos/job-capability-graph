const API_BASE = import.meta.env.VITE_API_BASE_URL ?? '/api/v1'

async function getJson<T>(path: string, signal?: AbortSignal): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, { signal })
  if (!response.ok) {
    const payload = await response.json().catch(() => null)
    throw new Error(payload?.detail ?? `请求失败（${response.status}）`)
  }
  return response.json() as Promise<T>
}

async function postJson<T>(path: string, body: unknown, headers?: Record<string, string>): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...headers },
    body: JSON.stringify(body),
  })
  if (!response.ok) {
    const payload = await response.json().catch(() => null)
    throw new Error(payload?.detail ?? `请求失败（${response.status}）`)
  }
  return response.json() as Promise<T>
}

export interface DataSourceItem {
  source_code: string
  source_name: string
  source_type_code: string
  entry_url: string | null
  content_type_code: string
  default_reliability_score: string | null
  source_status_code: string
}

export interface SourceCreatePayload {
  source_code: string
  source_name: string
  source_type_code: 'recruitment' | 'enterprise' | 'government' | 'research' | 'other'
  entry_url?: string | null
  content_type_code?: 'job' | 'industry' | 'milestone' | 'mixed'
  default_reliability_score: number
}

export interface CollectionPolicy {
  collection_policy_id: number
  source_code: string
  policy_version: string
  max_depth: number
  schedule_cron: string | null
  timezone_name: string
  rate_limit_per_minute: number
  domain_concurrency: number
  robots_status_code: string
  terms_checked: boolean
  is_active: boolean
}

export interface PolicyCreatePayload {
  source_code: string
  policy_version: string
  max_depth?: number
  schedule_cron?: string | null
  rate_limit_per_minute?: number
  robots_status_code?: 'unchecked' | 'allowed' | 'restricted' | 'disallowed'
  terms_checked?: boolean
}

export interface CollectionRun {
  run_code: string
  source_code: string
  policy_version: string
  run_status_code: string
  scheduled_at: string | null
  discovered_count: number
  changed_count: number
  unchanged_count: number
  failed_count: number
  error_summary?: string | null
}

export interface MilestoneItem {
  milestone_code: string
  milestone_name: string
  milestone_type_code: string
  event_date: string | null
  event_year: number
  description_text: string
  maturity_delta_score: string | null
  verification_status_code: string
  technology_codes: string[]
}

export interface MilestonePage {
  total: number
  limit: number
  offset: number
  items: MilestoneItem[]
}

export interface ReviewTask {
  task_code: string
  queue_code: string
  target_type_code: string
  target_id: number
  priority_score: string
  task_status_code: string
  assigned_user_code: string | null
  target_snapshot: Record<string, unknown>
  reason: { codes?: string[]; [key: string]: unknown } | null
}

export type ReviewActionCode = 'claim' | 'approve' | 'reject' | 'needs_revision'

export const dataCenterApi = {
  sources(signal?: AbortSignal) {
    return getJson<DataSourceItem[]>('/sources', signal)
  },
  createSource(payload: SourceCreatePayload) {
    return postJson<DataSourceItem>('/sources', payload)
  },
  policies(signal?: AbortSignal) {
    return getJson<CollectionPolicy[]>('/collection-policies', signal)
  },
  createPolicy(payload: PolicyCreatePayload) {
    return postJson<CollectionPolicy>('/collection-policies', payload)
  },
  runs(signal?: AbortSignal) {
    return getJson<CollectionRun[]>('/collection-runs', signal)
  },
  createRun(payload: { source_code: string; policy_version: string }) {
    return postJson<CollectionRun>('/collection-runs', payload)
  },
  executeRun(runCode: string) {
    return postJson<CollectionRun>(`/collection-runs/${encodeURIComponent(runCode)}/execute`, {})
  },
  milestones(params: { status?: string; limit?: number; offset?: number } = {}, signal?: AbortSignal) {
    const query = new URLSearchParams()
    if (params.status) query.set('status', params.status)
    query.set('limit', String(params.limit ?? 50))
    query.set('offset', String(params.offset ?? 0))
    return getJson<MilestonePage>(`/milestones?${query}`, signal)
  },
  reviews(status: string | null, signal?: AbortSignal) {
    const query = new URLSearchParams()
    if (status) query.set('status', status)
    return getJson<ReviewTask[]>(`/reviews/data?${query}`, signal)
  },
  /** 按审核目标类型路由到对应的审核动作端点（里程碑走数据审核，岗位版本走聚类审核）。 */
  reviewAction(task: ReviewTask, action: ReviewActionCode, reviewerCode: string, comment?: string) {
    const endpoint =
      task.target_type_code === 'job_role_version'
        ? `/job-roles/reviews/${task.task_code}/actions`
        : `/reviews/data/${task.task_code}/actions`
    return postJson<Record<string, unknown>>(
      endpoint,
      { action_code: action, comment_text: comment ?? null },
      { 'X-Reviewer-Code': reviewerCode },
    )
  },
}
