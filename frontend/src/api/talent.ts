const API_BASE = import.meta.env.VITE_API_BASE_URL ?? '/api/v1'

export interface ProfileQuestion {
  turn_no: number
  question_code: string
  question_text: string
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

export interface MatchResult {
  result_code: string
  rank_no: number
  overall_score: number
  confidence_score: number
  cluster_code: string
  job_title: string
  representative_jd: { job_code: string | null; company: string | null; region: string | null; job_level: string | null }
  dimensions: Array<{ code: string; label: string; score: number; weight: number }>
  recommendation: { reasons: string[]; warning: string }
  gaps: MatchGap[]
}

export interface MatchRun {
  run_code: string
  profile_version_code: string
  algorithm_version: string
  result_count: number
  results: MatchResult[]
}

export interface LearningStep {
  step_no: number
  technology_node_id: number
  technology_name: string
  gap_id: number
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
