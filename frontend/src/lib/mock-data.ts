// Mock data for the job atlas system

export interface JobNode {
  id: string;
  name: string;
  category: 'ai' | 'bigdata' | 'iot' | 'smart' | 'embodied';
  l1?: string; // 主导 L1 域（T1–T7 具身子域 / AI / BD / IOT / IS，后端 /api/graph 透传）
  level: 'junior' | 'mid' | 'senior';
  skills: string[];
  demand: number;
  salary: string;
  description: string;
}

export interface SkillNode {
  id: string;
  name: string;
  type: 'hard' | 'soft' | 'domain' | 'tool';
  jobs: string[];
  weight: number;
}

export interface NewJob {
  id: string;
  name: string;
  confidence: number;
  signalStrength: 'high' | 'medium' | 'low';
  source: string;
  skills: string[];
  growth: number;
  salary: string;
  description: string;
  scenarios: string[];
  bonusSkills: string[];
  /** 聚类聚合岗位数（发现页真实口径，来自 /api/clusters） */
  jobCount?: number;
  /** 聚类命名来源：llm（待审核）/ heuristic（规则命名） */
  nameSource?: 'llm' | 'heuristic';
}

export interface JobUpdate {
  id: string;
  jobId: string;
  jobName: string;
  level: string;
  updatedAt: string;
  changes: number;
  history: ChangeRecord[];
}

export interface ChangeRecord {
  id: string;
  type: 'add' | 'remove' | 'modify';
  skill: string;
  oldValue?: string;
  newValue?: string;
  source: string;
  confidence: number;
  date: string;
}

export interface ResumeMatch {
  overallScore: number;
  skillScore: number;
  experienceScore: number;
  gaps: GapItem[];
  learningPath: LearningItem[];
}

export interface GapItem {
  skill: string;
  severity: 'severe' | 'moderate' | 'minor';
  importance: number;
  difficulty: number;
}

export interface LearningItem {
  phase: string;
  title: string;
  duration: string;
  resources: string[];
}

// Job nodes for the atlas
export const jobNodes: JobNode[] = [
  { id: 'j1', name: 'AI算法工程师', category: 'ai', level: 'mid', skills: ['Python', 'PyTorch', '深度学习', 'NLP', '计算机视觉'], demand: 92, salary: '30-60K', description: '负责AI算法研发与模型优化' },
  { id: 'j2', name: '大模型应用工程师', category: 'ai', level: 'senior', skills: ['LLM', 'Prompt Engineering', 'RAG', 'LangChain', 'Agent'], demand: 98, salary: '40-80K', description: '基于大语言模型构建智能应用' },
  { id: 'j3', name: '数据工程师', category: 'bigdata', level: 'mid', skills: ['Spark', 'Flink', 'Hive', 'SQL', '数据建模'], demand: 85, salary: '25-50K', description: '构建与维护大数据处理管道' },
  { id: 'j4', name: '数据分析师', category: 'bigdata', level: 'junior', skills: ['SQL', 'Python', 'Tableau', '统计学', '数据可视化'], demand: 78, salary: '15-30K', description: '通过数据分析驱动业务决策' },
  { id: 'j5', name: 'IoT系统架构师', category: 'iot', level: 'senior', skills: ['嵌入式系统', 'MQTT', '边缘计算', '数字孪生', '系统架构'], demand: 72, salary: '35-70K', description: '设计物联网系统整体架构' },
  { id: 'j6', name: '嵌入式开发工程师', category: 'iot', level: 'mid', skills: ['C/C++', 'RTOS', 'ARM', 'Linux驱动', '硬件调试'], demand: 68, salary: '20-40K', description: '开发嵌入式系统与固件' },
  { id: 'j7', name: '智能产品经理', category: 'smart', level: 'senior', skills: ['产品规划', 'AI应用', '用户研究', '数据分析', '项目管理'], demand: 75, salary: '30-55K', description: '规划智能产品方向与路线图' },
  { id: 'j8', name: 'AI训练师', category: 'ai', level: 'junior', skills: ['数据标注', '模型评测', 'Prompt优化', '质量管控'], demand: 88, salary: '12-25K', description: '训练与优化AI模型表现' },
  { id: 'j9', name: '数据治理专家', category: 'bigdata', level: 'senior', skills: ['数据质量', '元数据管理', '数据标准', '合规治理', '数据血缘'], demand: 70, salary: '30-55K', description: '建立企业级数据治理体系' },
  { id: 'j10', name: '智能硬件工程师', category: 'smart', level: 'mid', skills: ['传感器', 'PCB设计', '嵌入式Linux', '通信协议', '测试验证'], demand: 65, salary: '20-35K', description: '研发智能硬件产品' },
  { id: 'j11', name: 'MLOps工程师', category: 'ai', level: 'mid', skills: ['Docker', 'K8s', 'CI/CD', '模型部署', '监控运维'], demand: 82, salary: '25-50K', description: '构建机器学习工程化平台' },
  { id: 'j12', name: '安全运营工程师', category: 'smart', level: 'mid', skills: ['网络安全', 'SIEM', '威胁检测', '应急响应', '安全合规'], demand: 76, salary: '22-45K', description: '保障信息系统安全运营' },
];

// Skill nodes
export const skillNodes: SkillNode[] = [
  { id: 's1', name: 'Python', type: 'hard', jobs: ['j1', 'j3', 'j4', 'j8'], weight: 95 },
  { id: 's2', name: 'PyTorch', type: 'hard', jobs: ['j1', 'j8'], weight: 88 },
  { id: 's3', name: '深度学习', type: 'hard', jobs: ['j1', 'j2'], weight: 90 },
  { id: 's4', name: 'NLP', type: 'hard', jobs: ['j1', 'j2'], weight: 85 },
  { id: 's5', name: 'LLM', type: 'hard', jobs: ['j2', 'j8'], weight: 96 },
  { id: 's6', name: 'RAG', type: 'hard', jobs: ['j2'], weight: 82 },
  { id: 's7', name: 'Spark', type: 'hard', jobs: ['j3'], weight: 78 },
  { id: 's8', name: 'SQL', type: 'hard', jobs: ['j3', 'j4'], weight: 92 },
  { id: 's9', name: '数据可视化', type: 'hard', jobs: ['j4', 'j7'], weight: 75 },
  { id: 's10', name: '嵌入式系统', type: 'hard', jobs: ['j5', 'j6'], weight: 80 },
  { id: 's11', name: '边缘计算', type: 'hard', jobs: ['j5'], weight: 70 },
  { id: 's12', name: '产品规划', type: 'soft', jobs: ['j7'], weight: 85 },
  { id: 's13', name: '数据分析', type: 'domain', jobs: ['j4', 'j7', 'j9'], weight: 88 },
  { id: 's14', name: 'Docker', type: 'tool', jobs: ['j11', 'j3'], weight: 82 },
  { id: 's15', name: 'K8s', type: 'tool', jobs: ['j11'], weight: 78 },
  { id: 's16', name: 'Prompt Engineering', type: 'hard', jobs: ['j2', 'j8'], weight: 90 },
  { id: 's17', name: 'Agent', type: 'hard', jobs: ['j2'], weight: 86 },
  { id: 's18', name: '项目管理', type: 'soft', jobs: ['j7', 'j5'], weight: 72 },
  { id: 's19', name: '网络安全', type: 'hard', jobs: ['j12'], weight: 80 },
  { id: 's20', name: '数据质量', type: 'domain', jobs: ['j9'], weight: 76 },
];

// New/emerging jobs
export const newJobs: NewJob[] = [
  { id: 'n1', name: 'AI Agent 架构师', confidence: 92, signalStrength: 'high', source: 'JD聚类+论文传导', skills: ['Agent框架', '多智能体协作', '工具编排', '记忆系统'], growth: 340, salary: '50-100K', description: '设计并构建基于大模型的智能Agent系统，实现复杂任务的自动化执行', scenarios: ['企业智能助手', '自动化工作流', '智能客服系统'], bonusSkills: ['分布式系统', '知识图谱'] },
  { id: 'n2', name: '数字孪生工程师', confidence: 85, signalStrength: 'high', source: '政策驱动+JD聚类', skills: ['3D建模', '实时渲染', 'IoT数据融合', '仿真引擎'], growth: 180, salary: '35-65K', description: '构建物理世界的数字镜像，实现实时监控与仿真优化', scenarios: ['智慧工厂', '智慧城市', '智能建筑'], bonusSkills: ['WebGL', 'Unity/Unreal'] },
  { id: 'n3', name: 'AI安全伦理官', confidence: 78, signalStrength: 'medium', source: '政策驱动+论文传导', skills: ['AI伦理', '风险评估', '合规审查', '偏见检测'], growth: 150, salary: '30-55K', description: '确保AI系统的公平性、透明性和合规性', scenarios: ['AI产品审核', '算法审计', '合规咨询'], bonusSkills: ['法律知识', '社会学'] },
  { id: 'n4', name: 'Prompt工程师', confidence: 95, signalStrength: 'high', source: 'JD聚类', skills: ['Prompt设计', '效果评测', '场景适配', '模型微调'], growth: 280, salary: '25-50K', description: '优化与大模型的交互方式，提升AI应用效果', scenarios: ['内容生成', '代码辅助', '数据分析'], bonusSkills: ['语言学', '心理学'] },
  { id: 'n5', name: '边缘AI开发者', confidence: 72, signalStrength: 'medium', source: '论文传导+JD聚类', skills: ['模型压缩', '端侧推理', '异构计算', '功耗优化'], growth: 120, salary: '30-55K', description: '在边缘设备上部署和运行AI模型', scenarios: ['智能摄像头', '车载AI', '工业检测'], bonusSkills: ['FPGA', 'TensorRT'] },
  { id: 'n6', name: '数据资产运营师', confidence: 68, signalStrength: 'low', source: '政策驱动', skills: ['数据资产评估', '数据交易', '价值量化', '合规管理'], growth: 95, salary: '25-45K', description: '管理和运营企业数据资产，推动数据价值变现', scenarios: ['数据交易所', '数据银行', '资产证券化'], bonusSkills: ['金融知识', '区块链技术'] },
];

// Job evolution updates
export const jobUpdates: JobUpdate[] = [
  {
    id: 'u1', jobId: 'j1', jobName: 'AI算法工程师', level: '中级', updatedAt: '2025-01-15', changes: 5,
    history: [
      { id: 'c1', type: 'add', skill: 'RAG技术栈', newValue: '必备', source: 'BOSS直聘/拉勾', confidence: 92, date: '2025-01-15' },
      { id: 'c2', type: 'modify', skill: '大模型微调', oldValue: '加分项', newValue: '必备项', source: '猎聘/智联', confidence: 88, date: '2025-01-10' },
      { id: 'c3', type: 'add', skill: 'Agent开发', newValue: '加分项', source: '论文传导', confidence: 75, date: '2025-01-05' },
      { id: 'c4', type: 'remove', skill: 'TensorFlow', source: '多源交叉验证', confidence: 85, date: '2024-12-20' },
      { id: 'c5', type: 'modify', skill: '模型部署', oldValue: '了解即可', newValue: '熟练掌握', source: '企业调研', confidence: 90, date: '2024-12-15' },
    ]
  },
  {
    id: 'u2', jobId: 'j3', jobName: '数据工程师', level: '中级', updatedAt: '2025-01-12', changes: 3,
    history: [
      { id: 'c6', type: 'add', skill: '实时计算(Flink)', newValue: '必备', source: 'BOSS直聘', confidence: 90, date: '2025-01-12' },
      { id: 'c7', type: 'modify', skill: '云原生数据湖', oldValue: '了解', newValue: '必备', source: '猎聘/脉脉', confidence: 85, date: '2025-01-08' },
      { id: 'c8', type: 'add', skill: '数据治理基础', newValue: '加分项', source: '政策文件', confidence: 78, date: '2025-01-02' },
    ]
  },
  {
    id: 'u3', jobId: 'j5', jobName: 'IoT系统架构师', level: '高级', updatedAt: '2025-01-10', changes: 4,
    history: [
      { id: 'c9', type: 'add', skill: 'AIoT融合', newValue: '必备', source: '行业报告', confidence: 88, date: '2025-01-10' },
      { id: 'c10', type: 'modify', skill: '边缘计算', oldValue: '加分项', newValue: '必备项', source: 'JD聚类', confidence: 92, date: '2025-01-06' },
      { id: 'c11', type: 'add', skill: '数字孪生平台', newValue: '加分项', source: '论文传导', confidence: 72, date: '2024-12-28' },
      { id: 'c12', type: 'remove', skill: 'ZigBee协议', source: '多源验证', confidence: 80, date: '2024-12-20' },
    ]
  },
  {
    id: 'u4', jobId: 'j7', jobName: '智能产品经理', level: '高级', updatedAt: '2025-01-08', changes: 3,
    history: [
      { id: 'c13', type: 'add', skill: 'AI应用设计', newValue: '必备', source: 'JD聚类', confidence: 94, date: '2025-01-08' },
      { id: 'c14', type: 'modify', skill: '数据分析能力', oldValue: '了解', newValue: '熟练', source: '企业调研', confidence: 86, date: '2025-01-03' },
      { id: 'c15', type: 'add', skill: '大模型产品化', newValue: '加分项', source: '论文传导', confidence: 70, date: '2024-12-25' },
    ]
  },
];

// Data governance
export interface DataSource {
  id: string;
  name: string;
  type: string;
  volume: number;
  quality: number;
  noiseRate: number;
  updateCycle: string;
  status: 'active' | 'warning' | 'inactive';
}

export interface AuditItem {
  id: string;
  entity: string;
  type: 'job' | 'skill';
  confidence: number;
  source: string;
  status: 'pending' | 'approved' | 'rejected';
  submitDate: string;
}

export const dataSources: DataSource[] = [
  { id: 'ds1', name: 'BOSS直聘', type: '招聘平台', volume: 125000, quality: 92, noiseRate: 3.2, updateCycle: '每日', status: 'active' },
  { id: 'ds2', name: '猎聘网', type: '招聘平台', volume: 98000, quality: 89, noiseRate: 4.1, updateCycle: '每日', status: 'active' },
  { id: 'ds3', name: '智联招聘', type: '招聘平台', volume: 110000, quality: 87, noiseRate: 5.0, updateCycle: '每日', status: 'active' },
  { id: 'ds4', name: 'arXiv论文库', type: '学术数据', volume: 45000, quality: 95, noiseRate: 1.2, updateCycle: '每周', status: 'active' },
  { id: 'ds5', name: '国家专利局', type: '专利数据', volume: 32000, quality: 93, noiseRate: 2.0, updateCycle: '每月', status: 'active' },
  { id: 'ds6', name: '政策文件库', type: '政策数据', volume: 8500, quality: 96, noiseRate: 0.8, updateCycle: '每月', status: 'active' },
  { id: 'ds7', name: '脉脉职场', type: '社交数据', volume: 67000, quality: 72, noiseRate: 12.5, updateCycle: '每周', status: 'warning' },
  { id: 'ds8', name: '行业报告库', type: '研报数据', volume: 15000, quality: 88, noiseRate: 3.5, updateCycle: '每月', status: 'active' },
];

export const auditItems: AuditItem[] = [
  { id: 'a1', entity: 'AI Agent 编排师', type: 'job', confidence: 62, source: 'JD聚类', status: 'pending', submitDate: '2025-01-14' },
  { id: 'a2', entity: '量子算法工程师', type: 'job', confidence: 58, source: '论文传导', status: 'pending', submitDate: '2025-01-13' },
  { id: 'a3', entity: '联邦学习框架', type: 'skill', confidence: 65, source: '多源交叉', status: 'pending', submitDate: '2025-01-12' },
  { id: 'a4', entity: 'AIGC内容审核员', type: 'job', confidence: 71, source: 'JD聚类', status: 'approved', submitDate: '2025-01-10' },
  { id: 'a5', entity: '脑机接口工程师', type: 'job', confidence: 45, source: '论文传导', status: 'rejected', submitDate: '2025-01-09' },
];

// Report templates
export interface ReportTemplate {
  id: string;
  name: string;
  type: string;
  description: string;
  sections: string[];
}

export const reportTemplates: ReportTemplate[] = [
  {
    id: 'r1', name: '岗位能力演化报告', type: 'evolution',
    description: '追踪特定岗位在一定周期内的能力变化轨迹，分析技能需求趋势',
    sections: ['摘要', '岗位概览', '能力变更明细', '趋势分析', '数据源说明', '结论与建议']
  },
  {
    id: 'r2', name: '新岗位立项论证报告', type: 'proposal',
    description: '对新兴岗位进行可行性论证，包含市场信号、技能需求、发展前景',
    sections: ['摘要', '岗位定义', '市场信号分析', '技能需求画像', '对标分析', '发展建议']
  },
  {
    id: 'r3', name: '区域人才白皮书', type: 'whitepaper',
    description: '全面分析特定区域信息技术人才现状、供需缺口与发展趋势',
    sections: ['摘要', '区域概况', '人才供给分析', '需求侧分析', '供需匹配度', '趋势预测', '政策建议']
  },
];

// ============================================
// 具身智能企业数据 (来源: 具身智能公司_融资分类完整版)
// ============================================
export interface CompanyNode {
  id: string;
  name: string;
  englishName: string;
  chainLevel: string;
  subField: string;
  products: string;
  productType: string;
  keyFeatures: string;
  massProduction: string;
  city: string;
  region: string;
  province: string;
  financeStage: string;
  financeRaw: string;
  website: string;
  skills: string[];
  positions: string[];
}

export interface CompanySkillStat {
  name: string;
  count: number;
  companies: string[];
}

export interface CompanyData {
  totalCompanies: number;
  companies: CompanyNode[];
  skills: CompanySkillStat[];
  positions: { name: string; count: number }[];
  chainLevels: Record<string, number>;
  regions: Record<string, number>;
  financeStages: Record<string, number>;
}

// 从 JSON 文件导入企业数据 (JSON keys are snake_case, mapped to camelCase interface)
import companyDataRaw from './company-data.json';
// eslint-disable-next-line @typescript-eslint/no-explicit-any
const rawJson = companyDataRaw as any;
const rawCompanies: any[] = rawJson.companies || [];
export const companyData: CompanyData = {
  totalCompanies: rawJson.total_companies ?? 0,
  companies: rawCompanies.map((c: any, idx: number) => ({
    id: `c${idx + 1}`,
    name: String(c.name ?? ''),
    englishName: String(c.english_name ?? ''),
    chainLevel: String(c.chain_level ?? ''),
    subField: String(c.sub_field ?? ''),
    products: String(c.products ?? ''),
    productType: String(c.product_type ?? ''),
    keyFeatures: String(c.key_features ?? ''),
    massProduction: String(c.mass_production ?? ''),
    city: String(c.city ?? ''),
    region: String(c.region ?? ''),
    province: String(c.province ?? ''),
    financeStage: String(c.finance_stage ?? ''),
    financeRaw: String(c.finance_raw ?? ''),
    website: String(c.website ?? ''),
    skills: Array.isArray(c.skills) ? c.skills.map(String) : [],
    positions: Array.isArray(c.positions) ? c.positions.map(String) : [],
  })),
  skills: Array.isArray(rawJson.skills) ? rawJson.skills : [],
  positions: Array.isArray(rawJson.positions) ? rawJson.positions : [],
  chainLevels: rawJson.chain_levels ?? {},
  regions: rawJson.regions ?? {},
  financeStages: rawJson.finance_stages ?? {},
};

// 企业产业链层级映射到图谱分类
export const chainLevelToCategory: Record<string, 'ai' | 'bigdata' | 'iot' | 'smart'> = {
  '上游-核心零部件': 'iot',
  '上游+中游': 'iot',
  '中游-整机制造': 'smart',
  '中游+下游': 'smart',
  '下游-场景应用': 'ai',
  '全产业链': 'ai',
  '其他': 'smart',
};

// 融资阶段颜色映射
export const financeStageColors: Record<string, string> = {
  '天使/种子轮': '#94A3B8',
  'Pre-A轮': '#60A5FA',
  'A轮': '#3B82F6',
  'B轮': '#8B5CF6',
  'C轮': '#7C3AED',
  'D轮及以后': '#6D28D9',
  '战略融资': '#F59E0B',
  'IPO/上市': '#10B981',
  '其他': '#94A3B8',
};

// 地区颜色映射
export const regionColors: Record<string, string> = {
  '华南': '#3B82F6',
  '华北': '#8B5CF6',
  '华东': '#10B981',
  '海外': '#F59E0B',
  '西南': '#EF4444',
  '华中': '#06B6D4',
  '东北': '#EC4899',
  '西北': '#F97316',
};
