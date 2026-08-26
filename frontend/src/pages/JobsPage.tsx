import {
  CircleDotDashed,
  RefreshCw,
  ShieldAlert,
  ShieldCheck,
  Sparkles,
} from 'lucide-react'
import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  CLASSIFICATION_BASELINE_NOTE,
  classificationColor,
  classificationLabels,
  discoveryApi,
  gapGradeStyle,
  maturityStageLabels,
  NO_GAP_GRADE_NOTE,
  EXTERNAL_EVIDENCE_CLASSIFICATIONS,
  type CandidateListItem,
  type DiscoveryRun,
} from '../api/discovery'
import { Panel } from '../components/ui'

// 分类的展示顺序：从「需要动作」到「无需动作」，让审核者先看到该处理的。
// 两类外部证据信号排在最前：它们的参照系是招聘市场而非本系统岗位库，
// 是本模块唯一能称为「发现」的产出。其余四类的分母都是自产的岗位库。
// 里程碑信号又排在研究侧之前——它的证据能指到具体的、有日期的产业事件，
// 而研究侧只能给出共现次数，且会受语料域偏离影响。
const CLASSIFICATION_ORDER = [
  'milestone_signal',
  'upstream_signal',
  'potential_new_role',
  'library_gap',
  'role_evolution',
  'existing_role',
]

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
  // 点统计栏的某一类 = 只看这一列。再点一次取消。分类多达六个，
  // 全部并排时单列很窄，需要一个「专注看一类」的出口。
  const [focus, setFocus] = useState<string | null>(null)

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

      {/*
        原本这里是一条「数据库 → 模型 → 入库」的流程示意图。它每次渲染都一样，
        不携带本轮任何信息；换成按分类的发现数，同一块版面就能回答
        「这一轮发现了什么、各类各多少」。
      */}
      <section className="discovery-stats">
        <div className="discovery-stats-total">
          <strong>{candidateTotal}</strong>
          <span>本轮候选合计</span>
        </div>
        <div className="discovery-stats-grid">
          {CLASSIFICATION_ORDER.map((code) => {
            const count = grouped[code]?.length ?? 0
            const color = classificationColor[code]
            return (
              <button
                key={code}
                className={`discovery-stat${count === 0 ? ' is-empty' : ''}`}
                style={{ borderTopColor: color?.dot }}
                onClick={() => {
                  if (count > 0) setFocus((current) => (current === code ? null : code))
                }}
                data-active={focus === code}
              >
                <b style={{ color: count > 0 ? color?.fg : undefined }}>{count}</b>
                <span>{classificationLabels[code] ?? code}</span>
              </button>
            )
          })}
        </div>
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
          <>
            {/*
              两个色标各说一件事，因此必须给图例——同一张卡上并排两个色块，
              不说明的话读者只会以为是同一维度的深浅。
            */}
            <div className="candidate-legend">
              <div>
                <span className="legend-kicker">缺口分级</span>
                {Object.entries(gapGradeStyle).map(([grade, style]) => (
                  <em key={grade} style={{ color: style.fg, background: style.bg }}>
                    {style.label}
                  </em>
                ))}
                <i>{NO_GAP_GRADE_NOTE}</i>
              </div>
              <div>
                <span className="legend-kicker">分类</span>
                {CLASSIFICATION_ORDER.filter((code) => grouped[code]?.length).map((code) => (
                  <em
                    key={code}
                    style={{
                      color: classificationColor[code]?.fg,
                      background: classificationColor[code]?.bg,
                    }}
                  >
                    {classificationLabels[code] ?? code}
                  </em>
                ))}
              </div>
            </div>

            <div className={`discovery-columns${focus ? ' is-focused' : ''}`}>
              {CLASSIFICATION_ORDER.filter(
                (code) => grouped[code]?.length && (!focus || focus === code),
              ).map((code) => {
                const color = classificationColor[code]
                return (
                  <section key={code} className="discovery-column">
                    <header style={{ borderTopColor: color?.dot }}>
                      <strong style={{ color: color?.fg }}>
                        {classificationLabels[code] ?? code}
                      </strong>
                      <b>{grouped[code].length}</b>
                      <p>
                        参照系：
                        {code === 'milestone_signal'
                          ? '具身智能产业里程碑事件'
                          : code === 'upstream_signal'
                            ? '论文与专利语料'
                            : '本系统由同一批 JD 聚类得到的岗位库'}
                      </p>
                    </header>
                    <div className="discovery-column-body">
                      {grouped[code].map((item) => {
                        const grade = item.gap_grade
                          ? gapGradeStyle[item.gap_grade]
                          : null
                        return (
                          <button
                            key={item.candidate_code}
                            onClick={() => onOpenCandidate(item.candidate_code)}
                          >
                            <div className="candidate-chips">
                              {grade ? (
                                <em style={{ color: grade.fg, background: grade.bg }}>
                                  {grade.label}
                                </em>
                              ) : null}
                              <em
                                style={{
                                  color: color?.fg,
                                  background: color?.bg,
                                }}
                              >
                                {classificationLabels[code] ?? code}
                              </em>
                              <b>{Number(item.candidate_score).toFixed(1)}</b>
                            </div>
                            <strong>{item.proposed_name}</strong>
                            <span>
                              {maturityStageLabels[item.maturity_stage_code] ??
                                item.maturity_stage_code}
                              {/*
                                外部证据类的 JD 支撑恒为 0——那是它们的定义。
                                写「支撑 0 份 JD」读起来像抽取失败，
                                换成这一类真正的立论：JD 侧无支撑。
                              */}
                              {' · '}
                              {EXTERNAL_EVIDENCE_CLASSIFICATIONS.has(
                                item.classification_code,
                              )
                                ? 'JD 侧无支撑'
                                : `支撑 ${item.support_job_count} 份 JD`}
                            </span>
                            {item.risk_flags.length > 0 ? (
                              <i>{item.risk_flags.length} 项风险标签</i>
                            ) : null}
                          </button>
                        )
                      })}
                    </div>
                  </section>
                )
              })}
            </div>
          </>
        )}
        <p className="discovery-baseline">{CLASSIFICATION_BASELINE_NOTE}</p>
      </Panel>
    </div>
  )
}
