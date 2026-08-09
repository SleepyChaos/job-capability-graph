import { ArrowRight, Check, Clock3, Database, FileText, History, Pencil, Plus, ScanText, UserRound, WandSparkles } from 'lucide-react'
import { useState, type FormEvent } from 'react'
import { Modal, Panel, ScoreBar, StatusTag } from '../components/ui'
import type { CandidateProfile, PageId } from '../types'

interface ResumePageProps {
  profiles: CandidateProfile[]
  selectedProfileId: string
  onSelectProfile: (profileId: string) => void
  onCreateVersion: (baseId: string, updates: Pick<CandidateProfile, 'name' | 'direction' | 'education' | 'summary' | 'skills'>) => void
  onUseForMatch: (profileId: string) => void
  onNavigate: (page: PageId) => void
  notify: (message: string) => void
}

export function ResumePage({ profiles, selectedProfileId, onSelectProfile, onCreateVersion, onUseForMatch, onNavigate, notify }: ResumePageProps) {
  const [editing, setEditing] = useState(false)
  const profile = profiles.find((item) => item.id === selectedProfileId) ?? profiles[0]

  if (!profile) {
    return <div className="match-select-hint"><UserRound size={23} /><strong>还没有求职者画像</strong><span>请先上传简历并完成建档对话。</span><button className="primary-button" onClick={() => onNavigate('talent')}>开始创建画像</button></div>
  }

  const facts = [
    { group: '求职目标', label: '目标岗位', value: profile.direction, evidence: '建档对话与画像确认', confidence: 96 },
    { group: '教育经历', label: '学历 / 专业', value: profile.education, evidence: '教育经历第 1 项', confidence: 99 },
    { group: '项目经历', label: '代表性项目', value: profile.skills.slice(0, 3).join('、'), evidence: '项目经历与补充问答', confidence: 93 },
    { group: '工作方式', label: '系统推断', value: profile.summary, evidence: '项目职责与对话回答', confidence: 78 },
  ]
  const nextVersion = Math.max(...profiles.filter((item) => item.name === profile.name).map((item) => item.version), 0) + 1

  const saveVersion = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    const data = new FormData(event.currentTarget)
    onCreateVersion(profile.id, {
      name: String(data.get('name') ?? profile.name),
      direction: String(data.get('direction') ?? profile.direction),
      education: String(data.get('education') ?? profile.education),
      summary: String(data.get('summary') ?? profile.summary),
      skills: String(data.get('skills') ?? '').split(/[、,，]/).map((item) => item.trim()).filter(Boolean),
    })
    setEditing(false)
    notify(`画像 v${nextVersion} 已入库，历史版本完整保留`)
  }

  return (
    <div className="page-stack">
      <div className="page-intro"><div><h2>求职者画像库</h2><p>每次解析或修改都会形成独立画像版本；选择一份画像后再发起岗位匹配。</p></div><div className="intro-actions"><button className="secondary-button" onClick={() => onNavigate('talent')}><Plus size={16} />新建画像</button><button className="primary-button" onClick={() => onUseForMatch(profile.id)}><ArrowRight size={16} />使用当前画像匹配岗位</button></div></div>

      <div className="profile-library-layout">
        <Panel title="历史画像" subtitle={`${profiles.length} 份画像记录`} action={<History size={16} />} className="profile-history-panel">
          <div className="profile-history-list">
            {profiles.map((item) => (
              <button className={item.id === profile.id ? 'selected' : ''} key={item.id} onClick={() => onSelectProfile(item.id)}>
                <span className="profile-list-avatar">{item.name.slice(0, 1)}</span>
                <div><strong>{item.name} · v{item.version}</strong><span>{item.direction}</span><small>{item.updatedAt} · {item.sourceFile}</small></div>
                <StatusTag tone={item.status === '已确认' ? 'success' : 'warning'}>{item.status}</StatusTag>
              </button>
            ))}
          </div>
        </Panel>

        <div className="profile-detail-area">
          <section className="profile-record-head">
            <div className="profile-identity"><span>{profile.name.slice(0, 1)}</span><div><strong>{profile.name} · 求职者画像 v{profile.version}</strong><small>画像 ID：{profile.id} · 入库时间：{profile.createdAt}</small></div></div>
            <div className="profile-record-actions"><StatusTag tone={profile.status === '已确认' ? 'success' : 'warning'}>{profile.status}</StatusTag><button className="secondary-button" onClick={() => setEditing(true)}><Pencil size={15} />修改并生成新版本</button></div>
          </section>

          <div className="resume-summary">
            <div className="resume-file"><div className="file-icon"><FileText size={24} /></div><div><strong>{profile.sourceFile}</strong><span>{profile.conversationRounds} 轮补充对话 · {profile.factsCount} 项事实</span></div><StatusTag tone="success"><Database size={12} />已入库</StatusTag></div>
            <div className="parse-flow">{['文本 / OCR', '事实抽取', '对话补全', '画像生成', '版本入库'].map((step) => <div key={step} className="done"><i><Check size={13} /></i><span>{step}</span></div>)}</div>
          </div>

          <div className="profile-detail-grid">
            <Panel title="结构化画像" subtitle={`${profile.factsCount} 项事实 · ${profile.skills.length} 个核心能力`} action={<button className="secondary-button" onClick={() => setEditing(true)}><Pencil size={15} />编辑</button>}>
              <div className="fact-list">{facts.map((fact) => <button key={`${fact.group}-${fact.label}`}><div><StatusTag tone={fact.group === '工作方式' ? 'info' : 'success'}>{fact.group === '工作方式' ? '系统推断' : '画像事实'}</StatusTag><strong>{fact.label}</strong><span>{fact.value}</span><small>证据：{fact.evidence}</small></div><b>{fact.confidence}%</b></button>)}</div>
            </Panel>
            <Panel title="画像摘要" subtitle={`画像 v${profile.version} · ${profile.matchRuns} 次匹配记录`} className="profile-panel">
              <div className="profile-score"><div><ScanText size={22} /><span>事实完整度</span></div><strong>{profile.completeness}%</strong></div>
              <ScoreBar label="技术证据" value={Math.max(profile.completeness - 4, 55)} /><ScoreBar label="项目证据" value={Math.max(profile.completeness - 9, 48)} /><ScoreBar label="方向明确度" value={Math.min(profile.completeness + 2, 96)} />
              <h3>核心能力</h3><div className="skill-tags">{profile.skills.map((skill) => <span key={skill}>{skill}</span>)}</div>
              <h3>画像洞察</h3><div className="insight-box"><WandSparkles size={17} /><p>{profile.summary}</p></div>
              <div className="profile-version-note"><Clock3 size={15} /><span>修改不会覆盖当前记录，而是生成 v{nextVersion} 并保留本版本。</span></div>
              <button className="primary-button full" onClick={() => onUseForMatch(profile.id)}>选择该画像并查看匹配结果</button>
            </Panel>
          </div>
        </div>
      </div>

      {editing ? <Modal title={`修改 ${profile.name} · 画像 v${profile.version}`} onClose={() => setEditing(false)}><form className="profile-edit-form" onSubmit={saveVersion}><div className="form-grid"><label>姓名<input name="name" defaultValue={profile.name} /></label><label>学历 / 专业<input name="education" defaultValue={profile.education} /></label></div><label>求职方向<input name="direction" defaultValue={profile.direction} /></label><label>核心能力（用逗号分隔）<input name="skills" defaultValue={profile.skills.join('、')} /></label><label>画像摘要<textarea name="summary" defaultValue={profile.summary} /></label><div className="profile-edit-note"><History size={15} />保存后生成新版本，当前版本及其历史匹配结果不会被覆盖。</div><div className="modal-actions"><button type="button" className="secondary-button" onClick={() => setEditing(false)}>取消</button><button className="primary-button">保存为 v{nextVersion}</button></div></form></Modal> : null}
    </div>
  )
}
