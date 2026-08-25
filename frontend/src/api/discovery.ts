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
  /** 支撑该候选的 JD 数。列表接口已下发，此前类型里漏了。 */
  support_job_count: number
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
  existing_role: '已被覆盖',
  existing_candidate: '已有候选',
  role_evolution: '岗位演化',
  library_gap: '岗位库缺失',
  potential_new_role: '潜在新岗位',
  insufficient_evidence: '证据不足',
}

/**
 * 每个分类对应的处置动作。四类候选的下一步完全不同，只给一个分类名不足以让
 * 审核者知道该做什么——尤其是「岗位库缺失」与「潜在新岗位」，前者是补录一个
 * 市场上早已存在的岗位，后者才是定义一个新岗位。
 */
export const classificationGuidance: Record<string, string> = {
  existing_role: '该能力组合已被既有岗位覆盖，且占到对方能力集的大半，视作同一岗位。无需新增定义；可用于核对既有岗位的能力画像是否完整。',
  role_evolution: '候选只是最邻近岗位的一个片段，或仅被部分覆盖。建议并入该岗位，作为其新版本的能力变化。',
  library_gap: '能力组合已经成熟、市场上大量在招，但岗位库里没有收录。动作是补录既有岗位，不是定义新岗位。',
  potential_new_role: '所依托的技术方向尚未全部跨过岗位化门槛。动作是新增岗位定义并持续跟踪。',
}

/**
 * 分类的分母说明——**必须与分类一同呈现**。
 *
 * 既有岗位库由同一批 JD 聚类得到，与候选同源，因此这四个分类衡量的是候选相对
 * **本系统岗位库**的新颖度，不等同于相对整个劳动力市场。实测把可比岗位的画像门槛
 * 从 2 项技术提到 8 项（可比岗位 532 → 66）后，「未被覆盖」的候选始终为 0——
 * 同源基线下该类别不可能非空。不写清楚这一点，读者会把「潜在新岗位」读成
 * 「市场上还没有的岗位」，而那是当前实现给不出的结论。
 */
export const CLASSIFICATION_BASELINE_NOTE =
  '以上分类的参照系是本系统由同一批 JD 聚类得到的岗位库，衡量的是相对该库的新颖度，' +
  '不代表该岗位在劳动力市场上不存在。'

/** 分类对应的展示色调，与 StatusTag 的 tone 取值一致。 */
export const classificationTone: Record<string, 'info' | 'warning' | 'success' | 'neutral'> = {
  existing_role: 'neutral',
  role_evolution: 'info',
  library_gap: 'warning',
  potential_new_role: 'success',
}

/** 评分维度的中文名。原始码直接显示给审核者不可读。 */
export const scoreComponentLabels: Record<string, string> = {
  publication_task_gap: '学术—产业落差',
  market_support: '市场支持度',
  community_cohesion: '技术组合内聚度',
  technology_maturity: '技术成熟度',
  temporal_growth_stability: '时序增长稳定性',
  evidence_completeness: '证据齐备度',
  novelty: '新颖度',
  single_company_penalty: '单一企业惩罚',
  single_source_penalty: '单一来源惩罚',
  marketing_penalty: '纯营销语料惩罚',
  contradiction_penalty: '证据矛盾惩罚',
  unverified_technology_penalty: '技术未经验证惩罚',
}

/**
 * 候选依托的某个 L2 技术方向的前瞻判断。
 *
 * 主语是**技术方向**，不是岗位——候选依托多个方向，岗位能否成立还取决于这些方向
 * 是否被同一批雇主组合进同一个职位，那不在推演的推断范围内。
 */
export interface ForesightDirection {
  technology_code: string
  technology_name: string
  crossed: boolean
  crossing_month: string | null
  peak_maturity: number
  milestone_count: number
  foresight_rank: number
  /** 该方向当前被多少份 JD 提及，以及在全部方向中的名次——描述现状，不是预测。 */
  jd_demand: number
  demand_rank: number | null
  demand_total_directions: number
  statement: string
}

/**
 * 由外部先验推出的参考窗口。
 *
 * **不是本系统的测量结果。** 时滞标定在自有数据上失败（截尾夹逼退化、
 * 秩相关 0.510 于 n=12 不显著、里程碑为回溯整理），窗口 = 最后一个方向成熟的
 * 时点 + 先验时滞。渲染时必须与真实计算出的跨越时点分开，并标明来源。
 */
export interface ForesightReferenceWindow {
  from: string
  to: string
  prior_months: [number, number]
  anchor_month: string
}

/** 最邻近的既有岗位。覆盖率说「有没有新能力」，Jaccard 说「是整个岗位还是它的一块」。 */
export interface NearestRoleCard {
  role_code: string
  role_name: string
  coverage: number
  jaccard: number
  role_technology_count: number
  shared_technology_count: number
}

export interface CandidateForesight {
  schema_version: string
  threshold: number
  /** configured_not_measured 表示门槛是设定值而非实测值，展示时必须说明。 */
  threshold_origin: string
  /** ① 技术地基成型区间：由真实跨越时点算出，零假设。 */
  foundation_from: string | null
  foundation_to: string | null
  foundation_complete: boolean
  foundation_ready_months: number | null
  /** ③ 参考窗口：外部先验，非测量结果。 */
  reference_window: ForesightReferenceWindow | null
  reference_window_origin: string
  reference_window_reason: string
  directions: ForesightDirection[]
  crossed_direction_count: number
  best_foresight_rank: number | null
}
