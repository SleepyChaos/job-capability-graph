'use client';

// 阶段 4：数据治理 —— 幻觉防控与人工审核工作台
// 机制：证据溯源 + 置信度门限（≥90% 且有证据自动放行）+ 未审核不入正式图谱
// 队列：图谱边 / 聚类命名 / 岗位定义；裁决留痕 reviews 表

import React, { useCallback, useEffect, useState } from 'react';
import {
  Shield, ShieldCheck, ShieldAlert, CheckCircle2, XCircle,
  ClipboardList, FileSearch, LoaderCircle, AlertTriangle, History,
} from 'lucide-react';
import {
  fetchReviewSummary, fetchReviewQueue, reviewDecide, fetchReviewLog,
  type ReviewSummary, type ReviewEdgeItem, type ReviewClusterItem,
  type ReviewDefinitionItem, type ReviewLogItem,
} from '@/lib/api';

type QueueKind = 'cluster' | 'definition' | 'edge';

const queueMeta: Record<QueueKind, { title: string; desc: string }> = {
  cluster: { title: '聚类命名', desc: 'LLM 生成的聚类名称待人工确认' },
  definition: { title: '岗位定义', desc: 'LLM 生成的五要素岗位定义待审' },
  edge: { title: '图谱边', desc: '低置信/无证据的技能关联待审' },
};

function parseStrList(v: string | null | undefined): string[] {
  if (!v) return [];
  const s = v.trim();
  if (s.startsWith('[')) {
    try {
      const p = JSON.parse(s);
      if (Array.isArray(p)) return p.map(String);
    } catch { /* fall through */ }
  }
  return s.split(/[,，]/).map(x => x.trim()).filter(Boolean);
}

export default function GovernancePage() {
  const [summary, setSummary] = useState<ReviewSummary | null>(null);
  const [queue, setQueue] = useState<QueueKind>('cluster');
  const [items, setItems] = useState<Record<string, unknown>[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [comment, setComment] = useState('');
  const [log, setLog] = useState<ReviewLogItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [s, q, lg] = await Promise.all([
        fetchReviewSummary(),
        fetchReviewQueue<Record<string, unknown>>(queue, 50),
        fetchReviewLog(20),
      ]);
      setSummary(s);
      setItems(q);
      setLog(lg);
      setSelectedId(q.length ? String(q[0].target_id) : null);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }, [queue]);

  useEffect(() => { void load(); }, [load]);

  const selected = items.find(i => String(i.target_id) === selectedId) as
    (ReviewEdgeItem | ReviewClusterItem | ReviewDefinitionItem) | undefined;

  const decide = async (action: 'approve' | 'reject') => {
    if (!selected) return;
    setBusy(action);
    setError(null);
    setNotice(null);
    try {
      await reviewDecide(queue, String(selected.target_id), action, comment);
      setNotice(action === 'approve' ? '已批准并写入正式库' : '已拒绝该候选');
      setComment('');
      await load();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(null);
    }
  };

  const pendingOf = (k: QueueKind) => summary?.pending[k] ?? 0;

  return (
    <div className="pt-14 min-h-screen bg-slate-50">
      <div className="max-w-7xl mx-auto px-6 py-6 space-y-5">
        {/* 页头 + 防控机制概览 */}
        <div className="flex items-start justify-between">
          <div>
            <h1 className="text-xl font-bold text-slate-800 flex items-center gap-2">
              <Shield className="w-5 h-5 text-blue-600" /> 数据治理 · 幻觉防控与人工审核
            </h1>
            <p className="text-sm text-slate-500 mt-1 max-w-2xl">
              {summary?.policy.description ?? '证据溯源 + 置信度门限 + 未审核不入正式图谱'}
            </p>
          </div>
          <button
            onClick={() => void load()}
            className="flex items-center gap-1.5 px-3 py-1.5 text-sm rounded-lg border border-slate-300 bg-white text-slate-600 hover:bg-slate-100"
          >
            <LoaderCircle className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} /> 刷新
          </button>
        </div>

        {/* 统计卡 */}
        {summary && (
          <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
            <StatCard icon={ClipboardList} label="待审聚类命名" value={pendingOf('cluster')} tone="amber" />
            <StatCard icon={FileSearch} label="待审岗位定义" value={pendingOf('definition')} tone="violet" />
            <StatCard icon={AlertTriangle} label="待审图谱边" value={pendingOf('edge')} tone="red" />
            <StatCard
              icon={ShieldCheck} label="证据覆盖率"
              value={`${(summary.edges.evidenceCoverage * 100).toFixed(1)}%`}
              sub={`${summary.edges.evidenceCovered}/${summary.edges.total} 条边可回溯 JD 原文`}
              tone="emerald"
            />
            <StatCard
              icon={History} label="已裁决记录" value={summary.decidedTotal}
              sub={`通过 ${summary.edges.approved} / 拒绝 ${summary.edges.rejected}`}
              tone="blue"
            />
          </div>
        )}

        {error && (
          <div className="flex items-center gap-2 px-4 py-2.5 rounded-lg bg-red-50 text-red-700 text-sm">
            <XCircle className="w-4 h-4" /> {error}
          </div>
        )}
        {notice && (
          <div className="flex items-center gap-2 px-4 py-2.5 rounded-lg bg-emerald-50 text-emerald-700 text-sm">
            <CheckCircle2 className="w-4 h-4" /> {notice}
          </div>
        )}

        {/* 队列切换 */}
        <div className="flex gap-2">
          {(Object.keys(queueMeta) as QueueKind[]).map(k => (
            <button
              key={k}
              onClick={() => setQueue(k)}
              className={`px-4 py-2 rounded-lg text-sm font-medium border transition-colors ${
                queue === k
                  ? 'bg-blue-600 text-white border-blue-600'
                  : 'bg-white text-slate-600 border-slate-300 hover:bg-slate-100'
              }`}
            >
              {queueMeta[k].title}
              <span className={`ml-2 px-1.5 py-0.5 rounded text-xs ${
                queue === k ? 'bg-white/20' : 'bg-slate-100 text-slate-500'
              }`}>{pendingOf(k)}</span>
            </button>
          ))}
        </div>

        {/* 审核工作区 */}
        <div className="grid grid-cols-1 lg:grid-cols-5 gap-4">
          {/* 左：队列 */}
          <div className="lg:col-span-2 bg-white rounded-xl border border-slate-200 overflow-hidden">
            <div className="px-4 py-2.5 border-b border-slate-200 flex items-center justify-between">
              <span className="text-sm font-semibold text-slate-700">{queueMeta[queue].desc}</span>
              <span className="text-xs text-slate-400">当页 {items.length} 条</span>
            </div>
            <div className="max-h-[520px] overflow-y-auto divide-y divide-slate-100">
              {loading && !items.length ? (
                <div className="p-8 text-center text-slate-400 text-sm">正在读取审核队列…</div>
              ) : null}
              {!loading && !items.length ? (
                <div className="p-8 text-center text-slate-400 text-sm">
                  <CheckCircle2 className="w-6 h-6 mx-auto mb-2 text-emerald-500" />
                  当前队列已清空，无待审候选
                </div>
              ) : null}
              {items.map(it => {
                const id = String(it.target_id);
                const title = queue === 'cluster' ? String(it.cluster_name)
                  : queue === 'definition' ? String(it.job_name)
                  : `${it.skill_term} @ ${String(it.job_title).split('\n')[0]}`;
                const meta = queue === 'cluster' ? `${it.job_count} 岗位 · ${it.name_source}`
                  : queue === 'definition' ? String(it.generation_source)
                  : `置信度 ${Math.round(Number(it.confidence) * 100)}%`;
                return (
                  <button
                    key={id}
                    onClick={() => setSelectedId(id)}
                    className={`w-full text-left px-4 py-2.5 hover:bg-slate-50 ${
                      selectedId === id ? 'bg-blue-50/70 border-l-2 border-blue-500' : ''
                    }`}
                  >
                    <div className="text-sm font-medium text-slate-700 truncate">{title}</div>
                    <div className="text-xs text-slate-400 mt-0.5">{id} · {meta}</div>
                  </button>
                );
              })}
            </div>
          </div>

          {/* 右：详情与裁决 */}
          <div className="lg:col-span-3 bg-white rounded-xl border border-slate-200 p-5">
            {!selected ? (
              <div className="h-full min-h-[300px] flex flex-col items-center justify-center text-slate-400 text-sm">
                <ShieldAlert className="w-8 h-8 mb-2" /> 选择左侧候选开始审核
              </div>
            ) : (
              <div className="space-y-4">
                <div className="flex items-center justify-between">
                  <div>
                    <div className="text-xs text-slate-400">审核编号 {String(selected.target_id)}</div>
                    <h3 className="text-lg font-bold text-slate-800">
                      {queue === 'cluster' ? (selected as ReviewClusterItem).cluster_name
                        : queue === 'definition' ? (selected as ReviewDefinitionItem).job_name
                        : (selected as ReviewEdgeItem).skill_term}
                    </h3>
                  </div>
                  <span className="px-2.5 py-1 rounded-full text-xs font-medium bg-amber-50 text-amber-700">待审核</span>
                </div>

                {/* 分类型详情 */}
                {queue === 'cluster' && (() => {
                  const c = selected as ReviewClusterItem;
                  return (
                    <DetailBlock>
                      <Field label="聚类描述" value={c.description || '—'} />
                      <Field label="共享技能" value={parseStrList(c.shared_skills).join('、') || '—'} />
                      <Field label="代表岗位" value={parseStrList(c.representative_titles).slice(0, 5).join('；') || '—'} />
                      <Field label="技术域" value={`${c.primary_l1_code || '—'} / ${c.primary_l2_name || '—'} · 聚合 ${c.job_count} 个岗位`} />
                      <Field label="命名来源" value={c.name_source === 'llm' ? 'LLM 生成（需人工确认，防命名幻觉）' : c.name_source} />
                    </DetailBlock>
                  );
                })()}
                {queue === 'definition' && (() => {
                  const d = selected as ReviewDefinitionItem;
                  return (
                    <DetailBlock>
                      <Field label="核心职责" value={d.core_duties} />
                      <Field label="必备技能" value={parseStrList(d.required_skills).join('、')} />
                      <Field label="加分技能" value={parseStrList(d.bonus_skills).join('、') || '—'} />
                      <Field label="应用场景" value={d.industry_scenarios || '—'} />
                      <Field label="生成来源" value={d.generation_source === 'llm' ? 'LLM 生成' : '启发式（真实聚类数据拼装）'} />
                    </DetailBlock>
                  );
                })()}
                {queue === 'edge' && (() => {
                  const e = selected as ReviewEdgeItem;
                  return (
                    <DetailBlock>
                      <Field label="所属岗位" value={e.job_title.split('\n')[0]} />
                      <Field label="置信度" value={`${Math.round(e.confidence * 100)}%（来源：${e.source}）`} />
                      <div>
                        <div className="text-xs font-medium text-slate-500 mb-1">JD 原文证据（溯源）</div>
                        <blockquote className="px-3 py-2 rounded-md bg-slate-50 border border-slate-200 text-sm text-slate-600 leading-relaxed">
                          {e.evidence || '（无证据片段——建议拒绝）'}
                        </blockquote>
                      </div>
                    </DetailBlock>
                  );
                })()}

                {/* 裁决区 */}
                <div className="pt-2 border-t border-slate-100 space-y-3">
                  <input
                    value={comment}
                    onChange={ev => setComment(ev.target.value)}
                    placeholder="审核意见（可选，将写入审核日志）"
                    className="w-full px-3 py-2 text-sm rounded-lg border border-slate-300 focus:outline-none focus:border-blue-500"
                  />
                  <div className="flex gap-2">
                    <button
                      onClick={() => void decide('approve')}
                      disabled={busy !== null}
                      className="flex items-center gap-1.5 px-4 py-2 rounded-lg text-sm font-medium bg-emerald-600 text-white hover:bg-emerald-700 disabled:opacity-50"
                    >
                      {busy === 'approve' ? <LoaderCircle className="w-4 h-4 animate-spin" /> : <CheckCircle2 className="w-4 h-4" />}
                      批准入正式库
                    </button>
                    <button
                      onClick={() => void decide('reject')}
                      disabled={busy !== null}
                      className="flex items-center gap-1.5 px-4 py-2 rounded-lg text-sm font-medium bg-white border border-red-300 text-red-600 hover:bg-red-50 disabled:opacity-50"
                    >
                      {busy === 'reject' ? <LoaderCircle className="w-4 h-4 animate-spin" /> : <XCircle className="w-4 h-4" />}
                      拒绝
                    </button>
                  </div>
                </div>
              </div>
            )}
          </div>
        </div>

        {/* 审核日志 */}
        <div className="bg-white rounded-xl border border-slate-200 overflow-hidden">
          <div className="px-4 py-2.5 border-b border-slate-200 text-sm font-semibold text-slate-700">
            审核日志（reviews 表留痕）
          </div>
          {!log.length ? (
            <div className="p-6 text-center text-sm text-slate-400">暂无审核记录</div>
          ) : (
            <table className="w-full text-sm">
              <thead>
                <tr className="bg-slate-50 text-xs text-slate-500">
                  <th className="text-left px-4 py-2 font-medium">时间</th>
                  <th className="text-left px-4 py-2 font-medium">类型</th>
                  <th className="text-left px-4 py-2 font-medium">目标</th>
                  <th className="text-left px-4 py-2 font-medium">动作</th>
                  <th className="text-left px-4 py-2 font-medium">审核员</th>
                  <th className="text-left px-4 py-2 font-medium">意见</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {log.map(l => (
                  <tr key={l.review_id}>
                    <td className="px-4 py-2 text-slate-500 text-xs whitespace-nowrap">{l.created_at}</td>
                    <td className="px-4 py-2 text-slate-600">{queueMeta[l.target_type as QueueKind]?.title ?? l.target_type}</td>
                    <td className="px-4 py-2 text-slate-600 max-w-[180px] truncate">{l.target_id}</td>
                    <td className="px-4 py-2">
                      <span className={`px-2 py-0.5 rounded text-xs font-medium ${
                        l.action === 'approve' ? 'bg-emerald-50 text-emerald-700' : 'bg-red-50 text-red-700'
                      }`}>{l.action === 'approve' ? '批准' : '拒绝'}</span>
                    </td>
                    <td className="px-4 py-2 text-slate-600">{l.reviewer}</td>
                    <td className="px-4 py-2 text-slate-500 text-xs max-w-[260px] truncate">{l.comment || '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>
    </div>
  );
}

function StatCard({ icon: Icon, label, value, sub, tone }: {
  icon: React.ComponentType<{ className?: string }>;
  label: string; value: number | string; sub?: string;
  tone: 'amber' | 'violet' | 'red' | 'emerald' | 'blue';
}) {
  const tones: Record<string, string> = {
    amber: 'text-amber-600 bg-amber-50',
    violet: 'text-violet-600 bg-violet-50',
    red: 'text-red-600 bg-red-50',
    emerald: 'text-emerald-600 bg-emerald-50',
    blue: 'text-blue-600 bg-blue-50',
  };
  return (
    <div className="bg-white rounded-xl border border-slate-200 p-4">
      <div className={`w-8 h-8 rounded-lg flex items-center justify-center mb-2 ${tones[tone]}`}>
        <Icon className="w-4 h-4" />
      </div>
      <div className="text-xl font-bold text-slate-800">{value}</div>
      <div className="text-xs text-slate-500 mt-0.5">{label}</div>
      {sub && <div className="text-[11px] text-slate-400 mt-1">{sub}</div>}
    </div>
  );
}

function DetailBlock({ children }: { children: React.ReactNode }) {
  return <div className="space-y-3">{children}</div>;
}

function Field({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div className="text-xs font-medium text-slate-500 mb-0.5">{label}</div>
      <div className="text-sm text-slate-700 leading-relaxed">{value}</div>
    </div>
  );
}
