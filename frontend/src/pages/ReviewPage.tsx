import {
  Check,
  ChevronRight,
  Database,
  FileCheck2,
  Fingerprint,
  History,
  Layers3,
  Link2,
  RefreshCw,
  Search,
  ShieldCheck,
  Tags,
  X,
} from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { dataCenterApi, type ReviewActionCode, type ReviewTask } from '../api/dataCenter'
import { MetricStrip, Modal, Panel, StatusTag } from '../components/ui'

const statusTabs = [
  { code: '', label: '全部' },
  { code: 'queued', label: '待审核' },
  { code: 'reviewing', label: '审核中' },
  { code: 'approved', label: '已通过' },
  { code: 'rejected', label: '已驳回' },
  { code: 'needs_revision', label: '需修改' },
]

const targetTypeLabels: Record<string, string> = {
  milestone: '产业里程碑',
  job_role_version: '岗位标准定义',
  job_cluster_assignment: 'JD 聚类归属',
  technology_mapping: '技术词映射',
}

const reasonLabels: Record<string, string> = {
  statistical_role_version_requires_review: '统计生成的岗位版本需人工确认',
  high_impact_fact_manual_review: '高影响事实需人工复核',
}

type SnapshotRecord = Record<string, unknown>

function taskTitle(task: ReviewTask): string {
  const snapshot = task.target_snapshot
  return String(snapshot.role_name ?? snapshot.milestone_name ?? snapshot.title ?? `目标 #${task.target_id}`)
}

function textValue(value: unknown, fallback = '—'): string {
  if (value === null || value === undefined || value === '') return fallback
  return String(value)
}

function numberValue(value: unknown): number {
  const parsed = Number(value)
  return Number.isFinite(parsed) ? parsed : 0
}

function snapshotList(value: unknown): SnapshotRecord[] {
  if (!Array.isArray(value)) return []
  return value.filter((item): item is SnapshotRecord => typeof item === 'object' && item !== null)
}

function statusTone(status: string): 'warning' | 'success' | 'danger' | 'info' {
  if (status === 'queued') return 'warning'
  if (status === 'approved') return 'success'
  if (status === 'rejected') return 'danger'
  return 'info'
}

function statusLabel(status: string): string {
  return statusTabs.find((tab) => tab.code === status)?.label ?? status
}

export function ReviewPage({ notify }: { notify: (message: string) => void }) {
  const [tasks, setTasks] = useState<ReviewTask[]>([])
  const [status, setStatus] = useState('')
  const [targetType, setTargetType] = useState('job_role_version')
  const [query, setQuery] = useState('')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [actingCode, setActingCode] = useState('')
  const [selectedCode, setSelectedCode] = useState('')
  const [traceOpen, setTraceOpen] = useState(false)
  const [reviewerCode, setReviewerCode] = useState(() => window.localStorage.getItem('reviewer_code') ?? 'reviewer-demo')

  useEffect(() => {
    const controller = new AbortController()
    setLoading(true)
    dataCenterApi.reviews(null, controller.signal)
      .then((items) => {
        setTasks(items)
        setSelectedCode(items.find((item) => item.target_type_code === 'job_role_version')?.task_code ?? items[0]?.task_code ?? '')
      })
      .catch((reason: Error) => { if (reason.name !== 'AbortError') setError(reason.message) })
      .finally(() => setLoading(false))
    return () => controller.abort()
  }, [])

  const stats = useMemo(() => {
    const next = {
      approved: 0,
      queued: 0,
      reviewing: 0,
      rejected: 0,
      needs_revision: 0,
      roleDefinitions: 0,
      milestones: 0,
      evidenceMarks: 0,
    }
    for (const task of tasks) {
      if (task.task_status_code === 'approved') next.approved += 1
      else if (task.task_status_code === 'queued') next.queued += 1
      else if (task.task_status_code === 'reviewing') next.reviewing += 1
      else if (task.task_status_code === 'rejected') next.rejected += 1
      else if (task.task_status_code === 'needs_revision') next.needs_revision += 1
      if (task.target_type_code === 'job_role_version') {
        next.roleDefinitions += 1
        next.evidenceMarks += snapshotList(task.target_snapshot.requirements).length
      } else if (task.target_type_code === 'milestone') {
        next.milestones += 1
      }
    }
    return next
  }, [tasks])

  const statusCount = (code: string) => code === '' ? tasks.length : numberValue(stats[code as keyof typeof stats])

  const filtered = useMemo(() => {
    const normalizedQuery = query.trim().toLowerCase()
    return tasks.filter((task) => {
      if (targetType && task.target_type_code !== targetType) return false
      if (status && task.task_status_code !== status) return false
      if (normalizedQuery && !`${taskTitle(task)} ${task.task_code}`.toLowerCase().includes(normalizedQuery)) return false
      return true
    })
  }, [tasks, status, targetType, query])

  const selected = filtered.find((task) => task.task_code === selectedCode) ?? filtered[0] ?? null
  const selectedRequirements = selected ? snapshotList(selected.target_snapshot.requirements) : []
  const selectedReasonCodes = selected?.reason?.codes ?? []

  const saveReviewer = (value: string) => {
    setReviewerCode(value)
    window.localStorage.setItem('reviewer_code', value)
  }

  const act = async (task: ReviewTask, action: ReviewActionCode) => {
    if (!reviewerCode.trim()) {
      notify('请先填写审核员编码（X-Reviewer-Code）')
      return
    }
    setActingCode(task.task_code)
    try {
      await dataCenterApi.reviewAction(task, action, reviewerCode.trim())
      setTasks((all) => all.map((item) => {
        if (item.task_code !== task.task_code) return item
        const next = action === 'claim' ? 'reviewing' : action === 'approve' ? 'approved' : action === 'reject' ? 'rejected' : 'needs_revision'
        return { ...item, task_status_code: next, assigned_user_code: reviewerCode.trim() }
      }))
      notify(`审核动作已记录：${action}（审计快照已写入 biz_review_action）`)
    } catch (reason) {
      notify(`审核失败：${(reason as Error).message}`)
    } finally {
      setActingCode('')
    }
  }

  return (
    <div className="page-stack annotation-review-page">
      <div className="page-intro">
        <div><h2>数据标注审核中心</h2><p>对岗位进行标准化定义与证据标注，事实与结果分层保存，确保每条结论可回溯。</p></div>
        <label className="inline-search" title="开发期审核身份，阶段 D 将迁移为 JWT 登录">审核员编码<input value={reviewerCode} onChange={(event) => saveReviewer(event.target.value)} placeholder="reviewer-demo" /></label>
      </div>

      <section className="annotation-story" aria-label="标注闭环">
        <div className="annotation-story-copy">
          <span>ANNOTATION LINEAGE</span>
          <h3>一条岗位结论，四步回溯到底</h3>
          <p>原始事实保持不变，标准结果独立成版；审核动作与证据索引共同组成可复核、可解释的追溯链。</p>
        </div>
        <div className="annotation-story-flow">
          <div><i><Database size={16} /></i><span>01 原始事实</span><strong>来源快照</strong></div>
          <ChevronRight size={16} />
          <div><i><Tags size={16} /></i><span>02 证据标注</span><strong>技术与权重</strong></div>
          <ChevronRight size={16} />
          <div><i><Layers3 size={16} /></i><span>03 标准结果</span><strong>岗位版本</strong></div>
          <ChevronRight size={16} />
          <div><i><History size={16} /></i><span>04 审核留痕</span><strong>人员与动作</strong></div>
        </div>
      </section>

      <MetricStrip items={[
        { label: '岗位标准定义', value: stats.roleDefinitions.toLocaleString(), delta: '个可审核版本' },
        { label: '成果证据标注', value: stats.evidenceMarks.toLocaleString(), delta: '项技术要求' },
        { label: '产业事实标注', value: stats.milestones.toLocaleString(), delta: '条里程碑' },
        { label: '已完成审核', value: stats.approved.toLocaleString(), delta: `共 ${tasks.length.toLocaleString()} 条可追溯任务` },
      ]} />

      <div className="annotation-review-toolbar">
        <div className="annotation-target-tabs" aria-label="标注对象">
          <button className={targetType === 'job_role_version' ? 'active' : ''} onClick={() => setTargetType('job_role_version')}>岗位标准定义 <em>{stats.roleDefinitions}</em></button>
          <button className={targetType === 'milestone' ? 'active' : ''} onClick={() => setTargetType('milestone')}>产业事实标注 <em>{stats.milestones}</em></button>
          <button className={targetType === '' ? 'active' : ''} onClick={() => setTargetType('')}>全部对象 <em>{tasks.length}</em></button>
        </div>
        <label className="inline-search"><Search size={15} /><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="搜索岗位名称或追溯编码" /></label>
      </div>

      <div className="annotation-review-layout">
        <Panel title="标注审核队列" subtitle={`${filtered.length.toLocaleString()} 条 · 选择结论查看完整证据链`}>
          <div className="review-status-tabs">
            {statusTabs.map((tab) => <button className={status === tab.code ? 'active' : ''} onClick={() => setStatus(tab.code)} key={tab.code || 'all'}>{tab.label}<em>{statusCount(tab.code)}</em></button>)}
          </div>
          {error ? <div className="empty-state"><ShieldCheck size={26} /><strong>加载失败</strong><span>{error}</span></div> : loading ? <div className="empty-state"><RefreshCw className="spin" size={22} /><strong>正在加载审核队列…</strong></div> : filtered.length === 0 ? (
            <div className="empty-state"><ShieldCheck size={26} /><strong>当前筛选下没有审核项</strong><span>切换状态或清除搜索条件查看其他记录。</span></div>
          ) : (
            <div className="annotation-task-list" role="listbox" aria-label="标注审核任务">
              {filtered.slice(0, 120).map((task) => {
                const requirements = snapshotList(task.target_snapshot.requirements)
                return (
                  <button className={selected?.task_code === task.task_code ? 'selected' : ''} onClick={() => setSelectedCode(task.task_code)} key={task.task_code} role="option" aria-selected={selected?.task_code === task.task_code}>
                    <div><StatusTag tone={statusTone(task.task_status_code)}>{statusLabel(task.task_status_code)}</StatusTag><small>{targetTypeLabels[task.target_type_code] ?? task.target_type_code}</small></div>
                    <strong>{taskTitle(task)}</strong>
                    <span>{task.target_type_code === 'job_role_version' ? `${requirements.length} 项技术要求 · 证据强度 ${numberValue(task.target_snapshot.evidence_strength_score).toFixed(1)}` : `${textValue(task.target_snapshot.event_year)} 年 · ${textValue(task.target_snapshot.milestone_type_code)}`}</span>
                    <code>{task.task_code}</code>
                  </button>
                )
              })}
              {filtered.length > 120 ? <p className="table-note">当前显示前 120 条，可通过搜索快速定位其余 {filtered.length - 120} 条。</p> : null}
            </div>
          )}
        </Panel>

        <Panel className="annotation-detail-panel">
          {!selected ? (
            <div className="empty-state"><FileCheck2 size={26} /><strong>选择一条结论查看标注链</strong></div>
          ) : (
            <div className="annotation-detail">
              <div className="annotation-detail-head">
                <div>
                  <div className="record-meta"><StatusTag tone={statusTone(selected.task_status_code)}>{statusLabel(selected.task_status_code)}</StatusTag><span>{targetTypeLabels[selected.target_type_code] ?? selected.target_type_code}</span><span>优先级 {numberValue(selected.priority_score).toFixed(1)}</span></div>
                  <h2>{taskTitle(selected)}</h2>
                  <p>{selected.target_type_code === 'job_role_version' ? '系统依据聚类事实生成岗位标准版本，技术要求、证据强度与演变事件分别留存。' : textValue(selected.target_snapshot.description_text, '该产业事实已进入人工标注与审核流程。')}</p>
                </div>
                <button className="secondary-button" onClick={() => setTraceOpen(true)}><Fingerprint size={15} />查看完整追溯</button>
              </div>

              <div className="annotation-lineage">
                <div><span>事实入口</span><strong>{textValue(selected.reason?.evolution_event_code ?? selected.target_snapshot.milestone_code, `target:${selected.target_id}`)}</strong></div>
                <ChevronRight size={14} />
                <div><span>标注对象</span><strong>{selected.target_type_code === 'job_role_version' ? `${selectedRequirements.length} 项技术要求` : `${Array.isArray(selected.target_snapshot.technology_codes) ? selected.target_snapshot.technology_codes.length : 0} 项技术关联`}</strong></div>
                <ChevronRight size={14} />
                <div><span>结果版本</span><strong>{selected.target_type_code === 'job_role_version' ? `v${textValue(selected.target_snapshot.version_no)}` : textValue(selected.target_snapshot.verification_status_code)}</strong></div>
                <ChevronRight size={14} />
                <div><span>审核记录</span><strong>{selected.assigned_user_code ?? '待领取'}</strong></div>
              </div>

              <div className="annotation-layer-grid">
                <section className="annotation-layer-card fact-layer">
                  <header><span>FACT LAYER</span><strong><Database size={15} />事实层 · 原始快照</strong></header>
                  <dl>
                    <div><dt>事实对象</dt><dd>{textValue(selected.target_snapshot.role_code ?? selected.target_snapshot.milestone_code)}</dd></div>
                    <div><dt>事实时间</dt><dd>{textValue(selected.target_snapshot.valid_from ?? selected.target_snapshot.event_date ?? selected.target_snapshot.event_year)}</dd></div>
                    <div><dt>证据入口</dt><dd>{textValue(selected.reason?.evolution_event_code ?? selected.reason?.publish_score)}</dd></div>
                    <div><dt>快照策略</dt><dd>只读留存 · 不覆盖源事实</dd></div>
                  </dl>
                </section>
                <section className="annotation-layer-card result-layer">
                  <header><span>RESULT LAYER</span><strong><FileCheck2 size={15} />结果层 · 标准定义</strong></header>
                  <dl>
                    <div><dt>标准名称</dt><dd>{taskTitle(selected)}</dd></div>
                    <div><dt>结果版本</dt><dd>{selected.target_type_code === 'job_role_version' ? `第 ${textValue(selected.target_snapshot.version_no)} 版` : textValue(selected.target_snapshot.milestone_type_code)}</dd></div>
                    <div><dt>证据强度</dt><dd>{selected.target_type_code === 'job_role_version' ? `${numberValue(selected.target_snapshot.evidence_strength_score).toFixed(2)} / 100` : `发布评分 ${textValue(selected.reason?.publish_score)}`}</dd></div>
                    <div><dt>审核结果</dt><dd>{statusLabel(selected.task_status_code)}</dd></div>
                  </dl>
                </section>
              </div>

              <section className="annotation-evidence-section">
                <div className="section-heading">
                  <div><span>EVIDENCE ANNOTATIONS</span><h3>{selected.target_type_code === 'job_role_version' ? '技术要求与证据权重' : '产业事实标注字段'}</h3></div>
                  <StatusTag tone="info">{selected.target_type_code === 'job_role_version' ? `${selectedRequirements.length} 项标注` : '事实快照'}</StatusTag>
                </div>
                {selected.target_type_code === 'job_role_version' ? (
                  selectedRequirements.length > 0 ? <div className="annotation-evidence-table">
                    <div className="annotation-evidence-head"><span>技术编码</span><span>标注类型</span><span>重要度</span><span>近期活跃度</span><span>证据状态</span></div>
                    {selectedRequirements.map((requirement, index) => (
                      <div className="annotation-evidence-row" key={`${textValue(requirement.technology_code)}-${index}`}>
                        <strong><Link2 size={13} />{textValue(requirement.technology_code)}</strong>
                        <span>{requirement.type === 'bonus' ? '加分能力' : '必备能力'}</span>
                        <span><i style={{ width: `${Math.min(100, numberValue(requirement.importance))}%` }} />{numberValue(requirement.importance).toFixed(1)}</span>
                        <span>{numberValue(requirement.recent_activity).toFixed(1)}</span>
                        <StatusTag tone="success">已关联</StatusTag>
                      </div>
                    ))}
                  </div> : <div className="empty-state compact"><Tags size={22} /><strong>该版本没有技术要求标注</strong></div>
                ) : (
                  <div className="milestone-annotation-card">
                    <div><span>发生年份</span><strong>{textValue(selected.target_snapshot.event_year)}</strong></div>
                    <div><span>事实类型</span><strong>{textValue(selected.target_snapshot.milestone_type_code)}</strong></div>
                    <div><span>成熟度变化</span><strong>{textValue(selected.target_snapshot.maturity_delta_score)}</strong></div>
                    <p>{textValue(selected.target_snapshot.description_text)}</p>
                  </div>
                )}
              </section>

              <footer className="annotation-audit-footer">
                <div><ShieldCheck size={17} /><span>审核留痕</span><strong>{selected.assigned_user_code ?? '尚未领取'}</strong></div>
                <div><History size={17} /><span>审核任务</span><strong>{selected.task_code}</strong></div>
                <div><Fingerprint size={17} /><span>存储分层</span><strong>事实快照 → 标准结果 → 审核动作</strong></div>
              </footer>

              <div className="review-actions">
                <div className="review-action-hint"><ShieldCheck size={16} /><span>所有处置都会保存审核人、动作、时间与目标快照，不修改原始事实记录。</span></div>
                <div className="review-action-buttons">
                  <button className="secondary-button" disabled={actingCode !== '' || selected.task_status_code !== 'queued'} onClick={() => act(selected, 'claim')}>领取任务</button>
                  <button className="secondary-button" disabled={actingCode !== '' || selected.task_status_code === 'rejected'} onClick={() => act(selected, 'reject')}><X size={15} />驳回</button>
                  <button className="primary-button" disabled={actingCode !== '' || selected.task_status_code === 'approved'} onClick={() => act(selected, 'approve')}><Check size={15} />确认并入标准库</button>
                </div>
              </div>
            </div>
          )}
        </Panel>
      </div>

      {selected && traceOpen ? (
        <Modal title={`结论追溯单 · ${selected.task_code}`} onClose={() => setTraceOpen(false)}>
          <div className="record-detail-form trace-detail-form">
            <div className="trace-ledger">
              <div><span>审核任务</span><strong>{selected.task_code}</strong></div>
              <div><span>事实对象</span><strong>{textValue(selected.target_snapshot.role_code ?? selected.target_snapshot.milestone_code, `target:${selected.target_id}`)}</strong></div>
              <div><span>演变 / 发布证据</span><strong>{textValue(selected.reason?.evolution_event_code ?? selected.reason?.publish_score)}</strong></div>
              <div><span>结果状态</span><strong>{statusLabel(selected.task_status_code)}</strong></div>
              <div><span>审核人</span><strong>{selected.assigned_user_code ?? '尚未领取'}</strong></div>
              <div><span>存储路径</span><strong>biz_review_task → biz_review_action</strong></div>
            </div>
            <label>进入审核原因<input value={selectedReasonCodes.map((code) => reasonLabels[code] ?? code).join('；') || '常规人工复核'} readOnly /></label>
            <label>不可变目标快照<textarea rows={12} readOnly value={JSON.stringify(selected.target_snapshot, null, 2)} /></label>
            <div className="modal-actions"><button type="button" className="secondary-button" onClick={() => setTraceOpen(false)}>关闭追溯单</button></div>
          </div>
        </Modal>
      ) : null}
    </div>
  )
}
