import {
  ArrowLeft, ArrowRight, BriefcaseBusiness, Building2, CalendarDays,
  CheckCircle2, ChevronRight, Database, FileSearch, FileText, GraduationCap,
  GitBranch, Info, Layers3, MapPin, Route, ShieldCheck, WalletCards, X,
} from 'lucide-react'
import { useEffect, useMemo, useState, type CSSProperties } from 'react'
import {
  talentApi, type LearningPath, type MatchExplanation, type MatchResult,
  type MatchRun, type ProfileSummary, type RequiredCapabilityGraph,
} from '../api/talent'
import { Panel, ScoreBar, StatusTag } from '../components/ui'
import type { PageId } from '../types'

interface MatchPageProps {
  profile: ProfileSummary
  onPathGenerated: (result: MatchResult, path: LearningPath) => void
  onNavigate: (page: PageId) => void
  notify: (message: string) => void
}

const gapLabels: Record<string, string> = {
  evidence_insufficient: '证据不足', transferable: '可迁移',
  depth_insufficient: '掌握深度不足', confirmed_missing: '已确认缺失',
  low_confidence_requirement: '岗位要求低置信',
}
const formatDate = (value: string | null) => value ? value.slice(0, 10) : '未注明'
const graphStatusLabels: Record<string, { label: string; tone: 'success' | 'warning' | 'info' | 'danger' | 'neutral' }> = {
  covered: { label: '已有证据', tone: 'success' },
  partial_evidence: { label: '证据待加强', tone: 'info' },
  evidence_insufficient: { label: '证据不足', tone: 'warning' },
  depth_insufficient: { label: '深度不足', tone: 'warning' },
  transferable: { label: '相邻能力可迁移', tone: 'info' },
  confirmed_missing: { label: '已确认缺失', tone: 'danger' },
}

function RequiredCapabilityTree({ graph, onClose, onOpenGraph }: { graph: RequiredCapabilityGraph; onClose: () => void; onOpenGraph: () => void }) {
  return (
    <section className="required-capability-tree" aria-label="必需能力与技能树关联">
      <header><div><GitBranch size={18} /><div><strong>必需能力技术树</strong><span>查看岗位要求在技能树中的位置与个人证据覆盖情况</span></div></div><div className="required-tree-actions"><button type="button" onClick={onOpenGraph}>查看完整关联图<ChevronRight size={14} /></button><button type="button" className="required-tree-close" onClick={onClose} aria-label="关闭技术树详情"><X size={17} /></button></div></header>
      <div className="required-tree-summary"><span>必需能力 <strong>{graph.total_count}</strong></span><span>已有证据 <strong>{graph.covered_count}</strong></span><span>待补证 <strong>{graph.unresolved_count}</strong></span><span>确认缺失 <strong>{graph.confirmed_missing_count}</strong></span></div>
      {graph.items.length ? <div className="required-tree-list">{graph.items.map((item) => {
        const status = graphStatusLabels[item.coverage_status] ?? { label: item.coverage_status, tone: 'neutral' as const }
        return <article key={item.technology_node_id} style={{ '--skill-domain-color': item.domain?.color || '#2f78bd' } as CSSProperties}>
          <div className="required-tree-skill"><i /><div><strong>{item.technology_name}</strong><span>{item.technology_code}{item.domain?.name ? ` · ${item.domain.name}` : ''}</span></div><StatusTag tone={status.tone}>{status.label}</StatusTag></div>
          <div className="required-tree-path" aria-label={`${item.technology_name} 技能树路径`}>{item.path.map((node, index) => <span key={node.technology_node_id}><b>{node.level_code}</b>{node.technology_name}{index < item.path.length - 1 ? <ChevronRight size={12} /> : null}</span>)}</div>
          <footer><span>{item.hard ? '硬性必需' : '组合要求'} · 规则 {item.operator}</span><span>岗位证据 {item.job_evidence.length} 条 · 个人证据 {item.candidate_evidence.length} 条</span></footer>
        </article>
      })}</div> : <div className="required-tree-empty">该岗位尚未形成可关联到技能树节点的明确必需能力。</div>}
      <p>评分仍由原十维固定公式计算；这里仅展示“必需能力覆盖”使用了哪些图谱节点及其层级关系。</p>
    </section>
  )
}

export function MatchPage({ profile, onPathGenerated, onNavigate, notify }: MatchPageProps) {
  const [run, setRun] = useState<MatchRun | null>(null)
  const [selectedCode, setSelectedCode] = useState('')
  const [loading, setLoading] = useState(true)
  const [pathLoading, setPathLoading] = useState(false)
  const [error, setError] = useState('')
  const [explanation, setExplanation] = useState<MatchExplanation | null>(null)
  const [expandedDimension, setExpandedDimension] = useState<string | null>(null)

  useEffect(() => {
    setLoading(true); setError(''); setRun(null); setSelectedCode('')
    talentApi.matches(profile.version_code)
      .then((next) => { setRun(next); setSelectedCode(next.results[0]?.result_code ?? '') })
      .catch((reason: Error) => setError(reason.message))
      .finally(() => setLoading(false))
  }, [profile.version_code])
  const selected = useMemo(
    () => run?.results.find((item) => item.result_code === selectedCode),
    [run, selectedCode],
  )

  useEffect(() => {
    setExpandedDimension(null)
    if (!selectedCode) { setExplanation(null); return }
    const controller = new AbortController()
    setExplanation(null)
    talentApi.explanation(selectedCode, controller.signal).then(setExplanation)
      .catch((reason: Error) => { if (reason.name !== 'AbortError') setExplanation(null) })
    return () => controller.abort()
  }, [selectedCode])

  useEffect(() => {
    if (!expandedDimension) return
    const previousOverflow = document.body.style.overflow
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setExpandedDimension(null)
    }
    document.body.style.overflow = 'hidden'
    window.addEventListener('keydown', closeOnEscape)
    return () => {
      document.body.style.overflow = previousOverflow
      window.removeEventListener('keydown', closeOnEscape)
    }
  }, [expandedDimension])

  const generatePath = async () => {
    if (!selected) return
    setPathLoading(true); setError('')
    try {
      const path = await talentApi.learningPath(selected.result_code)
      onPathGenerated(selected, path)
      notify(`已由 ${path.steps.length} 项可追溯差距生成发展路径`)
      onNavigate('learning')
    } catch (reason) { setError((reason as Error).message) }
    finally { setPathLoading(false) }
  }

  if (loading) return <div className="match-select-hint"><BriefcaseBusiness size={22} /><strong>正在从岗位数据库的全部有效岗位中计算匹配</strong><span>解析简历 → 解析岗位 JD → 十维确定性评分，大模型不参与打分。</span></div>
  if (error && !run) return <div className="match-select-hint"><Info size={22} /><strong>匹配运行失败</strong><span>{error}</span><button className="secondary-button" onClick={() => onNavigate('resume')}>返回画像库</button></div>

  return (
    <div className="page-stack match-page">
      <div className="page-intro"><div><h2>岗位匹配结果</h2><p>只保留三步主链路，所有分数均由本地确定性规则计算。</p></div><button className="secondary-button" onClick={() => onNavigate('resume')}><ArrowLeft size={15} />切换画像</button></div>
      <section className="simple-match-pipeline" aria-label="三步匹配流程">
        <div><FileSearch size={20} /><span>1</span><strong>解析简历</strong><small>提取事实与证据</small></div><ArrowRight size={18} />
        <div><FileText size={20} /><span>2</span><strong>解析岗位 JD</strong><small>提取要求与条件</small></div><ArrowRight size={18} />
        <div><ShieldCheck size={20} /><span>3</span><strong>规则匹配</strong><small>十维机械评分</small></div>
        <StatusTag tone="success">大模型不参与评分</StatusTag>
      </section>
      {error ? <p className="form-error">{error}</p> : null}
      <section className="match-profile-source"><div className="avatar">{profile.display_name.slice(0, 1)}</div><div><strong>{profile.display_name} · 求职者画像 v{profile.version_no}</strong><span>{profile.target_role_text || '目标待确认'} · {profile.skill_count} 项技术证据</span></div><StatusTag tone="success">已确认版本</StatusTag></section>

      <Panel title="具体岗位结果" subtitle={`从岗位数据库 ${run?.candidate_count ?? 0} 条有效岗位中召回并重排`} action={<span className="panel-action-note">返回 {run?.result_count ?? 0} 条</span>}>
        <div className="job-match-grid">{run?.results.map((job) => <button className={selectedCode === job.result_code ? 'selected' : ''} key={job.result_code} onClick={() => setSelectedCode(job.result_code)}><div className="job-card-top"><StatusTag tone={job.overall_score >= 60 ? 'success' : 'info'}>{job.overall_score}% 匹配</StatusTag><ChevronRight size={17} /></div><h3>{job.job_title}</h3><div className="job-card-meta"><span><Building2 size={13} />{job.job_detail?.company || '企业信息未公开'}</span><span><MapPin size={13} />{job.job_detail?.region || '地点未注明'}</span><span><WalletCards size={13} />{job.job_detail?.salary_text || '薪资未注明'}</span></div><div className="job-card-evidence"><strong>推荐依据</strong>{job.recommendation.reasons.slice(0, 2).map((reason) => <span key={reason}><CheckCircle2 size={13} />{reason}</span>)}</div></button>)}</div>
      </Panel>

      {selected ? <section className="match-detail-anchor">
        <section className="match-hero"><div className="compare-person"><div className="avatar">{profile.display_name.slice(0, 1)}</div><div><strong>{profile.display_name}</strong><span>画像 v{profile.version_no}</span></div></div><ArrowRight size={20} /><div className="compare-role"><div className="role-icon">岗</div><div><strong>{selected.job_title}</strong><span>{selected.job_detail?.company || '企业信息未公开'}</span></div></div><div className="match-score"><span>综合匹配度 <Info size={13} /></span><div><strong>{selected.overall_score}%</strong><StatusTag tone="info">置信度 {selected.confidence_score}%</StatusTag></div><ScoreBar value={selected.overall_score} /></div></section>
        <div className="match-actions"><button className="primary-button" onClick={generatePath} disabled={pathLoading}><Route size={16} />{pathLoading ? '正在生成路径' : '由差距生成发展路径'}</button></div>
        <div className="match-layout simplified-match-layout">
          <Panel title="十维评分" subtitle="点击“必需能力覆盖”可查看图谱技能树关联" className="dimension-panel"><div className="dimension-list">{selected.dimensions.map((dimension) => dimension.code === 'required_capability_fit' ? <button type="button" className={`dimension-graph-trigger ${expandedDimension === dimension.code ? 'expanded' : ''}`} key={dimension.code} onClick={() => setExpandedDimension((current) => current === dimension.code ? null : dimension.code)} aria-expanded={expandedDimension === dimension.code}><span>{dimension.label} · 权重 {Math.round(dimension.weight * 100)}%</span><div className="score-track"><i className={`score-fill score-fill--${dimension.score < 50 ? 'amber' : 'teal'}`} style={{ width: `${dimension.score}%` }} /></div><strong>{dimension.score}%</strong><em><GitBranch size={13} />查看技术树</em></button> : <ScoreBar key={dimension.code} label={`${dimension.label} · 权重 ${Math.round(dimension.weight * 100)}%`} value={dimension.score} tone={dimension.score < 50 ? 'amber' : 'teal'} />)}</div><p className="mechanical-score-note"><ShieldCheck size={15} />大模型仅可辅助抽取原文事实，不能生成、修改或校准分数。</p></Panel>
          <Panel title="岗位详细信息" subtitle={`岗位编号 ${selected.job_detail?.job_code || '未指定'}`}>
            <div className="job-detail-grid"><div><Building2 size={16} /><span>公司</span><strong>{selected.job_detail?.company || '未注明'}</strong></div><div><MapPin size={16} /><span>地点</span><strong>{selected.job_detail?.region || '未注明'}</strong></div><div><WalletCards size={16} /><span>薪资</span><strong>{selected.job_detail?.salary_text || '未注明'}</strong></div><div><GraduationCap size={16} /><span>学历</span><strong>{selected.job_detail?.education_text || '未注明'}</strong></div><div><Layers3 size={16} /><span>经验/级别</span><strong>{selected.job_detail?.experience_text || selected.job_detail?.job_level || '未注明'}</strong></div><div><BriefcaseBusiness size={16} /><span>用工类型</span><strong>{selected.job_detail?.employment_type || '未注明'}</strong></div><div><CalendarDays size={16} /><span>发布时间</span><strong>{formatDate(selected.job_detail?.published_at || null)}</strong></div><div><Database size={16} /><span>来源岗位编号</span><strong>{selected.job_detail?.source_job_id || selected.job_detail?.job_code || '未注明'}</strong></div><div><ShieldCheck size={16} /><span>数据状态</span><strong>{selected.job_detail?.posting_status === 'active' ? '有效岗位' : selected.job_detail?.posting_status || '未注明'}</strong></div></div>
            <div className="job-jd-content"><div><FileText size={17} /><strong>完整岗位 JD</strong></div><p>{selected.job_detail?.jd_text || '岗位原文暂未提供。'}</p></div>
          </Panel>
          <Panel title="关键差距" subtitle="简历未写明只表示证据不足"><div className="match-table"><div className="match-table-head"><span>能力项</span><span>证据解释</span><span>分类</span></div>{selected.gaps.map((gap) => <button key={gap.gap_id}><div><strong>{gap.technology_name}</strong><StatusTag tone="neutral">重要性 {gap.importance_score}</StatusTag></div><p>{gap.explanation}<small>岗位证据 {gap.job_evidence.length} 条 · 个人证据 {gap.candidate_evidence.length} 条</small></p><div><StatusTag tone={gap.gap_type_code === 'transferable' ? 'info' : 'warning'}>{gapLabels[gap.gap_type_code] || gap.gap_type_code}</StatusTag></div></button>)}</div></Panel>
          <Panel title="结果说明" subtitle="数据来源与解释边界" className="gap-panel"><div className="gap-list"><button className="transfer"><Database size={16} /><strong>来自岗位数据库</strong><p>候选范围为全部有效岗位，当前共 {run?.candidate_count ?? 0} 条。</p></button>{explanation ? <button><StatusTag tone={explanation.generation_method === 'llm_explanation' ? 'info' : 'neutral'}>{explanation.generation_method === 'llm_explanation' ? '文字解释' : '规则解释'}</StatusTag><strong>匹配解读</strong><p>{explanation.explanation_text}</p></button> : null}<button><StatusTag tone="warning">证据边界</StatusTag><strong>未写入不等于不会</strong><p>{selected.recommendation.warning}</p></button></div></Panel>
        </div>
      </section> : <div className="match-select-hint"><BriefcaseBusiness size={22} /><strong>当前没有可展示的岗位匹配</strong><span>请补充技术证据或检查岗位数据库。</span></div>}
      {selected && expandedDimension === 'required_capability_fit' ? <div className="capability-tree-backdrop" onMouseDown={(event) => { if (event.target === event.currentTarget) setExpandedDimension(null) }}><aside className="capability-tree-drawer" role="dialog" aria-modal="true" aria-label="必需能力技术树详情"><RequiredCapabilityTree graph={selected.required_capability_graph} onClose={() => setExpandedDimension(null)} onOpenGraph={() => onNavigate('graph-relations')} /></aside></div> : null}
    </div>
  )
}
