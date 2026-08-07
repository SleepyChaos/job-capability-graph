'use client';

import React, { useState } from 'react';
import {
  FileText, FilePlus, Edit3, Download, Eye,
  ChevronRight, ChevronDown, GripVertical,
  Sparkles, RefreshCw, Save, Printer,
  CheckCircle2, Clock, BarChart3,
} from 'lucide-react';
import { reportTemplates } from '@/lib/mock-data';

export default function ReportsPage() {
  const [activeTab, setActiveTab] = useState<'templates' | 'editor' | 'export'>('templates');
  const [selectedTemplate, setSelectedTemplate] = useState(reportTemplates[0]);
  const [isGenerating, setIsGenerating] = useState(false);
  const [generated, setGenerated] = useState(false);
  const [expandedSections, setExpandedSections] = useState<Set<number>>(new Set([0, 1, 2]));

  const toggleSection = (idx: number) => {
    setExpandedSections(prev => {
      const next = new Set(prev);
      if (next.has(idx)) next.delete(idx);
      else next.add(idx);
      return next;
    });
  };

  const handleGenerate = () => {
    setIsGenerating(true);
    setTimeout(() => {
      setIsGenerating(false);
      setGenerated(true);
      setActiveTab('editor');
    }, 2000);
  };

  // Mock report content
  const reportContent = [
    {
      title: '摘要',
      content: `本报告基于多源数据交叉验证，系统分析了${selectedTemplate.name}的核心发现。研究周期内，共追踪到 156 个信息技术岗位的能力变化，识别出 6 个新兴岗位方向。数据覆盖 8 个主流数据源，累计处理超过 50 万条有效数据记录。`,
      charts: false,
    },
    {
      title: '岗位概览',
      content: `当前新一代信息技术领域共覆盖 4 大技术方向：人工智能、大数据、物联网、智能系统。其中人工智能方向岗位需求增长最为显著，平均需求指数达到 87.5，较上季度提升 12.3%。大模型相关岗位（含大模型应用工程师、AI Agent架构师等）需求增速超过 200%。`,
      charts: true,
    },
    {
      title: '能力变更明细',
      content: `研究周期内共记录 45 项能力变更，其中新增 18 项、删除 7 项、修改 20 项。变更最为频繁的岗位为 AI 算法工程师（5项变更）和 IoT 系统架构师（4项变更）。新增能力中，RAG技术栈、Agent开发、大模型微调等与LLM相关的技能占比达到 60%。`,
      charts: true,
    },
    {
      title: '趋势分析',
      content: `基于时间序列分析与前沿技术传导模型，预测未来 6-12 个月以下趋势将持续强化：\n\n1. AI Agent 生态岗位需求将增长 150-200%\n2. 边缘AI与端侧部署能力将成为IoT岗位标配\n3. 数据治理与合规能力需求将向中初级岗位下沉\n4. 跨领域复合能力（AI+行业知识）将成为高级岗位核心要求`,
      charts: true,
    },
    {
      title: '数据源说明',
      content: `本报告数据来源涵盖 8 个数据源，包括 BOSS直聘（125,000条）、猎聘网（98,000条）、智联招聘（110,000条）等招聘平台数据，arXiv论文库（45,000条）与国家专利局（32,000条）等学术数据，以及政策文件库（8,500条）和行业报告库（15,000条）。所有数据均经过多源交叉验证，平均置信度 82.5%。`,
      charts: false,
    },
    {
      title: '结论与建议',
      content: `基于以上分析，提出以下建议：\n\n1. 重点关注大模型应用相关岗位的能力要求变化，及时调整人才培养方向\n2. 建立新兴岗位跟踪机制，对高信号岗位（AI Agent架构师、Prompt工程师等）进行持续监测\n3. 加强数据治理能力建设，为岗位能力演化提供更精准的数据支撑\n4. 推动跨领域复合型人才培养，满足智能系统方向对复合能力的需求`,
      charts: false,
    },
  ];

  return (
    <>
      {/* Sidebar */}
      <aside className="fixed left-0 top-14 bottom-0 w-60 bg-white border-r border-slate-200 overflow-y-auto z-10">
        <div className="p-4">
          <p className="text-xs font-medium text-slate-400 uppercase tracking-wider mb-3 px-1">报告中心</p>
          <div className="space-y-1">
            {[
              { id: 'templates', label: '报告模板', icon: FilePlus },
              { id: 'editor', label: '报告编辑', icon: Edit3 },
              { id: 'export', label: '导出管理', icon: Download },
            ].map(item => (
              <button
                key={item.id}
                onClick={() => setActiveTab(item.id as typeof activeTab)}
                className={`w-full flex items-center gap-2 px-3 py-2 rounded-lg text-sm transition-colors ${
                  activeTab === item.id ? 'bg-blue-50 text-blue-700' : 'text-slate-600 hover:bg-slate-50'
                }`}
              >
                <item.icon className="w-4 h-4" />
                {item.label}
              </button>
            ))}
          </div>

          <div className="mt-6">
            <p className="text-xs font-medium text-slate-400 uppercase tracking-wider mb-3 px-1">历史报告</p>
            <div className="space-y-1">
              {[
                { name: 'AI岗位Q4演化报告', date: '2025-01-10' },
                { name: '新岗位立项-Q1', date: '2025-01-05' },
                { name: '北京人才白皮书', date: '2024-12-28' },
              ].map(r => (
                <div key={r.name} className="px-2 py-1.5 rounded hover:bg-slate-50 cursor-pointer">
                  <p className="text-sm text-slate-600 truncate">{r.name}</p>
                  <p className="text-xs text-slate-400">{r.date}</p>
                </div>
              ))}
            </div>
          </div>
        </div>
      </aside>

      {/* Main content */}
      <div className="ml-60 flex-1 flex flex-col">
        {activeTab === 'templates' && (
          <div className="p-6">
            <h2 className="text-xl font-bold text-slate-800 mb-6">报告模板</h2>
            <div className="grid grid-cols-3 gap-4">
              {reportTemplates.map(tpl => (
                <div
                  key={tpl.id}
                  className={`bg-white rounded-xl border-2 p-5 cursor-pointer transition-all hover:shadow-md ${
                    selectedTemplate.id === tpl.id ? 'border-blue-500 bg-blue-50/30' : 'border-slate-200 hover:border-slate-300'
                  }`}
                  onClick={() => setSelectedTemplate(tpl)}
                >
                  <div className="flex items-center gap-3 mb-3">
                    <div className="w-10 h-10 rounded-lg bg-blue-50 flex items-center justify-center">
                      <FileText className="w-5 h-5 text-blue-600" />
                    </div>
                    <div>
                      <h3 className="text-sm font-semibold text-slate-800">{tpl.name}</h3>
                      <span className="text-xs text-slate-400">{tpl.type}</span>
                    </div>
                  </div>
                  <p className="text-sm text-slate-500 mb-3">{tpl.description}</p>
                  <div className="flex flex-wrap gap-1">
                    {tpl.sections.slice(0, 4).map(s => (
                      <span key={s} className="px-1.5 py-0.5 rounded bg-slate-100 text-xs text-slate-500">{s}</span>
                    ))}
                    {tpl.sections.length > 4 && (
                      <span className="px-1.5 py-0.5 rounded bg-slate-100 text-xs text-slate-400">+{tpl.sections.length - 4}</span>
                    )}
                  </div>
                </div>
              ))}
            </div>

            {/* Generate button */}
            <div className="mt-6 bg-white rounded-xl border border-slate-200 p-5">
              <h3 className="text-sm font-semibold text-slate-700 mb-3">生成参数</h3>
              <div className="grid grid-cols-3 gap-4 mb-4">
                <div>
                  <label className="text-xs text-slate-500 mb-1 block">领域方向</label>
                  <select className="w-full h-8 px-2 rounded-md border border-slate-200 text-sm bg-white focus:outline-none focus:border-blue-400">
                    <option>全部方向</option>
                    <option>人工智能</option>
                    <option>大数据</option>
                    <option>物联网</option>
                    <option>智能系统</option>
                  </select>
                </div>
                <div>
                  <label className="text-xs text-slate-500 mb-1 block">时间范围</label>
                  <select className="w-full h-8 px-2 rounded-md border border-slate-200 text-sm bg-white focus:outline-none focus:border-blue-400">
                    <option>近3个月</option>
                    <option>近6个月</option>
                    <option>近12个月</option>
                  </select>
                </div>
                <div>
                  <label className="text-xs text-slate-500 mb-1 block">侧重点</label>
                  <select className="w-full h-8 px-2 rounded-md border border-slate-200 text-sm bg-white focus:outline-none focus:border-blue-400">
                    <option>全面分析</option>
                    <option>趋势预测</option>
                    <option>能力变化</option>
                  </select>
                </div>
              </div>
              <button
                onClick={handleGenerate}
                disabled={isGenerating}
                className="px-6 py-2.5 rounded-lg bg-blue-600 text-white text-sm font-medium hover:bg-blue-700 transition-colors disabled:opacity-50 flex items-center gap-2"
              >
                {isGenerating ? (
                  <>
                    <RefreshCw className="w-4 h-4 animate-spin" />
                    生成中...
                  </>
                ) : (
                  <>
                    <Sparkles className="w-4 h-4" />
                    一键生成报告
                  </>
                )}
              </button>
            </div>
          </div>
        )}

        {activeTab === 'editor' && (
          <div className="flex-1 flex">
            {/* Left: Section navigation */}
            <div className="w-56 bg-white border-r border-slate-200 p-4 overflow-y-auto">
              <p className="text-xs font-medium text-slate-400 uppercase tracking-wider mb-3">目录结构</p>
              <div className="space-y-0.5">
                {reportContent.map((section, idx) => (
                  <button
                    key={idx}
                    onClick={() => toggleSection(idx)}
                    className={`w-full text-left flex items-center gap-2 px-2 py-1.5 rounded-md text-sm transition-colors ${
                      expandedSections.has(idx) ? 'bg-blue-50 text-blue-700' : 'text-slate-600 hover:bg-slate-50'
                    }`}
                  >
                    <GripVertical className="w-3 h-3 text-slate-300" />
                    <span className="flex-1 truncate">{section.title}</span>
                    {section.charts && <BarChart3 className="w-3 h-3 text-slate-300" />}
                  </button>
                ))}
              </div>
            </div>

            {/* Center: Editor */}
            <div className="flex-1 p-6 overflow-y-auto">
              <div className="max-w-3xl mx-auto">
                <div className="flex items-center justify-between mb-6">
                  <div>
                    <h2 className="text-xl font-bold text-slate-800">{selectedTemplate.name}</h2>
                    <p className="text-sm text-slate-400 mt-1">自动生成于 2025-01-15 | 数据截至 2025-01-14</p>
                  </div>
                  <div className="flex items-center gap-2">
                    <button className="px-3 py-1.5 rounded-md border border-slate-200 text-sm text-slate-600 hover:bg-slate-50 flex items-center gap-1">
                      <Save className="w-3.5 h-3.5" /> 保存
                    </button>
                    <button className="px-3 py-1.5 rounded-md border border-slate-200 text-sm text-slate-600 hover:bg-slate-50 flex items-center gap-1">
                      <Printer className="w-3.5 h-3.5" /> 打印
                    </button>
                  </div>
                </div>

                <div className="space-y-6">
                  {reportContent.map((section, idx) => (
                    <div key={idx} className="bg-white rounded-xl border border-slate-200 overflow-hidden">
                      <div className="px-5 py-3 bg-slate-50 border-b border-slate-200 flex items-center justify-between">
                        <h3 className="text-sm font-semibold text-slate-700">
                          {idx + 1}. {section.title}
                        </h3>
                        <div className="flex items-center gap-1">
                          <button className="p-1 rounded hover:bg-white text-slate-400 hover:text-slate-600">
                            <Edit3 className="w-3.5 h-3.5" />
                          </button>
                          <button className="p-1 rounded hover:bg-white text-slate-400 hover:text-slate-600">
                            <Sparkles className="w-3.5 h-3.5" />
                          </button>
                        </div>
                      </div>
                      <div className="p-5">
                        <div className="text-sm text-slate-600 leading-relaxed whitespace-pre-line">
                          {section.content}
                        </div>
                        {section.charts && (
                          <div className="mt-4 bg-slate-50 rounded-lg p-4">
                            <div className="flex items-center gap-2 mb-2">
                              <BarChart3 className="w-4 h-4 text-slate-400" />
                              <span className="text-xs text-slate-400">自动插入图表</span>
                            </div>
                            <div className="h-32 flex items-end gap-1">
                              {Array.from({ length: 12 }, (_, i) => ({
                                h: 30 + Math.random() * 70,
                              })).map((bar, i) => (
                                <div key={i} className="flex-1 rounded-t bg-blue-400/50" style={{ height: `${bar.h}%` }} />
                              ))}
                            </div>
                          </div>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </div>

            {/* Right: AI tools panel */}
            <div className="w-64 bg-white border-l border-slate-200 p-4 overflow-y-auto">
              <p className="text-xs font-medium text-slate-400 uppercase tracking-wider mb-3">AI 工具</p>
              <div className="space-y-2">
                {[
                  { label: 'AI续写', desc: '基于上下文自动续写', icon: Edit3 },
                  { label: '内容润色', desc: '优化表达与逻辑', icon: Sparkles },
                  { label: '数据补充', desc: '自动补充相关数据', icon: BarChart3 },
                  { label: '摘要生成', desc: '提取关键信息', icon: FileText },
                ].map(tool => (
                  <button key={tool.label} className="w-full flex items-center gap-2 px-3 py-2 rounded-lg text-sm text-slate-600 hover:bg-blue-50 hover:text-blue-700 transition-colors">
                    <tool.icon className="w-4 h-4" />
                    <div className="text-left">
                      <p className="text-sm">{tool.label}</p>
                      <p className="text-xs text-slate-400">{tool.desc}</p>
                    </div>
                  </button>
                ))}
              </div>

              <div className="mt-6">
                <p className="text-xs font-medium text-slate-400 uppercase tracking-wider mb-3">引用来源</p>
                <div className="space-y-1.5">
                  {[
                    { name: 'BOSS直聘', count: 125000 },
                    { name: '猎聘网', count: 98000 },
                    { name: '智联招聘', count: 110000 },
                    { name: 'arXiv论文库', count: 45000 },
                    { name: '国家专利局', count: 32000 },
                  ].map(src => (
                    <div key={src.name} className="flex items-center justify-between px-2 py-1 rounded hover:bg-slate-50">
                      <span className="text-xs text-slate-600">{src.name}</span>
                      <span className="text-xs text-slate-400">{(src.count / 1000).toFixed(0)}K</span>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </div>
        )}

        {activeTab === 'export' && (
          <div className="p-6">
            <h2 className="text-xl font-bold text-slate-800 mb-6">导出管理</h2>
            <div className="bg-white rounded-xl border border-slate-200 overflow-hidden">
              <table className="w-full">
                <thead>
                  <tr className="bg-slate-50 border-b border-slate-200">
                    <th className="text-left px-5 py-2.5 text-xs font-medium text-slate-500">报告名称</th>
                    <th className="text-left px-5 py-2.5 text-xs font-medium text-slate-500">类型</th>
                    <th className="text-left px-5 py-2.5 text-xs font-medium text-slate-500">生成时间</th>
                    <th className="text-center px-5 py-2.5 text-xs font-medium text-slate-500">状态</th>
                    <th className="text-center px-5 py-2.5 text-xs font-medium text-slate-500">操作</th>
                  </tr>
                </thead>
                <tbody>
                  {[
                    { name: 'AI岗位能力演化报告-2025Q1', type: '演化报告', date: '2025-01-15', status: 'ready' },
                    { name: '新岗位立项论证-AI Agent', type: '立项报告', date: '2025-01-12', status: 'ready' },
                    { name: '北京区域人才白皮书', type: '白皮书', date: '2025-01-10', status: 'ready' },
                    { name: '大数据岗位季度报告', type: '演化报告', date: '2025-01-08', status: 'generating' },
                  ].map((r, i) => (
                    <tr key={i} className="border-b border-slate-100 hover:bg-slate-50/50">
                      <td className="px-5 py-3 text-sm font-medium text-slate-700">{r.name}</td>
                      <td className="px-5 py-3">
                        <span className="text-xs px-2 py-0.5 rounded bg-slate-100 text-slate-600">{r.type}</span>
                      </td>
                      <td className="px-5 py-3 text-sm text-slate-500">{r.date}</td>
                      <td className="px-5 py-3 text-center">
                        {r.status === 'ready' ? (
                          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-medium bg-emerald-50 text-emerald-700">
                            <CheckCircle2 className="w-3 h-3" /> 已完成
                          </span>
                        ) : (
                          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-medium bg-amber-50 text-amber-700">
                            <Clock className="w-3 h-3" /> 生成中
                          </span>
                        )}
                      </td>
                      <td className="px-5 py-3 text-center">
                        <div className="flex items-center justify-center gap-1">
                          <button className="px-2 py-1 rounded text-xs text-blue-600 hover:bg-blue-50 flex items-center gap-1">
                            <Eye className="w-3 h-3" /> 预览
                          </button>
                          <button className="px-2 py-1 rounded text-xs text-slate-600 hover:bg-slate-50 flex items-center gap-1">
                            <Download className="w-3 h-3" /> PDF
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </div>
    </>
  );
}
