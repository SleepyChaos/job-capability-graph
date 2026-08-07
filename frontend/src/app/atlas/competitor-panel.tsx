'use client';

import { useState } from 'react';
import { Building2, Users, TrendingUp, MapPin, Shield, DollarSign, Clock, Award, ChevronRight, Target, Zap } from 'lucide-react';

// ============ Mock Data ============

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
    totalHires: 128,
    newPositions: 18,
    avgSalary: 45,
    patentOutput: 67,
    hotPositions: [
      { name: '具身大脑研究员', count: 10, growth: '+250%', patentReq: true, difficulty: '极高' },
      { name: '灵巧手控制算法', count: 7, growth: '+180%', patentReq: false, difficulty: '高' },
      { name: 'Sim2Real工程师', count: 5, growth: '+150%', patentReq: false, difficulty: '极高' },
      { name: '产品经理(机器人)', count: 3, growth: '+100%', patentReq: false, difficulty: '中' },
    ],
    talentDistribution: [
      { area: 'AI算法', count: 42, trend: 'surge' },
      { area: '运动控制', count: 25, trend: 'up' },
      { area: '仿真技术', count: 20, trend: 'surge' },
      { area: '硬件设计', count: 18, trend: 'stable' },
      { area: '产品管理', count: 12, trend: 'up' },
      { area: '系统集成', count: 11, trend: 'stable' },
    ],
    huntDifficulty: {
      successRate: 28,
      salaryPremium: 35,
      avgTenure: 14,
      patentBarrier: '极高',
    },
  },
  '优必选': {
    totalHires: 203,
    newPositions: 15,
    avgSalary: 38,
    patentOutput: 156,
    hotPositions: [
      { name: '伺服驱动工程师', count: 15, growth: '+60%', patentReq: true, difficulty: '高' },
      { name: 'SLAM算法工程师', count: 10, growth: '+30%', patentReq: false, difficulty: '中' },
      { name: '嵌入式开发', count: 12, growth: '+40%', patentReq: false, difficulty: '中' },
      { name: '项目经理', count: 5, growth: '+20%', patentReq: false, difficulty: '低' },
    ],
    talentDistribution: [
      { area: '运动控制', count: 45, trend: 'stable' },
      { area: '硬件设计', count: 38, trend: 'stable' },
      { area: '嵌入式', count: 32, trend: 'stable' },
      { area: '感知算法', count: 28, trend: 'stable' },
      { area: '项目管理', count: 35, trend: 'stable' },
      { area: '销售支持', count: 25, trend: 'stable' },
    ],
    huntDifficulty: {
      successRate: 45,
      salaryPremium: 15,
      avgTenure: 24,
      patentBarrier: '中',
    },
  },
};

export function CompetitorPanel() {
  const [selectedCompetitor, setSelectedCompetitor] = useState<string>('宇树科技');

  const data = competitorData[selectedCompetitor as keyof typeof competitorData];

  const getTrendIcon = (trend: string) => {
    switch (trend) {
      case 'surge': return <span className="text-xs text-red-600 font-medium">激增</span>;
      case 'up': return <span className="text-xs text-green-600 font-medium">增长</span>;
      default: return <span className="text-xs text-slate-500">稳定</span>;
    }
  };

  const maxCount = Math.max(...data.talentDistribution.map(t => t.count));

  return (
    <div className="space-y-5">
      {/* Competitor Selection */}
      <div className="bg-white rounded-xl border border-slate-200 p-4">
        <div className="flex items-center gap-2 mb-3">
          <Building2 className="w-4 h-4 text-indigo-600" />
          <span className="text-sm font-semibold text-slate-900">选择竞品企业</span>
        </div>
        <div className="flex flex-wrap gap-2">
          {Object.keys(competitorData).map((comp) => (
            <button
              key={comp}
              onClick={() => setSelectedCompetitor(comp)}
              className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-all ${
                selectedCompetitor === comp
                  ? 'bg-indigo-600 text-white'
                  : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
              }`}
            >
              {comp}
            </button>
          ))}
        </div>
      </div>

      {/* Overview Stats */}
      <div className="grid grid-cols-4 gap-3">
        <div className="bg-white rounded-xl border border-slate-200 p-3 text-center">
          <div className="text-xl font-bold text-slate-900">{data.totalHires}</div>
          <div className="text-xs text-slate-500 mt-0.5">总招聘人数</div>
        </div>
        <div className="bg-white rounded-xl border border-slate-200 p-3 text-center">
          <div className="text-xl font-bold text-green-600">{data.newPositions}</div>
          <div className="text-xs text-slate-500 mt-0.5">新增岗位</div>
        </div>
        <div className="bg-white rounded-xl border border-slate-200 p-3 text-center">
          <div className="text-xl font-bold text-slate-900">{data.avgSalary}万</div>
          <div className="text-xs text-slate-500 mt-0.5">平均年薪</div>
        </div>
        <div className="bg-white rounded-xl border border-slate-200 p-3 text-center">
          <div className="text-xl font-bold text-indigo-600">{data.patentOutput}</div>
          <div className="text-xs text-slate-500 mt-0.5">专利产出</div>
        </div>
      </div>

      {/* Talent Distribution Heatmap */}
      <div className="bg-white rounded-xl border border-slate-200 p-4">
        <div className="flex items-center gap-2 mb-3">
          <MapPin className="w-4 h-4 text-indigo-600" />
          <span className="text-sm font-semibold text-slate-900">岗位迁移热力图</span>
        </div>
        <div className="space-y-2">
          {data.talentDistribution.map((item) => (
            <div key={item.area} className="flex items-center gap-3">
              <span className="text-xs text-slate-600 w-16">{item.area}</span>
              <div className="flex-1 h-6 bg-slate-100 rounded overflow-hidden relative">
                <div
                  className={`h-full transition-all ${
                    item.trend === 'surge' ? 'bg-red-400' :
                    item.trend === 'up' ? 'bg-green-400' : 'bg-slate-300'
                  }`}
                  style={{ width: `${(item.count / maxCount) * 100}%` }}
                />
                <span className="absolute inset-0 flex items-center px-2 text-xs font-medium text-slate-700">
                  {item.count}人
                </span>
              </div>
              {getTrendIcon(item.trend)}
            </div>
          ))}
        </div>
      </div>

      {/* Hot New Positions */}
      <div className="bg-white rounded-xl border border-slate-200 p-4">
        <div className="flex items-center gap-2 mb-3">
          <Zap className="w-4 h-4 text-amber-500" />
          <span className="text-sm font-semibold text-slate-900">热门新增岗位</span>
        </div>
        <div className="space-y-2">
          {data.hotPositions.map((pos) => (
            <div key={pos.name} className="flex items-center gap-3 p-2.5 bg-slate-50 rounded-lg">
              <div className="flex-1">
                <div className="flex items-center gap-2">
                  <span className="text-sm font-medium text-slate-900">{pos.name}</span>
                  {pos.patentReq && (
                    <span className="text-xs px-1.5 py-0.5 bg-purple-50 text-purple-700 rounded">要求专利</span>
                  )}
                </div>
                <div className="flex items-center gap-3 mt-1">
                  <span className="text-xs text-slate-500">招聘 {pos.count}人</span>
                  <span className="text-xs text-green-600 font-medium">{pos.growth}</span>
                  <span className="text-xs text-slate-500">难度: {pos.difficulty}</span>
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Hunt Difficulty */}
      <div className="bg-white rounded-xl border border-slate-200 p-4">
        <div className="flex items-center gap-2 mb-3">
          <Target className="w-4 h-4 text-red-500" />
          <span className="text-sm font-semibold text-slate-900">定向挖猎评估</span>
        </div>
        <div className="grid grid-cols-2 gap-3">
          <div className="p-3 bg-slate-50 rounded-lg">
            <div className="flex items-center gap-1.5 mb-1">
              <Shield className="w-3.5 h-3.5 text-slate-500" />
              <span className="text-xs text-slate-500">挖猎成功率</span>
            </div>
            <div className="text-lg font-bold text-slate-900">{data.huntDifficulty.successRate}%</div>
          </div>
          <div className="p-3 bg-slate-50 rounded-lg">
            <div className="flex items-center gap-1.5 mb-1">
              <DollarSign className="w-3.5 h-3.5 text-slate-500" />
              <span className="text-xs text-slate-500">薪酬溢价</span>
            </div>
            <div className="text-lg font-bold text-slate-900">+{data.huntDifficulty.salaryPremium}%</div>
          </div>
          <div className="p-3 bg-slate-50 rounded-lg">
            <div className="flex items-center gap-1.5 mb-1">
              <Clock className="w-3.5 h-3.5 text-slate-500" />
              <span className="text-xs text-slate-500">平均在职月数</span>
            </div>
            <div className="text-lg font-bold text-slate-900">{data.huntDifficulty.avgTenure}个月</div>
          </div>
          <div className="p-3 bg-slate-50 rounded-lg">
            <div className="flex items-center gap-1.5 mb-1">
              <Award className="w-3.5 h-3.5 text-slate-500" />
              <span className="text-xs text-slate-500">专利壁垒</span>
            </div>
            <div className="text-lg font-bold text-slate-900">{data.huntDifficulty.patentBarrier}</div>
          </div>
        </div>
        <div className="mt-3 p-2.5 bg-amber-50 rounded-lg">
          <div className="flex items-center gap-2 text-xs text-amber-700">
            <ChevronRight className="w-3.5 h-3.5" />
            <span>建议：{selectedCompetitor}人才壁垒{data.huntDifficulty.patentBarrier}，建议通过技术社区/开源项目建立长期联系，降低挖猎成本</span>
          </div>
        </div>
      </div>
    </div>
  );
}
