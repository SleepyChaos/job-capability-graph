import {
  ArrowLeft,
  Building2,
  CalendarClock,
  Database,
  FileText,
  Layers,
  RefreshCw,
  ShieldAlert,
} from 'lucide-react'
import { useCallback, useEffect, useState } from 'react'
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
} from '../api/discovery'
import { Panel, StatusTag } from '../components/ui'
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
        </div>
        <div className="card-hero-score">
          <strong>{candidate.candidate_score.toFixed(1)}</strong>
          <span>综合证据分</span>
        </div>
      </header>

      <div className="card-metrics">
        <div><FileText size={17} /><span>支撑 JD</span><strong>{Number(card?.job_count ?? 0)}</strong></div>
        <div><Building2 size={17} /><span>独立企业</span><strong>{Number(card?.organization_count ?? 0)}</strong></div>
        <div><Database size={17} /><span>独立来源</span><strong>{Number(card?.source_count ?? 0)}</strong></div>
        <div><Layers size={17} /><span>能力项</span><strong>{candidate.technologies.length}</strong></div>
      </div>

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
                        <em>证据 {tech.evidence_count}</em>
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
          <Panel title="技术方向前瞻" subtitle="判断对象是技术方向，不是岗位出现时间">
            {foresight && foresight.directions.length > 0 ? (
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
                    <span className="foresight-kicker warn">预计出现参考窗口 · 外部先验</span>
                    <strong>
                      {foresight.reference_window.from} — {foresight.reference_window.to}
                    </strong>
                    <p>
                      以最后一个方向成熟的 {foresight.reference_window.anchor_month} 为锚点，
                      叠加 {foresight.reference_window.prior_months[0]}–
                      {foresight.reference_window.prior_months[1]} 个月的传导时滞先验推出。
                      <strong>该先验不是本系统的测量结果</strong>——时滞在自有数据上标定失败
                      （已成熟时长与当前需求的秩相关 0.510，n=12 不显著；且里程碑为回溯整理），
                      因此这个区间只能当作粗略参考，不能作为结论引用。
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

          <Panel title="证据来源" subtitle={`${Number(card?.job_count ?? 0)} 份真实 JD 支撑`}>
            <dl className="evidence-grid">
              <div>
                <dt>最邻近岗位覆盖率</dt>
                <dd>{Number(card?.nearest_role_overlap ?? 0).toFixed(2)}</dd>
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
                  {candidate.risk_flags.map((flag) => (
                    <span key={flag} className="risk-tag">{flag}</span>
                  ))}
                </div>
              </div>
            ) : null}
            <button className="ghost-button wide" onClick={() => setShowEvidence((value) => !value)}>
              {showEvidence ? '收起证据 JD 编号' : `展开证据 JD 编号（${(card?.evidence_ids as unknown[] | undefined)?.length ?? 0}）`}
            </button>
            {showEvidence ? (
              <div className="evidence-ids">
                {((card?.evidence_ids as number[] | undefined) ?? []).map((id) => (
                  <code key={id}>{id}</code>
                ))}
              </div>
            ) : null}
          </Panel>
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
        {detail.review_task_code && candidate.workflow_status_code === 'pending' ? (
          <button
            className="primary-button"
            onClick={() => {
              notify('处置动作已迁移到审核台，避免在资料页误触终态操作')
              onNavigate('review')
            }}
          >
            前往审核台处置
          </button>
        ) : null}
      </div>
    </div>
  )
}
