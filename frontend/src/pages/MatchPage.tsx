import { ArrowLeft, ArrowRight, BriefcaseBusiness, Building2, CheckCircle2, ChevronRight, Info, Layers3, MapPin, Route } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { talentApi, type LearningPath, type MatchExplanation, type MatchResult, type MatchRun, type ProfileSummary } from '../api/talent'
import { Panel, ScoreBar, StatusTag } from '../components/ui'
import type { PageId } from '../types'

interface MatchPageProps {
  profile: ProfileSummary
  onPathGenerated: (result: MatchResult, path: LearningPath) => void
  onNavigate: (page: PageId) => void
  notify: (message: string) => void
}

const gapLabels: Record<string, string> = { evidence_insufficient: '证据不足', transferable: '可迁移', depth_insufficient: '掌握深度不足', confirmed_missing: '已确认缺失', low_confidence_requirement: '岗位要求低置信' }

export function MatchPage({ profile, onPathGenerated, onNavigate, notify }: MatchPageProps) {
  const [run, setRun] = useState<MatchRun | null>(null)
  const [selectedCode, setSelectedCode] = useState('')
  const [loading, setLoading] = useState(true)
  const [pathLoading, setPathLoading] = useState(false)
  const [error, setError] = useState('')
  const [explanation, setExplanation] = useState<MatchExplanation | null>(null)

  useEffect(() => {
    setLoading(true); setError(''); setRun(null); setSelectedCode('')
    talentApi.matches(profile.version_code).then((next) => { setRun(next); setSelectedCode(next.results[0]?.result_code ?? '') }).catch((reason: Error) => setError(reason.message)).finally(() => setLoading(false))
  }, [profile.version_code])
  const selected = useMemo(() => run?.results.find((item) => item.result_code === selectedCode), [run, selectedCode])

  useEffect(() => {
    if (!selectedCode) { setExplanation(null); return }
    const controller = new AbortController()
    setExplanation(null)
    talentApi.explanation(selectedCode, controller.signal)
      .then(setExplanation)
      .catch((reason: Error) => { if (reason.name !== 'AbortError') setExplanation(null) })
    return () => controller.abort()
  }, [selectedCode])

  const generatePath = async () => {
    if (!selected) return
    setPathLoading(true); setError('')
    try { const path = await talentApi.learningPath(selected.result_code); onPathGenerated(selected, path); notify(`已由 ${path.steps.length} 项可追溯差距生成发展路径`); onNavigate('learning') } catch (reason) { setError((reason as Error).message) } finally { setPathLoading(false) }
  }

  if (loading) return <div className="match-select-hint"><BriefcaseBusiness size={22} /><strong>正在基于真实岗位聚类计算匹配</strong><span>总分由确定性维度贡献组成，LLM Provider 不参与 P0 打分。</span></div>
  if (error && !run) return <div className="match-select-hint"><Info size={22} /><strong>匹配运行失败</strong><span>{error}</span><button className="secondary-button" onClick={() => onNavigate('resume')}>返回画像库</button></div>

  return (
    <div className="page-stack match-page">
      <div className="page-intro"><div><h2>岗位匹配结果</h2><p>结果绑定 {profile.display_name} · 画像 v{profile.version_no} 和最新成功岗位聚类快照，可重复回放。</p></div><button className="secondary-button" onClick={() => onNavigate('resume')}><ArrowLeft size={15} />切换画像</button></div>
      {error ? <p className="form-error">{error}</p> : null}
      <section className="match-profile-source"><div className="avatar">{profile.display_name.slice(0, 1)}</div><div><strong>{profile.display_name} · 求职者画像 v{profile.version_no}</strong><span>{profile.target_role_text || '目标待确认'} · {profile.skill_count} 项技术证据</span></div><StatusTag tone="success">已确认版本</StatusTag></section>
      <Panel title="匹配结果" subtitle={`运行 ${run?.run_code ?? ''} · 算法 ${run?.algorithm_version ?? ''}`} action={<span className="panel-action-note">{run?.result_count ?? 0} 条真实结果</span>}>
        <div className="job-match-grid">{run?.results.map((job) => <button className={selectedCode === job.result_code ? 'selected' : ''} key={job.result_code} onClick={() => setSelectedCode(job.result_code)}><div className="job-card-top"><StatusTag tone={job.overall_score >= 60 ? 'success' : 'info'}>{job.overall_score}% 匹配</StatusTag><ChevronRight size={17} /></div><h3>{job.job_title}</h3><div className="job-card-meta"><span><Building2 size={13} />{job.representative_jd.company || '企业信息未公开'}</span><span><MapPin size={13} />{job.representative_jd.region || '地点未注明'}</span><span><Layers3 size={13} />{job.representative_jd.job_level || '级别未注明'}</span></div><div className="job-card-evidence"><strong>推荐依据</strong>{job.recommendation.reasons.map((reason) => <span key={reason}><CheckCircle2 size={13} />{reason}</span>)}</div><div className="job-card-gaps"><strong>主要差距</strong><span>{job.gaps.slice(0, 3).map((gap) => gap.technology_name).join('、') || '暂无关键差距'}</span></div></button>)}</div>
      </Panel>
      {selected ? <section className="match-detail-anchor"><div className="match-detail-title"><div><BriefcaseBusiness size={20} /><div><strong>{selected.job_title}</strong><span>岗位聚类 {selected.cluster_code} · 代表 JD {selected.representative_jd.job_code || '未指定'}</span></div></div></div><section className="match-hero"><div className="compare-person"><div className="avatar">{profile.display_name.slice(0, 1)}</div><div><strong>{profile.display_name} · 画像 v{profile.version_no}</strong><span>{profile.workflow_status_code}</span></div></div><ArrowRight size={20} /><div className="compare-role"><div className="role-icon">岗</div><div><strong>{selected.job_title}</strong><span>{selected.representative_jd.company || '岗位聚类'}</span></div></div><div className="match-score"><span>综合匹配度 <Info size={13} /></span><div><strong>{selected.overall_score}%</strong><StatusTag tone="info">置信度 {selected.confidence_score}%</StatusTag></div><ScoreBar value={selected.overall_score} /></div></section><div className="match-actions"><button className="primary-button" onClick={generatePath} disabled={pathLoading}><Route size={16} />{pathLoading ? '正在生成路径' : '由差距生成发展路径'}</button></div><div className="match-layout"><Panel title="维度得分" subtitle="确定性规则、权重和贡献可复核" className="dimension-panel"><div className="dimension-list">{selected.dimensions.map((dimension) => <ScoreBar key={dimension.code} label={`${dimension.label} · 权重 ${Math.round(dimension.weight * 100)}%`} value={dimension.score} tone={dimension.score < 50 ? 'amber' : 'teal'} />)}</div></Panel><Panel title="差距与双方证据" subtitle="缺少简历证据不会被标记为不会"><div className="match-table"><div className="match-table-head"><span>能力项</span><span>证据解释</span><span>分类</span></div>{selected.gaps.map((gap) => <button key={gap.gap_id}><div><strong>{gap.technology_name}</strong><StatusTag tone="neutral">重要性 {gap.importance_score}</StatusTag></div><p>{gap.explanation}<small>岗位证据 {gap.job_evidence.length} 条 · 个人证据 {gap.candidate_evidence.length} 条</small></p><div><StatusTag tone={gap.gap_type_code === 'transferable' ? 'info' : 'warning'}>{gapLabels[gap.gap_type_code] || gap.gap_type_code}</StatusTag></div></button>)}</div></Panel><Panel title="解释边界" subtitle="P0 不使用敏感属性或人格推断" className="gap-panel"><div className="gap-list">{explanation ? <button><StatusTag tone={explanation.generation_method === 'llm_explanation' ? 'info' : 'neutral'}>{explanation.generation_method === 'llm_explanation' ? 'LLM 解释' : '规则解释'}</StatusTag><strong>匹配解读</strong><p>{explanation.explanation_text}<small>生成版本 {explanation.model_version} · 仅组织确定性评分，不改写总分</small></p></button> : null}<button className="transfer"><StatusTag tone="info">可复核</StatusTag><strong>分数不是 LLM 直接生成</strong><p>能力覆盖、可迁移关系、求职目标和证据完整度分别计分并冻结算法版本。</p></button><button><StatusTag tone="warning">证据边界</StatusTag><strong>未写入不等于不会</strong><p>{selected.recommendation.warning}</p></button></div></Panel></div></section> : <div className="match-select-hint"><BriefcaseBusiness size={22} /><strong>当前没有可展示的岗位匹配</strong><span>请补充技术证据或等待岗位聚类数据更新。</span></div>}
    </div>
  )
}
