export interface JobGraphMetadata {
  sourceFile: string
  sourceSheet?: string
  enterpriseLibraryFile?: string
  generatedAt: string
  method: string
  releaseStatus: 'candidate_v0.1' | string
  releaseNote: string
  jobCount: number
  directionCount: number
  categoryCount: number
  clusterCount: number
  standardRoleCount?: number
  standardRoleVariantCount?: number
  standardRoleMappedJobCount?: number
  standardRoleMappingRate?: number
  portraitExcelOverride?: boolean
  skillCount: number
  technologyNodeCount?: number
  technologyMappedJobCount?: number
  technologyMappedJobRate?: number
  enterpriseCount?: number
  enterpriseMatchedJobCount?: number
  enterpriseMatchRate?: number
  enterprisePendingJobCount?: number
  warnings: string[]
}

export interface JobDirection {
  id: string
  name: string
  color: string
  jobCount: number
  categoryCount: number
  clusterCount: number
}

export interface JobCategory {
  id: string
  name: string
  directionId: string
  directionName: string
  color: string
  jobCount: number
  clusterCount: number
}

export interface NamedCount {
  name: string
  count: number
}

export interface RepresentativeJob {
  title: string
  count: number
  company: string
  occId: string
  url: string
  jdSnippet: string
  profile: JobPortrait
  clusterId?: string
  clusterName?: string
  categoryName?: string
  directionName?: string
}

export interface JobRecord extends RepresentativeJob {
  id: string
  jd: string
  clusterId: string
  clusterName: string
  standardRoleId: string
  standardRoleName: string
  standardRoleMappingMethod: string
  standardRoleMappingConfidence: number
  categoryId: string
  categoryName: string
  directionId: string
  directionName: string
  skills: string[]
  technologyTermIds: string[]
  technologyMappingMethods: string[]
  abilityLevel: string
  education: string
  experience: string
  enterpriseName: string
  industryStage: string
  companySpecialty: string
  financingRound: string
  companyRegion: string
  headquartersCity: string
}

export interface StandardProfilePoint {
  name: string
  count: number
  coverage: number
  evidenceOccIds: string[]
}

/**
 * 推演派生岗位的附加标记。只有来自新岗位发现、由 LLM 依候选数据卡生成画像的岗位
 * 带这几个字段——它们的招聘侧支撑恒为 0，界面必须能把它们与 JD 归纳出的岗位区分开。
 */
export interface InferredRoleMarks {
  origin?: 'inference_derived'
  candidateCode?: string
  classification?: string
  classificationCode?: string
  gapGrade?: string
  evidenceSummary?: string
  definition?: string
}

export interface StandardRole extends InferredRoleMarks {
  id: string
  code: string
  name: string
  clusterId: string
  clusterName: string
  categoryId: string
  categoryName: string
  directionId: string
  directionName: string
  color: string
  seedVariants: string[]
  observedVariants: NamedCount[]
  taxonomyMethod: string
  jobCount: number
  companyCount: number
  jdCount: number
  profileMethod: string
  releaseStatus: string
  standardProfile: Record<'responsibilities' | 'skills' | 'abilities' | 'scenarios' | 'conditions', StandardProfilePoint[]>
}

export interface StandardRoleAudit {
  seedRoleCount: number
  seedVariantCount: number
  mappedJobCount: number
  pendingJobCount: number
  mappingRate: number
  /** 图谱产物里并不产出这一项，声明为可选，避免界面拿到 undefined 还当数字用。 */
  rolesWithEvidence?: number
  mappingMethodDistribution: Record<string, number>
}

export interface JobPortrait {
  responsibilities: string[]
  skills: string[]
  abilities: string[]
  scenarios: string[]
  conditions: string[]
  jdEvidence: string[]
  jdAvailable: boolean
}

export interface JobCluster {
  id: string
  code: string
  name: string
  categoryId: string
  categoryName: string
  directionId: string
  directionName: string
  color: string
  jobCount: number
  companyCount: number
  candidateStatus: string
  currentDiscoveryMethod: string
  targetDiscoveryMethod: string
  ruleMatchedRate: number
  averageRuleScore: number
  uniqueTitleCount: number
  jdCoverageRate: number
  skillCoverageRate: number
  topCompanyShare: number
  portraitCoverage: Record<'responsibilities' | 'skills' | 'abilities' | 'scenarios' | 'conditions', number>
  topKeywords: string[]
  topSkills: NamedCount[]
  topCompanies: NamedCount[]
  representativeJobs: RepresentativeJob[]
  levelDistribution: Record<string, number>
  educationDistribution: Record<string, number>
  experienceDistribution: Record<string, number>
  industryDistribution: Record<string, number>
  regionDistribution: Record<string, number>
  financingDistribution: Record<string, number>
}

export interface EnterpriseRecord {
  id: string
  name: string
  jobCount: number
  industryStage: string
  industryCategory: string
  companySpecialty: string
  financingRound: string
  companyRegion: string
  headquartersCity: string
  directionDistribution: Record<string, number>
  categoryDistribution: Record<string, number>
  clusterDistribution: Record<string, number>
  representativeJobs: RepresentativeJob[]
}

export interface EnterpriseAnalysis {
  enterpriseLibraryFile: string
  enterpriseLibraryRecordCount: number
  sourceCompanyCount: number
  matchedEnterpriseCount: number
  matchedJobCount: number
  matchedJobRate: number
  pendingJobCount: number
  statusDistribution: Record<string, number>
  matchMethodDistribution: Record<string, number>
  industryDistribution: NamedCount[]
  industryCategoryDistribution: NamedCount[]
  regionDistribution: NamedCount[]
  financingDistribution: NamedCount[]
  headquartersCityDistribution: NamedCount[]
  topEnterprises: EnterpriseRecord[]
}

export interface JobTechnologyNode {
  id: string
  code: string
  name: string
  level: 'L1' | 'L2' | 'L3' | 'L4'
  parentId: string
  definition: string
  jobCount: number
  standardRoleCount: number
}

export interface TechnologyAudit {
  masterFile: string
  legacySummaryFile: string
  legacyMatchFile: string
  levelCounts: Record<'L1' | 'L2' | 'L3' | 'L4', number>
  mappedJobCount: number
  mappedJobRate: number
  pendingJobCount: number
  exactJdJobCount: number
  exactL4SkillJobCount: number
  activeL4TermCount: number
  mappingRule: string
  summaryRows: number
  matchRows: number
  matchedRelations: number
}

export interface JobGraphNode {
  id: string
  type: 'root' | 'direction' | 'category' | 'job_cluster' | 'standard_role' | 'job' | 'skill'
  label: string
  jobCount?: number
}

export interface JobGraphEdge {
  id: string
  source: string
  target: string
  type: 'contains' | 'contains_standard_role' | 'supported_by_job' | 'requires_skill'
  weight?: number
}

export interface JobEcosystemGraph {
  metadata: JobGraphMetadata
  directions: JobDirection[]
  categories: JobCategory[]
  clusters: JobCluster[]
  standardRoles: StandardRole[]
  standardRoleAudit: StandardRoleAudit
  jobs: JobRecord[]
  enterprises: EnterpriseRecord[]
  enterpriseAnalysis: EnterpriseAnalysis
  technologyNodes: JobTechnologyNode[]
  technologyAudit: TechnologyAudit
  nodes: JobGraphNode[]
  edges: JobGraphEdge[]
}

export async function loadJobEcosystemGraph(signal?: AbortSignal): Promise<JobEcosystemGraph> {
  const response = await fetch('/job-ecosystem-graph.json', { signal })
  if (!response.ok) throw new Error(`岗位图谱加载失败（${response.status}）`)
  return response.json() as Promise<JobEcosystemGraph>
}

/**
 * 推演派生岗位的五维画像。
 *
 * 与 `job-ecosystem-graph.json` 分开存放，而不是并进那份 39MB 的产物里：后者由 Excel
 * 管线整体重生成，手工塞两条进去下次重跑就没了；分开放才能各自演进。加载失败时按空
 * 处理——画像图谱缺两条推演岗位仍可用，不该因此整页报错。
 */
export async function loadDiscoveryRolePortraits(signal?: AbortSignal): Promise<StandardRole[]> {
  try {
    const response = await fetch('/discovery-role-portraits.json', { signal })
    if (!response.ok) return []
    const payload = (await response.json()) as { roles?: StandardRole[] }
    return payload.roles ?? []
  } catch (error) {
    if (error instanceof Error && error.name === 'AbortError') throw error
    return []
  }
}
