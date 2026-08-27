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

export interface StandardRole {
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
  rolesWithEvidence: number
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
