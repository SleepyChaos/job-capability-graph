// Mock数据 - 具身智能岗位能力图谱系统

// ============ Dashboard 统计数据 ============
export const dashboardStats = {
  totalJDs: 1247,
  totalTerms: 386,
  totalClusters: 24,
  totalNewPositions: 5,
  lastUpdated: "2026-08-08 14:30",
}

// ============ 技术词 Mock ============
export interface TechTerm {
  id: number
  name: string
  category: string
  level: string
  frequency: number
  trend: "rising" | "stable" | "declining"
  status: "active" | "emerging" | "deprecated"
}

export const techTerms: TechTerm[] = [
  { id: 1, name: "ROS2", category: "机器人操作系统", level: "intermediate", frequency: 89, trend: "rising", status: "active" },
  { id: 2, name: "SLAM", category: "感知与导航", level: "advanced", frequency: 76, trend: "stable", status: "active" },
  { id: 3, name: "运动规划", category: "运动控制", level: "advanced", frequency: 82, trend: "rising", status: "active" },
  { id: 4, name: "强化学习", category: "AI算法", level: "advanced", frequency: 95, trend: "rising", status: "active" },
  { id: 5, name: "大模型推理", category: "AI算法", level: "expert", frequency: 67, trend: "rising", status: "emerging" },
  { id: 6, name: "数字孪生", category: "仿真", level: "intermediate", frequency: 54, trend: "rising", status: "emerging" },
  { id: 7, name: "力控算法", category: "运动控制", level: "expert", frequency: 43, trend: "stable", status: "active" },
  { id: 8, name: "多模态感知", category: "感知与导航", level: "advanced", frequency: 71, trend: "rising", status: "active" },
  { id: 9, name: "嵌入式开发", category: "硬件", level: "basic", frequency: 62, trend: "stable", status: "active" },
  { id: 10, name: "Gazebo仿真", category: "仿真", level: "basic", frequency: 48, trend: "declining", status: "active" },
  { id: 11, name: "人形机器人", category: "机器人形态", level: "intermediate", frequency: 88, trend: "rising", status: "emerging" },
  { id: 12, name: "灵巧手操作", category: "运动控制", level: "expert", frequency: 35, trend: "rising", status: "emerging" },
]

// ============ 岗位聚类 Mock ============
export interface JobCluster {
  id: number
  name: string
  category: string
  jdCount: number
  termCount: number
  status: "active" | "pending_review" | "archived"
  isPredefined: boolean
  confidence: number
  topSkills: string[]
}

export const jobClusters: JobCluster[] = [
  { id: 1, name: "机器人算法工程师", category: "算法", jdCount: 186, termCount: 15, status: "active", isPredefined: true, confidence: 0.95, topSkills: ["ROS2", "SLAM", "运动规划", "C++"] },
  { id: 2, name: "具身智能研究员", category: "研究", jdCount: 94, termCount: 12, status: "active", isPredefined: true, confidence: 0.92, topSkills: ["强化学习", "大模型推理", "多模态感知", "PyTorch"] },
  { id: 3, name: "机器人硬件工程师", category: "硬件", jdCount: 127, termCount: 10, status: "active", isPredefined: true, confidence: 0.93, topSkills: ["嵌入式开发", "电路设计", "传感器集成", "PCB"] },
  { id: 4, name: "仿真工程师", category: "仿真", jdCount: 63, termCount: 8, status: "active", isPredefined: true, confidence: 0.91, topSkills: ["数字孪生", "Gazebo", "Isaac Sim", "物理引擎"] },
  { id: 5, name: "人形机器人系统工程师", category: "系统", jdCount: 45, termCount: 14, status: "active", isPredefined: false, confidence: 0.87, topSkills: ["人形机器人", "全身控制", "步态规划", "ROS2"] },
  { id: 6, name: "灵巧手操作工程师", category: "控制", jdCount: 18, termCount: 9, status: "pending_review", isPredefined: false, confidence: 0.72, topSkills: ["灵巧手操作", "力控算法", "触觉感知", "抓取规划"] },
]

// ============ 新发现岗位 Mock ============
export interface NewPosition {
  id: number
  name: string
  coreResponsibilities: string
  requiredSkills: string[]
  bonusSkills: string[]
  industryScenarios: string
  relatedMilestones: string[]
  confidence: number
  status: "candidate" | "confirmed" | "rejected"
  createdAt: string
}

export const newPositions: NewPosition[] = [
  {
    id: 1,
    name: "具身智能大模型部署工程师",
    coreResponsibilities: "负责将大语言模型与多模态模型部署到具身智能机器人平台，实现机器人对自然语言指令的理解与执行",
    requiredSkills: ["大模型推理", "ROS2", "边缘计算", "模型量化"],
    bonusSkills: ["多模态感知", "ONNX", "TensorRT"],
    industryScenarios: "服务机器人、工业协作机器人、家庭陪伴机器人",
    relatedMilestones: ["多模态大模型突破", "端侧推理芯片成熟"],
    confidence: 0.91,
    status: "candidate",
    createdAt: "2026-08-05",
  },
  {
    id: 2,
    name: "人机协作安全工程师",
    coreResponsibilities: "设计和验证人形机器人与人协作场景下的安全策略，确保符合安全标准",
    requiredSkills: ["力控算法", "安全标准", "传感器融合", "风险评估"],
    bonusSkills: ["ISO/TS 15066", "功能安全", "仿真测试"],
    industryScenarios: "制造业产线、医疗辅助、物流仓储",
    relatedMilestones: ["人形机器人量产里程碑"],
    confidence: 0.85,
    status: "candidate",
    createdAt: "2026-08-03",
  },
  {
    id: 3,
    name: "机器人数据标注与训练工程师",
    coreResponsibilities: "构建具身智能训练数据集，设计数据采集与标注流程，优化模型训练数据质量",
    requiredSkills: ["数据标注", "3D点云", "场景理解", "Python"],
    bonusSkills: ["强化学习", "仿真数据生成", "数据增强"],
    industryScenarios: "自动驾驶、机器人学习、数字孪生",
    relatedMilestones: ["大规模具身智能数据集发布"],
    confidence: 0.78,
    status: "candidate",
    createdAt: "2026-07-28",
  },
]

// ============ 能力更新事件 Mock ============
export interface CapabilityUpdate {
  id: number
  clusterName: string
  termName: string
  changeType: "added" | "removed" | "modified"
  description: string
  evidenceSource: string
  confidence: number
  createdAt: string
  status: "pending" | "confirmed" | "rejected"
}

export const capabilityUpdates: CapabilityUpdate[] = [
  { id: 1, clusterName: "机器人算法工程师", termName: "大模型推理", changeType: "added", description: "近期多个JD新增了大模型相关技能要求，反映AI与机器人融合趋势", evidenceSource: "JD#1024, JD#1031, JD#1045", confidence: 0.89, createdAt: "2026-08-07", status: "pending" },
  { id: 2, clusterName: "仿真工程师", termName: "Gazebo仿真", changeType: "modified", description: "Gazebo使用频率下降，Isaac Sim和MuJoCo提及频率上升，建议调整权重", evidenceSource: "技术词频率统计", confidence: 0.82, createdAt: "2026-08-06", status: "pending" },
  { id: 3, clusterName: "机器人硬件工程师", termName: "传统PLC编程", changeType: "removed", description: "近3个月JD中PLC编程出现频率下降至5%以下，疑似被ROS2取代", evidenceSource: "时间衰减分析", confidence: 0.76, createdAt: "2026-08-04", status: "confirmed" },
  { id: 4, clusterName: "具身智能研究员", termName: "具身大模型", changeType: "added", description: "多篇JD提及具身大模型（Embodied Foundation Model），为新兴技能要求", evidenceSource: "JD#1050, JD#1052", confidence: 0.91, createdAt: "2026-08-02", status: "confirmed" },
]

// ============ 爬取目标 Mock ============
export interface CrawlTarget {
  id: number
  name: string
  url: string
  type: "recruitment" | "company" | "government"
  frequency: string
  status: "active" | "paused" | "disabled"
  lastCrawlAt: string
  itemsCount: number
}

export const crawlTargets: CrawlTarget[] = [
  { id: 1, name: "某招聘平台-具身智能", url: "https://example.com/jobs/embodied-ai", type: "recruitment", frequency: "每日", status: "active", lastCrawlAt: "2026-08-08 06:00", itemsCount: 456 },
  { id: 2, name: "优必选官网-招聘", url: "https://www.ubtech.com/careers", type: "company", frequency: "每周", status: "active", lastCrawlAt: "2026-08-05 08:00", itemsCount: 23 },
  { id: 3, name: "工信部-智能制造政策", url: "https://www.miit.gov.cn/policy", type: "government", frequency: "每周", status: "active", lastCrawlAt: "2026-08-04 10:00", itemsCount: 12 },
  { id: 4, name: "宇树科技-招聘", url: "https://www.unitree.com/jobs", type: "company", frequency: "每周", status: "paused", lastCrawlAt: "2026-07-20 09:00", itemsCount: 8 },
]

// ============ 采集记录 Mock ============
export interface CrawlRecord {
  id: number
  targetName: string
  startedAt: string
  finishedAt: string
  status: "success" | "failed" | "running"
  newItems: number
  error?: string
}

export const crawlRecords: CrawlRecord[] = [
  { id: 1, targetName: "某招聘平台-具身智能", startedAt: "2026-08-08 06:00", finishedAt: "2026-08-08 06:12", status: "success", newItems: 8 },
  { id: 2, targetName: "优必选官网-招聘", startedAt: "2026-08-05 08:00", finishedAt: "2026-08-05 08:03", status: "success", newItems: 2 },
  { id: 3, targetName: "工信部-智能制造政策", startedAt: "2026-08-04 10:00", finishedAt: "2026-08-04 10:01", status: "success", newItems: 1 },
  { id: 4, targetName: "宇树科技-招聘", startedAt: "2026-07-20 09:00", finishedAt: "2026-07-20 09:00", status: "failed", newItems: 0, error: "连接超时" },
]

// ============ 技术里程碑 Mock ============
export interface Milestone {
  id: number
  title: string
  description: string
  techDirection: string
  occurredAt: string
  impactScope: string
  confidence: number
  status: "confirmed" | "pending"
}

export const milestones: Milestone[] = [
  { id: 1, title: "多模态大模型在机器人操作中的突破", description: "多个研究团队实现了基于多模态大模型的机器人灵巧操作", techDirection: "AI+机器人", occurredAt: "2026-06", impactScope: "具身智能全领域", confidence: 0.95, status: "confirmed" },
  { id: 2, title: "人形机器人量产成本降至10万以下", description: "多家企业宣布人形机器人量产成本突破，商业化落地加速", techDirection: "人形机器人", occurredAt: "2026-07", impactScope: "制造业、服务业", confidence: 0.90, status: "confirmed" },
  { id: 3, title: "端侧推理芯片算力突破100TOPS", description: "新一代边缘AI芯片发布，支持大模型本地推理", techDirection: "硬件", occurredAt: "2026-05", impactScope: "机器人智能化", confidence: 0.88, status: "confirmed" },
]

// ============ 简历匹配 Mock ============
export interface ResumeProfile {
  targetPosition: string
  skills: { name: string; level: string }[]
  workExperience: { company: string; role: string; duration: string }[]
  education: { school: string; degree: string; major: string }
  totalYears: number
  workStyle: string
  developmentDirection: string
  learningPotential: string
  strengthSummary: string
}

export const mockResumeProfile: ResumeProfile = {
  targetPosition: "机器人算法工程师",
  skills: [
    { name: "C++", level: "精通" },
    { name: "ROS2", level: "熟练" },
    { name: "SLAM", level: "熟练" },
    { name: "Python", level: "精通" },
    { name: "运动规划", level: "了解" },
    { name: "OpenCV", level: "熟练" },
  ],
  workExperience: [
    { company: "某机器人公司", role: "算法工程师", duration: "2023-2026" },
    { company: "某自动驾驶公司", role: "感知工程师", duration: "2021-2023" },
  ],
  education: { school: "某某大学", degree: "硕士", major: "机器人工程" },
  totalYears: 5,
  workStyle: "独立钻研型，擅长攻克技术难点",
  developmentDirection: "希望向具身智能方向发展，关注大模型与机器人结合",
  learningPotential: "技术栈跨度大，从感知到控制均有涉猎，学习能力强",
  strengthSummary: "具备扎实的SLAM和视觉算法基础，有实际项目交付经验，对新技术保持高敏感度",
}

export const mockMatchResult = {
  overallScore: 72,
  hardSkillScore: 78,
  depthScore: 65,
  experienceScore: 80,
  softMatchScore: 75,
  potentialScore: 82,
  matchedSkills: ["C++", "ROS2", "SLAM", "Python"],
  missingSkills: ["强化学习", "大模型推理", "数字孪生"],
  insufficientSkills: ["运动规划", "力控算法"],
  improvementPlan: {
    shortTerm: ["学习运动规划基础（MoveIt2）", "了解强化学习在机器人中的应用"],
    midTerm: ["完成一个基于RL的机器人控制项目", "学习大模型推理部署"],
    longTerm: ["系统学习具身智能理论框架", "参与开源具身智能项目"],
  },
}

// ============ 图谱节点 Mock ============
export interface GraphNode {
  id: string
  label: string
  type: "cluster" | "term" | "milestone"
  category?: string
  level?: string
  size?: number
}

export interface GraphEdge {
  source: string
  target: string
  label?: string
  weight?: number
}

export const graphNodes: GraphNode[] = [
  { id: "c1", label: "机器人算法工程师", type: "cluster", category: "算法", size: 40 },
  { id: "c2", label: "具身智能研究员", type: "cluster", category: "研究", size: 30 },
  { id: "c3", label: "机器人硬件工程师", type: "cluster", category: "硬件", size: 35 },
  { id: "c4", label: "仿真工程师", type: "cluster", category: "仿真", size: 25 },
  { id: "c5", label: "人形机器人系统工程师", type: "cluster", category: "系统", size: 22 },
  { id: "t1", label: "ROS2", type: "term", category: "机器人操作系统", size: 20 },
  { id: "t2", label: "SLAM", type: "term", category: "感知与导航", size: 18 },
  { id: "t3", label: "运动规划", type: "term", category: "运动控制", size: 18 },
  { id: "t4", label: "强化学习", type: "term", category: "AI算法", size: 22 },
  { id: "t5", label: "大模型推理", type: "term", category: "AI算法", size: 20 },
  { id: "t6", label: "数字孪生", type: "term", category: "仿真", size: 16 },
  { id: "t7", label: "力控算法", type: "term", category: "运动控制", size: 14 },
  { id: "t8", label: "多模态感知", type: "term", category: "感知与导航", size: 18 },
  { id: "t9", label: "嵌入式开发", type: "term", category: "硬件", size: 16 },
  { id: "t10", label: "人形机器人", type: "term", category: "机器人形态", size: 20 },
  { id: "m1", label: "多模态大模型突破", type: "milestone", size: 12 },
  { id: "m2", label: "人形机器人量产", type: "milestone", size: 12 },
]

export const graphEdges: GraphEdge[] = [
  { source: "c1", target: "t1", label: "必备", weight: 5 },
  { source: "c1", target: "t2", label: "必备", weight: 4 },
  { source: "c1", target: "t3", label: "必备", weight: 4 },
  { source: "c2", target: "t4", label: "必备", weight: 5 },
  { source: "c2", target: "t5", label: "必备", weight: 4 },
  { source: "c2", target: "t8", label: "必备", weight: 3 },
  { source: "c3", target: "t9", label: "必备", weight: 5 },
  { source: "c4", target: "t6", label: "必备", weight: 4 },
  { source: "c5", target: "t10", label: "必备", weight: 5 },
  { source: "c5", target: "t1", label: "必备", weight: 3 },
  { source: "c5", target: "t3", label: "加分", weight: 2 },
  { source: "m1", target: "t5", label: "推动", weight: 3 },
  { source: "m1", target: "t8", label: "推动", weight: 3 },
  { source: "m2", target: "t10", label: "推动", weight: 4 },
  { source: "c1", target: "t5", label: "新增", weight: 2 },
]
