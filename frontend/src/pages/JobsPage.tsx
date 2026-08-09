import {
  ArrowRight,
  ArrowUpRight,
  Building2,
  Check,
  CheckCircle2,
  CircleDotDashed,
  Database,
  FileText,
  GitCompareArrows,
  ShieldCheck,
  Sparkles,
} from 'lucide-react'
import { useState } from 'react'
import { Modal, Panel, ScoreBar, StatusTag } from '../components/ui'
import { roleCandidates } from '../data/mockData'

export function JobsPage({ notify }: { notify: (message: string) => void }) {
  const [selectedId, setSelectedId] = useState(1)
  const [showDefinition, setShowDefinition] = useState(false)
  const [approvedIds, setApprovedIds] = useState<number[]>([])
  const [runVersion, setRunVersion] = useState(4)
  const selected = roleCandidates.find((item) => item.id === selectedId) ?? roleCandidates[0]

  const runAutomaticDiscovery = () => {
    setRunVersion((version) => version + 1)
    notify('综合自动预测已完成：数据库快照与 3 个候选岗位已更新')
  }

  const approve = () => {
    setApprovedIds((items) => items.includes(selected.id) ? items : [...items, selected.id])
    setShowDefinition(false)
    notify(`${selected.name} 已通过新岗位专项审批并写入岗位定义库`)
  }

  return (
    <div className="page-stack discovery-page">
      <div className="page-intro">
        <div>
          <h2>综合自动预测候选</h2>
          <p>系统周期性扫描正式数据库，综合岗位覆盖缺口、技术推进和真实需求，输出全局新岗位候选。</p>
        </div>
        <button className="secondary-button" onClick={runAutomaticDiscovery}><Sparkles size={16} />运行自动预测</button>
      </div>

      <section className="discovery-boundary">
        <div><Database size={20} /><span><strong>可信事实数据库</strong>JD 岗位簇 · T/L 技术词 · 技术里程碑</span></div>
        <ArrowRight size={18} />
        <div><CircleDotDashed size={20} /><span><strong>综合自动预测模型</strong>覆盖缺口、技术推进、真实需求与组合创新</span></div>
        <ArrowRight size={18} />
        <div><ShieldCheck size={20} /><span><strong>专项审批入库</strong>审批新岗位定义，不审核前置抽取事实</span></div>
      </section>

      <Panel title="自动预测任务" subtitle="每周基于正式数据库快照重新计算，不读取待审核抽取数据">
        <div className="auto-discovery-status">
          <div><CheckCircle2 size={19} /><span><strong>最近运行完成</strong>数据库版本 2026.08.09 · 算法版本 discovery-v0.{runVersion}</span></div>
          <div><span>扫描岗位簇</span><strong>43</strong></div>
          <div><span>技术组合</span><strong>186</strong></div>
          <div><span>输出候选</span><strong>3</strong></div>
        </div>
      </Panel>

      <div className="jobs-layout">
        <Panel title="综合预测候选" subtitle="按综合证据分排序" className="candidate-list-panel">
          <div className="candidate-list">
            {roleCandidates.map((role) => (
              <button className={selected.id === role.id ? 'selected' : ''} onClick={() => setSelectedId(role.id)} key={role.id}>
                <div>
                  <StatusTag tone={approvedIds.includes(role.id) ? 'success' : role.stage === '新兴岗位' ? 'warning' : 'info'}>{approvedIds.includes(role.id) ? '已审批入库' : role.stage}</StatusTag>
                  <strong>{role.name}</strong>
                  <span>{role.primaryDomain}</span>
                </div>
                <b>{role.score}</b>
              </button>
            ))}
          </div>
        </Panel>

        <Panel className="candidate-detail">
          <div className="candidate-title">
            <div>
              <StatusTag tone={approvedIds.includes(selected.id) ? 'success' : 'warning'}>{approvedIds.includes(selected.id) ? '已审批入库' : selected.stage}</StatusTag>
              <h2>{selected.name}</h2>
              <p>{selected.summary}</p>
            </div>
            <div className="candidate-score"><strong>{selected.score}</strong><span>综合证据分</span></div>
          </div>
          <div className="candidate-facts">
            <div><FileText size={17} /><span>关联 JD</span><strong>{selected.jdCount}</strong></div>
            <div><Building2 size={17} /><span>独立企业</span><strong>{selected.companies}</strong></div>
            <div><ArrowUpRight size={17} /><span>近窗增长</span><strong>+{selected.growth}%</strong></div>
            <div><GitCompareArrows size={17} /><span>主领域</span><strong>{selected.primaryDomain.split(' ')[0]}</strong></div>
          </div>
          <div className="detail-section"><h3>岗位定义的 T 领域归属</h3><div className="domain-assignment"><div><span>主领域</span><strong>{selected.primaryDomain}</strong><ScoreBar value={86} /></div>{selected.secondaryDomains.map((domain, index) => <div key={domain}><span>次领域</span><strong>{domain}</strong><ScoreBar value={68 - index * 11} tone="blue" /></div>)}</div></div>
          <div className="detail-section"><h3>创新能力组合</h3><div className="skill-tags">{selected.skills.map((skill) => <span key={skill}>{skill}</span>)}</div></div>
          <div className="detail-section"><h3>新岗位定义依据</h3><ol className="evidence-list">{selected.evidence.map((item) => <li key={item}><Check size={16} /><span>{item}</span></li>)}</ol></div>
          <div className="detail-actions"><button className="secondary-button" onClick={() => notify('已将候选标记为继续观察')}>继续观察</button><button className="primary-button" disabled={approvedIds.includes(selected.id)} onClick={() => setShowDefinition(true)}>{approvedIds.includes(selected.id) ? '岗位定义已入库' : '完善定义并专项审批'}</button></div>
        </Panel>
      </div>

      {showDefinition ? (
        <Modal title="新岗位定义与专项审批" onClose={() => setShowDefinition(false)}>
          <div className="role-card-preview">
            <div className="special-review-note"><ShieldCheck size={17} /><span><strong>独立审批流程</strong>本次审批对象是基于数据库证据创新形成的岗位定义，不进入数据审核中心。</span></div>
            <StatusTag tone="warning">机械事实 + LLM 表达优化</StatusTag>
            <h3>{selected.name}</h3><p>{selected.summary}</p>
            <dl><div><dt>核心职责</dt><dd>建设具身智能数据与训练基础设施；联通仿真、真实数据和模型评测闭环。</dd></div><div><dt>必需技能</dt><dd>{selected.skills.slice(0, 3).join('、')}</dd></div><div><dt>加分技能</dt><dd>{selected.skills.slice(3).join('、')}</dd></div><div><dt>证据快照</dt><dd>{selected.jdCount} 条 JD · {selected.companies} 家企业 · 数据库版本 2026.08.09</dd></div></dl>
            <div className="modal-actions"><button className="secondary-button" onClick={() => { setShowDefinition(false); notify('岗位定义已退回继续完善') }}>退回修改</button><button className="primary-button" onClick={approve}>批准定义并入库</button></div>
          </div>
        </Modal>
      ) : null}
    </div>
  )
}
