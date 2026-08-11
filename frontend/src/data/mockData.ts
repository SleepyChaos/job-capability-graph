import type { ReviewItem, RoleCandidate, SourceItem } from '../types'

export const domains = [
  { code: 'T1', name: '智能算法与模型', value: 398, color: '#1769e0' },
  { code: 'T2', name: '感知与传感', value: 312, color: '#0b9c93' },
  { code: 'T3', name: '本体与核心零部件', value: 220, color: '#38a8dc' },
  { code: 'T4', name: '数据与仿真', value: 156, color: '#6fbd73' },
  { code: 'T5', name: '系统软件与工具链', value: 104, color: '#f2a43a' },
  { code: 'T6', name: '交互、安全与评测标准', value: 64, color: '#8e7ad5' },
  { code: 'T7', name: '应用与场景', value: 30, color: '#64748b' },
]

export const sources: SourceItem[] = [
  { id: 1, name: '智联招聘 · 机器人企业组', type: '招聘网站', target: '12 家企业岗位列表', cadence: '每日 09:00', lastRun: '今天 10:21', additions: 612, status: '正常' },
  { id: 2, name: 'BOSS直聘 · 具身智能', type: '招聘网站', target: '8 家企业岗位列表', cadence: '每 12 小时', lastRun: '今天 09:12', additions: 356, status: '正常' },
  { id: 3, name: '重点企业官网', type: '企业官网', target: '18 个新闻与招聘入口', cadence: '每日 08:30', lastRun: '今天 08:33', additions: 247, status: '正常' },
  { id: 4, name: '工信部与地方政策', type: '政府网站', target: '6 个政策与项目栏目', cadence: '每周一', lastRun: '昨天 17:40', additions: 38, status: '需检查' },
  { id: 5, name: '开源与论文动态', type: '技术动态', target: 'GitHub / arXiv 主题页', cadence: '每日 12:00', lastRun: '今天 08:15', additions: 189, status: '正常' },
]

export const roleCandidates: RoleCandidate[] = [
  {
    id: 1,
    name: '具身数据合成工程师',
    stage: '新兴岗位',
    primaryDomain: 'T5 仿真与数据生成',
    secondaryDomains: ['T3 具身决策与规划', 'T6 基础设施与平台'],
    score: 86,
    jdCount: 68,
    companies: 14,
    growth: 42,
    summary: '围绕仿真环境、合成数据管线与真实机器人数据闭环，构建可用于具身模型训练和验证的数据资产。',
    skills: ['Isaac Sim', '场景生成', 'Sim2Real', '数据闭环', 'Python'],
    evidence: ['近 90 天跨 14 家企业出现 68 条相关 JD', '仿真数据管线任务组合连续三个窗口增长', '与传统仿真工程师的职责差异度为 0.31'],
  },
  {
    id: 2,
    name: '具身智能训练工程师',
    stage: '萌芽岗位',
    primaryDomain: 'T3 具身决策与规划',
    secondaryDomains: ['T5 仿真与数据生成'],
    score: 78,
    jdCount: 52,
    companies: 11,
    growth: 35,
    summary: '面向机器人基础模型训练，连接数据处理、策略学习、仿真评测与真机验证流程。',
    skills: ['模仿学习', '强化学习', '多模态模型', '策略评测', 'PyTorch'],
    evidence: ['52 条 JD 中有 61% 同时要求训练与真机验证', '多模态策略学习技术词覆盖率上升 18pp', '11 家企业采用不同岗位名称描述同类任务'],
  },
  {
    id: 3,
    name: '机器人现场智能工程师',
    stage: '潜在岗位',
    primaryDomain: 'T7 行业应用与解决方案',
    secondaryDomains: ['T1 机器人本体与控制', 'T2 感知与环境理解'],
    score: 69,
    jdCount: 31,
    companies: 7,
    growth: 28,
    summary: '负责具身系统在复杂现场的部署、调试、数据回流与持续能力优化。',
    skills: ['系统部署', '现场调试', '故障诊断', '传感器标定', '数据回流'],
    evidence: ['近两个窗口持续出现但企业覆盖仍有限', '岗位任务同时包含交付、数据与模型调优', '与机器人实施工程师存在较高相似度，需继续观察'],
  },
]

export const skillRows = [
  { skill: 'ROS 2', level: '掌握', strength: 92, coverage: 84, companies: 28, trend: 14, state: '稳定' },
  { skill: '传感器融合', level: '掌握', strength: 90, coverage: 78, companies: 24, trend: 15, state: '增强' },
  { skill: '运动规划', level: '掌握', strength: 88, coverage: 72, companies: 22, trend: 16, state: '增强' },
  { skill: '实时控制', level: '熟悉', strength: 85, coverage: 69, companies: 19, trend: 15, state: '稳定' },
  { skill: 'Sim2Real', level: '熟悉', strength: 86, coverage: 61, companies: 17, trend: 21, state: '新兴' },
]

export const matchRows = [
  { skill: 'ROS 2', importance: '必需', evidence: '多机协同物流机器人：负责传感器话题管理与节点通信', result: '匹配', score: 92 },
  { skill: '传感器融合', importance: '必需', evidence: '室内定位项目：IMU + LiDAR + 相机 EKF 融合定位', result: '匹配', score: 88 },
  { skill: 'Python', importance: '必需', evidence: '数据处理与工具链：开发数据处理和评测工具', result: '匹配', score: 93 },
  { skill: '实时控制', importance: '必需', evidence: '提到控制器调试，但缺少周期、延迟和稳定性指标', result: '深度不足', score: 48 },
  { skill: 'Sim2Real', importance: '必需', evidence: '有仿真环境搭建记录，缺少迁移到真实平台的对比实验', result: '证据不足', score: 42 },
  { skill: 'SLAM', importance: '加分', evidence: '室内定位项目：完成地图构建、重定位与回环检测', result: '可迁移', score: 71 },
]

export const initialReviews: ReviewItem[] = [
  { id: 1, type: '技术关键词候选', content: '4D 高斯溅射（4DGS）', source: 'GitHub / arXiv · 3 个独立来源', confidence: 0.71, submittedAt: '今天 09:45', status: '待审核' },
  { id: 2, type: '技术里程碑候选', content: '端到端视觉运动策略完成真机长时验证', source: '企业官网 / 论文 · 时间存在冲突', confidence: 0.68, submittedAt: '今天 09:26', status: '待审核' },
  { id: 3, type: 'JD 结构化条目', content: '机器人系统工程师 · 工作地点与级别缺失', source: '招聘官网 · JD-RAW-01892', confidence: 0.74, submittedAt: '今天 09:08', status: '待审核' },
  { id: 4, type: 'T/L 分类', content: '多模态触觉策略 → T2 / L3 待确认', source: '候选技术词 · 语义近邻分歧', confidence: 0.66, submittedAt: '昨天 18:42', status: '待审核' },
  { id: 5, type: 'JD 聚类归属', content: '具身算法工程师 → 训练工程师簇 / 决策规划簇', source: 'JD-2026-01261 · 两簇距离接近', confidence: 0.63, submittedAt: '昨天 17:20', status: '待审核' },
]

export const taxonomyRows = [
  { level: 'L1', name: '一级分类', nodes: 7, mapped: 7, coverage: '100%', updated: '2026-07-27' },
  { level: 'L2', name: '二级分类', nodes: 43, mapped: 43, coverage: '100%', updated: '2026-07-27' },
  { level: 'L3', name: '标准技术点', nodes: 229, mapped: 229, coverage: '100%', updated: '2026-07-27' },
  { level: 'L4', name: '技术表面词', nodes: 1872, mapped: 1872, coverage: '100%', updated: '2026-07-27' },
]
