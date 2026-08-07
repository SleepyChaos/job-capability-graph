'use client';

// 人岗匹配页（阶段 3）：简历上传/粘贴 → 技能提取 → 匹配岗位 → 差距清单
// 数据全部来自统一后端 API（backend/api.py 阶段 3 路由）：
//   POST /api/resumes/upload  GET /api/resumes/{id}/match  GET /api/resumes
import React, { useEffect, useRef, useState } from 'react';
import {
  Upload, Target, CheckCircle2, XCircle, Loader2, AlertTriangle, FileText, Sparkles,
} from 'lucide-react';
import {
  uploadResumeFile, uploadResumeText, matchResume, fetchResumes,
  type UploadResumeResult, type MatchResponse, type MatchResult, type ResumeListItem,
} from '@/lib/api';

const severityConfig = {
  severe: { label: '缺失较多', cls: 'bg-red-50 text-red-700 border-red-200' },
  moderate: { label: '缺失中等', cls: 'bg-amber-50 text-amber-700 border-amber-200' },
  minor: { label: '缺失轻微', cls: 'bg-blue-50 text-blue-700 border-blue-200' },
};

function ScoreBar({ label, value }: { label: string; value: number | null }) {
  if (value === null) return null;
  return (
    <div className="flex items-center gap-2 text-xs text-slate-500">
      <span className="w-16 shrink-0">{label}</span>
      <div className="flex-1 h-1.5 bg-slate-100 rounded-full overflow-hidden">
        <div className="h-full bg-blue-500 rounded-full" style={{ width: `${Math.round(value * 100)}%` }} />
      </div>
      <span className="w-8 text-right tabular-nums">{Math.round(value * 100)}</span>
    </div>
  );
}

function MatchCard({ m, rank }: { m: MatchResult; rank: number }) {
  const sev = severityConfig[m.missing_severity];
  const pct = Math.round(m.score * 100);
  const pctColor = pct >= 70 ? 'text-green-600' : pct >= 45 ? 'text-amber-600' : 'text-red-600';
  return (
    <div className="bg-white border border-slate-200 rounded-xl p-5">
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <span className="text-xs font-medium text-slate-400">TOP {rank}</span>
            <h4 className="font-semibold text-slate-900 truncate">{m.title}</h4>
            <span className={`text-xs px-2 py-0.5 rounded-full border shrink-0 ${sev.cls}`}>{sev.label}</span>
          </div>
          <div className="text-sm text-slate-500 mt-1">
            {m.company}{m.city ? ` · ${m.city}` : ''}{m.salary ? ` · ${m.salary}` : ''}
          </div>
        </div>
        <div className={`text-2xl font-bold tabular-nums shrink-0 ${pctColor}`}>
          {pct}<span className="text-sm font-normal text-slate-400">分</span>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-x-6 gap-y-1.5 mt-3">
        <ScoreBar label="技能画像" value={m.capability_score} />
        <ScoreBar label="方向对口" value={m.l1_score} />
        <ScoreBar label="核心重合" value={m.core_jaccard} />
        <ScoreBar label="头衔相似" value={m.title_score} />
      </div>

      <div className="mt-4 grid grid-cols-1 md:grid-cols-3 gap-3 text-xs">
        <div>
          <div className="font-medium text-green-700 mb-1.5 flex items-center gap-1">
            <CheckCircle2 className="w-3.5 h-3.5" />已具备（{m.shared.length}）
          </div>
          <div className="flex flex-wrap gap-1">
            {m.shared.length
              ? m.shared.slice(0, 6).map(s => (
                <span key={s} className="px-1.5 py-0.5 bg-green-50 text-green-700 rounded border border-green-200">{s}</span>
              ))
              : <span className="text-slate-400">无共同技能</span>}
          </div>
        </div>
        <div>
          <div className="font-medium text-red-700 mb-1.5 flex items-center gap-1">
            <XCircle className="w-3.5 h-3.5" />技能差距（{m.missing.length}）
          </div>
          <div className="flex flex-wrap gap-1">
            {m.missing.length
              ? m.missing.slice(0, 6).map(s => (
                <span key={s} className="px-1.5 py-0.5 bg-red-50 text-red-700 rounded border border-red-200">{s}</span>
              ))
              : <span className="text-slate-400">无缺失</span>}
          </div>
        </div>
        <div>
          <div className="font-medium text-blue-700 mb-1.5 flex items-center gap-1">
            <Sparkles className="w-3.5 h-3.5" />额外优势（{m.extra.length}）
          </div>
          <div className="flex flex-wrap gap-1">
            {m.extra.length
              ? m.extra.slice(0, 6).map(s => (
                <span key={s} className="px-1.5 py-0.5 bg-blue-50 text-blue-700 rounded border border-blue-200">{s}</span>
              ))
              : <span className="text-slate-400">—</span>}
          </div>
        </div>
      </div>
    </div>
  );
}

export default function MatchingPage() {
  const [inputMode, setInputMode] = useState<'upload' | 'paste'>('upload');
  const [pasteText, setPasteText] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [parsed, setParsed] = useState<UploadResumeResult | null>(null);
  const [match, setMatch] = useState<MatchResponse | null>(null);
  const [history, setHistory] = useState<ResumeListItem[]>([]);
  const [selectedResume, setSelectedResume] = useState<string>('');
  const fileRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    fetchResumes(15).then(setHistory).catch(() => {/* 后端不可用时静默 */});
  }, []);

  async function runMatch(resumeId: string) {
    setBusy(true);
    setError('');
    try {
      const result = await matchResume(resumeId, 10);
      setMatch(result);
    } catch (e) {
      setError(e instanceof Error ? e.message : '匹配失败');
    } finally {
      setBusy(false);
    }
  }

  async function handleFile(file: File) {
    setBusy(true);
    setError('');
    setMatch(null);
    try {
      const result = await uploadResumeFile(file);
      setParsed(result);
      await runMatch(result.resume_id);
    } catch (e) {
      setError(e instanceof Error ? e.message : '解析失败');
    } finally {
      setBusy(false);
    }
  }

  async function handlePaste() {
    if (!pasteText.trim()) return;
    setBusy(true);
    setError('');
    setMatch(null);
    try {
      const result = await uploadResumeText(pasteText);
      setParsed(result);
      await runMatch(result.resume_id);
    } catch (e) {
      setError(e instanceof Error ? e.message : '解析失败');
    } finally {
      setBusy(false);
    }
  }

  async function handlePickHistory(id: string) {
    setSelectedResume(id);
    setParsed(null);
    await runMatch(id);
  }

  return (
    <div className="flex-1 p-6 max-w-6xl mx-auto w-full">
      <div className="mb-6">
        <h1 className="text-xl font-bold text-slate-900 flex items-center gap-2">
          <Target className="w-5 h-5 text-blue-600" />人岗匹配诊断
        </h1>
        <p className="text-sm text-slate-500 mt-1">
          上传简历 → 技能提取（统一技能本体）→ 全库岗位混合匹配 → 输出技能差距清单
        </p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* 左栏：输入 */}
        <div className="space-y-4">
          <div className="bg-white border border-slate-200 rounded-xl p-4">
            <div className="flex gap-1 mb-4 bg-slate-100 rounded-lg p-1">
              {(['upload', 'paste'] as const).map(mode => (
                <button
                  key={mode}
                  onClick={() => setInputMode(mode)}
                  className={`flex-1 py-1.5 text-sm rounded-md transition-colors ${
                    inputMode === mode ? 'bg-white shadow-sm text-blue-600 font-medium' : 'text-slate-500'
                  }`}
                >
                  {mode === 'upload' ? '上传文件' : '粘贴文本'}
                </button>
              ))}
            </div>

            {inputMode === 'upload' ? (
              <div
                className="border-2 border-dashed border-slate-200 rounded-lg p-6 text-center hover:border-blue-400 transition-colors cursor-pointer"
                onClick={() => fileRef.current?.click()}
                onDragOver={e => e.preventDefault()}
                onDrop={e => {
                  e.preventDefault();
                  const f = e.dataTransfer.files[0];
                  if (f) handleFile(f);
                }}
              >
                <Upload className="w-8 h-8 text-slate-300 mx-auto mb-2" />
                <p className="text-sm text-slate-600">点击或拖拽上传简历</p>
                <p className="text-xs text-slate-400 mt-1">支持 PDF / TXT（PDF 走 pypdf 文本层解析）</p>
                <input
                  ref={fileRef}
                  type="file"
                  accept=".pdf,.txt,.md"
                  className="hidden"
                  onChange={e => {
                    const f = e.target.files?.[0];
                    if (f) handleFile(f);
                  }}
                />
              </div>
            ) : (
              <div>
                <textarea
                  value={pasteText}
                  onChange={e => setPasteText(e.target.value)}
                  placeholder={'粘贴简历内容，例如：\n张三，求职意向：机器人算法工程师。熟悉 ROS、强化学习、SLAM 导航…'}
                  className="w-full h-40 text-sm border border-slate-200 rounded-lg p-3 resize-none focus:outline-none focus:border-blue-400"
                />
                <button
                  onClick={handlePaste}
                  disabled={busy || !pasteText.trim()}
                  className="mt-2 w-full py-2 bg-blue-600 text-white text-sm rounded-lg hover:bg-blue-700 disabled:opacity-50 flex items-center justify-center gap-2"
                >
                  {busy ? <Loader2 className="w-4 h-4 animate-spin" /> : <FileText className="w-4 h-4" />}
                  解析并匹配
                </button>
              </div>
            )}
            {busy && inputMode === 'upload' && (
              <div className="mt-2 text-xs text-slate-400 flex items-center gap-1">
                <Loader2 className="w-3 h-3 animate-spin" />解析与匹配中…
              </div>
            )}
            {error && (
              <div className="mt-3 text-xs text-red-600 bg-red-50 border border-red-200 rounded-lg p-2 flex items-start gap-1.5">
                <AlertTriangle className="w-3.5 h-3.5 shrink-0 mt-0.5" />{error}
              </div>
            )}
          </div>

          {/* 提取结果 */}
          {parsed && (
            <div className="bg-white border border-slate-200 rounded-xl p-4">
              <div className="text-sm font-semibold text-slate-800 mb-2">
                技能提取结果
                <span className="ml-2 text-xs font-normal text-slate-400">
                  {parsed.skills.length} 项 · {parsed.llmUsed ? '词典+LLM' : '词典正则（LLM 未启用自动降级）'}
                </span>
              </div>
              {(parsed.name || parsed.title) && (
                <div className="text-xs text-slate-500 mb-2">
                  {parsed.name && `候选人：${parsed.name}`}{parsed.title && ` · ${parsed.title}`}
                </div>
              )}
              <div className="flex flex-wrap gap-1.5">
                {parsed.skills.map(s => (
                  <span
                    key={s.skill_term}
                    className={`px-2 py-0.5 text-xs rounded-full border ${
                      s.source === 'llm'
                        ? 'bg-violet-50 text-violet-700 border-violet-200'
                        : 'bg-slate-50 text-slate-700 border-slate-200'
                    }`}
                    title={`来源：${s.source} · 置信度 ${s.confidence} · 域 ${s.l1_code}`}
                  >
                    {s.skill_term}
                  </span>
                ))}
                {parsed.skills.length === 0 && (
                  <span className="text-xs text-slate-400">未提取到本体内技能词</span>
                )}
              </div>
            </div>
          )}

          {/* 历史简历 */}
          <div className="bg-white border border-slate-200 rounded-xl p-4">
            <div className="text-sm font-semibold text-slate-800 mb-2">
              历史简历 <span className="text-xs font-normal text-slate-400">（点击直接匹配）</span>
            </div>
            <div className="space-y-1 max-h-64 overflow-y-auto">
              {history.map(r => (
                <button
                  key={r.resume_id}
                  onClick={() => handlePickHistory(r.resume_id)}
                  className={`w-full text-left px-2 py-1.5 rounded-md text-xs transition-colors ${
                    selectedResume === r.resume_id ? 'bg-blue-50 text-blue-700' : 'hover:bg-slate-50 text-slate-600'
                  }`}
                >
                  <span className="font-medium">{r.name || r.resume_id}</span>
                  <span className="text-slate-400 ml-2">{r.skill_count} 项技能</span>
                </button>
              ))}
              {history.length === 0 && <div className="text-xs text-slate-400">暂无</div>}
            </div>
          </div>
        </div>

        {/* 右栏：匹配结果 */}
        <div className="lg:col-span-2 space-y-4">
          {match && (
            <div className="flex items-center gap-3 text-sm text-slate-500">
              <span>候选岗位 <b className="text-slate-800">{match.candidate_count ?? match.matches.length}</b> 个</span>
              <span>·</span>
              <span>简历技能 <b className="text-slate-800">{match.resume_skill_count}</b> 项</span>
              {!match.semantic_available && (
                <span className="text-xs text-amber-600 bg-amber-50 border border-amber-200 rounded-full px-2 py-0.5">
                  语义模型未启用 · 按能力画像/方向/核心技能混合评分
                </span>
              )}
            </div>
          )}
          {match?.warning && (
            <div className="text-sm text-amber-700 bg-amber-50 border border-amber-200 rounded-lg p-3">
              {match.warning}
            </div>
          )}
          {match?.matches.map((m, i) => <MatchCard key={m.job_id} m={m} rank={i + 1} />)}
          {!match && !busy && (
            <div className="h-64 flex flex-col items-center justify-center text-slate-300 border-2 border-dashed border-slate-200 rounded-xl">
              <Target className="w-10 h-10 mb-2" />
              <p className="text-sm">上传简历或选择历史简历后展示匹配诊断</p>
            </div>
          )}
          {busy && !match && (
            <div className="h-64 flex items-center justify-center text-slate-400 text-sm gap-2">
              <Loader2 className="w-4 h-4 animate-spin" />匹配中…
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
