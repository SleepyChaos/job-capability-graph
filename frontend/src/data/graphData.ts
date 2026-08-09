export const domainColors: Record<string, string> = {
  T1: '#1769e0',
  T2: '#0b9c93',
  T3: '#38a8dc',
  T4: '#6fbd73',
  T5: '#f2a43a',
  T6: '#8e7ad5',
  T7: '#94a3b8',
}

export interface RelationNode {
  id: string
  label: string
  type: 'cluster' | 'skill'
  x: number
  y: number
  domain: string
  strength: number
  recentRate: number
}

export const relationNodes: RelationNode[] = [
  { id: 'integration', label: '系统集成岗位簇', type: 'cluster', x: 15, y: 24, domain: 'T7', strength: 96, recentRate: 84 },
  { id: 'planning-cluster', label: '决策与规划岗位簇', type: 'cluster', x: 49, y: 14, domain: 'T3', strength: 94, recentRate: 91 },
  { id: 'perception', label: '感知与理解岗位簇', type: 'cluster', x: 83, y: 27, domain: 'T2', strength: 92, recentRate: 87 },
  { id: 'control-cluster', label: '本体控制岗位簇', type: 'cluster', x: 18, y: 78, domain: 'T1', strength: 89, recentRate: 80 },
  { id: 'simulation', label: '仿真迁移岗位簇', type: 'cluster', x: 80, y: 80, domain: 'T5', strength: 84, recentRate: 76 },
  { id: 'ros', label: 'ROS 2', type: 'skill', x: 34, y: 38, domain: 'T6', strength: 92, recentRate: 88 },
  { id: 'planning', label: '运动规划', type: 'skill', x: 53, y: 32, domain: 'T3', strength: 94, recentRate: 92 },
  { id: 'fusion', label: '传感器融合', type: 'skill', x: 70, y: 44, domain: 'T2', strength: 95, recentRate: 90 },
  { id: 'control', label: '实时控制', type: 'skill', x: 34, y: 65, domain: 'T1', strength: 88, recentRate: 82 },
  { id: 'sim', label: 'Sim2Real', type: 'skill', x: 62, y: 69, domain: 'T5', strength: 86, recentRate: 78 },
  { id: 'multimodal', label: '多模态模型', type: 'skill', x: 66, y: 20, domain: 'T3', strength: 81, recentRate: 86 },
  { id: 'slam', label: 'SLAM', type: 'skill', x: 88, y: 52, domain: 'T2', strength: 91, recentRate: 83 },
  { id: 'field', label: '现场调试', type: 'skill', x: 12, y: 52, domain: 'T7', strength: 87, recentRate: 79 },
  { id: 'rl', label: '强化学习', type: 'skill', x: 48, y: 52, domain: 'T3', strength: 79, recentRate: 74 },
  { id: 'twin', label: '数字孪生', type: 'skill', x: 86, y: 62, domain: 'T5', strength: 75, recentRate: 69 },
]

export const relationNodeMap = new Map(relationNodes.map((node) => [node.id, node]))

export const relationEdges = [
  ['integration', 'ros'], ['integration', 'fusion'], ['integration', 'field'], ['integration', 'control'],
  ['planning-cluster', 'planning'], ['planning-cluster', 'multimodal'], ['planning-cluster', 'rl'],
  ['perception', 'fusion'], ['perception', 'slam'], ['perception', 'multimodal'],
  ['control-cluster', 'control'], ['control-cluster', 'planning'], ['control-cluster', 'ros'],
  ['simulation', 'sim'], ['simulation', 'twin'], ['simulation', 'rl'],
] as const

export const heatDayLabels = Array.from({ length: 45 }, (_, index) => {
  const date = new Date(Date.UTC(2026, 5, 26 + index))
  return `${String(date.getUTCMonth() + 1).padStart(2, '0')}-${String(date.getUTCDate()).padStart(2, '0')}`
})

const l2HeatDefinitions = [
  { id: 'motion-control', name: '运动与控制', domain: 'T1', base: 15, trend: 7, seed: 1 },
  { id: 'servo-drive', name: '伺服与驱动', domain: 'T1', base: 10, trend: 2, seed: 2 },
  { id: 'dexterous', name: '灵巧操作', domain: 'T1', base: 8, trend: 8, seed: 3 },
  { id: 'visual-perception', name: '视觉感知', domain: 'T2', base: 17, trend: 3, seed: 4 },
  { id: 'multimodal-perception', name: '多模态感知', domain: 'T2', base: 12, trend: 9, seed: 5 },
  { id: 'localization', name: '定位与建图', domain: 'T2', base: 16, trend: 1, seed: 6 },
  { id: 'motion-planning', name: '运动规划', domain: 'T3', base: 18, trend: 6, seed: 7 },
  { id: 'reinforcement-learning', name: '强化学习', domain: 'T3', base: 13, trend: 8, seed: 8 },
  { id: 'behavior-decision', name: '行为与任务决策', domain: 'T3', base: 11, trend: 5, seed: 9 },
  { id: 'human-robot', name: '人机交互', domain: 'T4', base: 9, trend: 3, seed: 10 },
  { id: 'language-interaction', name: '语言与多模态交互', domain: 'T4', base: 8, trend: 7, seed: 11 },
  { id: 'safe-collaboration', name: '安全协作', domain: 'T4', base: 7, trend: 2, seed: 12 },
  { id: 'simulation-platform', name: '仿真平台', domain: 'T5', base: 12, trend: 4, seed: 13 },
  { id: 'sim2real', name: 'Sim2Real', domain: 'T5', base: 10, trend: 9, seed: 14 },
  { id: 'synthetic-data', name: '合成数据生成', domain: 'T5', base: 7, trend: 8, seed: 15 },
  { id: 'middleware', name: '机器人中间件', domain: 'T6', base: 16, trend: 2, seed: 16 },
  { id: 'training-infra', name: '训练基础设施', domain: 'T6', base: 9, trend: 4, seed: 17 },
  { id: 'edge-cloud', name: '边云部署', domain: 'T6', base: 8, trend: 5, seed: 18 },
  { id: 'industrial-robotics', name: '工业机器人应用', domain: 'T7', base: 11, trend: 1, seed: 19 },
  { id: 'service-solution', name: '服务机器人方案', domain: 'T7', base: 8, trend: 4, seed: 20 },
  { id: 'field-integration', name: '现场系统集成', domain: 'T7', base: 13, trend: 6, seed: 21 },
]

export const l2TechnologyHeatRows = l2HeatDefinitions.map((definition) => ({
  id: definition.id,
  name: definition.name,
  domain: definition.domain,
  values: heatDayLabels.map((_, index) => Math.max(0, Math.min(18, Math.round(
    definition.base / 3 + definition.trend / 3 * ((index - 22) / 22) + ((definition.seed * 3 + index * 5) % 5) - 2,
  )))),
}))

const heatDomainNames: Record<string, string> = {
  T1: '机器人本体与控制', T2: '感知与环境理解', T3: '具身决策与规划', T4: '交互与人机协同',
  T5: '仿真与数据生成', T6: '基础设施与平台', T7: '行业应用与解决方案',
}

export const domainTechnologyHeatRows = Object.keys(heatDomainNames).map((domain) => {
  const rows = l2TechnologyHeatRows.filter((row) => row.domain === domain)
  return {
    domain,
    name: heatDomainNames[domain],
    values: heatDayLabels.map((_, day) => rows.reduce((sum, row) => sum + row.values[day], 0)),
  }
})

export const capabilityClusters = [
  {
    id: 'integration', name: '具身系统集成岗位簇', domain: 'T7', roles: 8, jdCount: 286, growth: 18,
    description: '聚合系统联调、部署交付、数据回流和跨模块问题闭环岗位。',
    skills: [
      { name: 'ROS 2', domain: 'T6', strength: 92, occurrences: 238, recentRate: 91, lastSeen: '本周', x: 50, y: 31 },
      { name: '传感器融合', domain: 'T2', strength: 90, occurrences: 221, recentRate: 88, lastSeen: '本周', x: 67, y: 39 },
      { name: '现场调试', domain: 'T7', strength: 88, occurrences: 205, recentRate: 82, lastSeen: '2 周前', x: 65, y: 66 },
      { name: '实时控制', domain: 'T1', strength: 85, occurrences: 187, recentRate: 67, lastSeen: '1 月前', x: 34, y: 67 },
      { name: 'Sim2Real', domain: 'T5', strength: 68, occurrences: 96, recentRate: 34, lastSeen: '4 月前', x: 20, y: 39 },
    ],
  },
  {
    id: 'planning', name: '具身决策与规划岗位簇', domain: 'T3', roles: 11, jdCount: 354, growth: 24,
    description: '聚合运动规划、策略学习、行为决策和基础模型训练岗位。',
    skills: [
      { name: '运动规划', domain: 'T3', strength: 94, occurrences: 312, recentRate: 94, lastSeen: '本周', x: 50, y: 30 },
      { name: '强化学习', domain: 'T3', strength: 86, occurrences: 266, recentRate: 87, lastSeen: '本周', x: 68, y: 40 },
      { name: '多模态模型', domain: 'T3', strength: 81, occurrences: 224, recentRate: 81, lastSeen: '2 周前', x: 64, y: 68 },
      { name: '模仿学习', domain: 'T3', strength: 75, occurrences: 171, recentRate: 56, lastSeen: '2 月前', x: 33, y: 68 },
      { name: 'PyTorch', domain: 'T6', strength: 62, occurrences: 109, recentRate: 29, lastSeen: '5 月前', x: 18, y: 39 },
    ],
  },
  {
    id: 'perception', name: '感知与环境理解岗位簇', domain: 'T2', roles: 9, jdCount: 312, growth: 15,
    description: '聚合定位建图、多模态感知、环境理解和传感器标定岗位。',
    skills: [
      { name: '传感器融合', domain: 'T2', strength: 95, occurrences: 292, recentRate: 95, lastSeen: '本周', x: 50, y: 29 },
      { name: 'SLAM', domain: 'T2', strength: 93, occurrences: 281, recentRate: 89, lastSeen: '本周', x: 68, y: 40 },
      { name: '视觉感知', domain: 'T2', strength: 89, occurrences: 248, recentRate: 84, lastSeen: '2 周前', x: 64, y: 67 },
      { name: '触觉感知', domain: 'T4', strength: 72, occurrences: 137, recentRate: 52, lastSeen: '2 月前', x: 32, y: 68 },
      { name: '标定工具链', domain: 'T6', strength: 60, occurrences: 88, recentRate: 25, lastSeen: '6 月前', x: 18, y: 39 },
    ],
  },
]
