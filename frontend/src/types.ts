export type PageId =
  | 'overview'
  | 'data'
  | 'sources'
  | 'management'
  | 'taxonomy'
  | 'jobs'
  | 'job-keyword'
  | 'job-name'
  | 'job-records'
  | 'graph'
  | 'graph-heatmap'
  | 'graph-relations'
  | 'graph-clusters'
  | 'talent'
  | 'resume'
  | 'match'
  | 'learning'
  | 'review'

export type StatusTone = 'success' | 'warning' | 'info' | 'danger' | 'neutral'

export interface SourceItem {
  id: number
  name: string
  type: string
  target: string
  cadence: string
  lastRun: string
  additions: number
  status: '正常' | '采集中' | '需检查'
}

export interface RoleCandidate {
  id: number
  name: string
  stage: '新兴岗位' | '萌芽岗位' | '潜在岗位'
  primaryDomain: string
  secondaryDomains: string[]
  score: number
  jdCount: number
  companies: number
  growth: number
  summary: string
  skills: string[]
  evidence: string[]
}

export interface ReviewItem {
  id: number
  type: string
  content: string
  source: string
  confidence: number
  submittedAt: string
  status: '待审核' | '观察' | '已通过' | '已驳回'
}

export interface CandidateProfile {
  id: string
  name: string
  version: number
  sourceFile: string
  createdAt: string
  updatedAt: string
  status: '待确认' | '已确认'
  direction: string
  education: string
  summary: string
  skills: string[]
  completeness: number
  factsCount: number
  conversationRounds: number
  matchRuns: number
}
