import { Activity, AlertTriangle, ArrowLeft } from 'lucide-react'
import type { CSSProperties } from 'react'
import { useEffect, useMemo, useState } from 'react'
import {
  graphApi,
  graphDomainCode,
  graphLevelCode,
  type HeatCell,
  type HeatmapResponse,
} from '../api/graphs'
import { DomainLegend } from '../components/DomainLegend'
import { GraphFilters, type GraphFilterState } from '../components/GraphFilters'
import { Panel, StatusTag } from '../components/ui'
import { domainColors } from '../data/graphData'

interface DailyHeatBandsProps {
  values: HeatCell[]
  domain: string
  labelPrefix: string
  maxValue: number
  selectedDay: number
  onSelect: (day: number) => void
}

function DailyHeatBands({ values, domain, labelPrefix, maxValue, selectedDay, onSelect }: DailyHeatBandsProps) {
  return <div className="daily-heat-bands">{[0, 1, 2].map((band) => {
    const start = band * 15
    return <div className="daily-heat-row" role="row" key={start}><span className="daily-heat-range">{values[start]?.metric_date.slice(5)}—{values[start + 14]?.metric_date.slice(5)}</span><div className="daily-heat-cells">{values.slice(start, start + 15).map((cell, offset) => {
      const day = start + offset
      const heat = maxValue ? Math.round(cell.trigger_document_count / maxValue * 100) : 0
      return <button type="button" role="gridcell" className={selectedDay === day ? 'selected' : ''} key={cell.metric_date} style={{ '--domain-color': domainColors[domain], '--heat': `${Math.max(4, heat)}%`, '--cell-text': heat >= 56 ? '#fff' : '#1c405b' } as CSSProperties} aria-label={`${labelPrefix}，${cell.metric_date}，新增材料触发 ${cell.trigger_document_count} 次`} aria-selected={selectedDay === day} onClick={() => onSelect(day)}>{cell.trigger_document_count}</button>
    })}</div></div>
  })}</div>
}

export function GraphHeatmapPage({ notify }: { notify: (message: string) => void }) {
  const [filters, setFilters] = useState<GraphFilterState>({ domain: 'T1 智能算法与模型', level: 'L2 能力域' })
  const [data, setData] = useState<HeatmapResponse | null>(null)
  const [globalSelection, setGlobalSelection] = useState({ domain: 'T1', day: 44 })
  const [detailSelection, setDetailSelection] = useState({ technologyId: 0, day: 44 })
  const [error, setError] = useState<string | null>(null)
  const domainCode = graphDomainCode(filters.domain) ?? 'T1'
  const levelCode = graphLevelCode(filters.level)

  useEffect(() => {
    const controller = new AbortController()
    setError(null)
    graphApi.heatmap(domainCode, levelCode, controller.signal)
      .then((response) => {
        setData(response)
        setDetailSelection((current) => ({
          technologyId: response.detail_series.some((item) => item.technology_node_id === current.technologyId) ? current.technologyId : response.detail_series[0]?.technology_node_id ?? 0,
          day: current.day,
        }))
      })
      .catch((reason: Error) => {
        if (reason.name !== 'AbortError') setError(reason.message)
      })
    return () => controller.abort()
  }, [domainCode, levelCode])

  const selectedGlobal = data?.domain_series.find((item) => item.domain_code === globalSelection.domain) ?? data?.domain_series[0]
  const selectedDetail = data?.detail_series.find((item) => item.technology_node_id === detailSelection.technologyId) ?? data?.detail_series[0]
  const globalMax = useMemo(() => Math.max(1, ...(data?.domain_series.flatMap((item) => item.values.map((cell) => cell.trigger_document_count)) ?? [1])), [data])
  const detailMax = useMemo(() => Math.max(1, ...(data?.detail_series.flatMap((item) => item.values.map((cell) => cell.trigger_document_count)) ?? [1])), [data])
  const hasProjection = Boolean(data && data.data_version !== 'uninitialized')

  return <div className="page-stack graph-analysis-page">
    <div className="graph-breadcrumb"><button onClick={() => { window.location.hash = '/graph-relations' }}><ArrowLeft size={13} />产业链全局图谱</button><span>/</span><strong>能力时间热力图</strong></div>
    <div className="page-intro"><div><h2>能力热力图</h2><p>每个日格统计当天新进入正式库、去重并通过语境校验的材料触发数；同一 JD 对同一技术点每天只计一次。</p></div>{data ? <StatusTag tone={data.window.data_status === 'partial' ? 'warning' : 'success'}>{data.window.observed_date_count}/45 天有可靠数据</StatusTag> : null}</div>
    {error ? <div className="empty-state"><Activity size={24} /><strong>热力图加载失败</strong><span>{error}</span></div> : null}
    {!error && !data ? <div className="empty-state"><Activity size={24} /><strong>正在聚合 45 天触发数据</strong><span>按技术域和标准技术层级生成日格。</span></div> : null}
    {data?.window.warning && hasProjection ? <div className="graph-data-warning" role="status"><AlertTriangle size={17} /><div><strong>时间覆盖不足</strong><span>{data.window.warning}</span></div></div> : null}
    {data && !hasProjection ? <div className="empty-state"><Activity size={24} /><strong>暂无热力图快照</strong><span>当前数据库尚未生成成功的岗位聚类运行；完成 JD 解析和聚类后，这里会显示近 45 天触发数据。</span></div> : null}
    {data && hasProjection ? <>
      <Panel title="全局技术域 · 近 45 天触发热力图" subtitle="固定 21 行 × 15 日格；每三行连续表示一个技术域" action={<StatusTag tone="info">315 个日格</StatusTag>}>
        <div className="calendar-heat-scroll"><div className="calendar-heat-grid" role="grid" aria-label="七个技术域最近45天材料触发次数热力图" aria-rowcount={21} aria-colcount={15}>{data.domain_series.map((series) => <section className="calendar-domain-group" key={series.domain_code} aria-label={`${series.domain_code} ${series.domain_name}`}><div className="calendar-domain-label"><i style={{ background: series.color }} /><strong>{series.domain_code}</strong><span>{series.domain_name}</span><small>45 天 {series.total_trigger_documents} 次</small></div><DailyHeatBands values={series.values} domain={series.domain_code} labelPrefix={`${series.domain_code} ${series.domain_name}`} maxValue={globalMax} selectedDay={globalSelection.domain === series.domain_code ? globalSelection.day : -1} onSelect={(day) => setGlobalSelection({ domain: series.domain_code, day })} /></section>)}</div></div>
        {selectedGlobal ? <div className="calendar-heat-footer" aria-live="polite"><DomainLegend /><div><span>选中日格</span><strong>{selectedGlobal.domain_code} {selectedGlobal.domain_name} · {selectedGlobal.values[globalSelection.day].metric_date}</strong><p>去重材料触发 <b>{selectedGlobal.values[globalSelection.day].trigger_document_count}</b> 次；原文提及 {selectedGlobal.values[globalSelection.day].trigger_mention_count} 次。</p></div><div className="heat-scale"><span>0 / 低频</span><i style={{ '--domain-color': selectedGlobal.color } as CSSProperties} /><span>高频</span></div></div> : null}
      </Panel>
      <GraphFilters initialValues={filters} onChange={setFilters} onApply={(summary) => notify(`热力图筛选已更新：${summary}`)} />
      <Panel title={`${domainCode} 技术域 · ${levelCode} 标准技术 45 天明细`} subtitle="每个技术节点使用三行十五列日格，按45天累计触发量排序" action={<StatusTag tone="success">{data.detail_series.length} 个节点</StatusTag>}>
        <div className="calendar-heat-scroll"><div className="calendar-heat-grid calendar-heat-grid--detail" role="grid" aria-label={`${domainCode}技术域标准技术最近45天触发次数`} aria-rowcount={data.detail_series.length * 3} aria-colcount={15}>{data.detail_series.map((series) => <section className="calendar-domain-group" key={series.technology_node_id} aria-label={`${series.technology_name}最近45天`}><div className="calendar-domain-label"><i style={{ background: domainColors[series.domain_code] }} /><strong>{series.technology_name}</strong><span>{series.domain_code} · {series.level_code}</span><small>45 天 {series.total_trigger_documents} 次</small></div><DailyHeatBands values={series.values} domain={series.domain_code} labelPrefix={`${series.domain_code} ${series.technology_name}`} maxValue={detailMax} selectedDay={selectedDetail?.technology_node_id === series.technology_node_id ? detailSelection.day : -1} onSelect={(day) => setDetailSelection({ technologyId: series.technology_node_id, day })} /></section>)}</div></div>
        {selectedDetail ? <div className="calendar-detail-summary" aria-live="polite"><i style={{ background: domainColors[selectedDetail.domain_code] }} /><div><span>选中标准技术</span><strong>{selectedDetail.technology_name}</strong></div><div><span>{selectedDetail.values[detailSelection.day].metric_date}</span><strong>{selectedDetail.values[detailSelection.day].trigger_document_count} 次触发</strong></div><div><span>45 天累计</span><strong>{selectedDetail.total_trigger_documents} 次</strong></div></div> : <div className="empty-state"><strong>当前筛选没有有效技术触发</strong><span>可更换技术域或层级。</span></div>}
      </Panel>
      <p className="chart-source-note">窗口：{data.window.start_date} 至 {data.window.end_date}；数据版本 {data.data_version}。零值在当前数据覆盖不足时不能解释为市场没有需求。</p>
    </> : null}
  </div>
}
