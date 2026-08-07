// 统一后端 API 适配层（阶段 2）：mock-data → 真实接口的数据映射
// 后端：FastAPI（backend/api.py），读取统一库 unified.db

import type { JobNode, SkillNode, NewJob } from './mock-data';

export const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE || 'http://localhost:8002';

export interface AtlasStats {
  jobs: number;
  skills: number;
  edges: number;
  clusters: number;
  clusteredJobs: number;
  l1Distribution: { code: string; name: string; clusters: number }[];
  pipeline: Record<string, string>;
}

export interface ClusterItem {
  id: string;
  name: string;
  description: string;
  sharedSkills: string[];
  representativeTitles: string[];
  keywords: string[];
  jobCount: number;
  nameSource: string;
  reviewStatus: string;
  clusteredAt: string;
  l1Code: string;
  l2Name: string;
  members: { id: string; title: string; company: string; city: string; salary: string }[];
}

async function getJSON<T>(path: string): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, { cache: 'no-store' });
  if (!res.ok) throw new Error(`API ${path} -> ${res.status}`);
  return res.json() as Promise<T>;
}

/** 全景图谱数据：岗位节点 + 技能节点（结构与 mock-data 的 JobNode/SkillNode 对齐） */
export async function fetchAtlasData(): Promise<{ jobs: JobNode[]; skills: SkillNode[] }> {
  const data = await getJSON<{ jobs: JobNode[]; skills: SkillNode[] }>(
    '/api/graph?level=all&category=all&limit_skills=150'
  );
  return { jobs: data.jobs, skills: data.skills };
}

/** L2 粒度技能热力图：行 = T1–T7 下的 L2 技能类目，热力值 = 活跃岗位去重计数 */
export interface HeatmapCell {
  junior: number;
  mid: number;
  senior: number;
}

export interface HeatmapRow {
  l2_id: number;
  l1_code: string;
  l2_name: string;
  cells: HeatmapCell;
}

export interface HeatmapData {
  days: number;
  total_jobs: number;
  rows: HeatmapRow[];
}

export function fetchHeatmap(days = 180): Promise<HeatmapData> {
  return getJSON<HeatmapData>(`/api/heatmap?days=${days}`);
}

/** 系统统计 */
export function fetchStats(): Promise<AtlasStats> {
  return getJSON<AtlasStats>('/api/stats');
}

/** 聚类结果 → NewJob（新岗位发现页口径）；阶段 2.5 起默认展示 job_count≥5 的头部聚类 */
export async function fetchClustersAsNewJobs(): Promise<NewJob[]> {
  const data = await getJSON<{ clusters: ClusterItem[]; total: number }>(
    '/api/clusters?min_jobs=5&limit=200'
  );
  return data.clusters.map((c): NewJob => {
    const signal = c.jobCount >= 5 ? 'high' : c.jobCount >= 3 ? 'medium' : 'low';
    return {
      id: c.id,
      name: c.name,
      // 启发式命名（规则）置信度更高；LLM 命名待人工审核，置信度略低
      confidence: c.nameSource === 'llm' ? 78 : 92,
      signalStrength: signal as NewJob['signalStrength'],
      source: `JD聚类分析（${c.jobCount} 个相似岗位聚合）`,
      skills: c.sharedSkills.slice(0, 8),
      growth: Math.min(c.jobCount * 15, 350),
      salary: c.members[0]?.salary || '',
      description: c.description,
      scenarios: c.representativeTitles,
      bonusSkills: c.keywords.filter(k => !c.sharedSkills.includes(k)).slice(0, 6),
      // 真实口径字段（发现页指标卡与卡片展示使用）
      jobCount: c.jobCount,
      nameSource: (c.nameSource === 'llm' ? 'llm' : 'heuristic') as NewJob['nameSource'],
    };
  });
}

/** 聚类详情（含成员岗位） */
export function fetchClusters(): Promise<ClusterItem[]> {
  return getJSON<{ clusters: ClusterItem[] }>('/api/clusters?min_jobs=5&limit=200').then(
    d => d.clusters
  );
}

// ---------------------------------------------------------------------------
// 阶段 3：简历解析与人岗匹配
// ---------------------------------------------------------------------------

export interface ResumeSkill {
  skill_term: string;
  l1_code: string;
  confidence: number;
  source: 'dictionary' | 'llm';
}

export interface UploadResumeResult {
  resume_id: string;
  name: string;
  title: string;
  llmUsed: boolean;
  skills: ResumeSkill[];
}

export interface MatchResult {
  job_id: string;
  title: string;
  company: string;
  city: string;
  salary: string;
  score: number;
  capability_score: number;
  l1_score: number;
  core_jaccard: number;
  title_score: number | null;
  coverage: number;
  shared: string[];
  missing: string[];
  extra: string[];
  missing_severity: 'severe' | 'moderate' | 'minor';
}

export interface MatchResponse {
  matches: MatchResult[];
  candidate_count?: number;
  resume_skill_count: number;
  semantic_available: boolean;
  warning?: string;
}

export interface ResumeListItem {
  resume_id: string;
  name: string;
  title: string;
  file_name: string | null;
  created_at: string;
  skill_count: number;
}

/** 上传简历（文件），解析 + 提取技能 */
export async function uploadResumeFile(file: File): Promise<UploadResumeResult> {
  const form = new FormData();
  form.append('file', file);
  const res = await fetch(`${API_BASE}/api/resumes/upload`, { method: 'POST', body: form });
  if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || `上传失败 ${res.status}`);
  return res.json();
}

/** 粘贴简历文本，解析 + 提取技能 */
export async function uploadResumeText(text: string): Promise<UploadResumeResult> {
  const form = new FormData();
  form.append('text', text);
  const res = await fetch(`${API_BASE}/api/resumes/upload`, { method: 'POST', body: form });
  if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || `解析失败 ${res.status}`);
  return res.json();
}

/** 人岗匹配：Top N 岗位 + 差距清单 */
export function matchResume(resumeId: string, topN = 10): Promise<MatchResponse> {
  return getJSON<MatchResponse>(`/api/resumes/${resumeId}/match?top_n=${topN}`);
}

/** 历史简历列表 */
export async function fetchResumes(limit = 20): Promise<ResumeListItem[]> {
  const data = await getJSON<{ resumes: ResumeListItem[] }>(`/api/resumes?limit=${limit}`);
  return data.resumes;
}

// ---------------------------------------------------------------------------
// 阶段 4：幻觉防控与人工审核
// ---------------------------------------------------------------------------

export interface ReviewSummary {
  pending: { edge: number; cluster: number; definition: number };
  edges: {
    approved: number;
    rejected: number;
    pending: number;
    evidenceCovered: number;
    total: number;
    evidenceCoverage: number;
  };
  decidedTotal: number;
  policy: { autoApproveConfidence: number; description: string };
}

export interface ReviewEdgeItem {
  target_id: string;
  job_title: string;
  skill_term: string;
  evidence: string | null;
  confidence: number;
  source: string;
  created_at: string;
}

export interface ReviewClusterItem {
  target_id: string;
  cluster_name: string;
  description: string | null;
  shared_skills: string;
  representative_titles: string;
  job_count: number;
  name_source: string;
  created_at: string;
  primary_l1_code: string | null;
  primary_l2_name: string | null;
}

export interface ReviewDefinitionItem {
  target_id: number;
  cluster_id: string;
  technology_id: string | null;
  job_type: string | null;
  job_name: string;
  core_duties: string;
  required_skills: string;
  bonus_skills: string;
  industry_scenarios: string;
  scores_json: string | null;
  evidence_json: string | null;
  generation_source: string;
  created_at: string;
}

export interface ReviewLogItem {
  review_id: number;
  target_type: string;
  target_id: string;
  action: string;
  reviewer: string;
  comment: string;
  created_at: string;
}

export function fetchReviewSummary(): Promise<ReviewSummary> {
  return getJSON<ReviewSummary>('/api/review/summary');
}

export async function fetchReviewQueue<T>(
  targetType: 'edge' | 'cluster' | 'definition',
  limit = 50
): Promise<T[]> {
  const data = await getJSON<{ items: T[] }>(
    `/api/review/queue?target_type=${targetType}&limit=${limit}`
  );
  return data.items;
}

export async function reviewDecide(
  targetType: string,
  targetId: string,
  action: 'approve' | 'reject',
  comment = ''
): Promise<{ status: string }> {
  const res = await fetch(`${API_BASE}/api/review/decide`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ targetType, targetId, action, reviewer: '前端审核员', comment }),
  });
  if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || `审核失败 ${res.status}`);
  return res.json();
}

export async function fetchReviewLog(limit = 50): Promise<ReviewLogItem[]> {
  const data = await getJSON<{ items: ReviewLogItem[] }>(`/api/review/log?limit=${limit}`);
  return data.items;
}

// ---------------------------------------------------------------------------
// 阶段 5：新岗位定义与能力动态更新
// ---------------------------------------------------------------------------

export interface JobDefinition {
  definition_id: number;
  cluster_id: string;
  job_name: string;
  core_duties: string;
  required_skills: string[];
  bonus_skills: string[];
  industry_scenarios: string;
  generation_source: string;
  review_status: string;
  created_at: string;
}

export interface SnapshotItem {
  snapshotId: number;
  label: string;
  jobId: string;
  title: string;
  skillCount: number;
  createdAt: string;
}

export interface EvolutionDiff {
  baseSnapshot: number;
  newSnapshot: number;
  jobId: string;
  added: string[];
  removed: string[];
  modified: string[];
  updateNote: string;
}

export async function generateDefinition(clusterId: string): Promise<{
  definitionId: number;
  llmUsed: boolean;
  jobName: string;
}> {
  const res = await fetch(`${API_BASE}/api/definitions/generate`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ clusterId }),
  });
  if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || `生成失败 ${res.status}`);
  return res.json();
}

export async function fetchDefinitions(limit = 20): Promise<JobDefinition[]> {
  const data = await getJSON<{ items: JobDefinition[] }>(`/api/definitions?limit=${limit}`);
  return data.items;
}

export async function takeSnapshot(jobId: string, label?: string): Promise<SnapshotItem> {
  const res = await fetch(`${API_BASE}/api/evolution/snapshot`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ jobId, label }),
  });
  if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || `快照失败 ${res.status}`);
  return res.json();
}

export async function refreshJobSkills(jobId: string, jdText?: string): Promise<{ skillCount: number }> {
  const res = await fetch(`${API_BASE}/api/evolution/refresh`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ jobId, jdText }),
  });
  if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || `重提取失败 ${res.status}`);
  return res.json();
}

export function fetchEvolutionDiff(base: number, newest: number): Promise<EvolutionDiff> {
  return getJSON<EvolutionDiff>(`/api/evolution/diff?base=${base}&new=${newest}`);
}

export async function fetchSnapshots(jobId?: string): Promise<SnapshotItem[]> {
  const q = jobId ? `?job_id=${encodeURIComponent(jobId)}` : '';
  const data = await getJSON<{ items: SnapshotItem[] }>(`/api/evolution/snapshots${q}`);
  return data.items;
}

/** 岗位搜索（动态演化页选岗位用；复用 /api/jobs 列表接口） */
export async function searchJobs(keyword: string, limit = 30): Promise<{ job_id: string; title: string; company: string }[]> {
  const data = await getJSON<{ jobs: { job_id: string; title: string; company: string }[] }>(
    `/api/jobs?limit=500`
  );
  const kw = keyword.trim().toLowerCase();
  if (!kw) return data.jobs.slice(0, limit);
  return data.jobs
    .filter(j => (j.title || '').toLowerCase().includes(kw) || (j.company || '').toLowerCase().includes(kw))
    .slice(0, limit);
}

// ---------------------------------------------------------------------------
// 阶段 6：技术演化驱动的新兴岗位发现（移植自 embodied-job-evolution-lab）
// ---------------------------------------------------------------------------

export interface EmergingTechnology {
  technology_id: string;
  standard_name: string;
  level: string;
  domain: string | null;
  definition: string | null;
  parent_id: string | null;
  aliases: string[];
  link_confidence: number;
}

export interface EmergingEvidenceJob {
  job_id: string;
  title: string;
  company: string;
  snippet: string;
  source_url?: string;
  confidence: number;
}

export interface EmergingCandidate {
  candidate_id: string;
  job_title: string;
  job_type: '新兴岗位' | '岗位演化' | '已有岗位';
  score: number;
  time_horizon: string;
  formation_reason: string;
  responsibilities: string[];
  required_skills: string[];
  bonus_skills: string[];
  application_scenarios: string[];
  job_definition: string;
  scores: Record<string, number>;
  evidence: {
    milestones: { event_id: string; name: string; event_date: string; source: string; snippet: string; confidence: number }[];
    jobs: EmergingEvidenceJob[];
  };
  evidence_path: { type: string; label: string }[];
  rank: number;
}

export interface EmergingRunResult {
  technology: EmergingTechnology & { maturity_score: number; target_date: string };
  candidate_jobs: EmergingCandidate[];
  metrics: {
    evidence_completeness: number;
    task_cohesion: number;
    existing_overlap: number;
    related_job_count: number;
    milestone_count: number;
  };
  config_id: string;
  generation_mode: string;
}

/** 技术实体搜索（标准实体链接，带置信度） */
export async function searchEmergingTechnologies(q: string): Promise<EmergingTechnology[]> {
  const data = await getJSON<{ items: EmergingTechnology[] }>(
    `/api/emerging/technologies/search?q=${encodeURIComponent(q)}`
  );
  return data.items;
}

/** 发起一次新兴岗位预测（同步执行） */
export async function runEmergingDiscovery(body: {
  technologyId: string;
  targetDate?: string;
  topK?: number;
  configId?: string;
  generationMode?: string;
}): Promise<{ run_id: string; status: string; result: EmergingRunResult }> {
  const res = await fetch(`${API_BASE}/api/emerging/run`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || `预测失败 ${res.status}`);
  return res.json();
}

/** 候选岗位提交审核（写 job_definitions pending，进入 governance 队列） */
export async function submitEmergingCandidate(
  runId: string,
  candidateId: string
): Promise<{ definitionId: number; reviewStatus: string }> {
  const res = await fetch(`${API_BASE}/api/emerging/submit`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ runId, candidateId }),
  });
  if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || `提交失败 ${res.status}`);
  return res.json();
}
