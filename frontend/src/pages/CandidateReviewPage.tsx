import {
  Building2,
  CheckCircle2,
  ExternalLink,
  FileText,
  FlaskConical,
  Layers,
  RefreshCw,
  ShieldAlert,
  ShieldCheck,
} from 'lucide-react'
import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  CLASSIFICATION_BASELINE_NOTE,
  classificationGuidance,
  classificationLabels,
  classificationTone,
  discoveryApi,
  emergenceWindow,
  maturityStageLabels,
  milestoneTypeLabels,
  EXTERNAL_EVIDENCE_CLASSIFICATIONS,
  type CandidateDetail,
  type CandidateListItem,
  type MilestoneEvidence,
  type TransmissionLagPrior,
  type NearestRoleCard,
  type UnverifiedTechnologyPage,
} from '../api/discovery'
import { Panel, StatusTag } from '../components/ui'
import type { PageId } from '../types'

/**
 * 候选审核台：**一次处置一个，动作按分类明确化**。
 *
 * 此前审批混在新岗位发现页的详情面板里，两个按钮叫「驳回观察」与「专项审批」，
 * 语义模糊且紧挨着资料内容——光标一滑就能误触，而驳回是终态：
 * `TERMINAL_CANDIDATE_STATUSES` 会让该技术组合**永不再被提出**，哪怕算法后来改了。
 * 这里把处置面与资料面彻底分开，并按分类给出该做什么，而不是给两个通用按钮。
 *
 * 资料在岗位数据卡（独立路由），本页只负责决定。
 *
 * 第二个页签是 **C 级待核查技术清单**。它不是候选，处置对象是技术点而非岗位，
 * 但同属「系统判不了、需要人来判」这一类工作，因此并入审核台而不是另开一页。
 * 该清单当前只读——判定结果的落库口径尚未定义，先如实呈现待判事实，
 * 不做一个点了没有后续的假按钮。
 */

/** 每个分类对应的推荐动作。四类候选的下一步完全不同，不能共用一组按钮。 */
const ACTION_BY_CLASSIFICATION: Record<
  string,
  { primary: string; primaryHint: string; secondary: string }
> = {
  existing_role: {
    primary: '归档（无需新增）',
    primaryHint: '该组合已被既有岗位覆盖且占其大半，归档后不再重复提出。',
    secondary: '仍要建为新岗位',
  },
  role_evolution: {
    primary: '并入最邻近岗位',
    primaryHint: '候选是该岗位的一个片段或部分重合，作为其能力变化并入。',
    secondary: '仍要建为新岗位',
  },
  library_gap: {
    primary: '补录为正式岗位',
    primaryHint: '能力组合已成熟、市场在招，只是岗位库未收录。补录而非创新定义。',
    secondary: '暂不补录',
  },
  potential_new_role: {
    primary: '新增岗位定义',
    primaryHint: '所依托技术方向尚未全部成熟，建库后需持续跟踪。',
    secondary: '继续观察',
  },
  // 上游信号没有任何招聘证据支撑，主按钮的措辞必须说明这一点：
  // 批准等于**在没有市场证据的情况下先建库**，与其它三类不是同一个决定。
  upstream_signal: {
    primary: '认定成立，先行建库',
    primaryHint:
      '零 JD 支撑。批准意味着仅凭上游语料证据先行建库，请先在数据卡核对共现次数与技术点。',
    secondary: '判为语料域偏离',
  },
  // 里程碑信号的驳回理由与上游不同：它不会有语料域偏离（事件是人工筛过的），
  // 真正要判的是「这个事件是否意味着一类工作」——很多发布只是产品动态。
  milestone_signal: {
    primary: '认定成立，先行建库',
    primaryHint:
      '零 JD 支撑。依据是下方列出的具体事件——请先判断这些事件是否真的意味着一类岗位，而不只是产品动态。',
    secondary: '判为不构成岗位',
  },
}

export function CandidateReviewPage({
  initialCandidateCode,
  onNavigate,
  notify,
}: {
  /** 从岗位数据卡跳进来时带的候选编码，直接定位到该条，免去在队列里重找。 */
  initialCandidateCode?: string | null
  onNavigate: (page: PageId, param?: string | null) => void
  notify: (message: string) => void
}) {
  const [items, setItems] = useState<CandidateListItem[]>([])
  const [detail, setDetail] = useState<CandidateDetail | null>(null)
  const [selectedCode, setSelectedCode] = useState('')
  const [filter, setFilter] = useState<string>('all')
  const [loading, setLoading] = useState(true)
  const [acting, setActing] = useState(false)
  const [error, setError] = useState('')
  const [tab, setTab] = useState<'candidates' | 'technologies'>('candidates')
  const [unverified, setUnverified] = useState<UnverifiedTechnologyPage | null>(null)
  const [unverifiedError, setUnverifiedError] = useState('')
  const reviewerCode = 'admin-demo'

  const load = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      // 只取待审的：审核台的职责是清队列，已处置的属于记录库。
      const page = await discoveryApi.candidates({ workflowStatus: 'pending', limit: 200 })
      setItems(page.items)
      const has = (code: string) => page.items.some((item) => item.candidate_code === code)
      setSelectedCode((current) => {
        if (current && has(current)) return current
        if (initialCandidateCode && has(initialCandidateCode)) return initialCandidateCode
        return page.items[0]?.candidate_code ?? ''
      })
    } catch (reason) {
      setError((reason as Error).message)
    } finally {
      setLoading(false)
    }
  }, [initialCandidateCode])

  useEffect(() => {
    void load()
  }, [load])

  useEffect(() => {
    const controller = new AbortController()
    discoveryApi
      .unverifiedTechnologies(controller.signal)
      .then(setUnverified)
      .catch((reason: Error) => {
        if (reason.name !== 'AbortError') setUnverifiedError(reason.message)
      })
    return () => controller.abort()
  }, [])

  useEffect(() => {
    if (!selectedCode) {
      setDetail(null)
      return
    }
    const controller = new AbortController()
    discoveryApi
      .candidateDetail(selectedCode, controller.signal)
      .then(setDetail)
      .catch((reason: Error) => {
        if (reason.name !== 'AbortError') setError(reason.message)
      })
    return () => controller.abort()
  }, [selectedCode])

  const grouped = useMemo(() => {
    const buckets: Record<string, CandidateListItem[]> = {}
    for (const item of items) {
      ;(buckets[item.classification_code] ??= []).push(item)
    }
    return buckets
  }, [items])

  const visible = filter === 'all' ? items : grouped[filter] ?? []

  const act = async (action: 'approve' | 'reject', message: string, comment?: string) => {
    if (!detail?.review_task_code) {
      notify('该候选没有待处理的审核任务')
      return
    }
    setActing(true)
    try {
      await discoveryApi.reviewAction(detail.review_task_code, action, reviewerCode, comment)
      notify(message)
      const remaining = items.filter((item) => item.candidate_code !== selectedCode)
      setItems(remaining)
      setSelectedCode(remaining[0]?.candidate_code ?? '')
    } catch (reason) {
      notify(`处置失败：${(reason as Error).message}`)
    } finally {
      setActing(false)
    }
  }

  const candidate = detail?.candidate
  const classification = candidate?.classification_code ?? ''
  const actions = ACTION_BY_CLASSIFICATION[classification]
  const card = (candidate?.mechanical_card ?? {}) as Record<string, unknown>
  const nearest = (card?.nearest_role ?? null) as NearestRoleCard | null
  const expression = (candidate?.expression ?? {}) as Record<string, unknown>
  // 两类外部证据候选的 JD 支撑恒为 0，事实位与基准说明都要另给。
  const isExternal = EXTERNAL_EVIDENCE_CLASSIFICATIONS.has(classification)
  const isMilestone = classification === 'milestone_signal'
  const milestones = (card?.milestones ?? []) as MilestoneEvidence[]
  const lag = (card?.expected_transmission_lag ?? null) as TransmissionLagPrior | null
  const window = emergenceWindow(card?.established_month as string | undefined, lag)

  return (
    <div className="page review-desk">
      <div className="review-tab-bar">
        <button
          className={tab === 'candidates' ? 'active' : ''}
          onClick={() => setTab('candidates')}
        >
          <ShieldCheck size={15} /> 候选处置 {items.length}
        </button>
        <button
          className={tab === 'technologies' ? 'active' : ''}
          onClick={() => setTab('technologies')}
        >
          <FlaskConical size={15} /> C 级待核查技术 {unverified?.items.length ?? 0}
        </button>
      </div>

      {tab === 'technologies' ? (
        <UnverifiedPanel data={unverified} error={unverifiedError} />
      ) : (
      <>
      <div className="review-queue-bar">
        <button
          className={filter === 'all' ? 'active' : ''}
          onClick={() => setFilter('all')}
        >
          全部待审 {items.length}
        </button>
        {Object.entries(grouped).map(([code, list]) => (
          <button key={code} className={filter === code ? 'active' : ''} onClick={() => setFilter(code)}>
            {classificationLabels[code] ?? code} {list.length}
          </button>
        ))}
      </div>

      {error ? (
        <div className="empty-state"><ShieldAlert size={25} /><strong>加载失败</strong><span>{error}</span></div>
      ) : null}

      <div className="review-layout">
        <Panel title="待审队列" subtitle={`${visible.length} 个 · 处置后自动跳到下一个`}>
          {loading ? (
            <div className="empty-state"><RefreshCw className="spin" size={22} /><strong>加载中…</strong></div>
          ) : visible.length === 0 ? (
            <div className="empty-state">
              <CheckCircle2 size={24} />
              <strong>队列已清空</strong>
              <span>没有待审候选。运行自动预测后会有新的提议进入。</span>
            </div>
          ) : (
            <div className="review-queue">
              {visible.map((item) => (
                <button
                  key={item.candidate_code}
                  className={item.candidate_code === selectedCode ? 'selected' : ''}
                  onClick={() => setSelectedCode(item.candidate_code)}
                >
                  <StatusTag tone={classificationTone[item.classification_code] ?? 'info'}>
                    {classificationLabels[item.classification_code] ?? item.classification_code}
                  </StatusTag>
                  <strong>{item.proposed_name}</strong>
                  {/* 外部证据类的 JD 支撑恒为 0，与候选墙用同一套措辞。 */}
                  <span>
                    {Number(item.candidate_score).toFixed(1)} 分 ·{' '}
                    {EXTERNAL_EVIDENCE_CLASSIFICATIONS.has(item.classification_code)
                      ? 'JD 侧无支撑'
                      : `支撑 ${item.support_job_count} 份 JD`}
                  </span>
                </button>
              ))}
            </div>
          )}
        </Panel>

        <Panel className="review-detail">
          {!candidate ? (
            <div className="empty-state"><FileText size={24} /><strong>选择左侧候选开始处置</strong></div>
          ) : (
            <div className="review-body">
              <div className="review-head">
                <StatusTag tone={classificationTone[classification] ?? 'info'}>
                  {classificationLabels[classification] ?? classification}
                </StatusTag>
                <StatusTag tone="warning">
                  {maturityStageLabels[candidate.maturity_stage_code] ?? candidate.maturity_stage_code}
                </StatusTag>
                <h2>{candidate.proposed_name}</h2>
                <p>{String(expression.one_line_definition ?? '尚未生成岗位定义。')}</p>
              </div>

              {/*
                上游信号的 JD 支撑恒为 0——这是它的定义，不是数据缺失。摆一排 0 会让
                审阅者以为抽取出错，所以这一类换成它真正有的证据：缺口等级、上游共现
                次数、锚点月份。
              */}
              {isExternal ? (
                <div className="review-facts">
                  <div>
                    <ShieldAlert size={16} /><span>缺口等级</span>
                    <strong>{String(card?.gap_grade ?? '—')} 级</strong>
                  </div>
                  <div>
                    <FlaskConical size={16} />
                    <span>{isMilestone ? '依据事件' : '上游最低共现'}</span>
                    <strong>
                      {isMilestone
                        ? Number(card?.milestone_count ?? 0)
                        : Number(card?.min_upstream_cooccurrence ?? 0)}
                    </strong>
                  </div>
                  <div>
                    <Layers size={16} /><span>能力项</span>
                    <strong>{candidate.technologies.length}</strong>
                  </div>
                </div>
              ) : (
                <div className="review-facts">
                  <div><FileText size={16} /><span>支撑 JD</span><strong>{Number(card?.job_count ?? 0)}</strong></div>
                  <div><Building2 size={16} /><span>独立企业</span><strong>{Number(card?.organization_count ?? 0)}</strong></div>
                  <div><Layers size={16} /><span>能力项</span><strong>{candidate.technologies.length}</strong></div>
                </div>
              )}

              {isExternal ? (
                <div className="review-nearest upstream">
                  <span>招聘侧证据</span>
                  <strong>无——全部 JD 中该组合共现 0 次</strong>
                  <em>
                    技术已成熟锚点 {String(card?.established_month ?? '—')}
                    {window
                      ? ` · 参考岗位涌现区间 ${window.from} 至 ${window.to}${
                          window.expired ? '（已过期）' : ''
                        }，外部先验，本系统无法验证`
                      : ''}
                  </em>
                </div>
              ) : null}

              {nearest ? (
                <div className="review-nearest">
                  <span>最邻近既有岗位</span>
                  <strong>{nearest.role_name}</strong>
                  <em>
                    覆盖率 {nearest.coverage.toFixed(2)} · 范围重合 {nearest.jaccard.toFixed(2)}
                    （共有 {nearest.shared_technology_count} 项，对方共 {nearest.role_technology_count} 项）
                  </em>
                </div>
              ) : null}

              {/*
                里程碑候选的全部价值在这里：它能把候选指回一组具体的、有日期有主体的
                事件。上游共现路径给不出这个——「两个技术在 5 篇论文里一起出现过」
                无从判断。审阅者要做的判断就是看着这些事件回答一句话：
                它们是否意味着一类工作，还是只是产品动态。
              */}
              {isMilestone && milestones.length > 0 ? (
                <div className="milestone-evidence">
                  <span>依据的产业事件（{milestones.length} 条）</span>
                  <ol>
                    {milestones.map((item) => (
                      <li key={item.milestone_code}>
                        <time>{item.event_date}</time>
                        <StatusTag tone="info">
                          {milestoneTypeLabels[item.milestone_type_code ?? ''] ??
                            item.milestone_type_code ??
                            '—'}
                        </StatusTag>
                        <strong>{item.milestone_name ?? item.milestone_code}</strong>
                      </li>
                    ))}
                  </ol>
                </div>
              ) : null}

              {candidate.risk_flags.length > 0 ? (
                <div className="review-risks">
                  <span>风险标签</span>
                  <div className="skill-tags">
                    {candidate.risk_flags.map((flag) => <span key={flag} className="risk-tag">{flag}</span>)}
                  </div>
                </div>
              ) : null}

              <button
                className="ghost-button wide"
                onClick={() => onNavigate('candidate', candidate.candidate_code)}
              >
                <ExternalLink size={14} /> 查看完整岗位数据卡
              </button>

              {/*
                动作按分类给，不给两个通用按钮。归档与补录在数据层面都是「不新建岗位」
                与「新建岗位」，但审核者看到的必须是这一类候选真正该做的事。
              */}
              <div className="review-actions">
                <div className="review-action-hint">
                  <ShieldCheck size={16} />
                  <span>{actions?.primaryHint ?? classificationGuidance[classification] ?? ''}</span>
                </div>
                <div className="review-action-buttons">
                  <button
                    className="secondary-button"
                    disabled={acting}
                    onClick={() =>
                      act('reject', '已记录为不新增，候选保留观察记录', '审核台处置：不新增岗位定义')
                    }
                  >
                    {actions?.secondary ?? '驳回观察'}
                  </button>
                  <button
                    className="primary-button"
                    disabled={acting}
                    onClick={() =>
                      act('approve', '已入库：正式岗位首版本与标准 JD 已生成')
                    }
                  >
                    {acting ? '提交中…' : actions?.primary ?? '批准入库'}
                  </button>
                </div>
                <p className="review-terminal-warning">
                  两个动作都是<strong>终态</strong>：处置后该技术组合不会再被重复提出，
                  即使算法版本更新。拿不准就先看数据卡。
                </p>
                {/*
                  分类基准说明只对前三类成立——它们的分类来自与 JD 聚类岗位库的比对。
                  上游信号根本没走这条路（它的定义就是 JD 里查无此组合），套用这段话
                  会把结论的来源说错，因此换成该候选自己的口径说明。
                */}
                <p className="review-baseline">
                  {isExternal
                    ? String(card?.caveat ?? '')
                    : CLASSIFICATION_BASELINE_NOTE}
                </p>
              </div>
            </div>
          )}
        </Panel>
      </div>
      </>
      )}
    </div>
  )
}

/**
 * C 级待核查技术清单。
 *
 * 每行是一个技术点，不是一个岗位候选。呈现三件事实：上游语料里它与别的技术最多
 * 共现过多少次、涉及多少对缺口、最早的锚点月份。审阅者要判的是它究竟属于
 * 「招聘市场还没出现的新技术」还是「上游语料谈的不是这个市场的事」。
 */
function UnverifiedPanel({
  data,
  error,
}: {
  data: UnverifiedTechnologyPage | null
  error: string
}) {
  if (error) {
    return (
      <div className="empty-state">
        <ShieldAlert size={25} />
        <strong>加载失败</strong>
        <span>{error}</span>
      </div>
    )
  }
  if (!data) {
    return (
      <div className="empty-state">
        <RefreshCw className="spin" size={22} />
        <strong>加载中…</strong>
      </div>
    )
  }
  // 空状态照常显示，不隐藏该分区——「当前语料条件下无待核查项」本身是结论。
  if (data.items.length === 0) {
    return (
      <div className="empty-state">
        <CheckCircle2 size={24} />
        <strong>无待核查技术点</strong>
        <span>最近一次上游缺口分析没有产出 C 级条目，或该分析尚未运行。</span>
      </div>
    )
  }
  return (
    <Panel
      title="C 级待核查技术清单"
      subtitle={`${data.items.length} 个技术点 · 来自运行 ${data.run_code ?? '—'}`}
    >
      <p className="review-baseline">{data.note}</p>
      <div className="unverified-list">
        {data.items.map((item) => (
          <div key={item.technology_code} className="unverified-row">
            <div className="unverified-head">
              <strong>{item.technology_name}</strong>
              <code>{item.technology_code}</code>
              <StatusTag tone="warning">JD 零命中</StatusTag>
            </div>
            <div className="unverified-facts">
              <span>上游最高共现 <strong>{item.max_upstream_cooccurrence}</strong> 次</span>
              <span>涉及 <strong>{item.pair_count}</strong> 对缺口</span>
              <span>最早锚点 <strong>{item.earliest_established ?? '—'}</strong></span>
            </div>
            <div className="skill-tags">
              {item.partner_names.map((name) => (
                <span key={name} className="skill-tag">{name}</span>
              ))}
            </div>
          </div>
        ))}
      </div>
    </Panel>
  )
}
