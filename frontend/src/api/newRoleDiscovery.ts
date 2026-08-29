/**
 * 技术—岗位图谱上的新岗位发现叠加层。
 *
 * 图谱本身跑在一份预生成的静态快照上，候选另出一份同源的小文件，两者靠
 * **技术编码**连接——候选的技术点与图谱 technologyNodes 用的是同一套
 * `T1.03.02` 体系，`technologyNodeIds` 是导出时就算好的挂载点。
 *
 * 候选是**未入库的提议**，与图谱里已观测的标准岗位不同级，呈现上必须能一眼分开。
 */

export interface DiscoveryCandidate {
  candidateCode: string
  name: string
  classification: string
  classificationCode: string
  maturity: string
  score: number
  supportJobCount: number
  organizationCount: number
  gapGrade: string
  technologyCodes: string[]
  technologyNames: string[]
  technologyNodeIds: string[]
  definition: string
}

export interface DiscoveryOverlay {
  metadata: {
    generatedAt: string
    candidateCount: number
    matchedTechnologyCodeCount: number
    /** 晚于图谱快照的技术词条，挂不上任何节点；不做近似匹配，如实留空。 */
    unmatchedTechnologyCodes: string[]
    joinKey: string
    note: string
  }
  candidates: DiscoveryCandidate[]
}

export async function fetchDiscoveryOverlay(signal?: AbortSignal): Promise<DiscoveryOverlay> {
  const response = await fetch('/new-role-discovery.json', { signal })
  if (!response.ok) throw new Error(`新岗位发现数据加载失败（${response.status}）`)
  return (await response.json()) as DiscoveryOverlay
}
