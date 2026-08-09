import { ArrowLeft, ArrowRight, BriefcaseBusiness, Building2, CheckCircle2, ChevronRight, FilePlus2, Info, Layers3, MapPin, RefreshCw, Route, XCircle } from 'lucide-react'
import { useState } from 'react'
import { Modal, Panel, ScoreBar, StatusTag } from '../components/ui'
import { matchRows } from '../data/mockData'
import type { CandidateProfile, PageId } from '../types'

const dimensions = [
  ['必需能力覆盖', 86], ['能力深度', 72], ['项目证据', 70], ['时间新鲜度', 68], ['场景相似度', 82], ['岗位级别', 75], ['任务语义', 79], ['可迁移能力', 85],
] as const

const jobs = [
  { name: '具身智能系统集成工程师', company: '星海机器人', location: '上海', score: 78, level: '中级', domain: 'T6 系统集成', reasons: ['ROS 2 项目证据充分', '定位与建图经验可迁移'], gaps: ['实时控制深度', 'Sim2Real 证据'] },
  { name: '机器人感知与定位算法工程师', company: '维境智能', location: '深圳', score: 74, level: '初中级', domain: 'T2 感知与认知', reasons: ['SLAM 与多传感器融合匹配', '项目场景相似度高'], gaps: ['深度学习部署', '视觉感知工程化'] },
  { name: '移动机器人导航工程师', company: '启程具身', location: '杭州', score: 69, level: '中级', domain: 'T4 规划与决策', reasons: ['路径规划与定位基础匹配', '多机协同经验有价值'], gaps: ['动态避障', '复杂场景量化结果'] },
] as const

interface MatchPageProps {
  profile: CandidateProfile
  selectedJob: string
  onSelectJob: (job: string) => void
  onNavigate: (page: PageId) => void
  notify: (message: string) => void
}

export function MatchPage({ profile, selectedJob, onSelectJob, onNavigate, notify }: MatchPageProps) {
  const selected = jobs.find((job) => job.name === selectedJob)
  const [score, setScore] = useState<number>(selected?.score ?? 78)
  const [filter, setFilter] = useState('全部')
  const [adding, setAdding] = useState(false)
  const [recomputing, setRecomputing] = useState(false)
  const rows = filter === '全部' ? matchRows : matchRows.filter((row) => row.result === filter)

  const chooseJob = (name: string, nextScore: number) => {
    onSelectJob(name)
    setScore(nextScore)
    window.setTimeout(() => document.querySelector('.match-detail-anchor')?.scrollIntoView({ behavior: 'smooth', block: 'start' }), 0)
  }

  const recompute = () => {
    setRecomputing(true)
    window.setTimeout(() => {
      setScore((value) => Math.min(value + 4, 92))
      setRecomputing(false)
      notify('匹配已重新计算：新增证据使项目证据维度提升 6 分')
    }, 900)
  }

  return (
    <div className="page-stack match-page">
      <div className="page-intro"><div><h2>岗位匹配结果</h2><p>当前结果绑定 {profile.name} · 画像 v{profile.version}；选择一条结果后进入对应差距与发展路径分析。</p></div><button className="secondary-button" onClick={() => onNavigate('resume')}><ArrowLeft size={15} />切换画像</button></div>
      <section className="match-profile-source">
        <div className="avatar">{profile.name.slice(0, 1)}</div>
        <div><strong>{profile.name} · 求职者画像 v{profile.version}</strong><span>{profile.direction} · {profile.skills.length} 项核心能力 · {profile.updatedAt}</span></div>
        <StatusTag tone={profile.status === '已确认' ? 'success' : 'warning'}>{profile.status === '已确认' ? '已用于本次匹配' : '待确认画像 · 演示匹配'}</StatusTag>
      </section>
      <Panel title="匹配结果" subtitle={`基于画像 ${profile.id}，综合能力覆盖、任务语义、岗位级别与场景相似度排序`} action={<span className="panel-action-note">3 条匹配结果</span>}>
        <div className="job-match-grid">
          {jobs.map((job) => (
            <button className={selectedJob === job.name ? 'selected' : ''} key={job.name} onClick={() => chooseJob(job.name, job.score)}>
              <div className="job-card-top"><StatusTag tone={job.score >= 75 ? 'success' : 'info'}>{job.score}% 匹配</StatusTag><ChevronRight size={17} /></div>
              <h3>{job.name}</h3>
              <div className="job-card-meta"><span><Building2 size={13} />{job.company}</span><span><MapPin size={13} />{job.location}</span><span><Layers3 size={13} />{job.level}</span></div>
              <p>{job.domain}</p>
              <div className="job-card-evidence"><strong>推荐依据</strong>{job.reasons.map((reason) => <span key={reason}><CheckCircle2 size={13} />{reason}</span>)}</div>
              <div className="job-card-gaps"><strong>主要差距</strong><span>{job.gaps.join('、')}</span></div>
            </button>
          ))}
        </div>
      </Panel>

      {selected ? (
        <section className="match-detail-anchor">
          <div className="match-detail-title"><div><BriefcaseBusiness size={20} /><div><strong>{selected.name}</strong><span>{selected.company} · 岗位版本 2026 Q2</span></div></div><button className="link-button" onClick={() => onSelectJob('')}>收起差距分析</button></div>
          <section className="match-hero">
            <div className="compare-person"><div className="avatar">{profile.name.slice(0, 1)}</div><div><strong>{profile.name} · 画像 v{profile.version}</strong><span>{profile.status} · {profile.updatedAt}</span></div></div><ArrowRight size={20} />
            <div className="compare-role"><div className="role-icon">岗</div><div><strong>{selected.name}</strong><span>{selected.company} · {selected.domain}</span></div></div>
            <div className="match-score"><span>综合匹配度 <Info size={13} /></span><div><strong>{score}%</strong><StatusTag tone={score >= 75 ? 'success' : 'info'}>{score >= 75 ? '中高置信度' : '中等置信度'}</StatusTag></div><ScoreBar value={score} /></div>
          </section>
          <div className="match-actions"><button className="secondary-button" onClick={() => setAdding(true)}><FilePlus2 size={16} />补充证据</button><button className="secondary-button" onClick={recompute} disabled={recomputing}><RefreshCw className={recomputing ? 'spin' : ''} size={16} />{recomputing ? '重新计算中' : '重新计算'}</button><button className="primary-button" onClick={() => { notify('已根据当前岗位差距生成 12 周发展路径'); onNavigate('learning') }}><Route size={16} />由差距生成发展路径</button></div>
          <div className="match-layout">
            <Panel title="维度得分" subtitle="规则分数与 LLM 语义判断结合" className="dimension-panel"><div className="dimension-list">{dimensions.map(([label, value]) => <ScoreBar key={label} label={label} value={score > selected.score && label === '项目证据' ? value + 6 : value} tone={value < 72 ? 'amber' : 'teal'} />)}</div></Panel>
            <Panel title="证据对比明细" subtitle="已匹配 32 项 / 岗位要求 41 项" action={<div className="segment-control small">{['全部', '匹配', '深度不足', '证据不足'].map((item) => <button className={filter === item ? 'active' : ''} onClick={() => setFilter(item)} key={item}>{item}</button>)}</div>}>
              <div className="match-table"><div className="match-table-head"><span>能力项</span><span>候选人证据</span><span>结果</span></div>{rows.map((row) => <button key={row.skill}><div><strong>{row.skill}</strong><StatusTag tone={row.importance === '必需' ? 'info' : 'neutral'}>{row.importance}</StatusTag></div><p>{row.evidence}</p><div><StatusTag tone={row.result === '匹配' ? 'success' : row.result === '可迁移' ? 'info' : 'warning'}>{row.result}</StatusTag><small>相关度 {row.score / 100}</small></div></button>)}</div>
            </Panel>
            <Panel title="差距洞察" subtitle="将直接驱动发展路径" className="gap-panel">
              <div className="gap-list"><button><StatusTag tone="warning">掌握深度不足</StatusTag><strong>实时控制</strong><p>当前证据未体现控制周期、延迟、抖动和稳定性指标。</p><span>查看要求与提升建议 <ArrowRight size={14} /></span></button><button><StatusTag tone="warning">证据不足</StatusTag><strong>Sim2Real</strong><p>缺少仿真到真实平台的迁移实验与量化结果。</p><span>查看需要补充的证据 <ArrowRight size={14} /></span></button><button className="transfer"><StatusTag tone="info">可迁移</StatusTag><strong>SLAM → 多传感器定位</strong><p>已有定位经验可迁移，建议补充多传感器时序与融合定位证据。</p><span>查看迁移路径 <ArrowRight size={14} /></span></button></div>
            </Panel>
          </div>
          <Panel title="发展路径预览" subtitle="由岗位差距、前置能力和可迁移关系生成"><div className="path-preview">{['实时控制基础', '仿真到现实迁移', '系统集成作品'].map((item, index) => <div key={item}><i>{index + 1}</i><div><strong>{item}</strong><span>{index === 0 ? '2–3 周 · 课程 + 实践' : index === 1 ? '3–4 周 · 仿真实验' : '4–6 周 · 项目交付'}</span></div>{index < 2 ? <ArrowRight size={18} /> : <CheckCircle2 size={18} />}</div>)}</div></Panel>
        </section>
      ) : <div className="match-select-hint"><BriefcaseBusiness size={22} /><strong>选择一个岗位查看详细差距</strong><span>岗位卡片先提供推荐理由和主要风险，完整分析仅在选择后展开。</span></div>}

      {adding ? <Modal title="补充匹配证据" onClose={() => setAdding(false)}><form className="evidence-form" onSubmit={(event) => { event.preventDefault(); setAdding(false); notify('补充证据已保存，请重新计算匹配') }}><label>关联能力<select><option>实时控制</option><option>Sim2Real</option><option>系统集成</option></select></label><label>证据描述<textarea defaultValue="在 100Hz 控制周期下完成底盘控制器调试，并记录延迟和跟踪误差。" /></label><label>证据来源<input defaultValue="机器人系统课程项目 / 控制实验报告" /></label><div className="form-note"><XCircle size={16} />补充内容将标记为“用户提供”，不会自动视为已验证事实。</div><div className="modal-actions"><button type="button" className="secondary-button" onClick={() => setAdding(false)}>取消</button><button className="primary-button">保存证据</button></div></form></Modal> : null}
    </div>
  )
}
