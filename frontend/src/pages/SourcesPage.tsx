import { ArrowRight, BrainCircuit, CheckCircle2, Clock3, Database, FileCheck2, FileText, Milestone, Network, Play, Plus, RefreshCw, Settings2, ShieldAlert, Tags } from 'lucide-react'
import { useState } from 'react'
import { sources as seedSources } from '../data/mockData'
import { MetricStrip, Panel, StatusTag } from '../components/ui'
import type { SourceItem } from '../types'

export function SourcesPage({ notify }: { notify: (message: string) => void }) {
  const [sources, setSources] = useState<SourceItem[]>(seedSources)
  const [running, setRunning] = useState<number | null>(null)

  const runSource = (id: number) => {
    setRunning(id)
    setSources((items) => items.map((item) => item.id === id ? { ...item, status: '采集中' } : item))
    window.setTimeout(() => {
      setSources((items) => items.map((item) => item.id === id ? { ...item, status: '正常', additions: item.additions + 12, lastRun: '刚刚' } : item))
      setRunning(null)
      notify('增量采集完成：发现 12 条新内容，4 条进入待审核池')
    }, 1100)
  }

  return (
    <div className="page-stack">
      <div className="page-intro">
        <div><h2>数据采集中枢</h2><p>维护招聘、企业、政府和技术动态入口，所有结果保留快照与证据链。</p></div>
        <button className="primary-button" onClick={() => notify('Mock：已打开新增数据源表单')}><Plus size={16} />新增数据源</button>
      </div>
      <MetricStrip items={[
        { label: '已启用数据源', value: '12' },
        { label: '今日新增文档', value: '1,442', delta: '↑ 8.3%' },
        { label: '解析成功率', value: '96.8%' },
        { label: '待处理异常', value: '3', delta: '需检查' },
      ]} />
      <Panel title="数据治理与入库流程" subtitle="本链路只从真实来源提取事实，不负责创新定义新岗位">
        <div className="ingestion-flow">
          <div className="ingestion-stage"><FileText size={19} /><div><strong>多源采集</strong><span>网页快照、正文与时间戳</span></div></div><ArrowRight size={17} />
          <div className="ingestion-stage"><BrainCircuit size={19} /><div><strong>清洗与幻觉防范</strong><span>去重、来源交叉验证、字段约束</span></div></div><ArrowRight size={17} />
          <div className="ingestion-stage ingestion-output"><FileCheck2 size={19} /><div><strong>结构化候选</strong><span>JD 条目 · 技术关键词 · 技术里程碑</span></div></div><ArrowRight size={17} />
          <div className="confidence-gate"><div className="high"><Database size={17} /><span><strong>高置信度</strong>直接进入数据库</span></div><div className="low"><ShieldAlert size={17} /><span><strong>低置信度</strong>进入数据审核中心</span></div></div>
        </div>
        <div className="data-routing-grid">
          <div><span className="routing-source"><FileText size={16} />JD 岗位条目</span><ArrowRight size={15} /><span><Network size={16} />岗位聚类与归属</span><ArrowRight size={15} /><strong>JD 库 / 岗位簇</strong></div>
          <div><span className="routing-source"><Tags size={16} />技术关键词</span><ArrowRight size={15} /><span>T1–T7 + L1–L4 分类</span><ArrowRight size={15} /><strong>技术词主数据</strong></div>
          <div><span className="routing-source"><Milestone size={16} />技术里程碑</span><ArrowRight size={15} /><span>T/L 领域与层级标注</span><ArrowRight size={15} /><strong>里程碑事件库</strong></div>
        </div>
      </Panel>
      <Panel title="数据源注册表" subtitle="列表页默认只深入一层到岗位或文章详情页" action={<button className="secondary-button"><Settings2 size={15} />批量策略</button>}>
        <div className="table-wrap">
          <table className="data-table">
            <thead><tr><th>数据源</th><th>类型</th><th>采集范围</th><th>周期</th><th>最近运行</th><th>新增</th><th>状态</th><th>操作</th></tr></thead>
            <tbody>{sources.map((source) => (
              <tr key={source.id}>
                <td><strong>{source.name}</strong><small>source-{String(source.id).padStart(3, '0')}</small></td>
                <td>{source.type}</td><td>{source.target}</td><td><Clock3 size={14} />{source.cadence}</td><td>{source.lastRun}</td><td>{source.additions}</td>
                <td><StatusTag tone={source.status === '正常' ? 'success' : source.status === '采集中' ? 'info' : 'warning'}>{source.status}</StatusTag></td>
                <td><button className="table-action" disabled={running !== null} onClick={() => runSource(source.id)}>{running === source.id ? <RefreshCw className="spin" size={15} /> : <Play size={15} />}运行</button></td>
              </tr>
            ))}</tbody>
          </table>
        </div>
      </Panel>
      <div className="two-columns">
        <Panel title="今日处理流水线">
          <ol className="pipeline-list">
            {['增量发现 1,442 条', '正文解析 1,396 条', '内容去重 1,217 条', '结构化抽取 1,184 条', '证据质检 1,146 条'].map((item, index) => <li key={item}><CheckCircle2 size={17} /><span>{item}</span><em>{98 - index * 2}%</em></li>)}
          </ol>
        </Panel>
        <Panel title="质量告警">
          <div className="alert-list">
            <button><StatusTag tone="warning">结构变化</StatusTag><div><strong>工信部政策栏目</strong><span>列表选择器成功率降至 72%</span></div></button>
            <button><StatusTag tone="info">重复转载</StatusTag><div><strong>行业媒体组</strong><span>发现 126 条高度相似内容，已合并来源组</span></div></button>
            <button><StatusTag tone="warning">时间缺失</StatusTag><div><strong>企业新闻页</strong><span>8 条内容未识别发布时间</span></div></button>
          </div>
        </Panel>
      </div>
    </div>
  )
}
