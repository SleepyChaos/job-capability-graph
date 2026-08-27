export interface IndustryEnterprise {
  id: string
  name: string
  aliases: string
  industryStage: string
  industryCategory: string
  originalStage: string
  companySpecialty: string
  financingRound: string
  financingDetail: string
  province: string
  city: string
  country: string
  district: string
  companyRegion: string
  headquartersCity: string
  headquartersPoint: [number, number] | null
  headquartersCoordinateLevel: string
  website: string
  recruitmentLinks: { label: string; url: string }[]
  reportedOpeningsRaw: string
  reportedOpenings: number | null
  recruitmentNotes: string
  recruitmentSource: string
  products: string
  productType: string
  features: string
  production: string
  operatingPath: string
  sourceNotes: string
  sourceRow: number
  jobIds: string[]
  jobCount: number
}

export interface IndustryGraphData {
  metadata: {
    generatedAt: string
    libraryFile: string
    enhancementFile: string
    baselineFile: string
    libraryDataRows: number
    enterpriseCount: number
    blankRowsExcluded: number[]
    normalizationConflicts: string[][]
    jobCount: number
    mappedJobCount: number
    pendingJobCount: number
    enterprisesWithJobs: number
    enterprisesWithoutJobs: number
    enterprisesWithRecruitmentLinks: number
    enterprisesWithReportedOpenings: number
    enterprisesWithHeadquartersPoints: number
    countNote: string
    overviewNote: string
    geographySource: string
    geographySourceUrl: string
  }
  enterprises: IndustryEnterprise[]
  stages: string[]
  categories: { name: string; primaryStage: string; note: string }[]
  overview: {
    stageDemand: { name: string; count: number }[]
    financingDemand: { name: string; count: number }[]
    directionStage: { direction: string; values: number[] }[]
  }
  map: { width: number; height: number; features: { name: string; region: string; path: string }[] }
}

export async function loadIndustryGraph(signal?: AbortSignal): Promise<IndustryGraphData> {
  const response = await fetch('/enterprise-industry-graph.json', { signal })
  if (!response.ok) throw new Error(`企业库图谱加载失败（${response.status}）`)
  return response.json() as Promise<IndustryGraphData>
}
