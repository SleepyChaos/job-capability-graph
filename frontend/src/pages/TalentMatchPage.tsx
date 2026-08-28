import { ArrowRight, Bot, ChevronDown, FileText, History, ListTree, Plus, RotateCcw, SendHorizontal, Sparkles, UploadCloud, UserRound } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { talentApi, type ProfileDetail, type ProfileSummary } from '../api/talent'
import type { PageId } from '../types'

interface ChatMessage { role: 'assistant' | 'user'; text: string }

type UnknownRecord = Record<string, unknown>

const EXTRACTION_FIELDS = [
  { code: 'job_responsibilities', label: '岗位职责', fields: ['value', 'role', 'summary'] },
  { code: 'required_skills', label: '必备技能', fields: ['normalized_keyword', 'raw_name', 'value'] },
  { code: 'tools_platforms', label: '工具平台', fields: ['value', 'normalized_keyword', 'raw_name'] },
  { code: 'education_major', label: '学历专业', fields: ['value', 'school', 'degree', 'major', 'period'] },
  { code: 'work_experience', label: '工作经验', fields: ['value', 'company', 'role', 'period', 'summary'] },
  { code: 'application_scenarios', label: '应用场景', fields: ['value', 'summary'] },
  { code: 'generic_capabilities', label: '通用能力', fields: ['value', 'summary'] },
] as const

function objectValue(value: unknown): UnknownRecord {
  return value && typeof value === 'object' && !Array.isArray(value) ? value as UnknownRecord : {}
}

function recordValues(value: unknown, fields: readonly string[]): string[] {
  if (!Array.isArray(value)) return []
  return value.flatMap((item) => {
    const record = objectValue(item)
    const parts = fields.map((field) => record[field]).filter((part): part is string => typeof part === 'string' && Boolean(part.trim()))
    return parts.length ? [[...new Set(parts.map((part) => part.trim()))].join(' · ')] : []
  })
}

function extractedDimensionValues(profile: ProfileDetail, code: string, fields: readonly string[]): string[] {
  const structured = objectValue(objectValue(profile.facts).structured)
  const dimensions = objectValue(structured.profile_dimensions)
  let values = recordValues(dimensions[code], fields)
  if (!values.length && code === 'job_responsibilities') values = [...recordValues(structured.work_experiences, fields), ...recordValues(structured.projects, fields)]
  if (!values.length && code === 'education_major') values = recordValues(structured.education, fields)
  if (!values.length && code === 'work_experience') values = recordValues(structured.work_experiences, fields)
  if (!values.length && code === 'required_skills') values = profile.skills.map((skill) => skill.technology_name)
  return [...new Set(values)].slice(0, 5)
}

function ExtractionDetails({ profile }: { profile: ProfileDetail }) {
  const extraction = objectValue(objectValue(profile.facts).extraction)
  const covered = EXTRACTION_FIELDS.filter((field) => extractedDimensionValues(profile, field.code, field.fields).length > 0).length
  return <details className="chat-extraction-details">
    <summary><span><ListTree size={15} /><strong>查看字段提取详情</strong><small>{covered}/7 类画像字段已识别 · {profile.skill_count} 项标准能力</small></span><ChevronDown size={16} /></summary>
    <div className="chat-extraction-body">
      <section className="chat-basic-fields">
        <h4>基本字段</h4>
        <div><span>姓名<strong>{profile.display_name || '未提取'}</strong></span><span>求职目标<strong>{profile.target_role_text || '未提取'}</strong></span><span>学历专业<strong>{profile.education_text || '未提取'}</strong></span><span>经历摘要<strong>{profile.experience_summary || '未提取'}</strong></span></div>
      </section>
      <section className="chat-seven-fields">
        <h4>七类画像字段</h4>
        <div>{EXTRACTION_FIELDS.map((field) => {
          const values = extractedDimensionValues(profile, field.code, field.fields)
          return <article className={values.length ? 'extracted' : 'unresolved'} key={field.code}><header><strong>{field.label}</strong><i>{values.length ? '已提取' : '未提取'}</i></header>{values.length ? <ul>{values.map((value) => <li key={value}>{value}</li>)}</ul> : <p>无原文证据，将进入主动追问候选。</p>}</article>
        })}</div>
      </section>
      <section className="chat-skill-fields">
        <h4>标准能力映射</h4>
        {profile.skills.length ? <div>{profile.skills.map((skill) => <span key={skill.skill_evidence_id}><strong>{skill.technology_name}</strong><small>{skill.raw_mention} · 置信度 {skill.confidence_score}%</small></span>)}</div> : <p>未发现能够映射到技术主数据的能力证据。</p>}
      </section>
      <footer>抽取方式：{String(extraction.method || '未记录')} · 模型：{String(extraction.model || '规则降级，无模型')}</footer>
    </div>
  </details>
}

interface TalentMatchPageProps {
  profiles: ProfileSummary[]
  hasProfiles: boolean
  onProfileCreated: (profile: ProfileDetail) => void
  onNavigate: (page: PageId) => void
  notify: (message: string) => void
}

function DialogueHistory({ profiles, activeVersionCode, busy, onNew, onSelect }: { profiles: ProfileSummary[]; activeVersionCode?: string; busy: boolean; onNew: () => void; onSelect: (versionCode: string) => void }) {
  return <aside className="dialogue-history-panel">
    <header><div><History size={16} /><span><strong>历史对话</strong><small>{profiles.length} 个建档记录</small></span></div><button onClick={onNew} aria-label="新建对话"><Plus size={15} /></button></header>
    <div className="dialogue-history-list">{profiles.length ? profiles.map((item) => <button className={item.version_code === activeVersionCode ? 'active' : ''} disabled={busy} key={item.version_code} onClick={() => onSelect(item.version_code)}><i>{item.display_name.slice(0, 1)}</i><span><strong>{item.display_name}</strong><small>{item.target_role_text || '目标岗位待补充'}</small><em>{item.conversation_round_count} 轮 · {item.source_name}</em></span><b>{item.workflow_status_code === 'confirmed' ? '已确认' : '草稿'}</b></button>) : <div className="dialogue-history-empty"><History size={22} /><span>暂无历史对话</span></div>}</div>
  </aside>
}

export function TalentMatchPage({ profiles, hasProfiles, onProfileCreated, onNavigate, notify }: TalentMatchPageProps) {
  const fileRef = useRef<HTMLInputElement>(null)
  const chatStreamRef = useRef<HTMLElement>(null)
  const [sourceName, setSourceName] = useState('粘贴文本简历')
  const [resumeText, setResumeText] = useState('')
  const [profile, setProfile] = useState<ProfileDetail | null>(null)
  const [parsedProfile, setParsedProfile] = useState<ProfileDetail | null>(null)
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [input, setInput] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    const stream = chatStreamRef.current
    if (!stream || !profile) return
    const frame = window.requestAnimationFrame(() => {
      stream.scrollTo({ top: stream.scrollHeight, behavior: 'smooth' })
    })
    return () => window.cancelAnimationFrame(frame)
  }, [busy, messages, profile])

  const begin = async () => {
    if (resumeText.trim().length < 30) {
      setError('请至少提供 30 个有效字符的简历文本，或上传 TXT/PDF/DOCX 文件。')
      return
    }
    setBusy(true); setError('')
    try {
      const next = await talentApi.createProfile({ source_name: sourceName, mime_type: 'text/plain', input_type_code: sourceName.endsWith('.txt') ? 'txt' : 'pasted_text', content_text: resumeText })
      afterParsed(next)
    } catch (reason) { setError((reason as Error).message) } finally { setBusy(false) }
  }

  const messagesForProfile = (next: ProfileDetail): ChatMessage[] => {
    const extraction = next.facts.extraction as { method?: string; model?: string } | undefined
    const method = extraction?.method === 'deepseek_evidence_locked'
      ? `DeepSeek（${extraction.model || '模型版本待确认'}）证据抽取`
      : '规则降级抽取'
    const historyMessages = (next.dialogue_history || []).flatMap((turn) => [
      { role: 'assistant' as const, text: turn.question_text },
      ...(turn.answer_text ? [{ role: 'user' as const, text: turn.answer_text }] : []),
    ])
    return [
      { role: 'assistant', text: `已通过${method}解析《${next.source_name}》，识别到 ${next.skill_count} 项标准技术能力。模型只提取原文事实；技术映射与后续评分全部由本地确定性规则完成。` },
      ...historyMessages,
    ]
  }

  const afterParsed = (next: ProfileDetail) => {
    setProfile(next)
    setParsedProfile(next)
    setMessages(messagesForProfile(next))
    onProfileCreated(next)
  }

  const answer = async (value: string) => {
    const text = value.trim()
    if (!profile || !text || busy) return
    setBusy(true); setError('')
    setMessages((items) => [...items, { role: 'user', text }])
    setInput('')
    try {
      const next = await talentApi.answer(profile.version_code, text)
      setProfile(next)
      setMessages((items) => [...items, { role: 'assistant', text: next.next_question?.question_text ?? '当前信息已达到 P0 建档门槛。你可以确认画像，也可以稍后通过新版本继续补充。' }])
    } catch (reason) { setError((reason as Error).message) } finally { setBusy(false) }
  }

  const publish = async () => {
    if (!profile || busy) return
    setBusy(true); setError('')
    try {
      const confirmed = await talentApi.publish(profile.version_code)
      onProfileCreated(confirmed)
      notify('求职者画像已确认并入库')
      onNavigate('resume')
    } catch (reason) { setError((reason as Error).message) } finally { setBusy(false) }
  }

  const uploadResume = async (file?: File) => {
    if (!file || busy) return
    setBusy(true); setError('')
    try {
      const next = await talentApi.uploadProfile(file)
      afterParsed(next)
    } catch (reason) {
      setError((reason as Error).message)
    } finally {
      setBusy(false)
      if (fileRef.current) fileRef.current.value = ''
    }
  }

  const reset = () => { setProfile(null); setParsedProfile(null); setMessages([]); setInput(''); setResumeText(''); setSourceName('粘贴文本简历'); setError('') }

  const openHistory = async (versionCode: string) => {
    if (busy) return
    setBusy(true); setError(''); setInput('')
    try {
      const next = await talentApi.profile(versionCode)
      setProfile(next); setParsedProfile(next); setMessages(messagesForProfile(next))
    } catch (reason) { setError((reason as Error).message) } finally { setBusy(false) }
  }

  const historyPanel = <DialogueHistory profiles={profiles} activeVersionCode={profile?.version_code} busy={busy} onNew={reset} onSelect={openHistory} />

  if (!profile) return (
    <div className="talent-dialogue-layout">{historyPanel}<section className="talent-entry">
      <div className="talent-entry-mark"><Sparkles size={25} /></div>
      <h2>从一场对话开始认识你</h2>
      <p>支持粘贴文本或上传 TXT / 文本型 PDF / DOCX（服务端解析，扫描件 OCR 尚未接入）。解析后进入 2–8 轮追问与画像确认。</p>
      <div className="talent-text-entry">
        <textarea aria-label="简历文本" value={resumeText} onChange={(event) => setResumeText(event.target.value)} placeholder="粘贴简历文本，例如：姓名、求职意向、教育经历、项目职责、使用的技术及项目结果……" />
        <div><span>{sourceName} · {resumeText.length} 字符</span><button type="button" className="secondary-button" onClick={() => fileRef.current?.click()} disabled={busy}><UploadCloud size={15} />选择并发送文件</button><button type="button" className="primary-button" onClick={begin} disabled={busy}><SendHorizontal size={15} />{busy ? '正在解析…' : '发送文本简历'}</button></div>
      </div>
      <input ref={fileRef} hidden type="file" accept=".txt,.pdf,.docx" onChange={(event) => uploadResume(event.target.files?.[0])} />
      {error ? <p className="form-error">{error}</p> : null}
      <div className="talent-entry-notes"><span>不使用敏感属性</span><i /><span>每项能力保留原文证据</span><i /><span>缺少信息不等于不会</span></div>
      {hasProfiles ? <button className="link-button talent-history" onClick={() => onNavigate('resume')}>查看历史求职者画像 <ArrowRight size={14} /></button> : null}
    </section></div>
  )

  return (
    <div className="talent-dialogue-layout">{historyPanel}<div className="talent-chat-page">
      <header className="talent-chat-head"><div><strong>求职者建档对话</strong><span>已完成 {profile.conversation_round_count} 轮 · 按七类画像缺口动态追问（最多 8 轮）</span></div><button className="secondary-button" onClick={reset}><RotateCcw size={14} />重新开始</button></header>
      <main ref={chatStreamRef} className="talent-chat-stream" aria-live="polite">
        <div className="chat-file"><FileText size={17} /><div><strong>{profile.source_name}</strong><span>{profile.skill_count} 项技术能力 · 完整度 {profile.completeness_score}%</span></div></div>
        {messages.map((message, index) => <div className="chat-message-block" key={`${message.role}-${index}`}><div className={`chat-message chat-message--${message.role}`}><span className="chat-avatar">{message.role === 'assistant' ? <Bot size={17} /> : <UserRound size={17} />}</span><p>{message.text}</p></div>{index === 0 && parsedProfile ? <ExtractionDetails profile={parsedProfile} /> : null}</div>)}
        {busy ? <div className="chat-thinking"><i /><i /><i /><span>正在保存用户补充并检查结束条件</span></div> : null}
      </main>
      <footer className="talent-chat-composer">
        {profile.workflow_status_code === 'draft' && profile.can_publish ? <button className="secondary-button" onClick={publish} disabled={busy}>确认并发布画像</button> : null}
        {profile.workflow_status_code === 'draft' && profile.next_question ? <div className="talent-input-row"><textarea value={input} onChange={(event) => setInput(event.target.value)} placeholder="输入你的回答…" onKeyDown={(event) => { if (event.key === 'Enter' && !event.shiftKey) { event.preventDefault(); answer(input) } }} /><button className="chat-send" aria-label="发送" onClick={() => answer(input)} disabled={!input.trim() || busy}><SendHorizontal size={18} /></button></div> : null}
        {error ? <small className="form-error">{error}</small> : <small>{profile.workflow_status_code === 'confirmed' ? '这是已确认的历史对话记录，仅供查看。' : '每轮回答保存为“用户补充”，不会覆盖简历事实。'}</small>}
      </footer>
    </div></div>
  )
}
