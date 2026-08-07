'use client';

// 新岗位发现工作台（阶段 6）：技术演化驱动路线（移植自 embodied-job-evolution-lab）
// 旅程：技术搜索 → 标准实体链接 → 发起预测 → 候选岗位（七维评分 + 证据链）→ 提交审核
// 数据全部来自 /api/emerging/* 真实接口；候选提交后进入 governance 审核闭环

import React, { useState } from 'react';
import {
  Sparkles, Search, Zap, GitBranch, CheckCircle2, ShieldAlert, ArrowRight,
  Loader2, Info, Send,
} from 'lucide-react';
import {
  searchEmergingTechnologies, runEmergingDiscovery, submitEmergingCandidate,
  type EmergingTechnology, type EmergingRunResult, type EmergingCandidate,
} from '@/lib/api';

const jobTypeStyle: Record<string, string> = {
  '新兴岗位': 'bg-emerald-50 text-emerald-700',
  '岗位演化': 'bg-amber-50 text-amber-700',
  '已有岗位': 'bg-slate-100 text-slate-600',
};

const scoreLabels: Record<string, string> = {
  technology_relevance: '技术相关性',
  task_gap: '任务缺口',
  cohesion: '任务内聚',
  cross_company: '跨公司信号',
  maturity: '技术成熟度',
  evidence: '证据强度',
  existing_overlap: '现有岗位重合',
};

function ScoreBars({ scores }: { scores: Record<string, number> }) {
  return (
    <div className="space-y-1.5">
      {Object.entries(scores).map(([key, value]) => (
        <div key={key} className="flex items-center gap-2">
          <span className="text-[11px] text-slate-500 w-24 shrink-0">{scoreLabels[key] ?? key}</span>
          <div className="flex-1 h-1.5 bg-slate-100 rounded-full overflow-hidden">
            <div
              className={`h-full rounded-full ${key === 'existing_overlap' ? 'bg-slate-400' : 'bg-blue-500'}`}
              style={{ width: `${Math.min(100, value * 100)}%` }}
            />
          </div>
          <span className="text-[11px] text-slate-400 w-9 text-right">{value.toFixed(2)}</span>
        </div>
      ))}
    </div>
  );
}

export default function DiscoveryPage() {
  // 技术搜索与实体链接
  const [query, setQuery] = useState('');
  const [techs, setTechs] = useState<EmergingTechnology[]>([]);
  const [selectedTech, setSelectedTech] = useState<EmergingTechnology | null>(null);
  const [searching, setSearching] = useState(false);

  // 预测运行
  const [mode, setMode] = useState<'rule' | 'mock' | 'llm'>('rule');
  const [running, setRunning] = useState(false);
  const [runId, setRunId] = useState('');
  const [result, setResult] = useState<EmergingRunResult | null>(null);
  const [error, setError] = useState('');

  // 提交审核状态
  const [submitted, setSubmitted] = useState<Record<string, boolean>>({});
  const [expanded, setExpanded] = useState<string>('');

  const doSearch = async () => {
    if (!query.trim()) return;
    setSearching(true);
    setError('');
    try {
      const items = await searchEmergingTechnologies(query.trim());
      setTechs(items);
      if (items.length === 0) setError('未找到相近技术实体，请尝试其他关键词（如：世界模型 / VLA / Sim-to-Real）');
    } catch (e) {
      setError(e instanceof Error ? e.message : '搜索失败，请确认后端已启动');
    } finally {
      setSearching(false);
    }
  };

  const doRun = async () => {
    if (!selectedTech) return;
    setRunning(true);
    setError('');
    setResult(null);
    setSubmitted({});
    try {
      const payload = await runEmergingDiscovery({
        technologyId: selectedTech.technology_id,
        generationMode: mode,
        topK: 5,
      });
      setRunId(payload.run_id);
      setResult(payload.result);
    } catch (e) {
      setError(e instanceof Error ? e.message : '预测失败');
    } finally {
      setRunning(false);
    }
  };

  const doSubmit = async (candidate: EmergingCandidate) => {
    try {
      await submitEmergingCandidate(runId, candidate.candidate_id);
      setSubmitted(prev => ({ ...prev, [candidate.candidate_id]: true }));
    } catch (e) {
      setError(e instanceof Error ? e.message : '提交失败');
    }
  };

  return (
    <div className="pt-14 min-h-screen bg-slate-50">
      <div className="max-w-6xl mx-auto px-6 py-6 space-y-5">
        {/* 页头 */}
        <div className="flex items-start justify-between">
          <div>
            <h1 className="text-xl font-bold text-slate-800 flex items-center gap-2">
              <Sparkles className="w-5 h-5 text-blue-600" /> 新岗位发现 · 技术演化驱动
            </h1>
            <p className="text-sm text-slate-500 mt-1">
              技能关键词实体链接 × 技术里程碑成熟度 × 现有岗位任务缺口 → 候选新兴岗位（证据链可溯源）
            </p>
          </div>
          <div className="rounded-lg border border-blue-100 bg-blue-50/60 px-3 py-2 max-w-sm">
            <p className="text-[11px] leading-relaxed text-blue-600 flex gap-1.5">
              <Info className="w-3.5 h-3.5 shrink-0 mt-0.5" />
              候选岗位提交后以「待审核」状态进入数据治理队列，审核通过方可作为正式岗位定义——未审核不入正式表。
            </p>
          </div>
        </div>

        {/* 步骤一：技术搜索与实体链接 */}
        <div className="bg-white rounded-xl border border-slate-200 p-5">
          <p className="text-sm font-medium text-slate-700 mb-3">① 搜索技术实体（标准实体链接）</p>
          <div className="flex gap-2">
            <div className="relative flex-1">
              <Search className="w-4 h-4 text-slate-400 absolute left-3 top-1/2 -translate-y-1/2" />
              <input
                value={query}
                onChange={e => setQuery(e.target.value)}
                onKeyDown={e => e.key === 'Enter' && doSearch()}
                placeholder="输入技术关键词，如：世界模型、VLA、Sim-to-Real、强化学习…"
                className="w-full h-9 pl-9 pr-3 rounded-lg border border-slate-200 text-sm focus:outline-none focus:border-blue-400"
              />
            </div>
            <button
              onClick={doSearch}
              disabled={searching}
              className="px-4 h-9 rounded-lg bg-blue-600 text-white text-sm font-medium hover:bg-blue-700 disabled:opacity-50 inline-flex items-center gap-1.5"
            >
              {searching ? <Loader2 className="w-4 h-4 animate-spin" /> : <Search className="w-4 h-4" />}
              搜索
            </button>
          </div>

          {techs.length > 0 && (
            <div className="mt-3 space-y-1.5">
              {techs.map(t => {
                const active = selectedTech?.technology_id === t.technology_id;
                return (
                  <button
                    key={t.technology_id}
                    onClick={() => setSelectedTech(t)}
                    className={`w-full text-left px-3 py-2 rounded-lg border text-sm transition-colors ${
                      active ? 'border-blue-400 bg-blue-50/60' : 'border-slate-100 hover:bg-slate-50'
                    }`}
                  >
                    <div className="flex items-center justify-between">
                      <span className="font-medium text-slate-800">
                        {t.standard_name}
                        <span className="ml-2 text-xs text-slate-400">{t.technology_id} · {t.level}</span>
                      </span>
                      <span className={`text-xs px-1.5 py-0.5 rounded ${
                        t.link_confidence >= 0.85 ? 'bg-emerald-50 text-emerald-600' : 'bg-amber-50 text-amber-600'
                      }`}>
                        链接置信度 {t.link_confidence.toFixed(2)}
                      </span>
                    </div>
                    {t.definition && <p className="text-xs text-slate-500 mt-0.5 line-clamp-1">{t.definition}</p>}
                  </button>
                );
              })}
            </div>
          )}

          {selectedTech && (
            <div className="mt-4 flex items-center justify-between rounded-lg bg-slate-50 border border-slate-200 px-4 py-3">
              <div>
                <p className="text-sm font-medium text-slate-800">
                  已选定：{selectedTech.standard_name}
                  <span className="ml-2 text-xs text-slate-400">{selectedTech.technology_id}</span>
                </p>
                <p className="text-xs text-slate-500 mt-0.5">
                  别名/子技术词 {selectedTech.aliases.length} 个用于 JD 证据召回
                </p>
              </div>
              <div className="flex items-center gap-2">
                <select
                  value={mode}
                  onChange={e => setMode(e.target.value as 'rule' | 'mock' | 'llm')}
                  className="h-9 px-2 rounded-lg border border-slate-200 text-sm bg-white focus:outline-none"
                >
                  <option value="rule">规则模式（知识库任务）</option>
                  <option value="mock">Mock 模式（链路联调）</option>
                  <option value="llm">LLM 模式（动态生成，无 Key 自动降级）</option>
                </select>
                <button
                  onClick={doRun}
                  disabled={running}
                  className="px-4 h-9 rounded-lg bg-violet-600 text-white text-sm font-medium hover:bg-violet-700 disabled:opacity-50 inline-flex items-center gap-1.5"
                >
                  {running ? <Loader2 className="w-4 h-4 animate-spin" /> : <Zap className="w-4 h-4" />}
                  {running ? '预测中…' : '发起新兴岗位预测'}
                </button>
              </div>
            </div>
          )}
        </div>

        {error && (
          <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-600">{error}</div>
        )}

        {/* 步骤二：预测结果 */}
        {result && (
          <>
            {/* 指标条 */}
            <div className="grid grid-cols-4 gap-4">
              {[
                { label: '技术成熟度', value: result.technology.maturity_score.toFixed(3), icon: GitBranch, color: 'text-violet-600', bg: 'bg-violet-50' },
                { label: '相关岗位召回', value: result.metrics.related_job_count, icon: Search, color: 'text-blue-600', bg: 'bg-blue-50' },
                { label: '里程碑证据', value: result.metrics.milestone_count, icon: Zap, color: 'text-amber-600', bg: 'bg-amber-50' },
                { label: '候选岗位', value: result.candidate_jobs.length, icon: Sparkles, color: 'text-emerald-600', bg: 'bg-emerald-50' },
              ].map(s => (
                <div key={s.label} className="bg-white rounded-xl border border-slate-200 p-4">
                  <div className="flex items-center justify-between mb-2">
                    <span className="text-sm text-slate-500">{s.label}</span>
                    <div className={`p-2 rounded-lg ${s.bg}`}>
                      <s.icon className={`w-4 h-4 ${s.color}`} />
                    </div>
                  </div>
                  <p className="text-2xl font-bold text-slate-800">{s.value}</p>
                </div>
              ))}
            </div>

            {/* 候选岗位卡片 */}
            <div className="space-y-4">
              {result.candidate_jobs.map(c => (
                <div key={c.candidate_id} className="bg-white rounded-xl border border-slate-200 p-5">
                  <div className="flex items-start justify-between mb-3">
                    <div>
                      <div className="flex items-center gap-2 flex-wrap">
                        <h3 className="text-base font-semibold text-slate-800">{c.job_title}</h3>
                        <span className={`px-2 py-0.5 rounded text-xs font-medium ${jobTypeStyle[c.job_type]}`}>
                          {c.job_type}
                        </span>
                        <span className="px-2 py-0.5 rounded text-xs font-medium bg-blue-50 text-blue-700">
                          时间窗 {c.time_horizon}
                        </span>
                      </div>
                      {/* 证据链面包屑 */}
                      <div className="flex items-center gap-1 mt-1.5 flex-wrap">
                        {c.evidence_path.map((p, i) => (
                          <React.Fragment key={i}>
                            {i > 0 && <ArrowRight className="w-3 h-3 text-slate-300" />}
                            <span className="px-1.5 py-0.5 rounded bg-slate-50 border border-slate-100 text-[11px] text-slate-500">
                              {p.label}
                            </span>
                          </React.Fragment>
                        ))}
                      </div>
                    </div>
                    <div className="text-right shrink-0 ml-4">
                      <p className="text-2xl font-bold text-slate-800">{c.score.toFixed(1)}</p>
                      <p className="text-xs text-slate-400">综合评分</p>
                    </div>
                  </div>

                  <p className="text-sm text-slate-500 mb-3">{c.formation_reason}</p>

                  <div className="grid grid-cols-2 gap-5">
                    <div>
                      <p className="text-xs font-medium text-slate-400 mb-2">七维分项得分</p>
                      <ScoreBars scores={c.scores} />
                    </div>
                    <div className="space-y-3">
                      <div>
                        <p className="text-xs font-medium text-slate-400 mb-1.5">核心职责（任务集合）</p>
                        <div className="space-y-1">
                          {c.responsibilities.slice(0, 4).map(r => (
                            <p key={r} className="text-xs text-slate-600 flex items-start gap-1.5">
                              <CheckCircle2 className="w-3.5 h-3.5 text-emerald-500 shrink-0 mt-0.5" /> {r}
                            </p>
                          ))}
                        </div>
                      </div>
                      <div>
                        <p className="text-xs font-medium text-slate-400 mb-1.5">必备技能</p>
                        <div className="flex flex-wrap gap-1">
                          {c.required_skills.map(s => (
                            <span key={s} className="px-1.5 py-0.5 rounded bg-blue-50 text-blue-700 text-[11px]">{s}</span>
                          ))}
                        </div>
                      </div>
                    </div>
                  </div>

                  {/* 证据区（可展开） */}
                  <div className="mt-4 pt-3 border-t border-slate-100">
                    <button
                      onClick={() => setExpanded(expanded === c.candidate_id ? '' : c.candidate_id)}
                      className="text-xs text-blue-600 hover:text-blue-700 inline-flex items-center gap-1"
                    >
                      <ShieldAlert className="w-3.5 h-3.5" />
                      {expanded === c.candidate_id ? '收起证据链' : `查看证据链（里程碑 ${c.evidence.milestones.length} · JD 证据 ${c.evidence.jobs.length}）`}
                    </button>
                    {expanded === c.candidate_id && (
                      <div className="mt-3 grid grid-cols-2 gap-4">
                        <div>
                          <p className="text-xs font-medium text-slate-400 mb-1.5">技术里程碑证据</p>
                          <div className="space-y-1.5">
                            {c.evidence.milestones.map(m => (
                              <div key={m.event_id} className="rounded-lg bg-slate-50 px-2.5 py-1.5">
                                <p className="text-xs text-slate-700 font-medium">{m.name}</p>
                                <p className="text-[11px] text-slate-400">{m.event_date} · {m.source} · 相关度 {m.confidence.toFixed(2)}</p>
                              </div>
                            ))}
                            {c.evidence.milestones.length === 0 && <p className="text-xs text-slate-400">无里程碑证据</p>}
                          </div>
                        </div>
                        <div>
                          <p className="text-xs font-medium text-slate-400 mb-1.5">真实 JD 证据</p>
                          <div className="space-y-1.5">
                            {c.evidence.jobs.map(j => (
                              <div key={j.job_id} className="rounded-lg bg-slate-50 px-2.5 py-1.5">
                                <p className="text-xs text-slate-700 font-medium">{j.title} · {j.company}</p>
                                <p className="text-[11px] text-slate-500 line-clamp-2">{j.snippet}</p>
                                <p className="text-[11px] text-slate-400">置信度 {j.confidence.toFixed(2)}</p>
                              </div>
                            ))}
                            {c.evidence.jobs.length === 0 && <p className="text-xs text-slate-400">无 JD 证据（任务缺口显著）</p>}
                          </div>
                        </div>
                      </div>
                    )}
                  </div>

                  {/* 提交审核 */}
                  <div className="mt-4 pt-3 border-t border-slate-100 flex justify-end">
                    <button
                      onClick={() => doSubmit(c)}
                      disabled={submitted[c.candidate_id]}
                      className={`px-3.5 py-1.5 rounded-lg text-xs font-medium inline-flex items-center gap-1.5 transition-colors ${
                        submitted[c.candidate_id]
                          ? 'bg-emerald-50 text-emerald-600 cursor-default'
                          : 'bg-violet-600 text-white hover:bg-violet-700'
                      }`}
                    >
                      {submitted[c.candidate_id]
                        ? <><CheckCircle2 className="w-3.5 h-3.5" /> 已提交审核（数据治理队列）</>
                        : <><Send className="w-3.5 h-3.5" /> 提交审核</>}
                    </button>
                  </div>
                </div>
              ))}
            </div>
          </>
        )}

        {/* 空态引导 */}
        {!result && !running && (
          <div className="py-12 text-center text-sm text-slate-400 bg-white rounded-xl border border-dashed border-slate-200">
            搜索一个技术实体并发起预测，系统将基于技术里程碑成熟度与现有岗位任务缺口生成候选新兴岗位
          </div>
        )}
      </div>
    </div>
  );
}
