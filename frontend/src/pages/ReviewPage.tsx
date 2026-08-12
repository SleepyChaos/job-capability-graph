import { Check, Eye, RefreshCw, Search, ShieldCheck, X } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { dataCenterApi, type ReviewActionCode, type ReviewTask } from '../api/dataCenter'
import { MetricStrip, Modal, Panel, StatusTag } from '../components/ui'

const statusTabs = [
  { code: 'queued', label: '待审核' },
  { code: 'reviewing', label: '审核中' },
  { code: 'approved', label: '已通过' },
  { code: 'rejected', label: '已驳回' },
  { code: 'needs_revision', label: '需修改' },
  { code: '', label: '全部' },
]

const targetTypeLabels: Record<string, string> = {
  milestone: '技术里程碑候选',
  job_role_version: '岗位版本建议',
  job_cluster_assignment: 'JD 聚类归属',
  technology_mapping: '技术词映射',
}

function taskTitle(task: ReviewTask): string {
  const snapshot = task.target_snapshot
  return String(snapshot.role_name ?? snapshot.milestone_name ?? snapshot.title ?? `目标 #${task.target_id}`)
}

export function ReviewPage({ notify }: { notify: (message: string) => void }) {
  const [tasks, setTasks] = useState<ReviewTask[]>([])
  const [status, setStatus] = useState('queued')
  const [query, setQuery] = useState('')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [actingCode, setActingCode] = useState('')
  const [detail, setDetail] = useState<ReviewTask | null>(null)
  const [reviewerCode, setReviewerCode] = useState(() => window.localStorage.getItem('reviewer_code') ?? 'reviewer-demo')

  useEffect(() => {
    const controller = new AbortController()
    setLoading(true)
    dataCenterApi.reviews(null, controller.signal)
      .then(setTasks)
      .catch((reason: Error) => { if (reason.name !== 'AbortError') setError(reason.message) })
      .finally(() => setLoading(false))
    return () => controller.abort()
  }, [])

  const saveReviewer = (value: string) => {
    setReviewerCode(value)
    window.localStorage.setItem('reviewer_code', value)
  }

  const filtered = useMemo(
    () => tasks.filter((task) => (status === '' || task.task_status_code === status) && taskTitle(task).toLowerCase().includes(query.toLowerCase())),
    [tasks, status, query],
  )

  const countBy = (code: string) => tasks.filter((task) => task.task_status_code === code).length

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
    <div className="page-stack">
      <div className="page-intro">
        <div><h2>数据审核中心</h2><p>只处理数据采集与抽取阶段的低置信度结果；新岗位定义在"新岗位发现"中执行专项审批。</p></div>
        <label className="inline-search" title="开发期审核身份，阶段 D 将迁移为 JWT 登录">审核员编码<input value={reviewerCode} onChange={(event) => saveReviewer(event.target.value)} placeholder="reviewer-demo" /></label>
      </div>
      <MetricStrip items={[
        { label: '待审核', value: String(countBy('queued')) },
        { label: '审核中', value: String(countBy('reviewing')) },
        { label: '已通过', value: String(countBy('approved')) },
        { label: '已驳回', value: String(countBy('rejected')) },
      ]} />
      <Panel title="低置信度抽取审核队列" subtitle="来自 /reviews/data 接口；岗位版本建议走 /job-roles/reviews 审核端点" action={<label className="inline-search"><Search size={15} /><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="搜索审核内容" /></label>}>
        <div className="review-status-tabs">{statusTabs.map((tab) => <button className={status === tab.code ? 'active' : ''} onClick={() => setStatus(tab.code)} key={tab.code || 'all'}>{tab.label}{tab.code ? <em style={{ marginLeft: 6 }}>{countBy(tab.code)}</em> : null}</button>)}</div>
        {error ? <div className="empty-state"><ShieldCheck size={26} /><strong>加载失败</strong><span>{error}</span></div> : loading ? <div className="empty-state"><RefreshCw className="spin" size={22} /><strong>正在加载审核队列…</strong></div> : (
          <div className="table-wrap">
            <table className="data-table">
              <thead><tr><th>类型 / 内容</th><th>原因</th><th>优先级</th><th>处理人</th><th>状态</th><th>操作</th></tr></thead>
              <tbody>{filtered.slice(0, 100).map((task) => (
                <tr key={task.task_code}>
                  <td><strong>{taskTitle(task)}</strong><small>{targetTypeLabels[task.target_type_code] ?? task.target_type_code} · {task.task_code}</small></td>
                  <td>{task.reason?.codes?.join('、') ?? '—'}</td>
                  <td>{Number(task.priority_score).toFixed(0)}</td>
                  <td>{task.assigned_user_code ?? '—'}</td>
                  <td><StatusTag tone={task.task_status_code === 'queued' ? 'warning' : task.task_status_code === 'approved' ? 'success' : task.task_status_code === 'rejected' ? 'danger' : 'info'}>{statusTabs.find((tab) => tab.code === task.task_status_code)?.label ?? task.task_status_code}</StatusTag></td>
                  <td>
                    <div className="review-actions">
                      <button title="查看快照" onClick={() => setDetail(task)}><Eye size={15} /></button>
                      <button title="领取" disabled={actingCode !== '' || task.task_status_code !== 'queued'} onClick={() => act(task, 'claim')}>领取</button>
                      <button title="通过" disabled={actingCode !== '' || task.task_status_code === 'approved'} onClick={() => act(task, 'approve')}><Check size={15} /></button>
                      <button title="驳回" disabled={actingCode !== '' || task.task_status_code === 'rejected'} onClick={() => act(task, 'reject')}><X size={15} /></button>
                    </div>
                  </td>
                </tr>
              ))}</tbody>
            </table>
            {filtered.length === 0 ? <div className="empty-state"><ShieldCheck size={26} /><strong>当前筛选下没有审核项</strong><span>切换状态或清除搜索条件查看其他记录。</span></div> : null}
            {filtered.length > 100 ? <p className="table-note">仅显示前 100 条，共 {filtered.length} 条。</p> : null}
          </div>
        )}
      </Panel>

      {detail ? (
        <Modal title={`审核快照 · ${detail.task_code}`} onClose={() => setDetail(null)}>
          <div className="record-detail-form">
            <div className="record-meta">
              <StatusTag tone="info">{targetTypeLabels[detail.target_type_code] ?? detail.target_type_code}</StatusTag>
              <span>优先级 {Number(detail.priority_score).toFixed(1)}</span>
              <span>{detail.task_status_code}</span>
            </div>
            <label>内容摘要<input value={taskTitle(detail)} readOnly /></label>
            <label>目标快照 JSON<textarea rows={14} readOnly value={JSON.stringify(detail.target_snapshot, null, 2)} /></label>
            <div className="modal-actions"><button type="button" className="secondary-button" onClick={() => setDetail(null)}>关闭</button></div>
          </div>
        </Modal>
      ) : null}
    </div>
  )
}
