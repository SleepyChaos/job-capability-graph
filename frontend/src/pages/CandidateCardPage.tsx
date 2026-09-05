import {
  ArrowLeft,
  Network,
  Building2,
  CalendarClock,
  Database,
  FileText,
  Layers,
  RefreshCw,
  ShieldAlert,
  Sparkles,
  UserRound,
} from 'lucide-react'
import { useCallback, useEffect, useState } from 'react'
import {
  classificationGuidance,
  classificationLabels,
  classificationTone,
  CLASSIFICATION_BASELINE_NOTE,
  discoveryApi,
  emergenceWindow,
  evidenceBadges,
  EXTERNAL_EVIDENCE_CLASSIFICATIONS,
  maturityStageLabels,
  milestoneTypeLabels,
  scoreComponentLabels,
  workflowStatusLabels,
  type CandidateDetail,
  type CandidateEvidencePage,
  type CandidateForesight,
  type MilestoneEvidence,
  type NearestRoleCard,
  type TransmissionLagPrior,
  type UpstreamEvidencePair,
  riskFlagText,
} from '../api/discovery'
import { Panel, StatusTag } from '../components/ui'

/** 技术类型 → 中文名。三类的传导时滞节奏本就不同，展示时要让读者看到用的是哪一档。 */
const TECHNOLOGY_CLASS_LABELS: Record<string, string> = {
  algorithm: '算法类',
  hardware: '硬件类',
  system_integration: '系统集成类',
}
import type { PageId } from '../types'

/**
 * 岗位数据卡：**给人看岗位，不看算法**。
 *
 * 主体是这个岗位是什么——待批准的岗位定义、需要哪些能力、证据来自哪里。算法为什么
 * 提出它是另一个问题，收在页面末尾的「算法依据」里默认折叠：审核者先要能判断
 * 「这是不是一个岗位」，再去看「算法凭什么这么算」，两件事挤在一屏会让人两件都
 * 读不下去。
 *
 * 审批动作**不在这里**。数据卡是只读的呈现面，处置动作在审核台，这样同一个页面
 * 不会既是资料又是表单——先前把两者混在一起，光标一滑就能误触驳回，而驳回是终态，
 * 会让该技术组合永不再被提出。
 */
export function CandidateCardPage({
  candidateCode,
  onNavigate,
  notify,
}: {
  candidateCode: string | null
  onNavigate: (page: PageId, param?: string | null) => void
  notify: (message: string) => void
}) {
  const [detail, setDetail] = useState<CandidateDetail | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [showEvidence, setShowEvidence] = useState(false)
  const [evidence, setEvidence] = useState<CandidateEvidencePage | null>(null)
  const [evidenceLoading, setEvidenceLoading] = useState(false)
  const [portraitRunning, setPortraitRunning] = useState(false)
  // 该候选是否已有五维画像。null = 还没问出结果，此时按钮不该先摆出一个可能说错的动作。
  const [portraitReady, setPortraitReady] = useState<boolean | null>(null)

  const load = useCallback(
    (signal?: AbortSignal) => {
      if (!candidateCode) return
      setLoading(true)
      setError('')
      discoveryApi
        .candidateDetail(candidateCode, signal)
        .then(setDetail)
        .catch((reason: Error) => {
          if (reason.name !== 'AbortError') setError(reason.message)
        })
        .finally(() => setLoading(false))
    },
    [candidateCode],
  )

  useEffect(() => {
    const controller = new AbortController()
    load(controller.signal)
    return () => controller.abort()
  }, [load])

  /*
    支撑文本按需拉取：多数读者不会展开，没必要跟数据卡一起加载。

    依赖里**不能放 `evidence`**——`setEvidence` 会让依赖变化，从而触发上一轮的清理
    函数 abort 掉刚刚完成的那次请求，界面就永远停在加载中。这里改由展开状态与候选
    编码驱动，取回后落库即可。
  */
  useEffect(() => {
    if (!showEvidence || !candidateCode) return
    const controller = new AbortController()
    setEvidenceLoading(true)
    discoveryApi
      .candidateEvidence(candidateCode, controller.signal)
      .then((page) => {
        if (controller.signal.aborted) return
        setEvidence(page)
        setEvidenceLoading(false)
      })
      .catch((reason: Error) => {
        if (reason.name === 'AbortError') return
        setEvidence({ total: 0, items: [] })
        setEvidenceLoading(false)
      })
    return () => controller.abort()
  }, [showEvidence, candidateCode])

  /*
    画像是否已生成，决定底部那个按钮这次是「跳过去看」还是「先生成」。

    问的是已入库画像清单（几 KB，不是候选详情的一部分），因此单独取一次；取不到时
    按「没有」处理——最坏结果是用户点了生成，而生成接口本身对已有画像是覆盖重算，
    不会把数据搞坏。
  */
  useEffect(() => {
    if (!candidateCode) return
    const controller = new AbortController()
    setPortraitReady(null)
    discoveryApi
      .rolePortraits(controller.signal)
      .then((page) => {
        if (controller.signal.aborted) return
        setPortraitReady(page.items.some((item) => item.candidate_code === candidateCode))
      })
      .catch((reason: Error) => {
        if (reason.name === 'AbortError') return
        setPortraitReady(false)
      })
    return () => controller.abort()
  }, [candidateCode])

  // 换一条候选时清掉上一条的支撑文本，避免展开后看到的是别人的证据。
  useEffect(() => {
    setEvidence(null)
    setShowEvidence(false)
  }, [candidateCode])

  if (!candidateCode) {
    return (
      <div className="page">
        <div className="empty-state">
          <FileText size={24} />
          <strong>未指定候选</strong>
          <span>从新岗位发现页选择一个候选，或使用形如 #/candidate/&lt;编码&gt; 的链接。</span>
        </div>
      </div>
    )
  }

  if (loading && !detail) {
    return (
      <div className="page">
        <div className="empty-state">
          <RefreshCw className="spin" size={22} />
          <strong>正在加载岗位数据卡…</strong>
        </div>
      </div>
    )
  }

  if (error || !detail) {
    return (
      <div className="page">
        <div className="empty-state">
          <ShieldAlert size={25} />
          <strong>加载失败</strong>
          <span>{error || '候选不存在'}</span>
        </div>
      </div>
    )
  }

  const candidate = detail.candidate
  const card = candidate.mechanical_card as Record<string, unknown>
  const expression = (candidate.expression ?? {}) as Record<string, unknown>
  const foresight = (card?.foresight ?? null) as CandidateForesight | null
  const classification = candidate.classification_code
  const responsibilities = (expression.core_responsibilities as string[] | undefined) ?? []
  const required = candidate.technologies.filter((item) => item.requirement_type === 'required')
  const bonus = candidate.technologies.filter((item) => item.requirement_type !== 'required')
  const isLlmNamed = expression.generation_method === 'llm_expression'
  const nearest = (card?.nearest_role ?? null) as NearestRoleCard | null
  /*
    外部证据类候选（研究侧领先信号、产业里程碑信号）的证据完全不在 JD 里。
    整张卡原本是围绕 JD 派生字段搭的——支撑 JD、独立企业、独立来源、证据 JD 编号、
    学术—产业落差、观测窗——对这两类**恒为 0**。摆一屏 0 不只是没信息，
    它会让读者以为抽取失败；而真正的证据（共现次数、里程碑事件）一个字都不显示。
    因此这两类走另一套事实位与证据区。
  */
  const isExternal = EXTERNAL_EVIDENCE_CLASSIFICATIONS.has(classification)
  const isMilestone = classification === 'milestone_signal'
  const gapBadge = evidenceBadges[String(card?.gap_grade ?? '')]
  const milestones = (card?.milestones ?? []) as MilestoneEvidence[]
  const evidencePairs = (card?.evidence_pairs ?? []) as UpstreamEvidencePair[]
  const jdMentions = (card?.jd_mentions ?? {}) as Record<string, number>
  /*
    卡片里的 `jd_mentions` 以**技术编码**为键——上游工具建卡时取的是
    `item["names"]`，而那个字段装的其实是编码。直接渲染会得到「T1.02.10 44 份」。
    卡片自带同序的 codes 与 names 两个数组，按位置对上即可，
    不必为历史数据改库。
  */
  const nameByCode = Object.fromEntries(
    ((card?.technology_codes ?? []) as string[]).map((code, index) => [
      code,
      ((card?.technology_names ?? []) as string[])[index] ?? code,
    ]),
  )
  const lag = (card?.expected_transmission_lag ?? null) as TransmissionLagPrior | null
  const window = emergenceWindow(card?.established_month as string | undefined, lag)

  return (
    <div className="page candidate-card-page">
      <div className="card-breadcrumb">
        <button className="ghost-button" onClick={() => onNavigate('jobs')}>
          <ArrowLeft size={15} /> 返回新岗位发现
        </button>
        <span className="mono-hint">{candidate.candidate_code}</span>
      </div>

      <header className="card-hero">
        <div>
          <div className="card-hero-tags">
            <StatusTag tone={classificationTone[classification] ?? 'info'}>
              {classificationLabels[classification] ?? classification}
            </StatusTag>
            <StatusTag tone="warning">
              {maturityStageLabels[candidate.maturity_stage_code] ?? candidate.maturity_stage_code}
            </StatusTag>
            <StatusTag tone="neutral">
              {workflowStatusLabels[candidate.workflow_status_code] ?? candidate.workflow_status_code}
            </StatusTag>
          </div>
          <h1>{candidate.proposed_name}</h1>
          <p className="card-hero-definition">
            {String(expression.one_line_definition ?? '尚未生成岗位定义。')}
          </p>
          <p className="card-hero-action">{classificationGuidance[classification] ?? ''}</p>
          {/*
            分母必须和分类同屏。不写清楚参照系是自产的岗位库，读者会把「潜在新岗位」
            读成「市场上还没有的岗位」——那是当前实现给不出的结论。
          */}
          <p className="card-hero-baseline">
            {isExternal ? String(card?.caveat ?? '') : CLASSIFICATION_BASELINE_NOTE}
          </p>
        </div>
        <div className="card-hero-score">
          <strong>{candidate.candidate_score.toFixed(1)}</strong>
          <span>综合证据分</span>
        </div>
      </header>

      {isExternal ? (
        <div className="card-metrics">
          {/*
            此处原来写「A 级 / B 级」。字母不说明任何事——读者既看不出 A 与 B 差在哪，
            也看不出它和旁边那些数字什么关系。改用与候选卡、审核台一致的说法，
            判据挂在 title 上。
          */}
          <div title={gapBadge?.hint}>
            <ShieldAlert size={17} /><span>缺口判定</span>
            <strong>{gapBadge?.label ?? '—'}</strong>
          </div>
          <div>
            <Database size={17} />
            <span>{isMilestone ? '依据事件' : '上游最低共现'}</span>
            <strong>
              {isMilestone
                ? Number(card?.milestone_count ?? 0)
                : Number(card?.min_upstream_cooccurrence ?? 0)}
            </strong>
          </div>
          <div>
            <FileText size={17} /><span>JD 共现</span>
            <strong>{Number(card?.jd_cooccurrence ?? 0)}</strong>
          </div>
          <div><Layers size={17} /><span>能力项</span><strong>{candidate.technologies.length}</strong></div>
        </div>
      ) : (
        <div className="card-metrics">
          <div><FileText size={17} /><span>支撑 JD</span><strong>{Number(card?.job_count ?? 0)}</strong></div>
          <div><Building2 size={17} /><span>独立企业</span><strong>{Number(card?.organization_count ?? 0)}</strong></div>
          <div><Database size={17} /><span>独立来源</span><strong>{Number(card?.source_count ?? 0)}</strong></div>
          <div><Layers size={17} /><span>能力项</span><strong>{candidate.technologies.length}</strong></div>
        </div>
      )}

      <div className="card-columns">
        <Panel
          title="岗位定义（待批准）"
          subtitle={
            isLlmNamed
              ? '名称与文字由 LLM 依据机械事实改写，事实本身不可变更'
              : '尚未生成 LLM 表达，当前为规则降级文本'
          }
        >
          <div className="jd-preview">
            <h3>{candidate.proposed_name}</h3>
            <p className="jd-definition">{String(expression.one_line_definition ?? '—')}</p>

            <h4>核心职责</h4>
            {responsibilities.length > 0 ? (
              <ol className="jd-list">
                {responsibilities.map((item) => (
                  <li key={item}>{item}</li>
                ))}
              </ol>
            ) : (
              <p className="jd-empty">尚未生成职责条目。</p>
            )}

            <h4>能力要求</h4>
            <div className="jd-skill-group">
              <span className="jd-skill-label">必需</span>
              <div className="skill-tags">
                {required.length > 0
                  ? required.map((tech) => (
                      <span key={tech.technology_code}>
                        {tech.technology_name}
                        {/*
                          「证据 N」数的是支撑该能力项的 JD 条数。外部证据类的证据
                          根本不在 JD 里，这里恒为 0——显示出来会被读成抽取失败。
                        */}
                        {isExternal ? null : <em>证据 {tech.evidence_count}</em>}
                      </span>
                    ))
                  : <span className="muted-tag">无</span>}
              </div>
            </div>
            {bonus.length > 0 ? (
              <div className="jd-skill-group">
                <span className="jd-skill-label">加分</span>
                <div className="skill-tags">
                  {bonus.map((tech) => (
                    <span key={tech.technology_code}>
                      {tech.technology_name}
                      <em>证据 {tech.evidence_count}</em>
                    </span>
                  ))}
                </div>
              </div>
            ) : null}

            {expression.formation_reason ? (
              <>
                <h4>形成原因</h4>
                <p className="jd-paragraph">{String(expression.formation_reason)}</p>
              </>
            ) : null}
            {expression.difference_explanation ? (
              <>
                <h4>与既有岗位的差异</h4>
                <p className="jd-paragraph">{String(expression.difference_explanation)}</p>
              </>
            ) : null}

            <p className="jd-disclaimer">
              本定义为参考模板，<strong>不代表真实招聘</strong>，不计入市场热度与岗位证据。
              批准入库后才会生成带版本号的正式标准 JD。
            </p>
          </div>
        </Panel>

        <div className="card-side">
          <Panel
            title={isExternal ? '锚点与岗位涌现区间' : '技术方向前瞻'}
            subtitle={
              isExternal
                ? '锚点是缺口成立的时点；涌现区间为外部先验，本系统无法验证'
                : '判断对象是技术方向，不是岗位出现时间'
            }
          >
            {/*
              前瞻面板读的是 rel_milestone_technology 的里程碑关联，那张表只覆盖
              31 个技术节点。对里程碑候选它会输出「没有里程碑证据，不作前瞻判断」
              ——而这条候选的全部依据恰恰就是一条里程碑事件，自相矛盾。
              外部证据类改用候选自己卡片里的锚点。
            */}
            {isExternal ? (
              <div className="external-anchor">
                <div>
                  <span className="foresight-kicker">
                    {isMilestone ? '最早依据事件' : '组合在上游站住脚于'}
                  </span>
                  <strong>{String(card?.established_month ?? '—')}</strong>
                </div>
                {window ? (
                  <div className={window.expired ? 'is-expired' : undefined}>
                    <span className="foresight-kicker">
                      参考岗位涌现区间 · 外部先验
                      {window.expired ? ' · 已过期' : ''}
                    </span>
                    <strong>
                      {window.from} 至 {window.to}
                    </strong>
                    <span className="anchor-derivation">
                      {`由锚点 ${String(card?.established_month ?? '—')} 加 ` +
                        `${lag?.low_months}–${lag?.high_months} 个月的传导时滞先验推出`}
                    </span>
                    {/*
                      区间落在过去时必须说破。候选里有锚点在 2019–2021 的
                      （缺口开了多年仍未闭合），照直显示会变成「预计 2020 年涌现」，
                      在 2026 年的界面上自相矛盾。
                    */}
                    <em>
                      {window.expired
                        ? '该区间已经过去，按先验这个岗位早该出现却仍未出现——更可能说明这两个技术在招聘上本就不该同现。'
                        : '按技术类型的传导时滞先验推出。U-3 回测不支持「上游领先招聘」这一前提，本区间是外部文献的参考值，不构成本系统的预测。'}
                    </em>
                  </div>
                ) : null}
              </div>
            ) : foresight && foresight.directions.length > 0 ? (
              <>
                {/*
                  三类时间信息按可信度从高到低排列，并在视觉上分开：
                  地基区间与需求现状是真实计算/观测，参考窗口是外部先验。
                  混排会让读者把先验当成测量结果。
                */}
                {foresight.foundation_from ? (
                  <div className="foresight-foundation">
                    <span className="foresight-kicker">技术地基成型区间 · 实测</span>
                    <strong>
                      {foresight.foundation_from}
                      {foresight.foundation_to !== foresight.foundation_from
                        ? ` — ${foresight.foundation_to}`
                        : ''}
                    </strong>
                    <p>
                      {foresight.foundation_complete
                        ? `所依托的技术方向已全部成熟，最后一个就位至今 ${foresight.foundation_ready_months} 个月。`
                        : '仍有技术方向尚未成熟，地基未完全就位。'}
                    </p>
                  </div>
                ) : null}

                {foresight.reference_window ? (
                  <div className="foresight-window">
                    <span className="foresight-kicker warn">
                      预计出现参考窗口 · 外部先验
                      {foresight.reference_window.technology_classes.length > 0
                        ? ` · ${foresight.reference_window.technology_classes
                            .map((code) => TECHNOLOGY_CLASS_LABELS[code] ?? code)
                            .join('、')}`
                        : ''}
                    </span>
                    <strong>
                      {foresight.reference_window.from} — {foresight.reference_window.to}
                    </strong>
                    <p>
                      以技术地基就位的 {foresight.reference_window.anchor_month} 为锚点，
                      叠加 {foresight.reference_window.prior_months[0]}–
                      {foresight.reference_window.prior_months[1]} 个月的传导时滞推出
                      {foresight.reference_window.coefficient
                        ? `（类型修正系数 ${foresight.reference_window.coefficient}）`
                        : ''}。
                      时滞按技术类型取值：算法类 10–15 月、系统集成类 12–18 月、硬件类 15–24 月。
                      <strong>这组参数来自外部参考研究，不是本系统的测量结果</strong>——
                      本项目 JD 侧的时间跨度仅约 10 周且为采集时间而非发布时间，
                      测不出 10–24 个月量级的时滞，因此该区间可用但<strong>无法在本系统内验证</strong>。
                    </p>
                  </div>
                ) : null}

                <p className="foresight-caveat">
                  下表为各方向<strong>已经发生</strong>的成熟事实与当前需求。岗位化门槛
                  θ = {foresight.threshold}
                  {foresight.threshold_origin === 'configured_not_measured' ? ' 为设定值而非实测值' : ''}。
                </p>
                <ul className="foresight-list">
                  {foresight.directions.map((item) => (
                    <li key={item.technology_code}>
                      <div>
                        <strong>{item.technology_name}</strong>
                        <span>
                          当前需求 {item.jd_demand} 份 JD
                          {item.demand_rank
                            ? `（${item.demand_total_directions} 个方向中第 ${item.demand_rank}）`
                            : ''}
                          {' · '}里程碑 {item.milestone_count} 条
                        </span>
                      </div>
                      {item.crossed ? (
                        <StatusTag tone="success">
                          <CalendarClock size={12} /> {item.crossing_month} 起技术已成熟
                        </StatusTag>
                      ) : (
                        <StatusTag tone="neutral">
                          尚未跨过（峰值 {item.peak_maturity.toFixed(2)}）
                        </StatusTag>
                      )}
                    </li>
                  ))}
                </ul>
              </>
            ) : (
              <div className="empty-state compact">
                <CalendarClock size={20} />
                <span>该候选依托的技术方向没有里程碑证据，不作前瞻判断。</span>
              </div>
            )}
          </Panel>

          {isExternal ? (
            <Panel
              title="证据来源"
              subtitle={
                isMilestone
                  ? `${milestones.length} 条产业里程碑事件 · JD 侧无支撑`
                  : `${evidencePairs.length} 组上游共现 · JD 侧无支撑`
              }
            >
              {isMilestone ? (
                <ol className="card-milestone-list">
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
              ) : (
                <ul className="card-pair-list">
                  {evidencePairs.map((item) => (
                    <li key={item.pair.join('|')}>
                      {/* `evidence_pairs.pair` 同样装的是编码，不是名称。 */}
                      <strong>
                        {item.pair.map((code) => nameByCode[code] ?? code).join(' + ')}
                      </strong>
                      <span>
                        上游共现 {item.upstream_cooccurrence} 次 · 站住脚于{' '}
                        {item.established_month} ·{' '}
                        <em title={evidenceBadges[item.grade]?.hint}>
                          {evidenceBadges[item.grade]?.label ?? item.grade}
                        </em>
                      </span>
                    </li>
                  ))}
                </ul>
              )}
              {/*
                招聘侧的两个数字必须同屏：各自提及说明这些技术在市场上不是没人要，
                共现 0 才是缺口本身。少了前者，读者无法区分「新组合」与「冷门技术」。
              */}
              <dl className="evidence-grid">
                <div>
                  <dt>JD 中各自提及</dt>
                  <dd>
                    {Object.entries(jdMentions).length > 0
                      ? Object.entries(jdMentions)
                          .map(([code, count]) => `${nameByCode[code] ?? code} ${count} 份`)
                          .join(' · ')
                      : '—'}
                  </dd>
                </div>
                <div>
                  <dt>JD 中同时要求</dt>
                  <dd>{Number(card?.jd_cooccurrence ?? 0)} 份 —— 这正是缺口本身</dd>
                </div>
                {isMilestone ? (
                  <div>
                    <dt>其中已人工验证的事件</dt>
                    <dd>
                      {Number(card?.verified_milestone_count ?? 0)} / {milestones.length}
                    </dd>
                  </div>
                ) : null}
              </dl>
              {candidate.risk_flags.length > 0 ? (
                <div className="risk-block">
                  <span>风险标签</span>
                  <div className="skill-tags">
                    {candidate.risk_flags.map((flag) => {
                      const text = riskFlagText(flag)
                      return (
                        <span key={flag} className="risk-tag" title={text.hint}>
                          {text.label}
                        </span>
                      )
                    })}
                  </div>
                </div>
              ) : null}
            </Panel>
          ) : (
          <Panel title="证据来源" subtitle={`${Number(card?.job_count ?? 0)} 份真实 JD 支撑`}>
            <dl className="evidence-grid">
              <div>
                <dt>最邻近既有岗位</dt>
                <dd className="nearest-role-name">{nearest?.role_name ?? '无可比岗位'}</dd>
              </div>
              <div>
                {/*
                  两个数字缺一不可：覆盖率说候选有没有既有岗位覆盖不了的能力，
                  Jaccard 说候选是整个岗位还是它的一块。只看覆盖率会随岗位库
                  增长饱和到 1.0——实测画像从 448 涨到 676 时正是如此。
                */}
                <dt>覆盖率 / 范围重合</dt>
                <dd>
                  {(nearest?.coverage ?? 0).toFixed(2)} / {(nearest?.jaccard ?? 0).toFixed(2)}
                  {nearest ? (
                    <span className="nearest-role-shape">
                      共有 {nearest.shared_technology_count} 项，对方共 {nearest.role_technology_count} 项
                    </span>
                  ) : null}
                </dd>
              </div>
              <div>
                <dt>学术—产业落差</dt>
                <dd>{Number(card?.task_gap ?? 0).toFixed(3)}</dd>
              </div>
              <div>
                <dt>观测窗</dt>
                <dd>{Number(card?.observation_window_count ?? 0)} 期</dd>
              </div>
              <div>
                <dt>应用证据</dt>
                <dd>{Number(card?.verified_application_evidence_count ?? 0)} 条</dd>
              </div>
            </dl>
            {candidate.risk_flags.length > 0 ? (
              <div className="risk-block">
                <span>风险标签</span>
                <div className="skill-tags">
                  {candidate.risk_flags.map((flag) => {
                    const text = riskFlagText(flag)
                    return (
                      <span key={flag} className="risk-tag" title={text.hint}>
                        {text.label}
                      </span>
                    )
                  })}
                </div>
              </div>
            ) : null}
            {/*
              此前这里展开的是一串证据片段编号。编号本身读者看不出任何东西——
              「凭什么提出这条候选」要能查到具体是哪些招聘文本、来自哪家企业。
              编号解析在后端完成（片段编号与岗位的对应关系记在任务证据表上）。
            */}
            <button className="ghost-button wide" onClick={() => setShowEvidence((value) => !value)}>
              {showEvidence
                ? '收起支撑招聘文本'
                : `展开支撑招聘文本（${evidence?.total ?? 0}）`}
            </button>
            {showEvidence ? (
              evidenceLoading ? (
                <div className="empty-state"><RefreshCw className="spin" size={20} /><strong>加载中…</strong></div>
              ) : !evidence || evidence.items.length === 0 ? (
                <div className="empty-state">
                  <FileText size={20} />
                  <strong>没有可展开的招聘文本</strong>
                  <span>外部证据类候选在招聘侧本就没有支撑，这是它的定义而非数据缺失。</span>
                </div>
              ) : (
                <div className="evidence-jd-list">
                  {evidence.items.map((item) => (
                    <div key={item.job_code} className="evidence-jd-row">
                      <strong>{item.title}</strong>
                      <span>
                        {item.company ?? '—'}
                        {item.region ? ` · ${item.region}` : ''}
                        {item.published_at ? ` · 发布 ${item.published_at}` : ''}
                        {!item.published_at && item.collected_at ? ` · 采集 ${item.collected_at}` : ''}
                      </span>
                      <code>{item.job_code}</code>
                    </div>
                  ))}
                  {evidence.total > evidence.items.length ? (
                    <p className="evidence-jd-more">
                      共 {evidence.total} 份，此处列出前 {evidence.items.length} 份。
                    </p>
                  ) : null}
                </div>
              )
            ) : null}
          </Panel>
          )}
        </div>
      </div>

      {/*
        算法依据默认折叠。它回答的是「算法凭什么提出这个候选」，与「这是不是一个
        岗位」是两个问题；把评分表摊在主视图里，是先前这个模块被认为过于复杂的
        主要来源。信息不删，只是默认不展示。
      */}
      <details className="algorithm-basis">
        <summary>算法依据 · 评分构成与判定口径</summary>
        <div className="table-wrap">
          <table className="data-table">
            <thead>
              <tr><th>维度</th><th>类型</th><th>原始分</th><th>权重</th><th>加权分</th></tr>
            </thead>
            <tbody>
              {candidate.score_components.map((component) => (
                <tr key={component.component_code}>
                  <td>{scoreComponentLabels[component.component_code] ?? component.component_code}</td>
                  <td>
                    <StatusTag tone={component.component_type_code === 'positive' ? 'info' : 'danger'}>
                      {component.component_type_code === 'positive' ? '正向' : '惩罚'}
                    </StatusTag>
                  </td>
                  <td>{component.raw_score.toFixed(2)}</td>
                  <td>{component.weight.toFixed(2)}</td>
                  <td>{component.weighted_score.toFixed(2)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="basis-note">
          分类依据最邻近岗位的能力覆盖率：≥ 0.75 判为已被覆盖，0.45–0.75 判为岗位演化，
          低于 0.45 时再看技术方向是否已全部跨过岗位化门槛——全部跨过且支撑量成熟的记为
          岗位库缺失，否则才是潜在新岗位。
        </p>
      </details>

      <div className="card-footer-actions">
        <button className="secondary-button" onClick={() => onNavigate('jobs')}>返回列表</button>
        {/*
          「在关联图谱中查看」与「生成五维画像」合并成一个按钮。

          分成两个时，使用者要自己判断该点哪个——而这个判断本来就是系统知道的：
          画像已生成就该直接去看，没生成就该先生成。合并后按钮只表达一个意图
          （看这条候选的五维画像），存在与否由它自己解决，生成完接着跳过去，
          不再要求使用者点两次、还得记住第二次该去哪个图。

          未入库的候选走另一条分支：画像写在标准 JD 上，没入库就没有这个载体，
          生成不了。此时保留原来的关联图谱入口——那是它唯一能露面的图，
          也是「岗位—能力关联图」在导航下线后仅存的入口，不能一并合掉。
        */}
        {candidate.workflow_status_code === 'approved' ? (
          <button
            className="secondary-button"
            disabled={portraitRunning || portraitReady === null}
            onClick={async () => {
              if (portraitReady) {
                onNavigate('job-portrait-graph', candidate.candidate_code)
                return
              }
              setPortraitRunning(true)
              try {
                const portrait = await discoveryApi.autoPortrait(candidate.candidate_code, 'admin-demo')
                setPortraitReady(true)
                notify(
                  `五维画像已生成（${portrait.provenance.generated_by}）：技能 ${portrait.skills.length} · ` +
                  `能力 ${portrait.abilities.length} · 场景 ${portrait.scenarios.length} · 条件 ${portrait.conditions.length}`,
                )
                onNavigate('job-portrait-graph', candidate.candidate_code)
              } catch (reason) {
                notify(`画像生成失败：${(reason as Error).message}`)
              } finally {
                setPortraitRunning(false)
              }
            }}
          >
            {portraitReady ? <UserRound size={15} /> : <Sparkles size={15} />}{' '}
            {portraitRunning
              ? '生成中…'
              : portraitReady === null
                ? '读取画像状态…'
                : portraitReady
                  ? '在岗位画像图谱中查看'
                  : '生成五维画像并查看'}
          </button>
        ) : (
          /*
            图谱里的候选节点编号是 `candidate:` + 候选编码。跳过去会自动勾上
            「叠加新岗位候选」并放开候选名额——图谱默认只取分数最高的 80 条，
            不放开的话大多数候选跳过去都定位不到自己。
          */
          <button
            className="secondary-button"
            onClick={() => onNavigate('graph-relations', `candidate:${candidate.candidate_code}`)}
          >
            <Network size={15} /> 在关联图谱中查看
          </button>
        )}
        {detail.review_task_code && candidate.workflow_status_code === 'pending' ? (
          <button
            className="primary-button"
            onClick={() => {
              notify('处置动作在审核台完成，避免在资料页误触终态操作')
              // 此前跳的是 'review'——那是数据审核中心（审 JD 抽取事实），
              // 与候选处置是两件事。带上候选编码，审核台直接定位到这一条，
              // 否则审核者到了那边还要在 164 条队列里再找一遍。
              onNavigate('candidate-review', candidate.candidate_code)
            }}
          >
            前往审核台处置
          </button>
        ) : null}
      </div>
    </div>
  )
}
