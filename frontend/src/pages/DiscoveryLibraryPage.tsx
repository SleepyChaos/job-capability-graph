import { Archive, ExternalLink, Inbox, RefreshCw, ShieldAlert } from 'lucide-react'
import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  classificationColor,
  classificationLabels,
  discoveryApi,
  evidenceBadges,
  LIBRARY_EVIDENCE_KEY,
  type CandidateListItem,
} from '../api/discovery'
import { Panel } from '../components/ui'
import type { PageId } from '../types'

/**
 * 新岗位发现库：**已通过审核、已进入岗位库**的发现结果。
 *
 * 与另外两页的分工——发现页看这一轮推演出了什么（全部待审），审核台逐条判断
 * 能不能入库，本页只陈列**判断结果为「能」的那些**。三页对应候选的三个阶段，
 * 混在一页会让「提议」和「已成立的岗位」看起来是一回事，而这两者的可信度
 * 差着一次人工判断。
 *
 * 入库后候选会生成一个 `origin_type_code = inference_derived` 的正式岗位，
 * 与 JD 聚类得到的 `cluster_derived` 岗位在岗位库里并存且可区分。
 */
export function DiscoveryLibraryPage({
  onNavigate,
}: {
  onNavigate: (page: PageId, param?: string | null) => void
}) {
  const [items, setItems] = useState<CandidateListItem[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  const load = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const page = await discoveryApi.candidates({ workflowStatus: 'approved', limit: 200 })
      setItems(page.items)
    } catch (reason) {
      setError((reason as Error).message)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void load()
  }, [load])

  const byClassification = useMemo(() => {
    const buckets: Record<string, number> = {}
    for (const item of items) {
      buckets[item.classification_code] = (buckets[item.classification_code] ?? 0) + 1
    }
    return buckets
  }, [items])

  return (
    <div className="page-stack">
      <div className="page-intro">
        <div>
          <h2>新岗位发现库</h2>
          <p>
            经审核台判定成立、已生成正式岗位定义与标准 JD 的发现结果。
            它们在岗位库中以「推演派生」标记，与 JD 聚类得到的岗位可区分。
          </p>
        </div>
        <button className="secondary-button" onClick={() => void load()}>
          <RefreshCw size={16} /> 刷新
        </button>
      </div>

      {error ? (
        <div className="empty-state">
          <ShieldAlert size={25} />
          <strong>加载失败</strong>
          <span>{error}</span>
        </div>
      ) : null}

      <Panel
        title="已入库的发现岗位"
        subtitle={`${items.length} 个 · 点击查看岗位数据卡与标准 JD`}
      >
        {loading ? (
          <div className="empty-state">
            <RefreshCw className="spin" size={22} />
            <strong>加载中…</strong>
          </div>
        ) : items.length === 0 ? (
          /*
            空状态本身有信息量：它说明「至今没有一条发现结果被判定成立」，
            而不是功能坏了。因此写清下一步在哪做，不把这一页藏起来。
          */
          <div className="empty-state">
            <Inbox size={24} />
            <strong>还没有入库的发现岗位</strong>
            <span>
              发现的候选都停在审核队列里，需要人工逐条判定。前往新岗位审核台处置后，
              判定成立的会出现在这里。
            </span>
            <button
              className="secondary-button"
              onClick={() => onNavigate('candidate-review')}
            >
              <ExternalLink size={14} /> 前往新岗位审核台
            </button>
          </div>
        ) : (
          <>
            <div className="library-summary">
              {Object.entries(byClassification).map(([code, count]) => (
                <span
                  key={code}
                  style={{
                    color: classificationColor[code]?.fg,
                    background: classificationColor[code]?.bg,
                  }}
                >
                  {classificationLabels[code] ?? code} {count}
                </span>
              ))}
            </div>
            <div className="library-table-wrap">
              <table className="data-table library-table">
                <thead>
                  <tr>
                    <th>岗位名称</th>
                    <th>来源与证据</th>
                    <th>正式岗位编码</th>
                    <th>入库时间</th>
                    <th />
                  </tr>
                </thead>
                <tbody>
                  {items.map((item) => {
                    const badge =
                      evidenceBadges[item.gap_grade ?? LIBRARY_EVIDENCE_KEY] ??
                      evidenceBadges[LIBRARY_EVIDENCE_KEY]
                    const color = classificationColor[item.classification_code]
                    return (
                      <tr key={item.candidate_code}>
                        <td>
                          <strong className="library-role-name">
                            {item.approved_role_name ?? item.proposed_name}
                          </strong>
                        </td>
                        <td>
                          <div className="candidate-chips">
                            <em
                              style={{ color: badge.fg, background: badge.bg }}
                              title={badge.hint}
                            >
                              {badge.label}
                            </em>
                            <em style={{ color: color?.fg, background: color?.bg }}>
                              {classificationLabels[item.classification_code] ??
                                item.classification_code}
                            </em>
                          </div>
                        </td>
                        <td>
                          <code>{item.approved_role_code ?? '—'}</code>
                        </td>
                        <td>{item.approved_at?.slice(0, 10) ?? '—'}</td>
                        <td>
                          <button
                            className="ghost-button"
                            onClick={() => onNavigate('candidate', item.candidate_code)}
                          >
                            <Archive size={14} /> 数据卡
                          </button>
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          </>
        )}
      </Panel>
    </div>
  )
}
