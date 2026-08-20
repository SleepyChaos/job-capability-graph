import { ArrowRight, Bot, FileText, RotateCcw, SendHorizontal, Sparkles, UploadCloud, UserRound } from 'lucide-react'
import { useRef, useState } from 'react'
import { talentApi, type ProfileDetail } from '../api/talent'
import type { PageId } from '../types'

interface ChatMessage { role: 'assistant' | 'user'; text: string }

interface TalentMatchPageProps {
  hasProfiles: boolean
  onProfileCreated: (profile: ProfileDetail) => void
  onNavigate: (page: PageId) => void
  notify: (message: string) => void
}

export function TalentMatchPage({ hasProfiles, onProfileCreated, onNavigate, notify }: TalentMatchPageProps) {
  const fileRef = useRef<HTMLInputElement>(null)
  const [sourceName, setSourceName] = useState('粘贴文本简历')
  const [resumeText, setResumeText] = useState('')
  const [profile, setProfile] = useState<ProfileDetail | null>(null)
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [input, setInput] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

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

  const afterParsed = (next: ProfileDetail) => {
    const extraction = next.facts.extraction as { method?: string; model?: string } | undefined
    const method = extraction?.method === 'deepseek_evidence_locked'
      ? `DeepSeek（${extraction.model || '模型版本待确认'}）证据抽取`
      : '规则降级抽取'
    setProfile(next)
    setMessages([
      { role: 'assistant', text: `已通过${method}解析《${next.source_name}》，识别到 ${next.skill_count} 项标准技术能力。模型只提取原文事实；技术映射与后续评分全部由本地确定性规则完成。` },
      ...(next.next_question ? [{ role: 'assistant' as const, text: next.next_question.question_text }] : []),
    ])
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

  const reset = () => { setProfile(null); setMessages([]); setInput(''); setResumeText(''); setSourceName('粘贴文本简历'); setError('') }

  if (!profile) return (
    <section className="talent-entry">
      <div className="talent-entry-mark"><Sparkles size={25} /></div>
      <h2>从一场对话开始认识你</h2>
      <p>支持粘贴文本或上传 TXT / 文本型 PDF / DOCX（服务端解析，扫描件 OCR 尚未接入）。解析后进入 2–8 轮追问与画像确认。</p>
      <div className="talent-text-entry">
        <textarea value={resumeText} onChange={(event) => setResumeText(event.target.value)} placeholder="粘贴简历文本，例如：姓名、求职意向、教育经历、项目职责、使用的技术及项目结果……" />
        <div><span>{sourceName} · {resumeText.length} 字符</span><button className="secondary-button" onClick={() => fileRef.current?.click()} disabled={busy}><UploadCloud size={15} />上传简历文件</button><button className="primary-button" onClick={begin} disabled={busy}>{busy ? '正在解析…' : '开始证据建档'}</button></div>
      </div>
      <input ref={fileRef} hidden type="file" accept=".txt,.pdf,.docx" onChange={(event) => uploadResume(event.target.files?.[0])} />
      {error ? <p className="form-error">{error}</p> : null}
      <div className="talent-entry-notes"><span>不使用敏感属性</span><i /><span>每项能力保留原文证据</span><i /><span>缺少信息不等于不会</span></div>
      {hasProfiles ? <button className="link-button talent-history" onClick={() => onNavigate('resume')}>查看历史求职者画像 <ArrowRight size={14} /></button> : null}
    </section>
  )

  return (
    <div className="talent-chat-page">
      <header className="talent-chat-head"><div><strong>求职者建档对话</strong><span>已完成 {profile.conversation_round_count} 轮 · 允许 2–8 轮结束</span></div><button className="secondary-button" onClick={reset}><RotateCcw size={14} />重新开始</button></header>
      <main className="talent-chat-stream" aria-live="polite">
        <div className="chat-file"><FileText size={17} /><div><strong>{profile.source_name}</strong><span>{profile.skill_count} 项技术能力 · 完整度 {profile.completeness_score}%</span></div></div>
        {messages.map((message, index) => <div className={`chat-message chat-message--${message.role}`} key={`${message.role}-${index}`}><span className="chat-avatar">{message.role === 'assistant' ? <Bot size={17} /> : <UserRound size={17} />}</span><p>{message.text}</p></div>)}
        {busy ? <div className="chat-thinking"><i /><i /><i /><span>正在保存用户补充并检查结束条件</span></div> : null}
      </main>
      <footer className="talent-chat-composer">
        {profile.can_publish ? <button className="secondary-button" onClick={publish} disabled={busy}>确认并发布画像</button> : null}
        {profile.next_question ? <div className="talent-input-row"><textarea value={input} onChange={(event) => setInput(event.target.value)} placeholder="输入你的回答…" onKeyDown={(event) => { if (event.key === 'Enter' && !event.shiftKey) { event.preventDefault(); answer(input) } }} /><button className="chat-send" aria-label="发送" onClick={() => answer(input)} disabled={!input.trim() || busy}><SendHorizontal size={18} /></button></div> : null}
        {error ? <small className="form-error">{error}</small> : <small>每轮回答保存为“用户补充”，不会覆盖简历事实。</small>}
      </footer>
    </div>
  )
}
