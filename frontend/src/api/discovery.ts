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

/**
 * 前三种由界面触发；后两种读 JD 之外的语料（论文/专利、产业里程碑），
 * 目前只能由离线工具跑，但运行记录会回到同一张表，因此类型必须包含它们
 * ——否则记录库拿到这两类运行时会在类型上说不通。
 */
export type DiscoveryMode =
  | 'automatic'
  | 'technology_directed'
  | 'name_inference'
  | 'upstream_gap'
  | 'milestone_gap'

/** 可由界面发起的模式。`createRun` 只接受这三种。 */
export type RunnableDiscoveryMode = 'automatic' | 'technology_directed' | 'name_inference'

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
  /**
   * 缺口分级。**只有外部证据类（研究侧/里程碑）才有**——它衡量的是
   * 「这个技术组合在招聘市场上从未共现」这件事有多可信。库内四类的参照系是
   * 自产岗位库，没有这个量，因此为 null，而不是补一个看起来同类、实则不同义的值。
   */
  gap_grade: string | null
  /** 已入库候选对应的正式岗位。未入库时为 null。 */
  approved_role_code: string | null
  approved_role_name: string | null
  /** 入库时间。候选表没有独立的审批时间字段，取的是最后一次更新时间。 */
  approved_at: string | null
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
  // 只能是可由界面发起的三种。缺口分析读 JD 之外的语料，走离线工具。
  mode_code: RunnableDiscoveryMode
  target_date: string
  selected_technology_ids?: number[]
  query_role_name?: string
  query_description?: string
}

/** 上游候选的证据条目：一组技术对在论文与专利语料中的共现情况。 */
export type UpstreamEvidencePair = {
  pair: string[]
  upstream_cooccurrence: number
  established_month: string
  grade: string
}

/**
 * 把锚点月份平移若干个月。`2026-08` + 8 → `2027-04`。
 *
 * 参考区间此前显示成「8–12 个月」，读者得拿锚点自己心算。信息量相同，
 * 但要多做一步换算，且换算结果才是他真正想看的东西。
 */
export function shiftMonth(anchor: string, months: number): string {
  const year = Number(anchor.slice(0, 4))
  const month = Number(anchor.slice(5, 7))
  if (!year || !month) return anchor
  const total = month - 1 + Math.round(months)
  return `${year + Math.floor(total / 12)}-${String((total % 12) + 1).padStart(2, '0')}`
}

/**
 * 由锚点与时滞先验推出的岗位涌现参考区间。
 *
 * `expired` 是必须一起返回的：候选里有锚点落在 2019–2021 的（缺口开了多年仍未
 * 闭合），平移后区间整个落在过去。把一段已经过去的时间当作「预计涌现区间」
 * 展示是自相矛盾的，界面必须标出来，让审阅者知道该读成
 * 「按先验早该出现却没出现」而不是「即将出现」。
 */
export function emergenceWindow(
  anchor: string | null | undefined,
  lag: TransmissionLagPrior | null,
): { from: string; to: string; expired: boolean } | null {
  if (!anchor || !lag || lag.low_months == null || lag.high_months == null) return null
  const from = shiftMonth(anchor, lag.low_months)
  const to = shiftMonth(anchor, lag.high_months)
  const now = new Date()
  const current = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`
  return { from, to, expired: to < current }
}

/** 传导时滞先验。外部文献推出，本系统的 U-3 回测不支持其前提，展示时必须标注。 */
export type TransmissionLagPrior = {
  status: string
  low_months: number
  high_months: number
  coefficient: number
  technology_classes: string[]
}

/**
 * 候选的支撑招聘文本。
 *
 * 事实卡里的证据编号是**证据片段**编号，读者展开后只能看到一串数字。
 * 这里把它解析成岗位标题、企业与日期，让「凭什么提出这条候选」可查到具体文本。
 */
export type CandidateEvidenceItem = {
  job_code: string
  title: string
  company: string | null
  region: string | null
  published_at: string | null
  collected_at: string | null
}

export type CandidateEvidencePage = {
  total: number
  items: CandidateEvidenceItem[]
}

/** 里程碑候选的证据条目：一个有日期、有主体的具体产业事件。 */
export type MilestoneEvidence = {
  milestone_code: string
  milestone_name: string | null
  milestone_type_code: string | null
  event_date: string
}

/** 里程碑事件类型的中文名。原始码直接显示给审阅者不可读。 */
export const milestoneTypeLabels: Record<string, string> = {
  paper: '论文',
  product_release: '产品发布',
  breakthrough: '技术突破',
  open_source: '开源',
  platform_release: '平台发布',
  standard_policy: '标准/政策',
  technology_demo: '技术演示',
  enterprise_application: '企业应用',
  other: '其它',
}

/**
 * C 级待核查技术点。
 *
 * 缺口分析把技术对分成 A/B/C 三级，C 级的判据是「至少一侧技术在全部 JD 中一次都没
 * 出现过」。这有两种互斥解释——该技术在招聘市场上尚未出现（正是新岗位信号），
 * 或语料域偏离（上游谈的东西与本市场无关）。**本系统区分不了这两者**，所以不做
 * 自动裁决，交人工判断一次即可：96 对 C 级背后只有 23 个技术点。
 */
export type UnverifiedTechnology = {
  technology_code: string
  technology_name: string
  max_upstream_cooccurrence: number
  pair_count: number
  earliest_established: string | null
  partner_codes: string[]
  partner_names: string[]
}

export type UnverifiedTechnologyPage = {
  run_code: string | null
  generated_at: string | null
  note: string
  items: UnverifiedTechnology[]
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
  candidateEvidence(candidateCode: string, signal?: AbortSignal) {
    return getJson<CandidateEvidencePage>(
      `/role-discovery/candidates/${encodeURIComponent(candidateCode)}/evidence`,
      signal,
    )
  },
  unverifiedTechnologies(signal?: AbortSignal) {
    return getJson<UnverifiedTechnologyPage>('/role-discovery/unverified-technologies', signal)
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
  upstream_signal: '研究侧领先信号',
  milestone_signal: '产业里程碑信号',
  insufficient_evidence: '证据不足',
}

/**
 * 本类候选与其余几类的**证据来源根本不同**，因此在界面上必须分区陈列。
 *
 * 其余分类的分母是本系统由 JD 聚类得到的岗位库，回答「这个能力组合在岗位库里有没有
 * 对应」；`upstream_signal` 来自论文与专利语料中已成形、而 JD 中从未出现的技术组合，
 * 回答「研究侧已经在一起做的事，招聘侧还没有」。混在一个列表里，读者无从判断
 * 某一条的「新」是相对岗位库而言还是相对招聘市场而言。
 *
 * `milestone_signal` 与 `upstream_signal` 问的是同一个问题，**但证据能指到的东西
 * 不同**：前者指向具体的、有日期有主体的产业事件（某公司某天发布了什么），
 * 后者只能给出「两个技术在 N 篇文献里一起出现过」。前者不受语料域偏离影响
 * （里程碑是人工筛过的具身智能事件），后者会——上游路径的「强化学习 + 无人机」
 * 多半就是 arXiv 的无人机研究占比过高造成的假象。两者互补，因此并列而不合并。
 */
export const UPSTREAM_SIGNAL_CLASSIFICATION = 'upstream_signal'
export const MILESTONE_SIGNAL_CLASSIFICATION = 'milestone_signal'

/** 证据来自招聘语料之外的候选。它们的 JD 支撑恒为 0，事实位与处置动作都要另给。 */
export const EXTERNAL_EVIDENCE_CLASSIFICATIONS = new Set([
  UPSTREAM_SIGNAL_CLASSIFICATION,
  MILESTONE_SIGNAL_CLASSIFICATION,
])

/**
 * 每个分类对应的处置动作。四类候选的下一步完全不同，只给一个分类名不足以让
 * 审核者知道该做什么——尤其是「岗位库缺失」与「潜在新岗位」，前者是补录一个
 * 市场上早已存在的岗位，后者才是定义一个新岗位。
 */
export const classificationGuidance: Record<string, string> = {
  existing_role: '该能力组合已被既有岗位覆盖，且占到对方能力集的大半，视作同一岗位。无需新增定义；可用于核对既有岗位的能力画像是否完整。',
  role_evolution: '候选只是最邻近岗位的一个片段，或仅被部分覆盖。建议并入该岗位，作为其新版本的能力变化。',
  library_gap: '能力组合已经成熟、市场上大量在招，但岗位库里没有收录。动作是补录既有岗位，不是定义新岗位。',
  upstream_signal: '该技术组合在论文与专利中已反复出现，但招聘市场上从未有岗位同时要求它们。这是待核查的信号，不是已存在的岗位——需要人工判断该组合是否确实会形成岗位。',
  potential_new_role: '所依托的技术方向尚未全部跨过岗位化门槛。动作是新增岗位定义并持续跟踪。',
  milestone_signal: '该技术组合已经出现在具体的产业里程碑事件中（产品发布、技术突破、开源等），但招聘市场上从未有岗位同时要求它们。里程碑证明该组合在产业侧已经存在，不证明有人在为它招聘——需要人工判断。',
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
/**
 * 分类色。**与缺口分级色是两套独立的语义**，不能共用色阶：
 * 分类回答「这是什么」，分级回答「证据有多硬」。同一张卡上两个色标各说一件事，
 * 用同一组颜色会让读者以为它们在说同一件事。
 *
 * 家族 B（里程碑/研究侧）给暖色与青色——参照系是招聘市场，是真正的「发现」；
 * 家族 A 给蓝灰系——参照系是自产岗位库，越靠后越不需要动作。
 */
export const classificationColor: Record<string, { fg: string; bg: string; dot: string }> = {
  milestone_signal: { fg: '#1f6b3f', bg: '#eaf6ee', dot: '#2f9457' },
  upstream_signal: { fg: '#0a6f68', bg: '#e6f5f3', dot: '#0b9c93' },
  potential_new_role: { fg: '#6b3fa0', bg: '#f2ecfa', dot: '#8455c4' },
  library_gap: { fg: '#8a5a11', bg: '#fdf3e3', dot: '#d9962a' },
  role_evolution: { fg: '#1c4d86', bg: '#eaf2fd', dot: '#3b7dd8' },
  existing_role: { fg: '#5a6b7e', bg: '#eff2f6', dot: '#8fa0b3' },
}

/**
 * 证据强度色标——每张候选卡的**第一个**色标。
 *
 * 两处改动的理由：
 *
 * **一、不用 A/B 字母。** 字母等级本身不表意，读者得先去查表才知道 A 比 B 强在
 * 哪里，而它们的差别恰恰是可以一句话说清的：A 是「这个组合从没被合招过，
 * 且不可能是巧合」，B 是「从没被合招过，但样本量不足以排除巧合」。
 * 直接把这句话写进标签。
 *
 * **二、库内四类也要有第一色标。** 此前它们这一格是空的，看起来像「漏了个标签」
 * 而不是「另一种东西」。实际差别是**参照系**：带缺口标的参照招聘市场
 * （市场上从没有岗位同时要求这些技术），不带的参照自产岗位库
 * （库里有没有对应岗位）。给它一个正面的标签「库内比对」，
 * 这个区别才在卡面上立得住。
 */
export const evidenceBadges: Record<
  string,
  { label: string; hint: string; fg: string; bg: string }
> = {
  A: {
    label: '缺口显著',
    hint: '两侧技术在招聘市场上都常见，却从未出现在同一个岗位里——可排除偶然',
    fg: '#a33a12',
    bg: '#fdeee5',
  },
  B: {
    label: '缺口存疑',
    hint: '两侧技术在招聘市场上都出现过，但样本量不足以排除「碰巧没撞上」',
    fg: '#8a6a15',
    bg: '#fbf3df',
  },
  library: {
    label: '库内比对',
    hint: '参照系是本系统自产的岗位库，回答「库里有没有对应岗位」，不涉及市场缺口',
    fg: '#5a6b7e',
    bg: '#eff2f6',
  },
}

/** 库内四类没有缺口分级，走 `library` 这一档。 */
export const LIBRARY_EVIDENCE_KEY = 'library'

export const classificationTone: Record<string, 'info' | 'warning' | 'success' | 'neutral'> = {
  existing_role: 'neutral',
  role_evolution: 'info',
  library_gap: 'warning',
  potential_new_role: 'success',
  upstream_signal: 'success',
  milestone_signal: 'success',
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
  /** 该候选技术组合归属的类型（算法/硬件/系统集成），决定用哪一档时滞先验。 */
  technology_classes: string[]
  coefficient: number | null
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
