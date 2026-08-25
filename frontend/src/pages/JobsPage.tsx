import {
  ArrowRight,
  Building2,
  CircleDotDashed,
  Database,
  FileText,
  RefreshCw,
  ShieldAlert,
  ShieldCheck,
  Sparkles,
} from 'lucide-react'
import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  classificationGuidance,
  classificationLabels,
  classificationTone,
  discoveryApi,
  maturityStageLabels,
  scoreComponentLabels,
  workflowStatusLabels,
  type CandidateDetail,
  type CandidateForesight,
  type CandidateListItem,
  type DiscoveryRun,
} from '../api/discovery'
import { Modal, Panel, StatusTag } from '../components/ui'

function todayISO(): string {
  return new Date().toISOString().slice(0, 10)
}

export function JobsPage({
  notify,
  onOpenCandidate,
}: {
  notify: (message: string) => void
  /** 打开该候选的岗位数据卡（独立路由，可直接分享，也是图谱候选节点的落点）。 */
  onOpenCandidate: (candidateCode: string) => void
}) {
  const [candidates, setCandidates] = useState<CandidateListItem[]>([])
  const [candidateTotal, setCandidateTotal] = useState(0)
  const [runs, setRuns] = useState<DiscoveryRun[]>([])
  const [selectedCode, setSelectedCode] = useState('')
  const [detail, setDetail] = useState<CandidateDetail | null>(null)
  const [loading, setLoading] = useState(true)
  const [detailLoading, setDetailLoading] = useState(false)
  const [error, setError] = useState('')
  const [running, setRunning] = useState(false)
  const [acting, setActing] = useState(false)
  const [showApproval, setShowApproval] = useState(false)
  const reviewerCode = window.localStorage.getItem('reviewer_code') ?? 'reviewer-demo'

  const reload = useCallback(async (signal?: AbortSignal) => {
    // 候选按技术组合去重，同一组合始终只有一行，因此不按运行过滤：
    // 复用的候选仍挂在首次发现的运行下，若只取最近一次运行会把它们全部漏掉。
    // 按运行浏览历史请用「推演结果记录库」。
    const [candidatePage, runRows] = await Promise.all([
      discoveryApi.candidates({ limit: 50 }, signal),
      discoveryApi.runs('automatic', signal),
    ])
    setCandidates(candidatePage.items)
    setCandidateTotal(candidatePage.total)
    setRuns(runRows)
    setSelectedCode((current) => current || candidatePage.items[0]?.candidate_code || '')
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
    if (!selectedCode) { setDetail(null); return }
    const controller = new AbortController()
    setDetailLoading(true)
    discoveryApi.candidateDetail(selectedCode, controller.signal)
      .then(setDetail)
      .catch((reason: Error) => { if (reason.name !== 'AbortError') setError(reason.message) })
      .finally(() => setDetailLoading(false))
    return () => controller.abort()
  }, [selectedCode])

  const latestRun = runs[0]
  const selected = useMemo(() => candidates.find((item) => item.candidate_code === selectedCode) ?? null, [candidates, selectedCode])
  const card = detail?.candidate.mechanical_card
  const expression = detail?.candidate.expression as Record<string, unknown> | null
  // 前瞻块随机械卡一并下发。只有当前算法版本刷新过的候选才带它，旧候选没有。
  const foresight = (card?.foresight ?? null) as CandidateForesight | null
  const classification = detail?.candidate.classification_code ?? ''

  const runAutomatic = async () => {
    setRunning(true)
    try {
      const run = await discoveryApi.createRun({ mode_code: 'automatic', target_date: todayISO() })
      notify(run.already_completed
        ? `相同数据快照已推演过（${run.run_code}），直接返回既有结果`
        : `自动预测完成：${run.candidate_count} 个候选、${run.task_count} 项任务${run.evidence_limited ? '（证据受限：缺少已验证里程碑或已批准岗位）' : ''}`)
      setSelectedCode('')
      await reload()
    } catch (reason) {
      notify(`自动预测失败：${(reason as Error).message}`)
    } finally {
      setRunning(false)
    }
  }

  const approveCandidate = async () => {
    if (!detail?.review_task_code) {
      notify('该候选没有待处理的专项审批任务')
      return
    }
    setActing(true)
    try {
      await discoveryApi.reviewAction(detail.review_task_code, 'approve', reviewerCode)
      setShowApproval(false)
      notify('专项审批通过：正式岗位首版本与标准 JD 已入库')
      await reload()
      setSelectedCode(detail.candidate.candidate_code)
    } catch (reason) {
      notify(`审批失败：${(reason as Error).message}`)
    } finally {
      setActing(false)
    }
  }

  const rejectCandidate = async () => {
    if (!detail?.review_task_code) return
    setActing(true)
    try {
      await discoveryApi.reviewAction(detail.review_task_code, 'reject', reviewerCode, '证据不足，继续观察')
      setShowApproval(false)
      notify('候选已驳回并保留观察记录')
      await reload()
    } catch (reason) {
      notify(`审批失败：${(reason as Error).message}`)
    } finally {
      setActing(false)
    }
  }

  const generateExpression = async () => {
    if (!detail) return
    setActing(true)
    try {
      const snapshot = await discoveryApi.autoExpression(detail.candidate.candidate_code, reviewerCode)
      setDetail((current) => current ? { ...current, candidate: snapshot } : current)
      const method = (snapshot.expression as Record<string, unknown> | null)?.generation_method
      notify(method === 'llm_expression' ? '表达层已由 LLM 生成并通过证据校验' : '未配置 LLM Key，表达层已按规则降级生成（需确认清单 Q1）')
    } catch (reason) {
      notify(`表达生成失败：${(reason as Error).message}`)
    } finally {
      setActing(false)
    }
  }

  return (
    <div className="page-stack discovery-page">
      <div className="page-intro">
        <div>
          <h2>综合自动预测候选</h2>
          <p>系统周期性扫描正式数据库，综合岗位覆盖缺口、技术推进和真实需求，输出全局新岗位候选。</p>
        </div>
        <button className="secondary-button" disabled={running} onClick={runAutomatic}>{running ? <RefreshCw className="spin" size={16} /> : <Sparkles size={16} />}运行自动预测</button>
      </div>

      <section className="discovery-boundary">
        <div><Database size={20} /><span><strong>可信事实数据库</strong>JD 岗位簇 · T/L 技术词 · 技术里程碑</span></div>
        <ArrowRight size={18} />
        <div><CircleDotDashed size={20} /><span><strong>综合自动预测模型</strong>覆盖缺口、技术推进、真实需求与组合创新</span></div>
        <ArrowRight size={18} />
        <div><ShieldCheck size={20} /><span><strong>专项审批入库</strong>审批新岗位定义，不审核前置抽取事实</span></div>
      </section>

      <Panel title="自动预测任务" subtitle="每次运行冻结数据快照与 target_date，相同快照幂等复用">
        {latestRun ? (
          <div className="auto-discovery-status">
            <div><ShieldCheck size={19} /><span><strong>最近运行 {latestRun.run_code}</strong>截点 {latestRun.target_date} · 状态 {latestRun.run_status_code}</span></div>
            <div><span>标准化任务</span><strong>{latestRun.task_count}</strong></div>
            <div><span>输出候选</span><strong>{latestRun.candidate_count}</strong></div>
            <div><span>证据状态</span><strong>{latestRun.evidence_limited ? '受限' : '充分'}</strong></div>
          </div>
        ) : <div className="empty-state"><Sparkles size={24} /><strong>尚未运行自动预测</strong><span>点击右上角"运行自动预测"，基于当前正式数据库快照生成全局候选。</span></div>}
      </Panel>

      {error ? <div className="empty-state"><ShieldAlert size={25} /><strong>加载失败</strong><span>{error}</span></div> : null}

      <div className="jobs-layout">
        <Panel title="推演候选" subtitle={`累计 ${candidateTotal} 个（按技术组合去重），按综合证据分排序`} className="candidate-list-panel">
          {loading ? <div className="empty-state"><RefreshCw className="spin" size={22} /><strong>正在加载候选…</strong></div> : (
            <div className="candidate-list">
              {candidates.map((candidate) => (
                <button className={selectedCode === candidate.candidate_code ? 'selected' : ''} onClick={() => setSelectedCode(candidate.candidate_code)} key={candidate.candidate_code}>
                  <div>
                    <StatusTag tone={candidate.workflow_status_code === 'approved' ? 'success' : candidate.workflow_status_code === 'rejected' ? 'danger' : 'warning'}>
                      {maturityStageLabels[candidate.maturity_stage_code] ?? candidate.maturity_stage_code} · {workflowStatusLabels[candidate.workflow_status_code] ?? candidate.workflow_status_code}
                    </StatusTag>
                    <strong>{candidate.proposed_name}</strong>
                    <span>{classificationLabels[candidate.classification_code] ?? candidate.classification_code} · {candidate.run_code}</span>
                  </div>
                  <b>{Number(candidate.candidate_score).toFixed(1)}</b>
                </button>
              ))}
              {candidates.length === 0 ? <div className="empty-state"><CircleDotDashed size={24} /><strong>暂无候选</strong><span>运行自动预测后在此展示。</span></div> : null}
            </div>
          )}
        </Panel>

        <Panel className="candidate-detail">
          {detailLoading ? <div className="empty-state"><RefreshCw className="spin" size={22} /><strong>正在加载候选详情…</strong></div>
            : !detail || !selected ? <div className="empty-state"><FileText size={24} /><strong>选择左侧候选查看详情</strong></div> : (
            <>
              <div className="candidate-title">
                <div>
                  <StatusTag tone={detail.candidate.workflow_status_code === 'approved' ? 'success' : 'warning'}>
                    {maturityStageLabels[detail.candidate.maturity_stage_code] ?? detail.candidate.maturity_stage_code} · {workflowStatusLabels[detail.candidate.workflow_status_code] ?? detail.candidate.workflow_status_code}
                  </StatusTag>
                  <h2>{detail.candidate.proposed_name}</h2>
                  <p>{String(expression?.one_line_definition ?? '尚未生成表达层：点击“一键生成表达”（LLM 可用时生成，否则规则降级）。')}</p>
                </div>
                <div className="candidate-title-side">
                  <button className="secondary-button" onClick={() => onOpenCandidate(detail.candidate.candidate_code)}>
                    打开岗位数据卡
                  </button>
                  <div className="candidate-score"><strong>{detail.candidate.candidate_score.toFixed(1)}</strong><span>综合证据分</span></div>
                </div>
              </div>
              <div className="detail-section">
                <h3>分类与处置</h3>
                <div className="classification-callout">
                  <StatusTag tone={classificationTone[classification] ?? 'info'}>
                    {classificationLabels[classification] ?? classification}
                  </StatusTag>
                  <p>{classificationGuidance[classification] ?? '该分类暂无处置说明。'}</p>
                  <span>与最邻近岗位的能力覆盖率 {Number(card?.nearest_role_overlap ?? 0).toFixed(2)}</span>
                </div>
              </div>
              <div className="candidate-facts">
                <div><FileText size={17} /><span>证据 JD</span><strong>{Number(card?.job_count ?? 0)}</strong></div>
                <div><Building2 size={17} /><span>独立企业</span><strong>{Number(card?.organization_count ?? 0)}</strong></div>
                <div><Database size={17} /><span>独立来源</span><strong>{Number(card?.source_count ?? 0)}</strong></div>
                <div><CircleDotDashed size={17} /><span>原始成熟度</span><strong>{Number(card?.maturity_raw ?? 0).toFixed(2)}</strong></div>
              </div>
              {detail.candidate.risk_flags.length > 0 ? (
                <div className="detail-section"><h3>风险标签</h3><div className="skill-tags">{detail.candidate.risk_flags.map((flag) => <span key={flag}>{flag}</span>)}</div></div>
              ) : null}
              <div className="detail-section">
                <h3>评分构成（正向维度与惩罚项）</h3>
                <div className="table-wrap"><table className="data-table">
                  <thead><tr><th>维度</th><th>类型</th><th>原始分</th><th>权重</th><th>加权分</th></tr></thead>
                  <tbody>{detail.candidate.score_components.map((component) => (
                    <tr key={component.component_code}>
                      <td>{scoreComponentLabels[component.component_code] ?? component.component_code}</td>
                      <td><StatusTag tone={component.component_type_code === 'positive' ? 'info' : 'danger'}>{component.component_type_code === 'positive' ? '正向' : '惩罚'}</StatusTag></td>
                      <td>{component.raw_score.toFixed(2)}</td>
                      <td>{component.weight.toFixed(2)}</td>
                      <td>{component.weighted_score.toFixed(2)}</td>
                    </tr>
                  ))}</tbody>
                </table></div>
              </div>
              {foresight && foresight.directions.length > 0 ? (
                <div className="detail-section">
                  <h3>技术方向前瞻</h3>
                  {/*
                    措辞的主语是技术方向，不是岗位。候选依托多个方向，岗位能否成立
                    还取决于这些方向是否被同一批雇主组合进同一个职位，那不在推演的
                    推断范围内——所以这里不写「该岗位将于 X 出现」。
                  */}
                  <p className="foresight-caveat">
                    以下判断针对候选依托的<strong>技术方向</strong>，不是对岗位出现时间的预测。
                    岗位化门槛 θ = {foresight.threshold}
                    {foresight.threshold_origin === 'configured_not_measured' ? ' 为设定值而非实测值' : ''}；
                    传导时滞未能标定，因此<strong>不给出时间窗口</strong>。
                  </p>
                  <div className="table-wrap"><table className="data-table">
                    <thead><tr><th>技术方向</th><th>状态</th><th>跨越时点</th><th>峰值成熟度</th><th>里程碑</th><th>全局名次</th></tr></thead>
                    <tbody>{foresight.directions.map((item) => (
                      <tr key={item.technology_code}>
                        <td>{item.technology_name}</td>
                        <td><StatusTag tone={item.crossed ? 'success' : 'neutral'}>{item.crossed ? '已跨过门槛' : '尚未跨过'}</StatusTag></td>
                        <td>{item.crossing_month ?? '—'}</td>
                        <td>{item.peak_maturity.toFixed(2)}</td>
                        <td>{item.milestone_count}</td>
                        <td>#{item.foresight_rank}</td>
                      </tr>
                    ))}</tbody>
                  </table></div>
                  <p className="foresight-caveat">
                    跨域排序的已知偏差：成熟度由人工整理的里程碑驱动，整理投入多的技术域会系统性排在前面。
                  </p>
                </div>
              ) : null}
              <div className="detail-section"><h3>关联技术词</h3><div className="skill-tags">{detail.candidate.technologies.map((tech) => <span key={tech.technology_code}>{tech.technology_name}（{tech.requirement_type === 'required' ? '必需' : '加分'} · 证据 {tech.evidence_count}）</span>)}</div></div>
              <div className="detail-actions">
                {detail.review_task_code && detail.candidate.workflow_status_code === 'pending'
                  ? <><button className="secondary-button" onClick={generateExpression} disabled={acting}>一键生成表达</button><button className="secondary-button" onClick={rejectCandidate} disabled={acting}>驳回观察</button><button className="primary-button" disabled={acting} onClick={() => setShowApproval(true)}>专项审批</button></>
                  : <StatusTag tone={detail.candidate.workflow_status_code === 'approved' ? 'success' : 'neutral'}>{detail.candidate.workflow_status_code === 'approved' ? '已审批入库' : `当前状态：${workflowStatusLabels[detail.candidate.workflow_status_code] ?? detail.candidate.workflow_status_code}`}</StatusTag>}
              </div>
            </>
          )}
        </Panel>
      </div>

      {showApproval && detail ? (
        <Modal title="新岗位定义与专项审批" onClose={() => setShowApproval(false)}>
          <div className="role-card-preview">
            <div className="special-review-note"><ShieldCheck size={17} /><span>
              <strong>独立审批流程</strong>
              {classification === 'library_gap'
                ? '本候选是「岗位库缺失」——该能力组合在市场上已经成熟且大量在招，只是岗位库尚未收录。本次审批是补录一个既有岗位，不是创新定义。'
                : classification === 'role_evolution'
                ? '本候选与既有岗位部分重合，更像其能力扩展。批准前请先确认它确实应当独立成岗，而非并入最邻近岗位的新版本。'
                : '本次审批对象是基于数据库证据形成的岗位定义，不进入数据审核中心。'}
              审批通过将在一个事务中创建正式岗位、首版本与标准 JD。
            </span></div>
            <StatusTag tone="warning">机械事实锁定 · 表达层仅优化语言</StatusTag>
            <h3>{detail.candidate.proposed_name}</h3>
            <p>{String(expression?.one_line_definition ?? '候选机械事实卡已通过证据门禁；批准后将生成正式岗位定义与标准 JD。')}</p>
            <dl>
              <div><dt>证据快照</dt><dd>{Number(card?.job_count ?? 0)} 条 JD · {Number(card?.organization_count ?? 0)} 家企业 · {Number(card?.source_count ?? 0)} 个来源 · 截点 {detail.run.target_date}</dd></div>
              <div><dt>任务缺口分</dt><dd>{Number(card?.task_gap ?? 0).toFixed(3)}</dd></div>
              <div><dt>最邻近岗位重合度</dt><dd>{Number(card?.nearest_role_overlap ?? 0).toFixed(2)}</dd></div>
              <div><dt>标准 JD</dt><dd>批准后生成，标记 is_market_evidence=false，不计入真实招聘证据</dd></div>
            </dl>
            <div className="modal-actions"><button className="secondary-button" disabled={acting} onClick={rejectCandidate}>驳回</button><button className="primary-button" disabled={acting} onClick={approveCandidate}>{acting ? '提交中…' : '批准定义并入库'}</button></div>
          </div>
        </Modal>
      ) : null}
    </div>
  )
}
