import { Archive, Eye, FileClock, RefreshCw, ShieldAlert } from 'lucide-react'
import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  discoveryApi,
  type CandidateListItem,
  type DiscoveryRun,
  type DiscoveryRunDetail,
} from '../api/discovery'
import { Modal, Panel, StatusTag } from '../components/ui'

// 前三种由界面触发，后两种目前只能由离线工具跑（它们要读 JD 之外的语料）。
// 记录库仍要认得它们的 mode_code——否则这两类运行会以原始码示人，
// 而它们恰恰是唯一参照系为招聘市场的两类产出。
const modeLabels: Record<string, string> = {
  automatic: '综合自动预测',
  technology_directed: '技术词定向推演',
  name_inference: '岗位名称推演',
  upstream_gap: '研究侧缺口分析',
  milestone_gap: '产业里程碑缺口分析',
}

const MODE_FILTERS = ['全部', ...Object.values(modeLabels)]

export function JobRecordsPage({ notify }: { notify: (message: string) => void }) {
  const [filter, setFilter] = useState('全部')
  const [runs, setRuns] = useState<DiscoveryRun[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [selectedRun, setSelectedRun] = useState<DiscoveryRun | null>(null)
  const [runDetail, setRunDetail] = useState<DiscoveryRunDetail | null>(null)
  const [runCandidates, setRunCandidates] = useState<CandidateListItem[]>([])

  const reload = useCallback(async (signal?: AbortSignal) => {
    const rows = await discoveryApi.runs(null, signal)
    setRuns(rows)
  }, [])

  useEffect(() => {
    const controller = new AbortController()
    setLoading(true)
    reload(controller.signal)
      .catch((reason: Error) => { if (reason.name !== 'AbortError') setError(reason.message) })
      .finally(() => setLoading(false))
    return () => controller.abort()
  }, [reload])

  useEffect(() => {
    if (!selectedRun) { setRunDetail(null); setRunCandidates([]); return }
    const controller = new AbortController()
    Promise.all([
      discoveryApi.runDetail(selectedRun.run_code, controller.signal),
      discoveryApi.candidates({ runCode: selectedRun.run_code, limit: 50 }, controller.signal),
    ])
      .then(([detail, page]) => { setRunDetail(detail); setRunCandidates(page.items) })
      .catch((reason: Error) => { if (reason.name !== 'AbortError') setError(reason.message) })
    return () => controller.abort()
  }, [selectedRun])

  const filteredRuns = useMemo(
    () => filter === '全部' ? runs : runs.filter((run) => modeLabels[run.mode_code] === filter),
    [runs, filter],
  )
  const successCount = runs.filter((run) => run.run_status_code === 'success').length
  const candidateTotal = runs.reduce((sum, run) => sum + run.candidate_count, 0)

  return (
    <div className="page-stack discovery-page">
      <div className="page-intro">
        <div><h2>推演结果记录库</h2><p>统一保存综合自动预测、技术词定向推演和岗位名称推演的输入快照、结果与后续处置。</p></div>
        <button className="secondary-button" onClick={() => { reload().then(() => notify('记录库已同步到最新状态')).catch((reason: Error) => notify(`同步失败：${reason.message}`)) }}><RefreshCw size={15} />刷新记录</button>
      </div>

      <div className="record-summary-strip">
        <div><span>累计推演运行</span><strong>{runs.length}</strong></div>
        <div><span>成功运行</span><strong>{successCount}</strong></div>
        <div><span>累计候选</span><strong>{candidateTotal}</strong></div>
        <div><span>证据受限运行</span><strong>{runs.filter((run) => run.evidence_limited).length}</strong></div>
      </div>

      {error ? <div className="empty-state"><ShieldAlert size={24} /><strong>加载失败</strong><span>{error}</span></div> : null}

      <Panel title="推演记录" subtitle={`当前显示 ${filteredRuns.length} 条，来自 /role-discovery/runs`} action={<div className="record-filter" aria-label="记录类型筛选">{MODE_FILTERS.map((item) => <button className={filter === item ? 'active' : ''} key={item} onClick={() => setFilter(item)}>{item}</button>)}</div>}>
        {loading ? <div className="empty-state"><RefreshCw className="spin" size={22} /><strong>正在加载记录…</strong></div> : (
          <div className="records-table-wrap">
            <table className="records-table">
              <thead><tr><th>运行编号</th><th>推演类型</th><th>时间截点</th><th>任务 / 候选</th><th>证据状态</th><th>运行状态</th><th>操作</th></tr></thead>
              <tbody>{filteredRuns.map((run) => (
                <tr key={run.run_code}>
                  <td><strong>{run.run_code}</strong><span>系统记录</span></td>
                  <td>{modeLabels[run.mode_code] ?? run.mode_code}</td>
                  <td>{run.target_date}</td>
                  <td>{run.task_count} / {run.candidate_count}</td>
                  <td>{run.evidence_limited ? <StatusTag tone="warning">受限</StatusTag> : <StatusTag tone="success">充分</StatusTag>}</td>
                  <td><StatusTag tone={run.run_status_code === 'success' ? 'success' : run.run_status_code === 'failed' ? 'danger' : 'info'}>{run.run_status_code}</StatusTag></td>
                  <td><button className="table-action" onClick={() => setSelectedRun(run)}><Eye size={14} />查看</button></td>
                </tr>
              ))}</tbody>
            </table>
            {filteredRuns.length === 0 ? <div className="empty-state"><Archive size={24} /><strong>暂无推演记录</strong><span>在"新岗位发现"或"定向推演"页面发起运行后将自动记录。</span></div> : null}
          </div>
        )}
      </Panel>

      {selectedRun ? (
        <Modal title={`推演运行 · ${selectedRun.run_code}`} onClose={() => setSelectedRun(null)}>
          <div className="record-detail">
            <FileClock size={25} />
            <div>
              <StatusTag tone="info">{modeLabels[selectedRun.mode_code] ?? selectedRun.mode_code}</StatusTag>
              <h3>{selectedRun.run_code}</h3>
              <p>截点 {selectedRun.target_date} · {runDetail?.query_role_name ? `查询岗位名：${runDetail.query_role_name}` : '输入快照已冻结'}</p>
            </div>
            <dl>
              <div><dt>任务数</dt><dd>{selectedRun.task_count}</dd></div>
              <div><dt>候选数</dt><dd>{selectedRun.candidate_count}</dd></div>
              <div><dt>已验证里程碑</dt><dd>{String(runDetail?.result_summary?.verified_milestone_count ?? '—')}</dd></div>
              <div><dt>已批准岗位数</dt><dd>{String(runDetail?.result_summary?.approved_role_count ?? '—')}</dd></div>
            </dl>
            <div className="table-wrap">
              <table className="data-table">
                <thead><tr><th>候选编码</th><th>建议名称</th><th>阶段</th><th>工作流</th><th>综合分</th></tr></thead>
                <tbody>{runCandidates.map((candidate) => (
                  <tr key={candidate.candidate_code}>
                    <td><small>{candidate.candidate_code}</small></td>
                    <td><strong>{candidate.proposed_name}</strong></td>
                    <td>{candidate.maturity_stage_code}</td>
                    <td>{candidate.workflow_status_code}</td>
                    <td>{Number(candidate.candidate_score).toFixed(1)}</td>
                  </tr>
                ))}</tbody>
              </table>
              {runCandidates.length === 0 ? <p className="table-note">本次运行未产生候选。</p> : null}
            </div>
            <div className="modal-actions"><button className="secondary-button" onClick={() => setSelectedRun(null)}>关闭</button></div>
          </div>
        </Modal>
      ) : null}
    </div>
  )
}
