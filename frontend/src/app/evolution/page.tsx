'use client';

// 阶段 5：新岗位定义与能力动态更新（交付案例）
// ① 从聚类生成五要素岗位定义（LLM，未审核不入正式表）
// ② 既有岗位：快照 → 更新 JD 重提取 → 快照差分（新增/删除/修改标注 + 更新说明）

import React, { useCallback, useEffect, useState } from 'react';
import {
  Sparkles, GitBranch, Camera, RefreshCw, LoaderCircle,
  CheckCircle2, XCircle, Plus, Minus, Pencil, AlertCircle, FileText,
} from 'lucide-react';
import {
  fetchClusters, generateDefinition, fetchDefinitions, reviewDecide,
  takeSnapshot, refreshJobSkills, fetchEvolutionDiff, searchJobs,
  API_BASE,
  type ClusterItem, type JobDefinition, type EvolutionDiff,
} from '@/lib/api';

type Tab = 'definition' | 'update';

interface JobBrief { job_id: string; title: string; company: string }
interface JobDetail { jd_text: string; skill_count: number }

export default function EvolutionPage() {
  const [tab, setTab] = useState<Tab>('definition');

  return (
    <div className="pt-14 min-h-screen bg-slate-50">
      <div className="max-w-7xl mx-auto px-6 py-6 space-y-5">
        <div>
          <h1 className="text-xl font-bold text-slate-800 flex items-center gap-2">
            <GitBranch className="w-5 h-5 text-violet-600" /> 动态演化 · 新岗位定义与能力更新
          </h1>
          <p className="text-sm text-slate-500 mt-1">
            聚类 → 五要素岗位定义（人工审核后入正式表）；既有岗位快照差分，追踪能力需求变化
          </p>
        </div>

        {/* 与「岗位发现」页的职责边界说明 */}
        <div className="flex items-start gap-2 px-4 py-3 rounded-lg bg-violet-50 border border-violet-200 text-sm text-violet-700">
          <AlertCircle className="w-4 h-4 mt-0.5 shrink-0" />
          <p>
            本页负责<b>定义与演化</b>：把「岗位发现」页的候选聚类正式定义为五要素岗位（LLM 生成 + 人工审核），
            并对既有岗位做能力快照差分。若从「岗位发现」页跳转而来，下方已自动选中对应聚类（如
            <span className="font-medium"> C56</span>）。
          </p>
        </div>

        <div className="flex gap-2">
          <TabBtn active={tab === 'definition'} onClick={() => setTab('definition')}
            icon={Sparkles} label="新岗位定义" />
          <TabBtn active={tab === 'update'} onClick={() => setTab('update')}
            icon={RefreshCw} label="能力动态更新" />
        </div>

        {tab === 'definition' ? <DefinitionPanel /> : <UpdatePanel />}
      </div>
    </div>
  );
}

function TabBtn({ active, onClick, icon: Icon, label }: {
  active: boolean; onClick: () => void;
  icon: React.ComponentType<{ className?: string }>; label: string;
}) {
  return (
    <button onClick={onClick}
      className={`flex items-center gap-1.5 px-4 py-2 rounded-lg text-sm font-medium border transition-colors ${
        active ? 'bg-violet-600 text-white border-violet-600'
          : 'bg-white text-slate-600 border-slate-300 hover:bg-slate-100'
      }`}>
      <Icon className="w-4 h-4" /> {label}
    </button>
  );
}

/* ------------------------- ① 新岗位定义 ------------------------- */

function DefinitionPanel() {
  const [clusters, setClusters] = useState<ClusterItem[]>([]);
  const [clusterId, setClusterId] = useState('');
  const [definitions, setDefinitions] = useState<JobDefinition[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const loadDefs = useCallback(() => {
    return fetchDefinitions(20).then(setDefinitions).catch(e => setError((e as Error).message));
  }, []);

  useEffect(() => {
    fetchClusters().then(cs => {
      setClusters(cs);
      // 支持从「岗位发现」页跳转预选：/evolution?cluster=C56
      const target = new URLSearchParams(window.location.search).get('cluster');
      const hit = cs.find(c => c.id === target) ?? cs[0];
      if (hit) setClusterId(hit.id);
    }).catch(e => setError((e as Error).message));
    void loadDefs();
  }, [loadDefs]);

  const generate = async () => {
    if (!clusterId) return;
    setBusy(true); setError(null); setNotice(null);
    try {
      const r = await generateDefinition(clusterId);
      setNotice(`已生成「${r.jobName}」定义（${r.llmUsed ? 'LLM' : '启发式'}），状态：待审核`);
      await loadDefs();
    } catch (e) {
      setError((e as Error).message);
    } finally { setBusy(false); }
  };

  const decide = async (def: JobDefinition, action: 'approve' | 'reject') => {
    setError(null); setNotice(null);
    try {
      await reviewDecide('definition', String(def.definition_id), action, '动态演化页审核');
      setNotice(action === 'approve' ? `「${def.job_name}」已批准入正式表` : `「${def.job_name}」已拒绝`);
      await loadDefs();
    } catch (e) { setError((e as Error).message); }
  };

  return (
    <div className="space-y-4">
      {/* 生成区 */}
      <div className="bg-white rounded-xl border border-slate-200 p-5">
        <div className="text-sm font-semibold text-slate-700 mb-3">
          从聚类生成五要素岗位定义（名称 / 职责 / 必备技能 / 加分技能 / 应用场景）
        </div>
        <div className="flex gap-3 items-center flex-wrap">
          <select value={clusterId} onChange={e => setClusterId(e.target.value)}
            className="flex-1 min-w-[320px] px-3 py-2 text-sm rounded-lg border border-slate-300 focus:outline-none focus:border-violet-500 bg-white">
            {clusters.map(c => (
              <option key={c.id} value={c.id}>
                {c.id} · {c.name}（{c.jobCount} 岗位 · {c.nameSource === 'llm' ? 'LLM命名' : '规则命名'}）
              </option>
            ))}
          </select>
          <button onClick={() => void generate()} disabled={busy || !clusterId}
            className="flex items-center gap-1.5 px-4 py-2 rounded-lg text-sm font-medium bg-violet-600 text-white hover:bg-violet-700 disabled:opacity-50">
            {busy ? <LoaderCircle className="w-4 h-4 animate-spin" /> : <Sparkles className="w-4 h-4" />}
            生成岗位定义
          </button>
        </div>
        <p className="text-xs text-slate-400 mt-2">
          未配置 LLM Key 时自动降级为启发式拼装（全部来自真实聚类数据，无生成幻觉）；生成结果一律待人工审核。
        </p>
      </div>

      {error && <Banner tone="error" text={error} />}
      {notice && <Banner tone="ok" text={notice} />}

      {/* 定义列表 */}
      {!definitions.length ? (
        <div className="bg-white rounded-xl border border-slate-200 p-10 text-center text-sm text-slate-400">
          尚无岗位定义，选择聚类后点击"生成岗位定义"
        </div>
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          {definitions.map(d => (
            <div key={d.definition_id} className="bg-white rounded-xl border border-slate-200 p-5 space-y-3">
              <div className="flex items-start justify-between">
                <div>
                  <div className="text-xs text-slate-400">
                    #{d.definition_id} · 聚类 {d.cluster_id} · {d.generation_source === 'llm' ? 'LLM 生成' : '启发式'}
                  </div>
                  <h3 className="text-base font-bold text-slate-800">{d.job_name}</h3>
                </div>
                <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${
                  d.review_status === 'approved' ? 'bg-emerald-50 text-emerald-700'
                    : d.review_status === 'rejected' ? 'bg-red-50 text-red-700'
                    : 'bg-amber-50 text-amber-700'
                }`}>
                  {d.review_status === 'approved' ? '已批准' : d.review_status === 'rejected' ? '已拒绝' : '待审核'}
                </span>
              </div>
              <DefField label="核心职责" value={d.core_duties} />
              <div>
                <div className="text-xs font-medium text-slate-500 mb-1">必备技能</div>
                <div className="flex flex-wrap gap-1.5">
                  {d.required_skills.map(s => (
                    <span key={s} className="px-2 py-0.5 rounded bg-blue-50 text-blue-700 text-xs">{s}</span>
                  ))}
                </div>
              </div>
              {d.bonus_skills.length > 0 && (
                <div>
                  <div className="text-xs font-medium text-slate-500 mb-1">加分技能</div>
                  <div className="flex flex-wrap gap-1.5">
                    {d.bonus_skills.map(s => (
                      <span key={s} className="px-2 py-0.5 rounded bg-violet-50 text-violet-700 text-xs">{s}</span>
                    ))}
                  </div>
                </div>
              )}
              <DefField label="应用场景" value={d.industry_scenarios} />
              {d.review_status === 'pending' && (
                <div className="flex gap-2 pt-1">
                  <button onClick={() => void decide(d, 'approve')}
                    className="flex items-center gap-1 px-3 py-1.5 rounded-lg text-xs font-medium bg-emerald-600 text-white hover:bg-emerald-700">
                    <CheckCircle2 className="w-3.5 h-3.5" /> 批准
                  </button>
                  <button onClick={() => void decide(d, 'reject')}
                    className="flex items-center gap-1 px-3 py-1.5 rounded-lg text-xs font-medium border border-red-300 text-red-600 hover:bg-red-50">
                    <XCircle className="w-3.5 h-3.5" /> 拒绝
                  </button>
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function DefField({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div className="text-xs font-medium text-slate-500 mb-0.5">{label}</div>
      <div className="text-sm text-slate-700 leading-relaxed">{value || '—'}</div>
    </div>
  );
}

/* ------------------------- ② 能力动态更新 ------------------------- */

function UpdatePanel() {
  const [keyword, setKeyword] = useState('');
  const [candidates, setCandidates] = useState<JobBrief[]>([]);
  const [job, setJob] = useState<JobBrief | null>(null);
  const [detail, setDetail] = useState<JobDetail | null>(null);
  const [jdText, setJdText] = useState('');
  const [baseSnap, setBaseSnap] = useState<number | null>(null);
  const [diff, setDiff] = useState<EvolutionDiff | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const t = setTimeout(() => {
      searchJobs(keyword).then(setCandidates).catch(e => setError((e as Error).message));
    }, 300);
    return () => clearTimeout(t);
  }, [keyword]);

  const selectJob = async (j: JobBrief) => {
    setJob(j); setBaseSnap(null); setDiff(null); setDetail(null); setError(null);
    try {
      const res = await fetch(`${API_BASE}/api/jobs/${encodeURIComponent(j.job_id)}`);
      const data = await res.json();
      const d = { jd_text: data.job?.jd_text || '', skill_count: data.skills?.length || 0 };
      setDetail(d);
      setJdText(d.jd_text);
    } catch (e) { setError((e as Error).message); }
  };

  const snapshot = async () => {
    if (!job) return;
    setBusy('snap'); setError(null);
    try {
      const s = await takeSnapshot(job.job_id, '更新前');
      setBaseSnap(s.snapshotId);
    } catch (e) { setError((e as Error).message); }
    finally { setBusy(null); }
  };

  const runUpdate = async () => {
    if (!job || baseSnap === null) return;
    setBusy('update'); setError(null); setDiff(null);
    try {
      await refreshJobSkills(job.job_id, jdText);
      const s2 = await takeSnapshot(job.job_id, '更新后');
      const d = await fetchEvolutionDiff(baseSnap, s2.snapshotId);
      setDiff(d);
      setBaseSnap(s2.snapshotId); // 差分基线前移，可连续追踪
    } catch (e) { setError((e as Error).message); }
    finally { setBusy(null); }
  };

  return (
    <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
      {/* 左：选岗位 + 编辑 JD */}
      <div className="space-y-4">
        <div className="bg-white rounded-xl border border-slate-200 p-5 space-y-3">
          <div className="text-sm font-semibold text-slate-700">1. 选择既有岗位</div>
          <input value={keyword} onChange={e => setKeyword(e.target.value)}
            placeholder="搜索岗位标题 / 公司…"
            className="w-full px-3 py-2 text-sm rounded-lg border border-slate-300 focus:outline-none focus:border-violet-500" />
          <div className="max-h-44 overflow-y-auto rounded-lg border border-slate-200 divide-y divide-slate-100">
            {candidates.slice(0, 30).map(j => (
              <button key={j.job_id} onClick={() => void selectJob(j)}
                className={`w-full text-left px-3 py-2 text-sm hover:bg-slate-50 ${
                  job?.job_id === j.job_id ? 'bg-violet-50/70' : ''}`}>
                <span className="text-slate-700">{(j.title || '').split('\n')[0]}</span>
                <span className="text-slate-400 text-xs ml-2">{j.company}</span>
              </button>
            ))}
          </div>
        </div>

        {job && (
          <div className="bg-white rounded-xl border border-slate-200 p-5 space-y-3">
            <div className="flex items-center justify-between">
              <div className="text-sm font-semibold text-slate-700">2. 更新 JD 并重提取</div>
              {detail && <span className="text-xs text-slate-400">当前技能 {detail.skill_count} 项</span>}
            </div>
            <div className="flex gap-2">
              <button onClick={() => void snapshot()} disabled={busy !== null || baseSnap !== null}
                className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium border border-slate-300 text-slate-600 hover:bg-slate-50 disabled:opacity-50">
                {busy === 'snap' ? <LoaderCircle className="w-3.5 h-3.5 animate-spin" /> : <Camera className="w-3.5 h-3.5" />}
                {baseSnap !== null ? `已拍快照 #${baseSnap}` : '拍"更新前"快照'}
              </button>
            </div>
            <textarea value={jdText} onChange={e => setJdText(e.target.value)} rows={9}
              placeholder="粘贴更新后的 JD 文本（如新增任职要求），再执行重提取"
              className="w-full px-3 py-2 text-xs rounded-lg border border-slate-300 focus:outline-none focus:border-violet-500 font-mono" />
            <button onClick={() => void runUpdate()}
              disabled={busy !== null || baseSnap === null}
              className="flex items-center gap-1.5 px-4 py-2 rounded-lg text-sm font-medium bg-violet-600 text-white hover:bg-violet-700 disabled:opacity-50">
              {busy === 'update' ? <LoaderCircle className="w-4 h-4 animate-spin" /> : <RefreshCw className="w-4 h-4" />}
              重提取 + 拍"更新后"快照 + 差分
            </button>
          </div>
        )}
        {error && <Banner tone="error" text={error} />}
      </div>

      {/* 右：差分结果 */}
      <div className="bg-white rounded-xl border border-slate-200 p-5">
        <div className="text-sm font-semibold text-slate-700 mb-3 flex items-center gap-1.5">
          <FileText className="w-4 h-4 text-violet-500" /> 快照差分结果
        </div>
        {!diff ? (
          <div className="min-h-[280px] flex flex-col items-center justify-center text-slate-400 text-sm">
            <GitBranch className="w-8 h-8 mb-2" />
            完成左侧"快照 → 更新 → 差分"流程后展示标注
          </div>
        ) : (
          <div className="space-y-4">
            <div className="px-3 py-2.5 rounded-lg bg-violet-50 text-violet-800 text-sm leading-relaxed">
              <AlertCircle className="w-4 h-4 inline mr-1.5 -mt-0.5" />
              {diff.updateNote}
            </div>
            <DiffGroup icon={Plus} label="新增能力" items={diff.added}
              chip="bg-emerald-50 text-emerald-700" empty="无新增" />
            <DiffGroup icon={Minus} label="移除能力" items={diff.removed}
              chip="bg-red-50 text-red-700" empty="无移除" />
            <DiffGroup icon={Pencil} label="置信度/证据更新" items={diff.modified}
              chip="bg-blue-50 text-blue-700" empty="无修改" />
            <div className="text-xs text-slate-400 pt-2 border-t border-slate-100">
              快照 #{diff.baseSnapshot} → #{diff.newSnapshot}，差分已写入 snapshot_diffs 表留痕
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

function DiffGroup({ icon: Icon, label, items, chip, empty }: {
  icon: React.ComponentType<{ className?: string }>;
  label: string; items: string[]; chip: string; empty: string;
}) {
  return (
    <div>
      <div className="text-xs font-medium text-slate-500 mb-1.5 flex items-center gap-1">
        <Icon className="w-3.5 h-3.5" /> {label}（{items.length}）
      </div>
      {items.length ? (
        <div className="flex flex-wrap gap-1.5">
          {items.map(s => (
            <span key={s} className={`px-2 py-0.5 rounded text-xs ${chip}`}>{s}</span>
          ))}
        </div>
      ) : (
        <div className="text-xs text-slate-400">{empty}</div>
      )}
    </div>
  );
}

function Banner({ tone, text }: { tone: 'ok' | 'error'; text: string }) {
  return (
    <div className={`flex items-center gap-2 px-4 py-2.5 rounded-lg text-sm ${
      tone === 'ok' ? 'bg-emerald-50 text-emerald-700' : 'bg-red-50 text-red-700'
    }`}>
      {tone === 'ok' ? <CheckCircle2 className="w-4 h-4" /> : <AlertCircle className="w-4 h-4" />}
      {text}
    </div>
  );
}
