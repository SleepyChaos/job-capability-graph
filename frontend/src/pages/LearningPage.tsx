import { ArrowLeft, ArrowRight, Check, Circle, Clock3, PlayCircle, RotateCcw, Target } from 'lucide-react'
import { useState } from 'react'
import { Panel, ScoreBar, StatusTag } from '../components/ui'
import type { CandidateProfile, PageId } from '../types'

const steps = [
  { id: 1, title: '实时控制基础', weeks: '第 1–3 周', target: '从“证据不足”提升到“熟悉”', task: '实现 100Hz 移动底盘控制器，记录周期、延迟、跟踪误差与稳定性。', outputs: ['控制原理笔记', '可运行代码', '性能评测报告'], impact: 4 },
  { id: 2, title: '仿真到现实迁移', weeks: '第 4–7 周', target: '建立 Sim2Real 可验证证据', task: '在仿真中训练或调试策略，完成真机迁移并对比仿真/真实指标差异。', outputs: ['迁移实验设计', '对比数据', '复盘文档'], impact: 6 },
  { id: 3, title: '系统集成作品', weeks: '第 8–12 周', target: '形成岗位级综合项目证据', task: '集成感知、规划与控制模块，完成异常恢复、日志观测和交付说明。', outputs: ['系统演示', '架构说明', '故障与性能报告'], impact: 7 },
]

export function LearningPage({ profile, selectedJob, onNavigate, notify }: { profile: CandidateProfile; selectedJob: string; onNavigate: (page: PageId) => void; notify: (message: string) => void }) {
  const [completed, setCompleted] = useState<number[]>([])
  const [selected, setSelected] = useState(1)
  const item = steps.find((step) => step.id === selected) ?? steps[0]
  const toggle = (id: number) => { setCompleted((items) => items.includes(id) ? items.filter((item) => item !== id) : [...items, id]); notify('学习步骤状态已更新') }
  return (
    <div className="page-stack">
      <div className="page-intro"><div><h2>能力发展路径</h2><p>{profile.name} · 画像 v{profile.version} → {selectedJob || '具身智能系统集成工程师'} · 由能力差距驱动 · 计划周期 12 周</p></div><div className="intro-actions"><button className="secondary-button" onClick={() => onNavigate('match')}><ArrowLeft size={15} />返回差距分析</button><button className="secondary-button" onClick={() => { setCompleted([]); notify('路径进度已重置') }}><RotateCcw size={15} />重置演示</button></div></div>
      <section className="learning-progress"><div><Target size={22} /><div><strong>目标匹配提升</strong><span>完成全部路径后预计提升至 88%–92%</span></div></div><ScoreBar value={completed.length / steps.length * 100} /><b>{completed.length} / {steps.length} 步完成</b></section>
      <div className="learning-layout">
        <Panel title="12 周路线图" subtitle="依赖顺序由能力图谱生成" className="roadmap-panel">
          <div className="roadmap">{steps.map((step, index) => <button className={`${selected === step.id ? 'selected' : ''} ${completed.includes(step.id) ? 'completed' : ''}`} key={step.id} onClick={() => setSelected(step.id)}><i>{completed.includes(step.id) ? <Check size={15} /> : step.id}</i><div><span>{step.weeks}</span><strong>{step.title}</strong><small>{step.target}</small></div><em>预计 +{step.impact} 分</em>{index < steps.length - 1 ? <ArrowRight className="roadmap-arrow" size={18} /> : null}</button>)}</div>
        </Panel>
        <Panel title={item.title} subtitle={item.weeks} className="learning-detail">
          <StatusTag tone={completed.includes(item.id) ? 'success' : 'info'}>{completed.includes(item.id) ? '已完成' : '当前步骤'}</StatusTag>
          <h3>实践任务</h3><p>{item.task}</p>
          <h3>前置能力</h3><div className="skill-tags"><span>Python / C++</span><span>ROS 2</span><span>{item.id === 1 ? '控制理论' : '机器人系统基础'}</span></div>
          <h3>验证产出</h3><ul className="output-list">{item.outputs.map((output) => <li key={output}>{completed.includes(item.id) ? <Check size={16} /> : <Circle size={14} />}<span>{output}</span></li>)}</ul>
          <div className="duration-note"><Clock3 size={16} />建议每周投入 8–10 小时，先完成产出再更新画像证据。</div>
          <button className="primary-button full" onClick={() => toggle(item.id)}>{completed.includes(item.id) ? '取消完成标记' : '标记该步骤完成'}</button>
        </Panel>
      </div>
      <Panel title="完成后的证据回流" subtitle="学习记录不会直接提高匹配分，只有经过确认的实践产出会成为画像证据"><div className="feedback-flow"><div><PlayCircle size={20} /><strong>完成实践任务</strong></div><ArrowRight size={18} /><div><Check size={20} /><strong>提交可验证产出</strong></div><ArrowRight size={18} /><div><Target size={20} /><strong>更新画像并重新匹配</strong></div></div></Panel>
    </div>
  )
}
