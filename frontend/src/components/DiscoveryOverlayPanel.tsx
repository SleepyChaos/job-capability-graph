import { classificationColor } from '../api/discovery'
import type { DiscoveryCandidate } from '../api/newRoleDiscovery'
import { Panel } from './ui'

/**
 * 新岗位发现叠加面板，三张图谱共用。
 *
 * 候选是**未入库的提议**，卡片用虚线边框与图谱里已观测的实体区分——同一屏里
 * 「已观测的岗位」和「算法提出的岗位」不能长得一样。`footnote` 由各视图给出
 * 自己的覆盖口径，读者才知道没列出来的那些为什么没列。
 */
export function DiscoveryOverlayPanel({
  title,
  subtitle,
  footnote,
  items,
  loading,
  error,
  empty,
}: {
  title: string
  subtitle: string
  footnote?: string
  items: DiscoveryCandidate[]
  loading: boolean
  error: string
  empty: string
}) {
  return (
    <Panel className="discovery-overlay-panel" title={title} subtitle={subtitle}>
      {error ? (
        <div className="empty-state"><span>{error}</span></div>
      ) : loading ? (
        <div className="empty-state"><span>加载中…</span></div>
      ) : items.length === 0 ? (
        <div className="empty-state"><span>{empty}</span></div>
      ) : (
        <>
          <div className="discovery-overlay-list">
            {items.map((item) => (
              <button
                key={item.candidateCode}
                onClick={() => { window.location.hash = `/candidate/${encodeURIComponent(item.candidateCode)}` }}
              >
                <div className="discovery-overlay-head">
                  <strong>{item.name}</strong>
                  <span
                    className="discovery-overlay-tag"
                    style={{
                      color: classificationColor[item.classificationCode]?.fg,
                      background: classificationColor[item.classificationCode]?.bg,
                    }}
                  >
                    {item.classification}
                  </span>
                </div>
                {item.definition ? <p>{item.definition}</p> : null}
                <small>
                  {item.technologyNames.slice(0, 3).join('、')}
                  {item.technologyNames.length > 3 ? ` 等 ${item.technologyNames.length} 项` : ''}
                  {' · '}成熟度{item.maturity}
                  {item.supportJobCount > 0 ? ` · 支撑 ${item.supportJobCount} 份 JD` : ' · 无招聘证据'}
                </small>
              </button>
            ))}
          </div>
          {footnote ? <p className="discovery-overlay-footnote">{footnote}</p> : null}
        </>
      )}
    </Panel>
  )
}

