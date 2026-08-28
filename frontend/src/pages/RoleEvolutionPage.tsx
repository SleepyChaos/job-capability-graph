import { AlertTriangle, GitCommitVertical, Layers, RefreshCw, ShieldAlert } from 'lucide-react'
import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  CHANGE_MARKS,
  changeKey,
  rolesApi,
  type RoleDetail,
  type RoleListItem,
} from '../api/roles'
import { Panel, StatusTag } from '../components/ui'

/**
 * 岗位能力演变。
 *
 * 演变只在「延续」关系上成立——同一岗位标识下相邻两个版本之间的能力差异。
 * 因此列表默认只列有两个及以上版本的岗位；首版岗位没有可比对象，列出来只会
 * 让读者以为「这个岗位没有变化」，而实际是「无从比较」。
 *
 * 变更标记直接叠在能力清单上，而不是另开一张「变更列表」：审阅者要判断的是
 * 「这个岗位现在要求什么、其中哪些是这一版才变的」，两件事分开看反而费劲。
 */
export function RoleEvolutionPage({ notify }: { notify: (message: string) => void }) {
  const [items, setItems] = useState<RoleListItem[]>([])
  const [total, setTotal] = useState(0)
  const [selectedCode, setSelectedCode] = useState('')
  const [detail, setDetail] = useState<RoleDetail | null>(null)
  const [loading, setLoading] = useState(true)
  const [detailLoading, setDetailLoading] = useState(false)
  const [changedOnly, setChangedOnly] = useState(false)
  const [error, setError] = useState('')

  const load = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const page = await rolesApi.list({ evolvedOnly: true, limit: 200 })
      setItems(page.items)
      setTotal(page.total)
      setSelectedCode((current) =>
        current && page.items.some((x) => x.role_code === current)
          ? current
          : page.items[0]?.role_code ?? '',
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
    setDetailLoading(true)
    rolesApi
      .detail(selectedCode, controller.signal)
      .then((data) => {
        if (controller.signal.aborted) return
        setDetail(data)
        setDetailLoading(false)
      })
      .catch((reason: Error) => {
        if (reason.name === 'AbortError') return
        setError(reason.message)
        setDetailLoading(false)
      })
    return () => controller.abort()
  }, [selectedCode])

  const visible = useMemo(
    () => (changedOnly ? items.filter((x) => x.change_count > 0) : items),
    [items, changedOnly],
  )

  // 变更按技术编码索引，渲染能力清单时直接查——变更项与能力项是同一批节点。
  const changeByCode = useMemo(() => {
    const map: Record<string, (typeof CHANGE_MARKS)[string] & { magnitude: string }> = {}
    for (const change of detail?.evolution_changes ?? []) {
      const style = CHANGE_MARKS[changeKey(change)]
      if (style) map[change.technology_code] = { ...style, magnitude: change.magnitude }
    }
    return map
  }, [detail])

  const tally = useMemo(() => {
    const counts: Record<string, number> = {}
    for (const change of detail?.evolution_changes ?? []) {
      const key = changeKey(change)
      counts[key] = (counts[key] ?? 0) + 1
    }
    return counts
  }, [detail])

  const versions = detail?.versions ?? []
  const current = versions[0]
  const previous = versions[1]

  return (
    <div className="page-stack">
      <div className="page-intro">
        <div>
          <h2>岗位能力演变</h2>
          <p>
            同一岗位标识下，相邻两个版本之间的能力要求差异。仅「延续」关系产生新版本，
            因此这里只列有两个及以上版本的岗位。
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

      <div className="review-layout">
        <Panel
          title="有版本可比的岗位"
          subtitle={`${total} 个 · 其中 ${items.filter((x) => x.change_count > 0).length} 个本版有能力变化`}
          action={
            <label className="evolution-filter">
              <input
                type="checkbox"
                checked={changedOnly}
                onChange={(event) => setChangedOnly(event.target.checked)}
              />
              只看有变化的
            </label>
          }
        >
          {loading ? (
            <div className="empty-state">
              <RefreshCw className="spin" size={22} />
              <strong>加载中…</strong>
            </div>
          ) : visible.length === 0 ? (
            <div className="empty-state">
              <Layers size={24} />
              <strong>没有符合条件的岗位</strong>
              <span>当前语料为单一时点快照，多数岗位只有首版，尚无可比对象。</span>
            </div>
          ) : (
            <div className="review-queue">
              {visible.map((item) => (
                <button
                  key={item.role_code}
                  className={item.role_code === selectedCode ? 'selected' : ''}
                  onClick={() => setSelectedCode(item.role_code)}
                >
                  <strong>{item.canonical_name}</strong>
                  <span>
                    v{item.latest_version_no} · {item.version_count} 个版本 · 能力项{' '}
                    {item.requirement_count}
                    {item.change_count > 0 ? ` · 本版变更 ${item.change_count}` : ' · 本版无变化'}
                  </span>
                  {item.has_comparison_warning ? <em>证据量波动提示</em> : null}
                </button>
              ))}
            </div>
          )}
        </Panel>

        <Panel className="review-detail">
          {!detail ? (
            <div className="empty-state">
              <GitCommitVertical size={24} />
              <strong>选择左侧岗位查看能力演变</strong>
            </div>
          ) : detailLoading ? (
            <div className="empty-state">
              <RefreshCw className="spin" size={22} />
              <strong>加载中…</strong>
            </div>
          ) : (
            <div className="review-body">
              <div className="review-head">
                <StatusTag tone="info">{detail.lifecycle_status}</StatusTag>
                <h2>{detail.canonical_name}</h2>
                <p>{detail.definition ?? '尚无岗位定义。'}</p>
              </div>

              {/* 版本条：两版之间发生了什么，一行说完 */}
              {current && previous ? (
                <div className="version-rail">
                  <span>
                    v{previous.version_no}
                    <small>{previous.valid_from}</small>
                  </span>
                  <i />
                  <span>
                    v{current.version_no}
                    <small>{current.valid_from} 起</small>
                  </span>
                  <div className="version-tally">
                    {Object.entries(CHANGE_MARKS).map(([key, style]) =>
                      tally[key] ? (
                        <em key={key} style={{ color: style.fg, background: style.bg }}>
                          {style.mark} {style.label} {tally[key]}
                        </em>
                      ) : null,
                    )}
                    {detail.evolution_changes.length === 0 ? (
                      <em className="version-tally-none">本版无能力变化</em>
                    ) : null}
                  </div>
                </div>
              ) : null}

              {/*
                对比警告不阻断版本生成——版本本身是事实，需要提醒的是怎么解读它。
                两版证据量相差过大时，能力项的增减可能只是采集量的波动。
              */}
              {detail.evolution_warning ? (
                <div className="evolution-warning">
                  <AlertTriangle size={16} />
                  <span>{detail.evolution_warning}</span>
                </div>
              ) : null}

              <div className="requirement-table-wrap">
                <table className="data-table requirement-table">
                  <thead>
                    <tr>
                      <th>能力项</th>
                      <th>重要度</th>
                      <th>支撑 JD</th>
                      <th>独立企业</th>
                      <th>本版变化</th>
                    </tr>
                  </thead>
                  <tbody>
                    {detail.requirements.map((req) => {
                      const change = changeByCode[req.technology_code]
                      return (
                        <tr key={req.technology_code} className={change ? 'is-changed' : undefined}>
                          <td>
                            <strong>{req.technology_name}</strong>
                            <code>{req.technology_code}</code>
                          </td>
                          <td className="num">{Number(req.importance).toFixed(1)}</td>
                          <td className="num">{req.job_count}</td>
                          <td className="num">{req.organization_count}</td>
                          <td>
                            {change ? (
                              <em style={{ color: change.fg, background: change.bg }}>
                                {change.mark} {change.label}
                                {Number(change.magnitude) ? ` ${Number(change.magnitude).toFixed(1)}` : ''}
                              </em>
                            ) : (
                              <span className="no-change">—</span>
                            )}
                          </td>
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
              </div>

              {/*
                能力清单只含最新版仍在的项；「已消失」的能力不在其中，
                否则读者会以为它还是当前要求。单列一处补上。
              */}
              {detail.evolution_changes.filter((c) => c.change_type === 'removed').length > 0 ? (
                <div className="removed-capabilities">
                  <span>本版消失的能力</span>
                  <div className="skill-tags">
                    {detail.evolution_changes
                      .filter((c) => c.change_type === 'removed')
                      .map((c) => (
                        <span
                          key={c.technology_code}
                          className="risk-tag"
                          title={c.technology_code}
                        >
                          {c.technology_name ?? c.technology_code}
                        </span>
                      ))}
                  </div>
                </div>
              ) : null}

              <p className="review-baseline">
                变化由同一岗位相邻两个版本的能力画像逐项比对得出，每条变更挂接支撑它的证据跨度。
                仅「延续」关系产生新版本；合并与拆分在人工确认前不产生版本。
              </p>
            </div>
          )}
        </Panel>
      </div>
    </div>
  )
}
