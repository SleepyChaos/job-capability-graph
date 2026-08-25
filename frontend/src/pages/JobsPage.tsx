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
  CLASSIFICATION_BASELINE_NOTE,
  classificationGuidance,
  classificationLabels,
  classificationTone,
  discoveryApi,
  maturityStageLabels,
  type CandidateListItem,
  type DiscoveryRun,
} from '../api/discovery'
import { Panel, StatusTag } from '../components/ui'

// 分类的展示顺序：从「需要动作」到「无需动作」，让审核者先看到该处理的。
const CLASSIFICATION_ORDER = ['potential_new_role', 'library_gap', 'role_evolution', 'existing_role']

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
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [running, setRunning] = useState(false)

  const reload = useCallback(async (signal?: AbortSignal) => {
    // 候选按技术组合去重，同一组合始终只有一行，因此不按运行过滤：
    // 复用的候选仍挂在首次发现的运行下，若只取最近一次运行会把它们全部漏掉。
    // 按运行浏览历史请用「推演结果记录库」。
    const [candidatePage, runRows] = await Promise.all([
      discoveryApi.candidates({ limit: 200 }, signal),
      discoveryApi.runs('automatic', signal),
    ])
    setCandidates(candidatePage.items)
    setCandidateTotal(candidatePage.total)
    setRuns(runRows)
  }, [])

  useEffect(() => {
    const controller = new AbortController()
    setLoading(true)
    reload(controller.signal)
      .catch((reason: Error) => { if (reason.name !== 'AbortError') setError(reason.message) })
      .finally(() => setLoading(false))
    return () => controller.abort()
  }, [reload])

  const latestRun = runs[0]
  const grouped = useMemo(() => {
    const buckets: Record<string, CandidateListItem[]> = {}
    for (const item of candidates) (buckets[item.classification_code] ??= []).push(item)
    return buckets
  }, [candidates])

  const runAutomatic = async () => {
    setRunning(true)
    try {
      const run = await discoveryApi.createRun({ mode_code: 'automatic', target_date: todayISO() })
      notify(run.already_completed
        ? `相同数据快照已推演过（${run.run_code}），直接返回既有结果`
        : `自动预测完成：${run.candidate_count} 个候选、${run.task_count} 项任务${run.evidence_limited ? '（证据受限：缺少已验证里程碑或已批准岗位）' : ''}`)
      await reload()
    } catch (reason) {
      notify(`自动预测失败：${(reason as Error).message}`)
    } finally {
      setRunning(false)
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

      {/*
        总览只回答「这一轮发现了什么」：运行状态 + 按分类分组的候选卡片墙。
        单个候选的资料在岗位数据卡（独立路由），处置在审核台——三件事分开之后，
        这一页不再需要详情面板与审批弹窗，也就没有了误触终态操作的入口。
      */}
      <Panel
        title="本轮候选"
        subtitle={`${candidateTotal} 个 · 按技术组合去重 · 点击卡片查看岗位数据卡`}
      >
        {loading ? (
          <div className="empty-state"><RefreshCw className="spin" size={22} /><strong>正在加载候选…</strong></div>
        ) : candidates.length === 0 ? (
          <div className="empty-state"><CircleDotDashed size={24} /><strong>暂无候选</strong><span>运行自动预测后在此展示。</span></div>
        ) : (
          <div className="discovery-groups">
            {CLASSIFICATION_ORDER.filter((code) => grouped[code]?.length).map((code) => (
              <section key={code} className="discovery-group">
                <header>
                  <StatusTag tone={classificationTone[code] ?? 'info'}>
                    {classificationLabels[code] ?? code}
                  </StatusTag>
                  <span>{grouped[code].length} 个</span>
                  <p>{classificationGuidance[code] ?? ''}</p>
                </header>
                <div className="candidate-wall">
                  {grouped[code].map((item) => (
                    <button key={item.candidate_code} onClick={() => onOpenCandidate(item.candidate_code)}>
                      <b>{Number(item.candidate_score).toFixed(1)}</b>
                      <strong>{item.proposed_name}</strong>
                      <span>
                        {maturityStageLabels[item.maturity_stage_code] ?? item.maturity_stage_code}
                        {' · '}支撑 {item.support_job_count} 份 JD
                      </span>
                      {item.risk_flags.length > 0 ? (
                        <em>{item.risk_flags.length} 项风险标签</em>
                      ) : null}
                    </button>
                  ))}
                </div>
              </section>
            ))}
          </div>
        )}
        <p className="discovery-baseline">{CLASSIFICATION_BASELINE_NOTE}</p>
      </Panel>
    </div>
  )
}
