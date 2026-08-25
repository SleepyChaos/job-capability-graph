import {
  Building2,
  CheckCircle2,
  ExternalLink,
  FileText,
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
  maturityStageLabels,
  type CandidateDetail,
  type CandidateListItem,
  type NearestRoleCard,
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
}

export function CandidateReviewPage({
  onNavigate,
  notify,
}: {
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
  const reviewerCode = 'admin-demo'

  const load = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      // 只取待审的：审核台的职责是清队列，已处置的属于记录库。
      const page = await discoveryApi.candidates({ workflowStatus: 'pending', limit: 200 })
      setItems(page.items)
      setSelectedCode((current) =>
        current && page.items.some((item) => item.candidate_code === current)
          ? current
          : page.items[0]?.candidate_code ?? '',
      )
    } catch (reason) {
      setError((reason as Error).message)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void load()
  }, [load])

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

  return (
    <div className="page review-desk">
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
                  <span>{Number(item.candidate_score).toFixed(1)} 分 · 支撑 {item.support_job_count} 份 JD</span>
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

              <div className="review-facts">
                <div><FileText size={16} /><span>支撑 JD</span><strong>{Number(card?.job_count ?? 0)}</strong></div>
                <div><Building2 size={16} /><span>独立企业</span><strong>{Number(card?.organization_count ?? 0)}</strong></div>
                <div><Layers size={16} /><span>能力项</span><strong>{candidate.technologies.length}</strong></div>
              </div>

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
                <p className="review-baseline">{CLASSIFICATION_BASELINE_NOTE}</p>
              </div>
            </div>
          )}
        </Panel>
      </div>
    </div>
  )
}
