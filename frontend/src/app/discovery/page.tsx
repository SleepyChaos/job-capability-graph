'use client';

import React, { useEffect, useState } from 'react';
import {
  Sparkles, Zap, ExternalLink, CheckCircle2, ArrowRight, Layers, ShieldAlert, Info,
} from 'lucide-react';
import { useRouter } from 'next/navigation';
import { type NewJob } from '@/lib/mock-data';
import { fetchClustersAsNewJobs } from '@/lib/api';

const signalColors = {
  high: { bg: 'bg-emerald-50', text: 'text-emerald-700', dot: 'bg-emerald-500' },
  medium: { bg: 'bg-amber-50', text: 'text-amber-700', dot: 'bg-amber-500' },
  low: { bg: 'bg-slate-100', text: 'text-slate-600', dot: 'bg-slate-400' },
};
const signalLabels = { high: '高信号', medium: '中信号', low: '低信号' };

export default function DiscoveryPage() {
  const router = useRouter();
  // 新岗位候选：来自统一库聚类结果（/api/clusters，job_count≥5 头部聚类）
  const [newJobs, setNewJobs] = useState<NewJob[]>([]);
  const [selectedJob, setSelectedJob] = useState<NewJob | null>(null);
  const [signalFilter, setSignalFilter] = useState<string>('all');

  useEffect(() => {
    let cancelled = false;
    fetchClustersAsNewJobs()
      .then(jobs => { if (!cancelled) setNewJobs(jobs); })
      .catch(() => { /* 后端不可用时保持空列表，页面提示无数据 */ });
    return () => { cancelled = true; };
  }, []);

  const filteredJobs = newJobs.filter(j => {
    if (signalFilter !== 'all' && j.signalStrength !== signalFilter) return false;
    return true;
  });

  const goDefine = (job: NewJob) => {
    router.push(`/evolution?cluster=${encodeURIComponent(job.id)}`);
  };

  // 全部指标均为统一库真实统计口径（job_count / 命名来源），无展示性数值
  const stats = [
    { label: '高信号候选', value: newJobs.filter(j => j.signalStrength === 'high').length, icon: Zap, color: 'text-emerald-600', bg: 'bg-emerald-50' },
    { label: '候选岗位数', value: newJobs.length, icon: Sparkles, color: 'text-blue-600', bg: 'bg-blue-50' },
    { label: '聚合岗位数', value: newJobs.reduce((s, j) => s + (j.jobCount ?? 0), 0), icon: Layers, color: 'text-violet-600', bg: 'bg-violet-50' },
    { label: '待审核命名', value: newJobs.filter(j => j.nameSource === 'llm').length, icon: ShieldAlert, color: 'text-amber-600', bg: 'bg-amber-50' },
  ];

  return (
    <>
      {/* Sidebar */}
      <aside className="fixed left-0 top-14 bottom-0 w-60 bg-white border-r border-slate-200 overflow-y-auto z-10">
        <div className="p-4">
          <p className="text-xs font-medium text-slate-400 uppercase tracking-wider mb-3 px-1">筛选条件</p>
          <div className="space-y-3">
            <div>
              <label className="text-xs text-slate-500 mb-1 block">信号强度</label>
              <select value={signalFilter} onChange={e => setSignalFilter(e.target.value)}
                className="w-full h-8 px-2 rounded-md border border-slate-200 text-sm bg-white focus:outline-none focus:border-blue-400">
                <option value="all">全部</option>
                <option value="high">高信号（≥5 岗位聚合）</option>
                <option value="medium">中信号（3-4 岗位聚合）</option>
                <option value="low">低信号（2 岗位聚合）</option>
              </select>
            </div>
          </div>

          {/* 页面职责说明：与「动态演化」页的边界 */}
          <div className="mt-6 rounded-lg border border-blue-100 bg-blue-50/60 p-3">
            <p className="text-xs font-medium text-blue-700 mb-1 flex items-center gap-1">
              <Info className="w-3.5 h-3.5" /> 本页职责
            </p>
            <p className="text-[11px] leading-relaxed text-blue-600">
              仅负责<b>候选发现与浏览</b>：数据来自统一库 JD 聚类（job_count≥5 的头部聚类）。
              将候选正式定义为五要素岗位、审核入库与能力演化，请进入「动态演化」页。
            </p>
          </div>
        </div>
      </aside>

      {/* Main content */}
      <div className="ml-60 flex-1 p-6 overflow-y-auto">
        <div className="flex items-center gap-1 mb-6 bg-slate-100 rounded-lg p-1 w-fit">
          <span className="px-4 py-2 rounded-md text-sm font-medium bg-white text-blue-700 shadow-sm">
            <Sparkles className="w-4 h-4 inline mr-1.5 -mt-0.5" />
            市场新岗位发现
          </span>
        </div>

        {/* Stats cards（真实统计口径） */}
        <div className="grid grid-cols-4 gap-4 mb-6">
          {stats.map(s => (
            <div key={s.label} className="bg-white rounded-xl border border-slate-200 p-4 hover:shadow-sm transition-shadow">
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

        {/* Job cards */}
        <div className="grid grid-cols-2 gap-4">
          {filteredJobs.length === 0 && (
            <div className="col-span-2 py-16 text-center text-sm text-slate-400 bg-white rounded-lg border border-dashed border-slate-200">
              暂无新岗位候选：请先运行数据管线（python3 -m pipeline.run_pipeline）并启动后端 API，或当前筛选条件下无结果
            </div>
          )}
          {filteredJobs.map(job => {
            const sc = signalColors[job.signalStrength];
            const llmNamed = job.nameSource === 'llm';
            return (
              <div
                key={job.id}
                className="bg-white rounded-xl border border-slate-200 p-5 hover:shadow-md hover:-translate-y-0.5 transition-all cursor-pointer"
                onClick={() => setSelectedJob(job)}
              >
                <div className="flex items-start justify-between mb-3">
                  <div>
                    <h3 className="text-base font-semibold text-slate-800 mb-1">{job.name}</h3>
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-medium ${sc.bg} ${sc.text}`}>
                        <span className={`w-1.5 h-1.5 rounded-full ${sc.dot}`} />
                        {signalLabels[job.signalStrength]}
                      </span>
                      <span className={`px-2 py-0.5 rounded text-xs font-medium ${
                        llmNamed ? 'bg-amber-50 text-amber-700' : 'bg-emerald-50 text-emerald-700'
                      }`}>
                        {llmNamed ? 'LLM命名 · 待审核' : '规则命名 · 已生效'}
                      </span>
                    </div>
                  </div>
                  <div className="text-right">
                    <p className="text-base font-bold text-slate-800">{job.jobCount ?? 0} 岗位</p>
                    <p className="text-xs text-slate-400">{job.salary}</p>
                  </div>
                </div>

                <p className="text-sm text-slate-500 mb-3 line-clamp-2">{job.description}</p>

                <div className="flex flex-wrap gap-1.5 mb-3">
                  {job.skills.map(s => (
                    <span key={s} className="px-2 py-0.5 rounded bg-blue-50 text-blue-700 text-xs">{s}</span>
                  ))}
                </div>

                <div className="flex items-center justify-between pt-3 border-t border-slate-100">
                  <span className="text-xs text-slate-400 flex items-center gap-1">
                    <ExternalLink className="w-3 h-3" /> {job.source}
                  </span>
                  <div className="flex items-center gap-1">
                    <button
                      onClick={e => { e.stopPropagation(); goDefine(job); }}
                      className="px-2.5 py-1 rounded-md text-xs text-violet-700 bg-violet-50 hover:bg-violet-100 transition-colors inline-flex items-center gap-1"
                    >
                      去定义 <ArrowRight className="w-3 h-3" />
                    </button>
                    <button
                      onClick={e => { e.stopPropagation(); setSelectedJob(job); }}
                      className="px-2.5 py-1 rounded-md text-xs text-slate-600 hover:bg-slate-50 transition-colors"
                    >
                      详情
                    </button>
                  </div>
                </div>
              </div>
            );
          })}
        </div>

        {/* Detail modal（全部为真实聚类数据） */}
        {selectedJob && (
          <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30" onClick={() => setSelectedJob(null)}>
            <div className="bg-white rounded-2xl shadow-2xl w-[700px] max-h-[80vh] overflow-hidden" onClick={e => e.stopPropagation()}>
              <div className="p-6 overflow-y-auto max-h-[80vh]">
                <div className="flex items-center justify-between mb-4">
                  <div>
                    <h2 className="text-xl font-bold text-slate-800">{selectedJob.name}</h2>
                    <div className="flex items-center gap-2 mt-1">
                      <span className={`px-2 py-0.5 rounded text-xs font-medium ${signalColors[selectedJob.signalStrength].bg} ${signalColors[selectedJob.signalStrength].text}`}>
                        {signalLabels[selectedJob.signalStrength]}
                      </span>
                      <span className={`px-2 py-0.5 rounded text-xs font-medium ${
                        selectedJob.nameSource === 'llm' ? 'bg-amber-50 text-amber-700' : 'bg-emerald-50 text-emerald-700'
                      }`}>
                        {selectedJob.nameSource === 'llm' ? 'LLM命名 · 待审核' : '规则命名 · 已生效'}
                      </span>
                    </div>
                  </div>
                  <button onClick={() => setSelectedJob(null)} className="text-slate-400 hover:text-slate-600">✕</button>
                </div>

                <p className="text-sm text-slate-600 mb-4">{selectedJob.description}</p>

                <div className="grid grid-cols-3 gap-3 mb-4">
                  <div className="bg-slate-50 rounded-lg p-3">
                    <p className="text-xs text-slate-400 mb-1">聚合岗位数</p>
                    <p className="text-xl font-bold text-slate-800">{selectedJob.jobCount ?? 0}</p>
                  </div>
                  <div className="bg-slate-50 rounded-lg p-3">
                    <p className="text-xs text-slate-400 mb-1">聚类编号</p>
                    <p className="text-lg font-bold text-slate-700">{selectedJob.id}</p>
                  </div>
                  <div className="bg-slate-50 rounded-lg p-3">
                    <p className="text-xs text-slate-400 mb-1">代表薪资</p>
                    <p className="text-lg font-bold text-slate-700">{selectedJob.salary}</p>
                  </div>
                </div>

                <div className="mb-4">
                  <p className="text-sm font-medium text-slate-700 mb-2">共享技能（聚类内高频）</p>
                  <div className="flex flex-wrap gap-1.5">
                    {selectedJob.skills.map(s => (
                      <span key={s} className="px-2.5 py-1 rounded-md bg-blue-50 text-blue-700 text-sm">{s}</span>
                    ))}
                  </div>
                </div>

                <div className="mb-4">
                  <p className="text-sm font-medium text-slate-700 mb-2">关联技能</p>
                  <div className="flex flex-wrap gap-1.5">
                    {selectedJob.bonusSkills.map(s => (
                      <span key={s} className="px-2.5 py-1 rounded-md bg-violet-50 text-violet-700 text-sm">{s}</span>
                    ))}
                  </div>
                </div>

                <div className="mb-4">
                  <p className="text-sm font-medium text-slate-700 mb-2">代表岗位方向</p>
                  <div className="space-y-1">
                    {selectedJob.scenarios.map(s => (
                      <div key={s} className="flex items-center gap-2 text-sm text-slate-600">
                        <CheckCircle2 className="w-4 h-4 text-emerald-500" /> {s}
                      </div>
                    ))}
                  </div>
                </div>

                <div>
                  <p className="text-sm font-medium text-slate-700 mb-2">数据源追溯</p>
                  <div className="space-y-1">
                    <div className="flex items-center justify-between py-1.5 px-2 rounded hover:bg-slate-50">
                      <span className="text-sm text-slate-600">{selectedJob.source}</span>
                      <span className="text-xs text-emerald-600">统一库真实统计</span>
                    </div>
                  </div>
                </div>

                <div className="mt-5 pt-4 border-t border-slate-100 flex gap-2">
                  <button
                    onClick={() => { setSelectedJob(null); goDefine(selectedJob); }}
                    className="flex-1 py-2 rounded-lg bg-violet-600 text-white text-sm font-medium hover:bg-violet-700 transition-colors inline-flex items-center justify-center gap-1"
                  >
                    去动态演化页生成定义 <ArrowRight className="w-4 h-4" />
                  </button>
                </div>
              </div>
            </div>
          </div>
        )}
      </div>
    </>
  );
}
