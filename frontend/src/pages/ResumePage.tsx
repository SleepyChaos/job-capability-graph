import { ArrowRight, Check, Database, FileText, History, Pencil, Plus, ScanText, UserRound, WandSparkles } from 'lucide-react'
import { useEffect, useState, type FormEvent } from 'react'
import { talentApi, type ProfileDetail, type ProfileSummary } from '../api/talent'
import { Modal, Panel, ScoreBar, StatusTag } from '../components/ui'
import type { PageId } from '../types'

interface ResumePageProps {
  profiles: ProfileSummary[]
  selectedVersionCode: string
  onSelectProfile: (versionCode: string) => void
  onProfilesChanged: (profile: ProfileSummary) => void
  onUseForMatch: (versionCode: string) => void
  onNavigate: (page: PageId) => void
  notify: (message: string) => void
}

export function ResumePage({ profiles, selectedVersionCode, onSelectProfile, onProfilesChanged, onUseForMatch, onNavigate, notify }: ResumePageProps) {
  const [detail, setDetail] = useState<ProfileDetail | null>(null)
  const [editing, setEditing] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    if (!selectedVersionCode) { setDetail(null); return }
    const controller = new AbortController()
    talentApi.profile(selectedVersionCode, controller.signal).then(setDetail).catch((reason: Error) => { if (reason.name !== 'AbortError') setError(reason.message) })
    return () => controller.abort()
  }, [selectedVersionCode])

  if (!profiles.length || !selectedVersionCode) return <div className="match-select-hint"><UserRound size={23} /><strong>还没有求职者画像</strong><span>请先提供 TXT 或粘贴简历文本并完成建档对话。</span><button className="primary-button" onClick={() => onNavigate('talent')}>开始创建画像</button></div>
  if (!detail) return <div className="match-select-hint"><ScanText size={23} /><strong>{error || '正在读取求职者画像'}</strong></div>
  const extraction = detail.facts.extraction as { method?: string; model?: string } | undefined
  const extractionLabel = extraction?.method === 'deepseek_evidence_locked' ? `DeepSeek 证据抽取 · ${extraction.model || '模型版本待确认'}` : '规则抽取（LLM 降级）'

  const saveVersion = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault(); setError('')
    const data = new FormData(event.currentTarget)
    try {
      const created = await talentApi.createVersion(detail.version_code, { target_role_text: String(data.get('target_role_text') ?? ''), education_text: String(data.get('education_text') ?? ''), experience_summary: String(data.get('experience_summary') ?? '') })
      onProfilesChanged(created); onSelectProfile(created.version_code); setDetail(created); setEditing(false)
      notify(`画像 v${created.version_no} 已入库，原画像与历史匹配保持不变`)
    } catch (reason) { setError((reason as Error).message) }
  }

  const confirm = async () => {
    try { const confirmed = await talentApi.publish(detail.version_code); setDetail(confirmed); onProfilesChanged(confirmed); notify('画像版本已确认，可发起真实岗位匹配') } catch (reason) { setError((reason as Error).message) }
  }

  return (
    <div className="page-stack">
      <div className="page-intro"><div><h2>求职者画像库</h2><p>解析、用户补充和系统洞察分层保存；修改生成新版本，不覆盖旧匹配报告。</p></div><div className="intro-actions"><button className="secondary-button" onClick={() => onNavigate('talent')}><Plus size={16} />新建画像</button><button className="primary-button" disabled={detail.workflow_status_code !== 'confirmed'} onClick={() => onUseForMatch(detail.version_code)}><ArrowRight size={16} />使用当前画像匹配岗位</button></div></div>
      {error ? <p className="form-error">{error}</p> : null}
      <div className="profile-library-layout">
        <Panel title="历史画像" subtitle={`${profiles.length} 个不可变版本`} action={<History size={16} />} className="profile-history-panel"><div className="profile-history-list">{profiles.map((item) => <button className={item.version_code === detail.version_code ? 'selected' : ''} key={item.version_code} onClick={() => onSelectProfile(item.version_code)}><span className="profile-list-avatar">{item.display_name.slice(0, 1)}</span><div><strong>{item.display_name} · v{item.version_no}</strong><span>{item.target_role_text || '目标岗位待确认'}</span><small>{item.created_at.slice(0, 16).replace('T', ' ')} · {item.source_name}</small></div><StatusTag tone={item.workflow_status_code === 'confirmed' ? 'success' : 'warning'}>{item.workflow_status_code === 'confirmed' ? '已确认' : '草稿'}</StatusTag></button>)}</div></Panel>
        <div className="profile-detail-area">
          <section className="profile-record-head"><div className="profile-identity"><span>{detail.display_name.slice(0, 1)}</span><div><strong>{detail.display_name} · 求职者画像 v{detail.version_no}</strong><small>版本 ID：{detail.version_code} · {detail.conversation_round_count} 轮补充问答</small></div></div><div className="profile-record-actions"><StatusTag tone={detail.workflow_status_code === 'confirmed' ? 'success' : 'warning'}>{detail.workflow_status_code === 'confirmed' ? '已确认' : '待确认'}</StatusTag><button className="secondary-button" onClick={() => setEditing(true)}><Pencil size={15} />修改并生成新版本</button></div></section>
          <div className="resume-summary"><div className="resume-file"><div className="file-icon"><FileText size={24} /></div><div><strong>{detail.source_name}</strong><span>{detail.skill_count} 项标准能力 · 完整度 {detail.completeness_score}% · {extractionLabel}</span></div><StatusTag tone="success"><Database size={12} />已入库</StatusTag></div><div className="parse-flow">{['文本准入', '事实抽取', '本地技术映射', '对话补全', '版本入库'].map((step) => <div key={step} className="done"><i><Check size={13} /></i><span>{step}</span></div>)}</div></div>
          <div className="profile-detail-grid">
            <Panel title="能力证据" subtitle={`${detail.skills.length} 项通过技术主数据映射的 L3 能力`}><div className="fact-list">{detail.skills.map((skill) => <button key={skill.skill_evidence_id}><div><StatusTag tone="success">简历事实</StatusTag><strong>{skill.technology_name}</strong><span>原始表达：{skill.raw_mention}</span><small>证据：{skill.evidence_text}</small></div><b>{skill.confidence_score}%</b></button>)}</div></Panel>
            <Panel title="画像摘要" subtitle={`画像 v${detail.version_no} · ${detail.match_run_count} 次历史匹配`} className="profile-panel"><div className="profile-score"><div><ScanText size={22} /><span>事实完整度</span></div><strong>{detail.completeness_score}%</strong></div><ScoreBar label="技术证据" value={Math.min(100, detail.skill_count * 10)} /><ScoreBar label="补充问答" value={Math.min(100, detail.conversation_round_count / detail.maximum_rounds * 100)} /><h3>求职目标</h3><p>{detail.target_role_text || '证据不足，需通过新版本补充'}</p><h3>教育与经历</h3><p>{detail.education_text || '教育信息待补充'}</p><div className="insight-box"><WandSparkles size={17} /><p>{detail.insights.statements?.[0]?.text || detail.insights.warning || '画像洞察待确认'}</p></div>{detail.workflow_status_code === 'draft' ? <button className="primary-button full" disabled={!detail.can_publish} onClick={confirm}>确认当前画像版本</button> : <button className="primary-button full" onClick={() => onUseForMatch(detail.version_code)}>选择该画像并查看匹配结果</button>}</Panel>
          </div>
        </div>
      </div>
      {editing ? <Modal title={`修改画像 v${detail.version_no}`} onClose={() => setEditing(false)}><form className="profile-edit-form" onSubmit={saveVersion}><label>求职方向<input name="target_role_text" defaultValue={detail.target_role_text ?? ''} /></label><label>学历 / 专业<input name="education_text" defaultValue={detail.education_text ?? ''} /></label><label>经历摘要<textarea name="experience_summary" defaultValue={detail.experience_summary ?? ''} /></label><div className="profile-edit-note"><History size={15} />保存后生成新版本；技术证据复制并等待重新确认。</div><div className="modal-actions"><button type="button" className="secondary-button" onClick={() => setEditing(false)}>取消</button><button className="primary-button">保存为 v{detail.version_no + 1}</button></div></form></Modal> : null}
    </div>
  )
}
