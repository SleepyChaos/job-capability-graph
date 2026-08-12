const API_BASE = import.meta.env.VITE_API_BASE_URL ?? '/api/v1'

async function getJson<T>(path: string, signal?: AbortSignal): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, { signal })
  if (!response.ok) {
    const payload = await response.json().catch(() => null)
    throw new Error(payload?.detail ?? `请求失败（${response.status}）`)
  }
  return response.json() as Promise<T>
}

async function sendJson<T>(method: 'POST' | 'PUT', path: string, body: unknown, headers?: Record<string, string>): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    method,
    headers: { 'Content-Type': 'application/json', ...headers },
    body: JSON.stringify(body),
  })
  if (!response.ok) {
    const payload = await response.json().catch(() => null)
    throw new Error(payload?.detail ?? `请求失败（${response.status}）`)
  }
  return response.json() as Promise<T>
}

export type DiscoveryMode = 'automatic' | 'technology_directed' | 'name_inference'

export interface DiscoveryRun {
  run_code: string
  mode_code: DiscoveryMode
  target_date: string
  run_status_code: string
  candidate_count: number
  task_count: number
  evidence_limited: boolean
  already_completed?: boolean
}

export interface DiscoveryRunDetail {
  run_code: string
  mode_code: DiscoveryMode
  target_date: string
  run_status_code: string
  query_role_name: string | null
  input_snapshot: Record<string, unknown> | null
  result_summary: Record<string, unknown> | null
  created_at: string | null
}

export interface CandidateListItem {
  candidate_code: string
  proposed_name: string
  maturity_stage_code: string
  workflow_status_code: string
  candidate_score: string
  classification_code: string
  risk_flags: string[]
  run_code: string
}

export interface CandidatePage {
  total: number
  items: CandidateListItem[]
}

export interface CandidateTechnology {
  technology_code: string
  technology_name: string
  requirement_type: string
  importance: number
  evidence_count: number
}

export interface ScoreComponent {
  component_code: string
  component_type_code: string
  raw_score: number
  weight: number
  weighted_score: number
}

export interface CandidateSnapshot {
  candidate_code: string
  proposed_name: string
  maturity_stage_code: string
  workflow_status_code: string
  candidate_score: number
  classification_code: string
  risk_flags: string[]
  mechanical_card: Record<string, unknown>
  expression: Record<string, unknown> | null
  approved_role_id: number | null
  technologies: CandidateTechnology[]
  score_components: ScoreComponent[]
}

export interface StandardJdItem {
  standard_jd_code: string
  version_no: number
  title: string
  content: Record<string, unknown>
  is_market_evidence: boolean
}

export interface CandidateDetail {
  candidate: CandidateSnapshot
  run: {
    run_code: string
    mode_code: DiscoveryMode
    target_date: string
    input_snapshot: Record<string, unknown> | null
    result_summary: Record<string, unknown> | null
  }
  review_task_code: string | null
  standard_jds: StandardJdItem[]
}

export interface RunCreatePayload {
  mode_code: DiscoveryMode
  target_date: string
  selected_technology_ids?: number[]
  query_role_name?: string
  query_description?: string
}

export const discoveryApi = {
  runs(modeCode: DiscoveryMode | null, signal?: AbortSignal) {
    const query = new URLSearchParams({ limit: '50' })
    if (modeCode) query.set('mode_code', modeCode)
    return getJson<DiscoveryRun[]>(`/role-discovery/runs?${query}`, signal)
  },
  runDetail(runCode: string, signal?: AbortSignal) {
    return getJson<DiscoveryRunDetail>(`/role-discovery/runs/${encodeURIComponent(runCode)}`, signal)
  },
  createRun(payload: RunCreatePayload) {
    return sendJson<DiscoveryRun>('POST', '/role-discovery/runs', payload)
  },
  candidates(
    params: { workflowStatus?: string; maturityStage?: string; runCode?: string; limit?: number; offset?: number } = {},
    signal?: AbortSignal,
  ) {
    const query = new URLSearchParams()
    if (params.workflowStatus) query.set('workflow_status', params.workflowStatus)
    if (params.maturityStage) query.set('maturity_stage', params.maturityStage)
    if (params.runCode) query.set('run_code', params.runCode)
    query.set('limit', String(params.limit ?? 50))
    query.set('offset', String(params.offset ?? 0))
    return getJson<CandidatePage>(`/role-discovery/candidates?${query}`, signal)
  },
  candidateDetail(candidateCode: string, signal?: AbortSignal) {
    return getJson<CandidateDetail>(`/role-discovery/candidates/${encodeURIComponent(candidateCode)}`, signal)
  },
  reviewAction(taskCode: string, action: 'claim' | 'approve' | 'reject' | 'needs_revision', reviewerCode: string, comment?: string) {
    return sendJson<CandidateSnapshot>(
      'POST',
      `/role-discovery/reviews/${encodeURIComponent(taskCode)}/actions`,
      { action_code: action, comment_text: comment ?? null },
      { 'X-Reviewer-Code': reviewerCode },
    )
  },
  autoExpression(candidateCode: string, reviewerCode: string) {
    return sendJson<CandidateSnapshot>(
      'POST',
      `/role-discovery/candidates/${encodeURIComponent(candidateCode)}/expression/auto`,
      {},
      { 'X-Reviewer-Code': reviewerCode },
    )
  },
}

export const maturityStageLabels: Record<string, string> = {
  potential: '潜在岗位',
  budding: '萌芽岗位',
  emerging: '新兴岗位',
  confirmed: '已确认',
}

export const workflowStatusLabels: Record<string, string> = {
  pending: '待审批',
  reviewing: '审批中',
  needs_revision: '需修改',
  approved: '已批准',
  rejected: '已驳回',
  merged: '已归并',
}

export const classificationLabels: Record<string, string> = {
  new_role_candidate: '新岗位候选',
  existing_role: '已有岗位',
  existing_candidate: '已有候选',
  potential_new_role: '潜在新岗位',
  insufficient_evidence: '证据不足',
}
