import { BookOpen, ExternalLink, RefreshCw, Search, ShieldAlert } from 'lucide-react'
import { useCallback, useEffect, useState } from 'react'
import {
  dataCenterApi,
  type DocumentDetail,
  type DocumentFacets,
  type DocumentItem,
} from '../api/dataCenter'
import { MetricStrip, Modal, Panel, StatusTag } from '../components/ui'

const PAGE_SIZE = 20

export function LiteraturePage({ notify }: { notify: (message: string) => void }) {
  const [facets, setFacets] = useState<DocumentFacets | null>(null)
  const [items, setItems] = useState<DocumentItem[]>([])
  const [total, setTotal] = useState(0)
  const [offset, setOffset] = useState(0)
  const [query, setQuery] = useState('')
  const [yearFrom, setYearFrom] = useState<number | null>(null)
  const [yearTo, setYearTo] = useState<number | null>(null)
  const [detail, setDetail] = useState<DocumentDetail | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    const controller = new AbortController()
    dataCenterApi
      .documentFacets(controller.signal)
      .then(setFacets)
      .catch((reason: Error) => { if (reason.name !== 'AbortError') setError(reason.message) })
    return () => controller.abort()
  }, [])

  const load = useCallback((signal?: AbortSignal) => {
    setLoading(true)
    setError('')
    dataCenterApi
      .documents(
        {
          search: query || undefined,
          doc_type: 'paper',
          year_from: yearFrom ?? undefined,
          year_to: yearTo ?? undefined,
          limit: PAGE_SIZE,
          offset,
        },
        signal,
      )
      .then((page) => { setItems(page.items); setTotal(page.total) })
      .catch((reason: Error) => { if (reason.name !== 'AbortError') setError(reason.message) })
      .finally(() => setLoading(false))
  }, [query, yearFrom, yearTo, offset])

  useEffect(() => {
    const controller = new AbortController()
    const timer = window.setTimeout(() => load(controller.signal), query ? 300 : 0)
    return () => { window.clearTimeout(timer); controller.abort() }
  }, [load, query])

  // 改检索条件必须回到第一页：否则在第 20 页上换关键词，新结果只有 3 条时页面会是空的。
  const updateQuery = (value: string) => { setQuery(value); setOffset(0) }
  const updateYear = (which: 'from' | 'to', value: string) => {
    const parsed = value === '' ? null : Number(value)
    if (which === 'from') setYearFrom(parsed)
    else setYearTo(parsed)
    setOffset(0)
  }

  const paperFacet = facets?.types.find((item) => item.code === 'paper')
  const years = facets?.years ?? []
  const openDetail = async (documentCode: string) => {
    try {
      setDetail(await dataCenterApi.document(documentCode))
    } catch (reason) {
      notify(`文献详情加载失败：${(reason as Error).message}`)
    }
  }

  return (
    <div className="page-stack">
      <div className="page-intro">
        <div>
          <h2>论文文献检索</h2>
          <p>
            检索已入库的 arXiv 上游语料。论文的发表日期是文档自带属性而非采集产物，
            因此它是上游信号里唯一干净的时间轴，用于判断「研究侧已经在做、招聘侧还没出现」。
          </p>
        </div>
      </div>

      <MetricStrip items={[
        { label: '论文文献', value: (paperFacet?.count ?? 0).toLocaleString(), delta: 'arXiv 摘要语料' },
        { label: '原始文档合计', value: (facets?.total ?? 0).toLocaleString(), delta: `${facets?.types.length ?? 0} 类文档` },
        { label: '覆盖年份', value: years.length > 0 ? `${years[years.length - 1].code}–${years[0].code}` : '—', delta: `${years.length} 个年度` },
        { label: '当前命中', value: total.toLocaleString(), delta: query ? `关键词「${query}」` : '未设关键词' },
      ]} />

      <Panel
        title="文献库"
        subtitle="标题与摘要全文匹配；结果按发表日期倒序"
        action={
          <label className="inline-search">
            <Search size={15} />
            <input value={query} onChange={(event) => updateQuery(event.target.value)} placeholder="搜索标题或摘要，如 manipulation、grasp" />
          </label>
        }
      >
        <div className="dataset-tabs" style={{ marginBottom: '14px' }}>
          <button className={yearFrom === null && yearTo === null ? 'active' : ''} onClick={() => { setYearFrom(null); setYearTo(null); setOffset(0) }}>
            <span>全部年份</span><em>{(paperFacet?.count ?? 0).toLocaleString()}</em>
          </button>
          {years.slice(0, 6).map((year) => (
            <button
              key={year.code}
              className={yearFrom === Number(year.code) && yearTo === Number(year.code) ? 'active' : ''}
              onClick={() => { setYearFrom(Number(year.code)); setYearTo(Number(year.code)); setOffset(0) }}
            >
              <span>{year.code}</span><em>{year.count.toLocaleString()}</em>
            </button>
          ))}
        </div>

        <div className="literature-range">
          <label>起始年<input type="number" value={yearFrom ?? ''} onChange={(event) => updateYear('from', event.target.value)} placeholder="不限" /></label>
          <label>截止年<input type="number" value={yearTo ?? ''} onChange={(event) => updateYear('to', event.target.value)} placeholder="不限" /></label>
        </div>

        {error ? (
          <div className="empty-state"><ShieldAlert size={25} /><strong>加载失败</strong><span>{error}</span></div>
        ) : loading ? (
          <div className="empty-state"><RefreshCw className="spin" size={22} /><strong>正在检索…</strong></div>
        ) : items.length === 0 ? (
          <div className="empty-state"><BookOpen size={25} /><strong>没有匹配的文献</strong><span>尝试放宽关键词或年份范围。</span></div>
        ) : (
          <>
            <div className="literature-list">
              {items.map((item) => (
                <button key={item.document_code} className="literature-card" onClick={() => openDetail(item.document_code)}>
                  <div className="literature-head">
                    <strong>{item.title ?? '（无标题）'}</strong>
                    <time>{item.published_at ?? '日期未知'}</time>
                  </div>
                  <p>{item.excerpt}</p>
                  <div className="literature-meta">
                    {item.source_record_key ? <StatusTag tone="info">{item.source_record_key}</StatusTag> : null}
                    {item.categories.slice(0, 4).map((category) => <StatusTag key={category} tone="neutral">{category}</StatusTag>)}
                  </div>
                </button>
              ))}
            </div>
            <div className="pagination-row">
              <button className="secondary-button" disabled={offset === 0} onClick={() => setOffset((value) => Math.max(0, value - PAGE_SIZE))}>上一页</button>
              <span>{offset + 1}–{Math.min(offset + PAGE_SIZE, total)} / {total.toLocaleString()}</span>
              <button className="secondary-button" disabled={offset + PAGE_SIZE >= total} onClick={() => setOffset((value) => value + PAGE_SIZE)}>下一页</button>
            </div>
          </>
        )}
      </Panel>

      {detail ? (
        <Modal title={detail.title ?? detail.document_code} onClose={() => setDetail(null)}>
          <div className="record-detail-form">
            <div className="record-meta">
              <StatusTag tone="success">{detail.source_record_key ?? detail.document_code}</StatusTag>
              <span>{detail.published_at ?? '日期未知'}</span>
              <span>{detail.source_name}</span>
              <span>版本 v{detail.version_no}</span>
            </div>
            <div className="literature-meta" style={{ marginBottom: '12px' }}>
              {detail.categories.map((category) => <StatusTag key={category} tone="neutral">{category}</StatusTag>)}
            </div>
            <label>摘要<textarea rows={10} readOnly value={detail.content_text || '（该文档没有摘要正文）'} /></label>
            <div className="modal-actions">
              {detail.canonical_url ? (
                <a className="secondary-button" href={detail.canonical_url} target="_blank" rel="noreferrer noopener">
                  <ExternalLink size={15} />在 arXiv 打开
                </a>
              ) : null}
              <button type="button" className="secondary-button" onClick={() => setDetail(null)}>关闭</button>
            </div>
          </div>
        </Modal>
      ) : null}
    </div>
  )
}
