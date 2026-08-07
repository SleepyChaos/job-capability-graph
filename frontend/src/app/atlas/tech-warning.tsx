'use client';

import { useState } from 'react';
import { TrendingDown, TrendingUp, AlertTriangle, Lightbulb, Zap, Activity, ArrowRight } from 'lucide-react';

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

export function TechWarningPanel() {
  const [selectedTech, setSelectedTech] = useState<string>('激光SLAM');
  const [isAnalyzing, setIsAnalyzing] = useState(false);

  const data = techTrends[selectedTech as keyof typeof techTrends];

  const handleAnalyze = () => {
    setIsAnalyzing(true);
    setTimeout(() => setIsAnalyzing(false), 1500);
  };

  const maxTrend = Math.max(...data.trendData);

  return (
    <div className="space-y-5">
      {/* Input */}
      <div className="bg-white rounded-xl border border-slate-200 p-4">
        <div className="flex items-center gap-2 mb-3">
          <Activity className="w-4 h-4 text-indigo-600" />
          <span className="text-sm font-semibold text-slate-900">输入公司核心技术栈</span>
        </div>
        <div className="flex flex-wrap gap-2 mb-3">
          {Object.keys(techTrends).map((tech) => (
            <button
              key={tech}
              onClick={() => setSelectedTech(tech)}
              className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-all ${
                selectedTech === tech
                  ? 'bg-indigo-600 text-white'
                  : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
              }`}
            >
              {tech}
            </button>
          ))}
        </div>
        <button
          onClick={handleAnalyze}
          disabled={isAnalyzing}
          className="w-full py-2.5 bg-indigo-600 text-white rounded-lg text-sm font-medium hover:bg-indigo-700 transition-all disabled:opacity-50 flex items-center justify-center gap-2"
        >
          {isAnalyzing ? (
            <>
              <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
              正在分析技术趋势...
            </>
          ) : (
            <>
              <Zap className="w-4 h-4" />
              分析技术路线
            </>
          )}
        </button>
      </div>

      {/* Trend Chart */}
      <div className="bg-white rounded-xl border border-slate-200 p-4">
        <div className="flex items-center justify-between mb-3">
          <span className="text-sm font-semibold text-slate-900">技术热度趋势（12个月）</span>
          {data.decline ? (
            <span className="flex items-center gap-1 text-xs text-red-600 bg-red-50 px-2 py-0.5 rounded">
              <TrendingDown className="w-3 h-3" />
              衰退预警
            </span>
          ) : (
            <span className="flex items-center gap-1 text-xs text-green-600 bg-green-50 px-2 py-0.5 rounded">
              <TrendingUp className="w-3 h-3" />
              持续增长
            </span>
          )}
        </div>
        <div className="flex items-end gap-1 h-24">
          {data.trendData.map((val, idx) => (
            <div key={idx} className="flex-1 flex flex-col items-center gap-1">
              <div
                className={`w-full rounded-t transition-all ${data.decline ? 'bg-red-400' : 'bg-green-400'}`}
                style={{ height: `${(val / maxTrend) * 100}%`, opacity: 0.5 + (idx / data.trendData.length) * 0.5 }}
              />
            </div>
          ))}
        </div>
        <div className="flex justify-between mt-1">
          <span className="text-xs text-slate-400">12月前</span>
          <span className="text-xs text-slate-400">当前</span>
        </div>
      </div>

      {/* Warning / Growth Summary */}
      <div className={`rounded-xl border p-4 ${data.decline ? 'bg-red-50 border-red-200' : 'bg-green-50 border-green-200'}`}>
        {data.decline ? (
          <>
            <div className="flex items-center gap-2 mb-2">
              <AlertTriangle className="w-4 h-4 text-red-600" />
              <span className="text-sm font-semibold text-red-900">技术衰退预警</span>
            </div>
            <div className="space-y-1.5 text-xs text-red-800">
              <p>论文年增长率 <span className="font-bold">{data.paperGrowth}%</span>，专利被替代率超 <span className="font-bold">{data.patentReplacement}%</span></p>
              <p>预计 <span className="font-bold">{data.timeline}</span> 后，该技能需求量将下降 <span className="font-bold">{data.demandDrop}%</span></p>
            </div>
          </>
        ) : (
          <>
            <div className="flex items-center gap-2 mb-2">
              <TrendingUp className="w-4 h-4 text-green-600" />
              <span className="text-sm font-semibold text-green-900">技术增长态势</span>
            </div>
            <div className="space-y-1.5 text-xs text-green-800">
              <p>论文年增长率 <span className="font-bold">+{data.paperGrowth}%</span>，技术处于上升期</p>
              <p>专利替代率仅 <span className="font-bold">{data.patentReplacement}%</span>，技术壁垒稳固</p>
            </div>
          </>
        )}
      </div>

      {/* Emerging Skills */}
      <div className="bg-white rounded-xl border border-slate-200 p-4">
        <div className="flex items-center gap-2 mb-3">
          <Lightbulb className="w-4 h-4 text-amber-500" />
          <span className="text-sm font-semibold text-slate-900">新兴技能推荐</span>
        </div>
        <div className="space-y-2.5">
          {data.emergingSkills.map((skill) => (
            <div key={skill.name} className="flex items-center gap-3 p-2.5 bg-slate-50 rounded-lg">
              <div className="flex-1">
                <div className="flex items-center gap-2">
                  <span className="text-sm font-medium text-slate-900">{skill.name}</span>
                  <span className={`text-xs px-1.5 py-0.5 rounded ${
                    skill.scarcity === '极高' ? 'bg-red-100 text-red-700' :
                    skill.scarcity === '高' ? 'bg-orange-100 text-orange-700' :
                    'bg-blue-100 text-blue-700'
                  }`}>
                    {skill.scarcity}稀缺
                  </span>
                </div>
                <div className="flex items-center gap-3 mt-1">
                  <span className="text-xs text-slate-500">增长率 +{skill.growth}%</span>
                  <span className="text-xs text-slate-500">·</span>
                  <span className="text-xs text-slate-500">{skill.stage}</span>
                </div>
              </div>
              <button className="px-2.5 py-1 bg-indigo-50 text-indigo-700 rounded text-xs font-medium hover:bg-indigo-100 transition-colors flex items-center gap-1">
                <ArrowRight className="w-3 h-3" />
                加入JD
              </button>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
