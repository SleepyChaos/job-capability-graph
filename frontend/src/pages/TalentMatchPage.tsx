import { ArrowRight, Bot, FileText, Paperclip, RotateCcw, SendHorizontal, Sparkles, UploadCloud, UserRound } from 'lucide-react'
import { useRef, useState } from 'react'
import type { PageId } from '../types'

interface ChatMessage {
  role: 'assistant' | 'user'
  text: string
}

const questions = [
  {
    text: '你目前最想进入哪类具身智能岗位？如果还不确定，也可以描述更喜欢的工作内容。',
    replies: ['系统集成与联调', '感知与定位', '运动控制与规划'],
  },
  {
    text: '在已有经历中，哪个项目最能代表你的能力？你具体负责了什么、结果如何？',
    replies: ['多机协同机器人项目', '室内定位与建图项目', '我想自己描述'],
  },
  {
    text: '你更偏好研究探索、工程交付，还是跨模块协调？这会影响岗位环境与团队角色的匹配。',
    replies: ['工程交付', '研究探索', '跨模块协调'],
  },
  {
    text: '未来 1–2 年你希望形成怎样的能力组合？有没有明确不考虑的方向或工作条件？',
    replies: ['成为系统集成骨干', '向算法研发深入', '先看综合建议'],
  },
]

interface TalentMatchPageProps {
  hasProfiles: boolean
  onProfileCreated: (sourceFile: string, conversationRounds: number) => void
  onNavigate: (page: PageId) => void
  notify: (message: string) => void
}

export function TalentMatchPage({ hasProfiles, onProfileCreated, onNavigate, notify }: TalentMatchPageProps) {
  const fileRef = useRef<HTMLInputElement>(null)
  const [fileName, setFileName] = useState('')
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [input, setInput] = useState('')
  const [questionIndex, setQuestionIndex] = useState(0)
  const [parsing, setParsing] = useState(false)
  const [generating, setGenerating] = useState(false)

  const beginWithFile = (file?: File) => {
    if (!file) return
    setFileName(file.name)
    setParsing(true)
    window.setTimeout(() => {
      setParsing(false)
      setMessages([
        { role: 'assistant', text: `已完成《${file.name}》的文本与结构解析。我识别到教育、项目和技术能力等信息，接下来会用 2–8 轮问题补全仅靠简历无法判断的部分。` },
        { role: 'assistant', text: questions[0].text },
      ])
    }, 850)
  }

  const answer = (value: string) => {
    const text = value.trim()
    if (!text || !fileName) return
    const nextIndex = questionIndex + 1
    setMessages((items) => [
      ...items,
      { role: 'user', text },
      { role: 'assistant', text: nextIndex < questions.length ? questions[nextIndex].text : '信息已经足够。我会区分简历事实、你的补充陈述和模型推断，生成一份可确认、可继续修订的求职者画像。' },
    ])
    setQuestionIndex(nextIndex)
    setInput('')
  }

  const generateProfile = () => {
    setGenerating(true)
    window.setTimeout(() => {
      setGenerating(false)
      onProfileCreated(fileName, Math.max(questionIndex, 2))
      notify('求职者画像已解析完成并入库，可在画像库中继续修改')
      onNavigate('resume')
    }, 900)
  }

  const reset = () => {
    setFileName('')
    setMessages([])
    setQuestionIndex(0)
    setInput('')
  }

  if (!fileName) {
    return (
      <section className="talent-entry">
        <div className="talent-entry-mark"><Sparkles size={25} /></div>
        <h2>从一场对话开始认识你</h2>
        <p>上传简历或直接粘贴经历。系统会先解析事实，再通过 2–8 轮追问补全求职目标、偏好与发展意愿。</p>
        <button className="talent-composer talent-composer--empty" type="button" onClick={() => fileRef.current?.click()}>
          <span>上传 PDF、DOCX、TXT 或图片简历</span>
          <span className="talent-upload-action"><UploadCloud size={17} />选择文件</span>
        </button>
        <input ref={fileRef} hidden type="file" accept=".pdf,.doc,.docx,.txt,image/*" onChange={(event) => beginWithFile(event.target.files?.[0])} />
        <div className="talent-entry-notes"><span>事实与推断分层</span><i /><span>每项能力保留证据</span><i /><span>画像由你最终确认</span></div>
        {hasProfiles ? <button className="link-button talent-history" onClick={() => onNavigate('resume')}>查看历史求职者画像 <ArrowRight size={14} /></button> : null}
      </section>
    )
  }

  return (
    <div className="talent-chat-page">
      <header className="talent-chat-head">
        <div><strong>求职者建档对话</strong><span>{questionIndex >= questions.length ? '信息收集完成' : `第 ${Math.min(questionIndex + 1, questions.length)} 轮 · 最多 8 轮`}</span></div>
        <button className="secondary-button" onClick={reset}><RotateCcw size={14} />重新开始</button>
      </header>
      <main className="talent-chat-stream" aria-live="polite">
        <div className="chat-file"><FileText size={17} /><div><strong>{fileName}</strong><span>{parsing ? '正在解析文本与版面…' : '解析完成 · 已识别 19 项事实与 12 项标准能力'}</span></div></div>
        {parsing ? <div className="chat-thinking"><i /><i /><i /><span>正在读取简历并映射技术词标准库</span></div> : null}
        {messages.map((message, index) => (
          <div className={`chat-message chat-message--${message.role}`} key={`${message.role}-${index}`}>
            <span className="chat-avatar">{message.role === 'assistant' ? <Bot size={17} /> : <UserRound size={17} />}</span>
            <p>{message.text}</p>
          </div>
        ))}
        {!parsing && questionIndex < questions.length ? (
          <div className="quick-replies">
            {questions[questionIndex].replies.map((reply) => <button key={reply} onClick={() => answer(reply)}>{reply}</button>)}
          </div>
        ) : null}
      </main>
      <footer className="talent-chat-composer">
        {questionIndex >= 2 ? <button className="secondary-button" onClick={generateProfile} disabled={generating}>{generating ? '正在生成…' : questionIndex >= questions.length ? '生成求职者画像' : '信息已足够，提前生成画像'}</button> : null}
        <div className="talent-input-row">
          <button className="icon-button" aria-label="补充文件" onClick={() => fileRef.current?.click()}><Paperclip size={18} /></button>
          <textarea value={input} onChange={(event) => setInput(event.target.value)} placeholder={questionIndex >= questions.length ? '还可以继续补充信息，或直接生成画像' : '输入你的回答…'} onKeyDown={(event) => { if (event.key === 'Enter' && !event.shiftKey) { event.preventDefault(); answer(input) } }} />
          <button className="chat-send" aria-label="发送" onClick={() => answer(input)} disabled={!input.trim()}><SendHorizontal size={18} /></button>
        </div>
        <small>AI 生成内容仅作为画像推断依据，提交匹配前可逐项修改和确认。</small>
      </footer>
      <input ref={fileRef} hidden type="file" accept=".pdf,.doc,.docx,.txt,image/*" onChange={(event) => beginWithFile(event.target.files?.[0])} />
    </div>
  )
}
