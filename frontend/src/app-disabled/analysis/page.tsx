'use client';

import { useState, useMemo } from 'react';
import { Search, TrendingDown, TrendingUp, AlertTriangle, Lightbulb, Building2, MapPin, FileText, Target, Zap, BarChart3, ArrowRight, Shield, Users, Award, ChevronRight, Activity, Brain, Cpu } from 'lucide-react';

// ============ Mock Data ============

const techTrends = {
  '激光SLAM': {
    decline: true,
    paperGrowth: -5.2,
    patentReplacement: 42,
    demandDrop: 30,
    timeline: '18个月',
    emergingSkills: [
      { name: 'NeRF-based 建图', growth: 280, scarcity: '极高', stage: '爆发前期' },
      { name: '端到端导航', growth: 195, scarcity: '高', stage: '快速增长期' },
      { name: '3D高斯泼溅', growth: 420, scarcity: '极高', stage: '萌芽期' },
    ],
    trendData: [45, 42, 38, 35, 32, 28, 25, 22, 20, 18, 16, 15],
  },
  '传统运动控制': {
    decline: true,
    paperGrowth: -2.1,
    patentReplacement: 25,
    demandDrop: 15,
    timeline: '24个月',
    emergingSkills: [
      { name: '强化学习控制', growth: 150, scarcity: '高', stage: '快速增长期' },
      { name: 'Sim2Real迁移', growth: 220, scarcity: '极高', stage: '爆发前期' },
    ],
    trendData: [30, 29, 28, 27, 26, 25, 24, 23, 22, 21, 20, 19],
  },
  'ROS1': {
    decline: true,
    paperGrowth: -12,
    patentReplacement: 55,
    demandDrop: 40,
    timeline: '12个月',
    emergingSkills: [
      { name: 'ROS2', growth: 85, scarcity: '中', stage: '成熟期' },
      { name: '微服务架构', growth: 60, scarcity: '中', stage: '增长期' },
    ],
    trendData: [50, 45, 40, 35, 30, 26, 22, 18, 15, 12, 10, 8],
  },
  '深度学习': {
    decline: false,
    paperGrowth: 15,
    patentReplacement: 5,
    demandDrop: 0,
    timeline: '—',
    emergingSkills: [
      { name: '大语言模型微调', growth: 320, scarcity: '极高', stage: '爆发期' },
      { name: '多模态融合', growth: 180, scarcity: '高', stage: '快速增长期' },
      { name: '具身智能大脑', growth: 450, scarcity: '极高', stage: '萌芽期' },
    ],
    trendData: [20, 25, 30, 35, 40, 45, 50, 55, 60, 65, 70, 75],
  },
  '计算机视觉': {
    decline: false,
    paperGrowth: 8,
    patentReplacement: 10,
    demandDrop: 0,
    timeline: '—',
    emergingSkills: [
      { name: '3D视觉感知', growth: 160, scarcity: '高', stage: '快速增长期' },
      { name: '视觉-语言模型', growth: 280, scarcity: '极高', stage: '爆发前期' },
    ],
    trendData: [30, 32, 34, 36, 38, 40, 42, 44, 46, 48, 50, 52],
  },
};

const competitorData = {
  '宇树科技': {
    totalHires: 156,
    newPositions: 23,
    avgSalary: 42,
    patentOutput: 89,
    hotPositions: [
      { name: '具身数据采集工程师', count: 8, growth: '+300%', patentReq: true, difficulty: '中' },
      { name: '强化学习算法工程师', count: 12, growth: '+85%', patentReq: false, difficulty: '高' },
      { name: '仿真引擎开发', count: 6, growth: '+200%', patentReq: false, difficulty: '极高' },
      { name: '机器人系统架构师', count: 4, growth: '+50%', patentReq: true, difficulty: '高' },
    ],
    talentDistribution: [
      { area: '运动控制', count: 35, trend: 'stable' },
      { area: '感知算法', count: 28, trend: 'up' },
      { area: '仿真技术', count: 18, trend: 'up' },
      { area: '数据采集', count: 15, trend: 'surge' },
      { area: '硬件设计', count: 22, trend: 'stable' },
      { area: '系统集成', count: 38, trend: 'stable' },
    ],
    huntDifficulty: {
      successRate: 35,
      salaryPremium: 25,
      avgTenure: 18,
      patentBarrier: '高',
    },
  },
  '智元机器人': {
    totalHires: 203,
    newPositions: 31,
    avgSalary: 48,
    patentOutput: 156,
    hotPositions: [
      { name: '具身大脑研究员', count: 15, growth: '+400%', patentReq: true, difficulty: '极高' },
      { name: '世界模型工程师', count: 8, growth: '+500%', patentReq: true, difficulty: '极高' },
      { name: '灵巧手控制算法', count: 10, growth: '+150%', patentReq: false, difficulty: '高' },
      { name: 'Sim2Real专家', count: 6, growth: '+250%', patentReq: true, difficulty: '极高' },
    ],
    talentDistribution: [
      { area: 'AI算法', count: 52, trend: 'surge' },
      { area: '运动控制', count: 38, trend: 'up' },
      { area: '仿真技术', count: 25, trend: 'surge' },
      { area: '硬件研发', count: 35, trend: 'stable' },
      { area: '数据工程', count: 28, trend: 'up' },
      { area: '产品管理', count: 25, trend: 'stable' },
    ],
    huntDifficulty: {
      successRate: 22,
      salaryPremium: 40,
      avgTenure: 14,
      patentBarrier: '极高',
    },
  },
  '优必选': {
    totalHires: 178,
    newPositions: 18,
    avgSalary: 38,
    patentOutput: 234,
    hotPositions: [
      { name: '人形机器人算法', count: 20, growth: '+60%', patentReq: true, difficulty: '高' },
      { name: '伺服驱动工程师', count: 12, growth: '+30%', patentReq: false, difficulty: '中' },
      { name: '嵌入式开发', count: 15, growth: '+20%', patentReq: false, difficulty: '中' },
      { name: '产品经理(机器人)', count: 5, growth: '+100%', patentReq: false, difficulty: '低' },
    ],
    talentDistribution: [
      { area: '运动控制', count: 45, trend: 'stable' },
      { area: '伺服系统', count: 32, trend: 'stable' },
      { area: '嵌入式', count: 28, trend: 'stable' },
      { area: '感知算法', count: 22, trend: 'up' },
      { area: '产品管理', count: 18, trend: 'up' },
      { area: '售后服务', count: 33, trend: 'stable' },
    ],
    huntDifficulty: {
      successRate: 45,
      salaryPremium: 15,
      avgTenure: 24,
      patentBarrier: '中',
    },
  },
};

const policyData = {
  '人形机器人创新发展指导意见': {
    issuer: '工信部',
    date: '2024-01',
    level: '国家级',
    keyPoints: [
      { text: '重点突破高功率密度执行器', newJobs: ['伺服驱动算法工程师', '执行器研发工程师'], demandGrowth: 180 },
      { text: '构建人形机器人开源生态', newJobs: ['开源社区运营', '机器人SDK开发'], demandGrowth: 120 },
      { text: '推进场景应用示范', newJobs: ['场景解决方案架构师', '应用部署工程师'], demandGrowth: 95 },
      { text: '建立标准体系', newJobs: ['机器人标准化工程师', '检测认证专家'], demandGrowth: 60 },
    ],
    regionSaturation: [
      { region: '北京', jobs: 45, saturation: 72, competition: '激烈' },
      { region: '上海', jobs: 38, saturation: 65, competition: '较激烈' },
      { region: '广东', jobs: 52, saturation: 58, competition: '中等' },
      { region: '浙江', jobs: 28, saturation: 45, competition: '较低' },
      { region: '江苏', jobs: 32, saturation: 52, competition: '中等' },
    ],
  },
  '新一代人工智能发展规划': {
    issuer: '国务院',
    date: '2023-06',
    level: '国家级',
    keyPoints: [
      { text: '发展智能芯片与传感器', newJobs: ['AI芯片设计工程师', '智能传感器研发'], demandGrowth: 200 },
      { text: '推动AI+制造业融合', newJobs: ['工业AI架构师', '智能制造顾问'], demandGrowth: 150 },
      { text: '建设AI基础设施', newJobs: ['AI平台工程师', 'MLOps工程师'], demandGrowth: 130 },
    ],
    regionSaturation: [
      { region: '北京', jobs: 68, saturation: 80, competition: '极激烈' },
      { region: '广东', jobs: 55, saturation: 70, competition: '激烈' },
      { region: '上海', jobs: 48, saturation: 68, competition: '激烈' },
      { region: '浙江', jobs: 35, saturation: 55, competition: '中等' },
      { region: '四川', jobs: 22, saturation: 40, competition: '较低' },
    ],
  },
};

const candidateProfiles = {
  '扩散策略研究': {
    name: '扩散策略(Diffusion Policy)方向',
    maturity: '学术前沿',
    papers: 12,
    citations: 340,
    industryAdoption: '初期',
    scarcity: '极高',
    recommendation: '破格录用',
    recommendationLevel: 'green',
    analysis: [
      { dimension: '技术稀缺度', score: 95, color: 'green' },
      { dimension: '产业匹配度', score: 78, color: 'blue' },
      { dimension: '成长潜力', score: 92, color: 'green' },
      { dimension: '工程落地能力', score: 45, color: 'orange' },
      { dimension: '团队协作适配', score: 70, color: 'blue' },
    ],
    matchedJobs: [
      { title: '具身智能算法研究员', match: 88, company: '智元机器人', salary: '50-70万' },
      { title: '机器人学习算法工程师', match: 82, company: '宇树科技', salary: '45-60万' },
      { title: 'AI Research Scientist', match: 75, company: '某外企研究院', salary: '60-90万' },
    ],
  },
  '传统SLAM研究': {
    name: '传统SLAM方向',
    maturity: '工程成熟',
    papers: 8,
    citations: 180,
    industryAdoption: '成熟期',
    scarcity: '中',
    recommendation: '常规录用',
    recommendationLevel: 'yellow',
    analysis: [
      { dimension: '技术稀缺度', score: 40, color: 'orange' },
      { dimension: '产业匹配度', score: 85, color: 'green' },
      { dimension: '成长潜力', score: 55, color: 'yellow' },
      { dimension: '工程落地能力', score: 88, color: 'green' },
      { dimension: '团队协作适配', score: 75, color: 'blue' },
    ],
    matchedJobs: [
      { title: 'SLAM算法工程师', match: 92, company: '某自动驾驶公司', salary: '35-50万' },
      { title: '导航算法工程师', match: 85, company: '某AGV企业', salary: '30-45万' },
      { title: '感知算法工程师', match: 70, company: '某机器人公司', salary: '35-50万' },
    ],
  },
};

// ============ Components ============

function TechWarningPanel() {
  const [selectedTech, setSelectedTech] = useState<string>('激光SLAM');
  const [isAnalyzing, setIsAnalyzing] = useState(false);

  const data = techTrends[selectedTech as keyof typeof techTrends];

  const handleAnalyze = () => {
    setIsAnalyzing(true);
    setTimeout(() => setIsAnalyzing(false), 1500);
  };

  return (
    <div className="space-y-6">
      {/* Input Section */}
      <div className="bg-white rounded-xl border border-slate-200 p-6">
        <h3 className="text-lg font-semibold text-slate-900 mb-4 flex items-center gap-2">
          <Search className="w-5 h-5 text-blue-600" />
          输入公司核心技术栈
        </h3>
        <div className="flex gap-3">
          <div className="flex-1 relative">
            <input
              type="text"
              value={selectedTech}
              onChange={(e) => setSelectedTech(e.target.value)}
              placeholder="输入技术名称，如：激光SLAM、深度学习、ROS..."
              className="w-full px-4 py-2.5 border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500"
            />
            <div className="absolute right-2 top-1/2 -translate-y-1/2 flex gap-1">
              {Object.keys(techTrends).slice(0, 3).map((tech) => (
                <button
                  key={tech}
                  onClick={() => setSelectedTech(tech)}
                  className="px-2 py-0.5 text-xs bg-slate-100 text-slate-600 rounded hover:bg-blue-50 hover:text-blue-600 transition-colors"
                >
                  {tech}
                </button>
              ))}
            </div>
          </div>
          <button
            onClick={handleAnalyze}
            disabled={isAnalyzing}
            className="px-6 py-2.5 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors font-medium disabled:opacity-50"
          >
            {isAnalyzing ? '分析中...' : '开始分析'}
          </button>
        </div>
      </div>

      {/* Results */}
      {data && (
        <div className="space-y-6">
          {/* Warning Banner */}
          <div className={`rounded-xl p-6 ${data.decline ? 'bg-gradient-to-r from-red-50 to-orange-50 border border-red-100' : 'bg-gradient-to-r from-green-50 to-emerald-50 border border-green-100'}`}>
            <div className="flex items-start gap-4">
              <div className={`p-3 rounded-xl ${data.decline ? 'bg-red-100' : 'bg-green-100'}`}>
                {data.decline ? <TrendingDown className="w-6 h-6 text-red-600" /> : <TrendingUp className="w-6 h-6 text-green-600" />}
              </div>
              <div className="flex-1">
                <h4 className={`text-lg font-semibold mb-2 ${data.decline ? 'text-red-900' : 'text-green-900'}`}>
                  {data.decline ? '技术衰退预警' : '技术健康度良好'}
                </h4>
                {data.decline ? (
                  <p className="text-slate-700 leading-relaxed">
                    <span className="font-medium">{selectedTech}</span> 方向论文年增长率
                    <span className="font-bold text-red-600 mx-1">{data.paperGrowth}%</span>，
                    专利被替代率超
                    <span className="font-bold text-red-600 mx-1">{data.patentReplacement}%</span>。
                    预计
                    <span className="font-bold text-orange-600 mx-1">{data.timeline}</span>后，
                    该技能需求量将下降
                    <span className="font-bold text-red-600 mx-1">{data.demandDrop}%</span>。
                  </p>
                ) : (
                  <p className="text-slate-700 leading-relaxed">
                    <span className="font-medium">{selectedTech}</span> 方向论文年增长率
                    <span className="font-bold text-green-600 mx-1">+{data.paperGrowth}%</span>，
                    技术生态健康，建议持续投入。
                  </p>
                )}
              </div>
            </div>
          </div>

          {/* Trend Chart */}
          <div className="bg-white rounded-xl border border-slate-200 p-6">
            <h4 className="text-sm font-semibold text-slate-900 mb-4">近12个月技术热度趋势</h4>
            <div className="flex items-end gap-2 h-32">
              {data.trendData.map((value, i) => (
                <div key={i} className="flex-1 flex flex-col items-center gap-1">
                  <div
                    className={`w-full rounded-t transition-all ${data.decline ? 'bg-gradient-to-t from-red-500 to-red-300' : 'bg-gradient-to-t from-green-500 to-green-300'}`}
                    style={{ height: `${(value / Math.max(...data.trendData)) * 100}%` }}
                  />
                  <span className="text-[10px] text-slate-400">{i + 1}月</span>
                </div>
              ))}
            </div>
          </div>

          {/* Emerging Skills */}
          <div className="bg-white rounded-xl border border-slate-200 p-6">
            <h4 className="text-sm font-semibold text-slate-900 mb-4 flex items-center gap-2">
              <Lightbulb className="w-4 h-4 text-amber-500" />
              新兴技能推荐
            </h4>
            <div className="space-y-3">
              {data.emergingSkills.map((skill) => (
                <div key={skill.name} className="flex items-center gap-4 p-3 rounded-lg bg-slate-50 hover:bg-blue-50 transition-colors">
                  <div className="flex-1">
                    <div className="flex items-center gap-2">
                      <span className="font-medium text-slate-900">{skill.name}</span>
                      <span className={`px-2 py-0.5 text-xs rounded-full ${
                        skill.stage === '爆发前期' ? 'bg-purple-100 text-purple-700' :
                        skill.stage === '快速增长期' ? 'bg-blue-100 text-blue-700' :
                        'bg-green-100 text-green-700'
                      }`}>
                        {skill.stage}
                      </span>
                    </div>
                    <div className="flex items-center gap-4 mt-1 text-xs text-slate-500">
                      <span>增长率: <span className="text-green-600 font-medium">+{skill.growth}%</span></span>
                      <span>稀缺度: <span className={`font-medium ${skill.scarcity === '极高' ? 'text-red-600' : 'text-orange-600'}`}>{skill.scarcity}</span></span>
                    </div>
                  </div>
                  <button className="px-3 py-1.5 text-xs font-medium text-blue-600 bg-blue-50 rounded-lg hover:bg-blue-100 transition-colors">
                    加入JD
                  </button>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function CompetitorAnalysisPanel() {
  const [selectedCompany, setSelectedCompany] = useState<string>('宇树科技');
  const data = competitorData[selectedCompany as keyof typeof competitorData];

  return (
    <div className="space-y-6">
      {/* Company Selector */}
      <div className="bg-white rounded-xl border border-slate-200 p-6">
        <h3 className="text-lg font-semibold text-slate-900 mb-4 flex items-center gap-2">
          <Building2 className="w-5 h-5 text-purple-600" />
          选择竞品企业
        </h3>
        <div className="flex gap-3 flex-wrap">
          {Object.keys(competitorData).map((company) => (
            <button
              key={company}
              onClick={() => setSelectedCompany(company)}
              className={`px-4 py-2 rounded-lg font-medium transition-all ${
                selectedCompany === company
                  ? 'bg-purple-600 text-white shadow-sm'
                  : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
              }`}
            >
              {company}
            </button>
          ))}
        </div>
      </div>

      {data && (
        <>
          {/* Overview Stats */}
          <div className="grid grid-cols-4 gap-4">
            <div className="bg-white rounded-xl border border-slate-200 p-4">
              <div className="text-sm text-slate-500">近半年招聘</div>
              <div className="text-2xl font-bold text-slate-900 mt-1">{data.totalHires}<span className="text-sm font-normal text-slate-500 ml-1">人</span></div>
            </div>
            <div className="bg-white rounded-xl border border-slate-200 p-4">
              <div className="text-sm text-slate-500">新增岗位</div>
              <div className="text-2xl font-bold text-green-600 mt-1">{data.newPositions}<span className="text-sm font-normal text-slate-500 ml-1">个</span></div>
            </div>
            <div className="bg-white rounded-xl border border-slate-200 p-4">
              <div className="text-sm text-slate-500">平均薪资</div>
              <div className="text-2xl font-bold text-slate-900 mt-1">{data.avgSalary}<span className="text-sm font-normal text-slate-500 ml-1">万/年</span></div>
            </div>
            <div className="bg-white rounded-xl border border-slate-200 p-4">
              <div className="text-sm text-slate-500">专利产出</div>
              <div className="text-2xl font-bold text-purple-600 mt-1">{data.patentOutput}<span className="text-sm font-normal text-slate-500 ml-1">项</span></div>
            </div>
          </div>

          {/* Talent Distribution Heatmap */}
          <div className="bg-white rounded-xl border border-slate-200 p-6">
            <h4 className="text-sm font-semibold text-slate-900 mb-4 flex items-center gap-2">
              <MapPin className="w-4 h-4 text-orange-500" />
              岗位迁移热力图
            </h4>
            <div className="grid grid-cols-3 gap-3">
              {data.talentDistribution.map((item) => (
                <div key={item.area} className={`p-4 rounded-lg border ${
                  item.trend === 'surge' ? 'bg-red-50 border-red-200' :
                  item.trend === 'up' ? 'bg-orange-50 border-orange-200' :
                  'bg-slate-50 border-slate-200'
                }`}>
                  <div className="flex items-center justify-between">
                    <span className="font-medium text-slate-900">{item.area}</span>
                    <span className={`text-xs px-2 py-0.5 rounded-full ${
                      item.trend === 'surge' ? 'bg-red-100 text-red-700' :
                      item.trend === 'up' ? 'bg-orange-100 text-orange-700' :
                      'bg-slate-100 text-slate-600'
                    }`}>
                      {item.trend === 'surge' ? '激增' : item.trend === 'up' ? '增长' : '稳定'}
                    </span>
                  </div>
                  <div className="mt-2 flex items-center gap-2">
                    <div className="flex-1 h-2 bg-slate-200 rounded-full overflow-hidden">
                      <div
                        className={`h-full rounded-full ${
                          item.trend === 'surge' ? 'bg-red-500' :
                          item.trend === 'up' ? 'bg-orange-500' :
                          'bg-slate-400'
                        }`}
                        style={{ width: `${(item.count / 60) * 100}%` }}
                      />
                    </div>
                    <span className="text-sm font-medium text-slate-700">{item.count}人</span>
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Hot Positions */}
          <div className="bg-white rounded-xl border border-slate-200 p-6">
            <h4 className="text-sm font-semibold text-slate-900 mb-4">热门新增岗位</h4>
            <div className="space-y-2">
              {data.hotPositions.map((pos) => (
                <div key={pos.name} className="flex items-center gap-4 p-3 rounded-lg hover:bg-slate-50 transition-colors">
                  <div className="flex-1">
                    <div className="flex items-center gap-2">
                      <span className="font-medium text-slate-900">{pos.name}</span>
                      {pos.patentReq && (
                        <span className="px-1.5 py-0.5 text-[10px] bg-purple-100 text-purple-700 rounded">要求专利</span>
                      )}
                    </div>
                    <div className="text-xs text-slate-500 mt-0.5">
                      招聘 {pos.count} 人 | 增长 {pos.growth} | 挖猎难度: {pos.difficulty}
                    </div>
                  </div>
                  <ArrowRight className="w-4 h-4 text-slate-400" />
                </div>
              ))}
            </div>
          </div>

          {/* Hunt Difficulty */}
          <div className="bg-white rounded-xl border border-slate-200 p-6">
            <h4 className="text-sm font-semibold text-slate-900 mb-4 flex items-center gap-2">
              <Target className="w-4 h-4 text-red-500" />
              定向挖猎评估
            </h4>
            <div className="grid grid-cols-4 gap-4">
              <div className="text-center p-4 bg-slate-50 rounded-lg">
                <div className="text-2xl font-bold text-blue-600">{data.huntDifficulty.successRate}%</div>
                <div className="text-xs text-slate-500 mt-1">预估成功率</div>
              </div>
              <div className="text-center p-4 bg-slate-50 rounded-lg">
                <div className="text-2xl font-bold text-orange-600">+{data.huntDifficulty.salaryPremium}%</div>
                <div className="text-xs text-slate-500 mt-1">薪酬溢价</div>
              </div>
              <div className="text-center p-4 bg-slate-50 rounded-lg">
                <div className="text-2xl font-bold text-slate-900">{data.huntDifficulty.avgTenure}</div>
                <div className="text-xs text-slate-500 mt-1">平均在职月数</div>
              </div>
              <div className="text-center p-4 bg-slate-50 rounded-lg">
                <div className={`text-2xl font-bold ${
                  data.huntDifficulty.patentBarrier === '极高' ? 'text-red-600' :
                  data.huntDifficulty.patentBarrier === '高' ? 'text-orange-600' :
                  'text-green-600'
                }`}>{data.huntDifficulty.patentBarrier}</div>
                <div className="text-xs text-slate-500 mt-1">专利壁垒</div>
              </div>
            </div>
          </div>
        </>
      )}
    </div>
  );
}

function PolicyPredictionPanel() {
  const [selectedPolicy, setSelectedPolicy] = useState<string>('人形机器人创新发展指导意见');
  const data = policyData[selectedPolicy as keyof typeof policyData];

  return (
    <div className="space-y-6">
      {/* Policy Selector */}
      <div className="bg-white rounded-xl border border-slate-200 p-6">
        <h3 className="text-lg font-semibold text-slate-900 mb-4 flex items-center gap-2">
          <FileText className="w-5 h-5 text-emerald-600" />
          选择政策文件
        </h3>
        <div className="flex gap-3 flex-wrap">
          {Object.keys(policyData).map((policy) => (
            <button
              key={policy}
              onClick={() => setSelectedPolicy(policy)}
              className={`px-4 py-2 rounded-lg font-medium transition-all ${
                selectedPolicy === policy
                  ? 'bg-emerald-600 text-white shadow-sm'
                  : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
              }`}
            >
              {policy}
            </button>
          ))}
        </div>
      </div>

      {data && (
        <>
          {/* Policy Info */}
          <div className="bg-gradient-to-r from-emerald-50 to-teal-50 rounded-xl border border-emerald-100 p-6">
            <div className="flex items-center gap-4">
              <div className="p-3 bg-emerald-100 rounded-xl">
                <FileText className="w-6 h-6 text-emerald-700" />
              </div>
              <div>
                <h4 className="font-semibold text-slate-900">{selectedPolicy}</h4>
                <div className="flex items-center gap-3 mt-1 text-sm text-slate-600">
                  <span>发布机构: {data.issuer}</span>
                  <span>|</span>
                  <span>发布时间: {data.date}</span>
                  <span>|</span>
                  <span className="px-2 py-0.5 bg-emerald-100 text-emerald-700 rounded text-xs">{data.level}</span>
                </div>
              </div>
            </div>
          </div>

          {/* Policy Breakdown */}
          <div className="bg-white rounded-xl border border-slate-200 p-6">
            <h4 className="text-sm font-semibold text-slate-900 mb-4 flex items-center gap-2">
              <Zap className="w-4 h-4 text-amber-500" />
              政策拆解 — 催生新岗位
            </h4>
            <div className="space-y-4">
              {data.keyPoints.map((point, i) => (
                <div key={i} className="p-4 rounded-lg bg-slate-50 border border-slate-100">
                  <div className="flex items-start gap-3">
                    <div className="w-6 h-6 rounded-full bg-emerald-100 text-emerald-700 flex items-center justify-center text-xs font-bold flex-shrink-0">
                      {i + 1}
                    </div>
                    <div className="flex-1">
                      <p className="font-medium text-slate-900 mb-2">"{point.text}"</p>
                      <div className="flex flex-wrap gap-2">
                        {point.newJobs.map((job) => (
                          <span key={job} className="px-2 py-1 bg-blue-50 text-blue-700 rounded text-xs font-medium">
                            {job}
                          </span>
                        ))}
                      </div>
                      <div className="mt-2 text-xs text-slate-500">
                        预计需求增长: <span className="text-green-600 font-medium">+{point.demandGrowth}%</span>
                      </div>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Regional Saturation */}
          <div className="bg-white rounded-xl border border-slate-200 p-6">
            <h4 className="text-sm font-semibold text-slate-900 mb-4 flex items-center gap-2">
              <MapPin className="w-4 h-4 text-blue-500" />
              地区岗位饱和指数
            </h4>
            <div className="space-y-3">
              {data.regionSaturation.map((region) => (
                <div key={region.region} className="flex items-center gap-4">
                  <span className="w-16 font-medium text-slate-900">{region.region}</span>
                  <div className="flex-1 h-8 bg-slate-100 rounded-lg overflow-hidden relative">
                    <div
                      className={`h-full rounded-lg transition-all ${
                        region.saturation > 70 ? 'bg-gradient-to-r from-red-400 to-red-500' :
                        region.saturation > 50 ? 'bg-gradient-to-r from-orange-400 to-orange-500' :
                        'bg-gradient-to-r from-green-400 to-green-500'
                      }`}
                      style={{ width: `${region.saturation}%` }}
                    />
                    <div className="absolute inset-0 flex items-center px-3">
                      <span className="text-xs font-medium text-white drop-shadow-sm">
                        {region.jobs}个岗位 | 饱和度 {region.saturation}%
                      </span>
                    </div>
                  </div>
                  <span className={`w-16 text-right text-xs font-medium ${
                    region.competition === '极激烈' || region.competition === '激烈' ? 'text-red-600' :
                    region.competition === '中等' ? 'text-orange-600' :
                    'text-green-600'
                  }`}>
                    {region.competition}
                  </span>
                </div>
              ))}
            </div>
            <div className="mt-4 p-3 bg-blue-50 rounded-lg">
              <p className="text-xs text-blue-700">
                <span className="font-medium">建议：</span>
                {data.regionSaturation.find(r => r.saturation < 50) && (
                  <>优先在 <span className="font-bold">{data.regionSaturation.find(r => r.saturation < 50)?.region}</span> 布局，该区域竞争较低，人才获取成本更优。</>
                )}
              </p>
            </div>
          </div>
        </>
      )}
    </div>
  );
}

// ============ Main Page ============

export default function AnalysisPage() {
  const [activeTab, setActiveTab] = useState<'tech' | 'competitor' | 'policy'>('tech');

  const tabs = [
    { id: 'tech' as const, label: '技术路线预警仪', icon: Activity, color: 'blue' },
    { id: 'competitor' as const, label: '竞品人才围栏', icon: Users, color: 'purple' },
    { id: 'policy' as const, label: '政策岗位预测', icon: FileText, color: 'emerald' },
  ];

  return (
    <div className="flex h-[calc(100vh-56px)]">
      {/* Sidebar */}
      <aside className="w-60 bg-white border-r border-slate-200 flex flex-col">
        <div className="p-4 border-b border-slate-200">
          <h2 className="text-sm font-semibold text-slate-900">智能分析</h2>
          <p className="text-xs text-slate-500 mt-0.5">多库联动深度洞察</p>
        </div>
        <nav className="flex-1 p-3 space-y-1">
          {tabs.map((tab) => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={`w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm transition-all ${
                activeTab === tab.id
                  ? 'bg-blue-50 text-blue-700 font-medium'
                  : 'text-slate-600 hover:bg-slate-50'
              }`}
            >
              <tab.icon className={`w-4 h-4 ${activeTab === tab.id ? 'text-blue-600' : 'text-slate-400'}`} />
              {tab.label}
            </button>
          ))}
        </nav>
        <div className="p-4 border-t border-slate-200">
          <div className="p-3 bg-gradient-to-br from-blue-50 to-indigo-50 rounded-lg">
            <div className="text-xs font-medium text-blue-900">数据来源</div>
            <div className="mt-2 space-y-1 text-[11px] text-blue-700">
              <div className="flex items-center gap-1.5"><Cpu className="w-3 h-3" /> 专利库</div>
              <div className="flex items-center gap-1.5"><Brain className="w-3 h-3" /> 论文库</div>
              <div className="flex items-center gap-1.5"><Award className="w-3 h-3" /> 岗位库</div>
              <div className="flex items-center gap-1.5"><Building2 className="w-3 h-3" /> 企业库</div>
              <div className="flex items-center gap-1.5"><Shield className="w-3 h-3" /> 政策库</div>
            </div>
          </div>
        </div>
      </aside>

      {/* Main Content */}
      <main className="flex-1 overflow-y-auto bg-slate-50 p-6">
        {/* Header */}
        <div className="mb-6">
          <h1 className="text-xl font-bold text-slate-900">
            {tabs.find(t => t.id === activeTab)?.label}
          </h1>
          <p className="text-sm text-slate-500 mt-1">
            {activeTab === 'tech' && '分析技术栈生命周期，预警衰退风险，推荐新兴技能方向'}
            {activeTab === 'competitor' && '追踪竞品人才布局，评估挖猎难度，制定人才策略'}
            {activeTab === 'policy' && '解读政策文件，预测催生岗位，分析地区竞争态势'}
          </p>
        </div>

        {/* Content */}
        {activeTab === 'tech' && <TechWarningPanel />}
        {activeTab === 'competitor' && <CompetitorAnalysisPanel />}
        {activeTab === 'policy' && <PolicyPredictionPanel />}
      </main>
    </div>
  );
}
