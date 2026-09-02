/**
 * 数据底座总量口径（《第三章 多源数据采集与治理》）。
 *
 * **为什么需要这一层常量。** 页面上的数字默认来自运行库，但运行库只装了三条主线里
 * 已经跑通的那部分：JD、论文、里程碑。标准、专利、人才与高校三类数据尚未建表，
 * 机构库也只导入了带招聘证据的企业（84 家），与第三章记载的 1,034 家差着一个数量级。
 * 演示时若只显示运行库实数，读者会把「尚未入库」误读成「项目没有这些数据」。
 *
 * **取数优先级。** 运行库实数优先；与第三章冲突时以第三章为准；两者都没有时才用
 * 宣传物料上的数字。每个常量注明出自第三章哪一节，改文档时对着改，不必翻页面代码。
 *
 * **不写进这里的数**：宣传 banner 上的「人才高校 7,586 条」——第三章中查不到出处，
 * 运行库也没有对应表，缺依据的数字不进代码。
 */

/** 招聘信息（第三章 3.2）。运行库存的是通过质量门槛的那部分，与 `valid` 一致。 */
export const jobPostingBaseline = {
  raw: 4655,
  valid: 3718,
} as const

/** 机构库（第三章 3.3）。表 3-1 另记「共 1,618 家」，与 3.3 正文的 1,034 家不一致，此处取正文。 */
export const organizationBaseline = {
  total: 1034,
  enterprise: 632,
  university: 235,
  institute: 165,
  government: 2,
  /** 完成产业链标注的企业分布，合计等于 enterprise。 */
  industryChain: { midstream: 424, upstream: 120, downstream: 49, support: 39 },
} as const

/** 技术成果库（第三章 3.4）。 */
export const techAssetBaseline = {
  papers: 13282,
  /** 命中不少于 2 个 L3 技术点、可用于共现分析的文献。 */
  papersWithCooccurrence: 2049,
  milestones: 474,
  standardsCollected: 134,
  standardsRetained: 123,
  patentRecords: 13396,
  /** 面向新岗位推演单独整理，与专利著录数据不合并计数（3.4 说明）。 */
  patentSignalCorpus: 4206,
} as const

/**
 * 成果技术标注的对外展示量，取宣传物料口径 1,872。
 *
 * **它的实际出处是词表 v1.1 的 L4 技术词数**，不是技术成果条数——第三章的技术成果库
 * 由 13,282 篇文献、4,206 条专利信号与 474 条里程碑构成，没有 1,872 这个量；运行库
 * 当前词表已到 v1.3，L4 为 2,548、全量 2,840。此处按项目对外统一口径固定为 1,872，
 * 与词表版本脱钩：词表升版时这个数不应跟着变，否则宣传材料与平台会再次对不上。
 */
export const techAnnotationDisplayCount = 1872

/** 岗位治理结果（第三章 3.2）。与运行库的聚类直出结果粒度不同，页面上分别标注。 */
export const roleStructureBaseline = {
  careerDirections: 6,
  careerCategories: 17,
  roleClusters: 42,
  standardRoles: 107,
} as const

/** 数据组织（第三章 3.5）。运行库当前 84 张表，其余随标准/专利/人才三块建表补齐。 */
export const storageBaseline = { tableCount: 137 } as const
