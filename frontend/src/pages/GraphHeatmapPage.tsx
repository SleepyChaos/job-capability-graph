import type { CSSProperties } from 'react'
import { useState } from 'react'
import { DomainLegend } from '../components/DomainLegend'
import { GraphFilters, type GraphFilterState } from '../components/GraphFilters'
import { Panel, StatusTag } from '../components/ui'
import { domainColors, domainTechnologyHeatRows, heatDayLabels, l2TechnologyHeatRows } from '../data/graphData'

const detailInitialFilters: GraphFilterState = {
  domain: 'T1 机器人本体与控制',
  level: 'L2 能力域',
  stack: '全部技术栈',
  period: '近 45 天',
}

interface DailyHeatBandsProps {
  values: number[]
  domain: string
  labelPrefix: string
  maxValue: number
  selectedDay: number
  onSelect: (day: number, value: number) => void
}

function DailyHeatBands({ values, domain, labelPrefix, maxValue, selectedDay, onSelect }: DailyHeatBandsProps) {
  return (
    <div className="daily-heat-bands">
      {[0, 1, 2].map((band) => {
        const start = band * 15
        const bandValues = values.slice(start, start + 15)
        return (
          <div className="daily-heat-row" role="row" key={start}>
            <span className="daily-heat-range">{heatDayLabels[start]}—{heatDayLabels[start + 14]}</span>
            <div className="daily-heat-cells">
              {bandValues.map((value, offset) => {
                const day = start + offset
                return (
                  <button
                    type="button"
                    role="gridcell"
                    className={selectedDay === day ? 'selected' : ''}
                    key={heatDayLabels[day]}
                    style={{
                      '--domain-color': domainColors[domain],
                      '--heat': `${Math.max(7, Math.round(value / maxValue * 100))}%`,
                      '--cell-text': value >= maxValue * .56 ? '#fff' : '#1c405b',
                    } as CSSProperties}
                    aria-label={`${labelPrefix}，${heatDayLabels[day]}，新增材料触发 ${value} 次`}
                    aria-selected={selectedDay === day}
                    onClick={() => onSelect(day, value)}
                  >{value}</button>
                )
              })}
            </div>
          </div>
        )
      })}
    </div>
  )
}

export function GraphHeatmapPage({ notify }: { notify: (message: string) => void }) {
  const [filters, setFilters] = useState<GraphFilterState>(detailInitialFilters)
  const [globalSelection, setGlobalSelection] = useState({ domain: 'T3', day: 44 })
  const [detailSelection, setDetailSelection] = useState({ rowId: l2TechnologyHeatRows[0].id, day: 44 })
  const domainCode = filters.domain.startsWith('T') ? filters.domain.slice(0, 2) : 'T1'
  const visibleL2Rows = l2TechnologyHeatRows.filter((row) => row.domain === domainCode)
  const selectedGlobalRow = domainTechnologyHeatRows.find((row) => row.domain === globalSelection.domain) ?? domainTechnologyHeatRows[2]
  const selectedDetailRow = visibleL2Rows.find((row) => row.id === detailSelection.rowId) ?? visibleL2Rows[0]
  const selectedGlobalValue = selectedGlobalRow.values[globalSelection.day]
  const selectedDetailValue = selectedDetailRow.values[detailSelection.day]

  const updateFilters = (next: GraphFilterState) => {
    const nextDomain = next.domain.startsWith('T') ? next.domain.slice(0, 2) : 'T1'
    if (nextDomain !== domainCode) {
      const firstRow = l2TechnologyHeatRows.find((row) => row.domain === nextDomain)
      if (firstRow) setDetailSelection({ rowId: firstRow.id, day: 44 })
    }
    setFilters(next)
  }

  return (
    <div className="page-stack graph-analysis-page">
      <div className="page-intro"><div><h2>能力热力图</h2><p>以日格呈现最近 45 天新增材料对技术词的触发次数；默认按七个技术域汇总，筛选后下钻到域内 L2 技术词。</p></div></div>

      <Panel title="全局技术域 · 近 45 天触发热力图" subtitle="固定 21 行 × 15 日格；每三行连续表示一个技术域的 45 天，每格对应一天" action={<StatusTag tone="info">315 个日格</StatusTag>}>
        <div className="calendar-heat-scroll">
          <div className="calendar-heat-grid" role="grid" aria-label="七个技术域最近 45 天材料触发次数热力图，共 21 行 15 列" aria-rowcount={21} aria-colcount={15}>
            {domainTechnologyHeatRows.map((row) => {
              const total = row.values.reduce((sum, value) => sum + value, 0)
              return (
                <section className="calendar-domain-group" key={row.domain} aria-label={`${row.domain} ${row.name}`}>
                  <div className="calendar-domain-label"><i style={{ background: domainColors[row.domain] }} /><strong>{row.domain}</strong><span>{row.name}</span><small>45 天 {total} 次</small></div>
                  <DailyHeatBands values={row.values} domain={row.domain} labelPrefix={`${row.domain} ${row.name}`} maxValue={42} selectedDay={globalSelection.domain === row.domain ? globalSelection.day : -1} onSelect={(day) => setGlobalSelection({ domain: row.domain, day })} />
                </section>
              )
            })}
          </div>
        </div>
        <div className="calendar-heat-footer" aria-live="polite"><DomainLegend /><div><span>选中日格</span><strong>{selectedGlobalRow.domain} {selectedGlobalRow.name} · {heatDayLabels[globalSelection.day]}</strong><p>新增材料触发 <b>{selectedGlobalValue}</b> 次；45 天累计 {selectedGlobalRow.values.reduce((sum, value) => sum + value, 0)} 次。</p></div><div className="heat-scale"><span>0 / 低频</span><i style={{ '--domain-color': domainColors[selectedGlobalRow.domain] } as CSSProperties} /><span>高频</span></div></div>
      </Panel>

      <GraphFilters initialValues={detailInitialFilters} onChange={updateFilters} onApply={(summary) => notify(`热力图筛选已更新：${summary}`)} />

      <Panel title={`${domainCode} 技术域 · L2 技术词 45 天触发明细`} subtitle="分类筛选后的每个 L2 技术词仍使用三行十五列日格，便于比较同一技术域内的触发频次" action={<StatusTag tone="success">{visibleL2Rows.length} 个 L2 技术词</StatusTag>}>
        <div className="calendar-heat-scroll">
          <div className="calendar-heat-grid calendar-heat-grid--detail" role="grid" aria-label={`${domainCode} 技术域 L2 技术词最近 45 天触发次数`} aria-rowcount={visibleL2Rows.length * 3} aria-colcount={15}>
            {visibleL2Rows.map((row) => {
              const total = row.values.reduce((sum, value) => sum + value, 0)
              return (
                <section className="calendar-domain-group" key={row.id} aria-label={`${row.name}最近45天`}>
                  <div className="calendar-domain-label"><i style={{ background: domainColors[row.domain] }} /><strong>{row.name}</strong><span>{row.domain} · L2</span><small>45 天 {total} 次</small></div>
                  <DailyHeatBands values={row.values} domain={row.domain} labelPrefix={`${row.domain} ${row.name}`} maxValue={18} selectedDay={selectedDetailRow.id === row.id ? detailSelection.day : -1} onSelect={(day) => setDetailSelection({ rowId: row.id, day })} />
                </section>
              )
            })}
          </div>
        </div>
        <div className="calendar-detail-summary" aria-live="polite"><i style={{ background: domainColors[selectedDetailRow.domain] }} /><div><span>选中 L2 技术词</span><strong>{selectedDetailRow.name}</strong></div><div><span>{heatDayLabels[detailSelection.day]}</span><strong>{selectedDetailValue} 次触发</strong></div><div><span>45 天累计</span><strong>{selectedDetailRow.values.reduce((sum, value) => sum + value, 0)} 次</strong></div></div>
      </Panel>
      <p className="chart-source-note">统计口径：每个日格统计当天新采集、去重并完成有效解析的材料对对应技术域或 L2 技术词的触发次数；没有触发按 0 显示。</p>
    </div>
  )
}
