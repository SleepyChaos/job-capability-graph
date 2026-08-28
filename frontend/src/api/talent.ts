const API_BASE = import.meta.env.VITE_API_BASE_URL ?? '/api/v1'

export interface ProfileQuestion {
  turn_no: number
  question_code: string
  question_text: string
}

export interface ProfileDialogueTurn extends ProfileQuestion {
  answer_text: string | null
  answer_source_code: string
  created_at: string | null
}

export interface ProfileSkill {
  skill_evidence_id: number
  technology_node_id: number
  technology_code: string
  technology_name: string
  level_code: string
  raw_mention: string
  evidence_text: string
  source_type_code: string
  evidence_level_code: string
  confidence_score: number
  user_confirmed: boolean
}

export interface ProfileSummary {
  profile_code: string
  version_code: string
  version_no: number
  display_name: string
  source_name: string
  mime_type: string
  workflow_status_code: 'draft' | 'confirmed'
  target_role_text: string | null
  education_text: string | null
  completeness_score: number
  conversation_round_count: number
  skill_count: number
  match_run_count: number
  created_at: string
}

export interface ProfileDetail extends ProfileSummary {
  experience_summary: string | null
  preferences: Record<string, { value: string; source: string; turn_no: number }>
  facts: Record<string, unknown>
  insights: { status: string; statements: Array<{ text: string; source: string; evidence_ids: string[] }>; warning?: string }
  skills: ProfileSkill[]
  next_question: ProfileQuestion | null
  dialogue_history: ProfileDialogueTurn[]
  profile_dimension_coverage: Record<string, boolean>
  missing_profile_dimensions: Array<{ code: string; label: string }>
  can_publish: boolean
  minimum_rounds: number
  maximum_rounds: number
}

export interface MatchGap {
  gap_id: number
  technology_node_id: number
  technology_name: string
  gap_type_code: 'evidence_insufficient' | 'transferable' | 'depth_insufficient' | 'confirmed_missing'
  importance_score: number
  candidate_evidence: string[]
  job_evidence: string[]
  explanation: string
}

export interface RequiredCapabilityGraphNode {
  technology_node_id: number
  technology_code: string
  technology_name: string
  level_code: string
}

export interface RequiredCapabilityGraphItem {
  technology_node_id: number
  technology_code: string
  technology_name: string
  level_code: string
  operator: string
  hard: boolean
  weight: number
  coverage_status: 'covered' | 'partial_evidence' | 'evidence_insufficient' | 'depth_insufficient' | 'transferable' | 'confirmed_missing'
  candidate_evidence: string[]
  job_evidence: string[]
  domain: { code: string; name: string; color: string | null } | null
  path: RequiredCapabilityGraphNode[]
}

export interface RequiredCapabilityGraph {
  requirement_source: string
  expression_operator: string | null
  total_count: number
  covered_count: number
  unresolved_count: number
  confirmed_missing_count: number
  items: RequiredCapabilityGraphItem[]
}

export interface JobGraphAssociation {
  status: 'linked' | 'unlinked'
  schema_version: string
  source_job_id: string | null
  job_code: string | null
  job_title: string | null
  company: string | null
  standard_role: {
    role_code: string
    name: string
    job_count: number
    match_confidence: string | null
    match_method: string | null
  } | null
  hierarchy: {
    direction: string | null
    category: string | null
    cluster_code: string | null
    cluster_name: string | null
  } | null
  portrait: {
    responsibilities: string[]
    skills: string[]
    capabilities: string[]
    scenarios: string[]
    conditions: string[]
  } | null
  technology_paths: Array<{
    path: Array<{ level: 'L1' | 'L2' | 'L3' | 'L4'; code: string; name: string }>
    match_method: string | null
    evidence_grade: boolean
    hit_terms: string[]
  }>
  requirement_coverage: RequiredCapabilityGraph
  message: string
}

export interface MatchResult {
  result_code: string
  rank_no: number
  overall_score: number
  confidence_score: number
  cluster_code: string
  job_title: string
  representative_jd: { job_code: string | null; company: string | null; region: string | null; job_level: string | null }
  job_detail: {
    job_code: string
    source_job_id: string | null
    title_raw: string
    title_normalized: string
    company: string | null
    region: string | null
    employment_type: string | null
    job_level: string | null
    salary_text: string | null
    salary_min_monthly_cny: number | null
    salary_max_monthly_cny: number | null
    salary_months_per_year: number | null
    education_code: string | null
    education_text: string | null
    experience_min_years: number | null
    experience_max_years: number | null
    experience_text: string | null
    published_at: string | null
    collected_at: string
    expired_at: string | null
    posting_status: string
    jd_text: string
    parse_confidence_score: number | null
    publish_score: number | null
    data_origin: string
    data_source_id: number
  } | null
  dimensions: Array<{ code: string; label: string; score: number; lower_score: number; upper_score: number; weight: number; contribution: number; status: string }>
  required_capability_graph: RequiredCapabilityGraph
  job_graph_association: JobGraphAssociation
  recommendation: { reasons: string[]; warning: string }
  gaps: MatchGap[]
}

export interface MatchRun {
  run_code: string
  profile_version_code: string
  algorithm_version: string
  result_count: number
  candidate_scope: 'all_active_job_postings'
  candidate_count: number
  pipeline: ['resume_parse', 'job_jd_parse', 'deterministic_match']
  scoring_policy: {
    llm_used: false
    dimension_count: number
    dimensions: Array<{ code: string; label: string; weight: number }>
  }
  results: MatchResult[]
}

export interface LearningStep {
  step_no: number
  technology_node_id: number | null
  technology_name: string
  gap_id: number | null
  gap_type_code: string
  depends_on: number[]
  learning_focus: string
  practice_task: string
  verification: string
  estimated_weeks: number
  improves_dimension: string
  evidence_reference: string
}

export interface LearningPath {
  path_code: string
  match_result_id: number
  version_no: number
  algorithm_version: string
  summary: string
  steps: LearningStep[]
  workflow_status_code: string
}

export interface MatchExplanation {
  result_code: string
  explanation_text: string
  generation_method: string
  model_version: string
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: { 'Content-Type': 'application/json', ...init?.headers },
  })
  if (!response.ok) {
    const payload = await response.json().catch(() => null) as { detail?: string } | null
    throw new Error(payload?.detail ?? `请求失败（${response.status}）`)
  }
  return response.json() as Promise<T>
}

async function uploadFile<T>(path: string, file: File): Promise<T> {
  const form = new FormData()
  form.append('file', file)
  const response = await fetch(`${API_BASE}${path}`, { method: 'POST', body: form })
  if (!response.ok) {
    const payload = await response.json().catch(() => null) as { detail?: string } | null
    throw new Error(payload?.detail ?? `上传失败（${response.status}）`)
  }
  return response.json() as Promise<T>
}

export const talentApi = {
  profiles: (signal?: AbortSignal) => request<ProfileSummary[]>('/talent/profiles', { signal }),
  profile: (versionCode: string, signal?: AbortSignal) => request<ProfileDetail>(`/talent/profiles/${versionCode}`, { signal }),
  createProfile: (payload: { source_name: string; mime_type: string; input_type_code: 'pasted_text' | 'txt'; content_text: string }) => request<ProfileDetail>('/talent/profiles', { method: 'POST', body: JSON.stringify(payload) }),
  uploadProfile: (file: File) => uploadFile<ProfileDetail>('/talent/profiles/upload', file),
  answer: (versionCode: string, answerText: string) => request<ProfileDetail>(`/talent/profiles/${versionCode}/answers`, { method: 'POST', body: JSON.stringify({ answer_text: answerText }) }),
  publish: (versionCode: string) => request<ProfileDetail>(`/talent/profiles/${versionCode}/publish`, { method: 'POST' }),
  createVersion: (versionCode: string, payload: { target_role_text?: string; education_text?: string; experience_summary?: string }) => request<ProfileDetail>(`/talent/profiles/${versionCode}/versions`, { method: 'POST', body: JSON.stringify(payload) }),
  matches: (versionCode: string) => request<MatchRun>(`/talent/profiles/${versionCode}/matches`, { method: 'POST' }),
  learningPath: (resultCode: string) => request<LearningPath>(`/talent/matches/${resultCode}/learning-path`, { method: 'POST' }),
  explanation: (resultCode: string, signal?: AbortSignal) => request<MatchExplanation>(`/talent/matches/${resultCode}/explanation`, { signal }),
}
