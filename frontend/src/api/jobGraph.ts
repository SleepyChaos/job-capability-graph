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

let graphCache: JobEcosystemGraph | null = null
let graphInflight: Promise<JobEcosystemGraph> | null = null

/**
 * 让调用方的 signal 只中断「这次等待」，不中断底层那次共享请求。
 *
 * 三个页面共用同一份图谱，谁先进谁发起请求。若把调用方的 signal 直接挂到 fetch 上，
 * 用户在加载途中切走一次就会把请求打掉，另一个页面还在等的 Promise 跟着一起失败。
 * 这里改成只在本次等待上做竞速：页面卸载时它拿到 AbortError（三处调用方都按名字
 * 忽略这个错误），而请求继续跑完并填进缓存，下次进页面直接命中。
 */
function raceAbort<T>(promise: Promise<T>, signal?: AbortSignal): Promise<T> {
  if (!signal) return promise
  if (signal.aborted) return Promise.reject(new DOMException('图谱加载已取消', 'AbortError'))
  return new Promise<T>((resolve, reject) => {
    const onAbort = () => reject(new DOMException('图谱加载已取消', 'AbortError'))
    signal.addEventListener('abort', onAbort, { once: true })
    promise.then(resolve, reject).finally(() => signal.removeEventListener('abort', onAbort))
  })
}

/**
 * 岗位生态图谱产物，进程内只取一次。
 *
 * JobEcosystemPage / JobDiscoveryPage / TechToRolePage 各自独立调用本函数，原先每次
 * 切页都要重新 fetch 并重新 JSON.parse 这 39MB（HTTP 层能命中磁盘缓存，省下的只是
 * 下载，解析开销每切一次付一遍）。缓存解析结果后，一个会话内只付一次。
 *
 * 缓存的是解析后的对象、只在成功时写入；失败会清掉在途 Promise，下次进页面能重试。
 */
export async function loadJobEcosystemGraph(signal?: AbortSignal): Promise<JobEcosystemGraph> {
  if (graphCache) return graphCache
  if (!graphInflight) {
    graphInflight = fetch('/job-ecosystem-graph.json')
      .then((response) => {
        if (!response.ok) throw new Error(`岗位图谱加载失败（${response.status}）`)
        return response.json() as Promise<JobEcosystemGraph>
      })
      .then((graph) => {
        graphCache = graph
        return graph
      })
      .catch((error: unknown) => {
        graphInflight = null
        throw error
      })
  }
  return raceAbort(graphInflight, signal)
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
