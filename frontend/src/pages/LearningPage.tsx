import { ArrowLeft, ArrowRight, Check, Circle, Clock3, PlayCircle, Target } from 'lucide-react'
import { useState } from 'react'
import type { LearningPath, MatchResult, ProfileSummary } from '../api/talent'
import { Panel, ScoreBar, StatusTag } from '../components/ui'
import type { PageId } from '../types'

export function LearningPage({ profile, result, path, onNavigate, notify }: { profile: ProfileSummary; result: MatchResult | null; path: LearningPath | null; onNavigate: (page: PageId) => void; notify: (message: string) => void }) {
  const [completed, setCompleted] = useState<number[]>([])
  const [selected, setSelected] = useState(1)
  if (!result || !path) return <div className="match-select-hint"><Target size={22} /><strong>还没有绑定差距的发展路径</strong><span>请先选择一条匹配结果，再由其差距生成路径。</span><button className="primary-button" onClick={() => onNavigate('match')}>返回匹配分析</button></div>
  const item = path.steps.find((step) => step.step_no === selected) ?? path.steps[0]
  const totalWeeks = path.steps.reduce((total, step) => total + step.estimated_weeks, 0)
  const toggle = (stepNo: number) => { setCompleted((items) => items.includes(stepNo) ? items.filter((value) => value !== stepNo) : [...items, stepNo]); notify('本地进度已更新；只有提交可验证产出后才会形成新画像证据') }
  return (
    <div className="page-stack">
      <div className="page-intro"><div><h2>能力发展路径</h2><p>{profile.display_name} · 画像 v{profile.version_no} → {result.job_title} · 路径 {path.path_code}</p></div><button className="secondary-button" onClick={() => onNavigate('match')}><ArrowLeft size={15} />返回差距分析</button></div>
      <section className="learning-progress"><div><Target size={22} /><div><strong>差距驱动的 P0 路径</strong><span>{path.summary}</span></div></div><ScoreBar value={path.steps.length ? completed.length / path.steps.length * 100 : 0} /><b>{completed.length} / {path.steps.length} 步完成</b></section>
      <div className="learning-layout">
        <Panel title={`${totalWeeks} 周路线图`} subtitle={`算法 ${path.algorithm_version} · 每步绑定 gap ID`} className="roadmap-panel"><div className="roadmap">{path.steps.map((step, index) => <button className={`${selected === step.step_no ? 'selected' : ''} ${completed.includes(step.step_no) ? 'completed' : ''}`} key={step.step_no} onClick={() => setSelected(step.step_no)}><i>{completed.includes(step.step_no) ? <Check size={15} /> : step.step_no}</i><div><span>预计 {step.estimated_weeks} 周</span><strong>{step.technology_name}</strong><small>{step.gap_type_code} · {step.evidence_reference}</small></div>{index < path.steps.length - 1 ? <ArrowRight className="roadmap-arrow" size={18} /> : null}</button>)}</div></Panel>
        {item ? <Panel title={item.technology_name} subtitle={`步骤 ${item.step_no} · 前置步骤 ${item.depends_on.join('、') || '无'}`} className="learning-detail"><StatusTag tone={completed.includes(item.step_no) ? 'success' : 'info'}>{completed.includes(item.step_no) ? '本地标记已完成' : '当前步骤'}</StatusTag><h3>学习重点</h3><p>{item.learning_focus}</p><h3>具身智能实践任务</h3><p>{item.practice_task}</p><h3>验证标准</h3><ul className="output-list"><li>{completed.includes(item.step_no) ? <Check size={16} /> : <Circle size={14} />}<span>{item.verification}</span></li><li><Circle size={14} /><span>完成后回到画像库，以“用户提供”来源提交证据并重新匹配</span></li></ul><div className="duration-note"><Clock3 size={16} />预计 {item.estimated_weeks} 周；完成状态本身不会自动提高匹配分。</div><button className="primary-button full" onClick={() => toggle(item.step_no)}>{completed.includes(item.step_no) ? '取消完成标记' : '标记该步骤完成'}</button></Panel> : null}
      </div>
      <Panel title="证据回流边界" subtitle="发展路径是行动建议，不是候选人已经掌握能力的证明"><div className="feedback-flow"><div><PlayCircle size={20} /><strong>完成实践任务</strong></div><ArrowRight size={18} /><div><Check size={20} /><strong>提交代码与指标</strong></div><ArrowRight size={18} /><div><Target size={20} /><strong>生成新画像版本并重算</strong></div></div></Panel>
    </div>
  )
}
