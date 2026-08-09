import { Download, Eye, Filter, History, Pencil, Plus, Search, TableProperties } from 'lucide-react'
import { useMemo, useState } from 'react'
import { MetricStrip, Modal, Panel, StatusTag } from '../components/ui'

type DatasetId = 'jd' | 'terms' | 'milestones' | 'documents'

interface DataRecord {
  id: string
  dataset: DatasetId
  title: string
  category: string
  source: string
  updatedAt: string
  version: string
  status: '正式' | '候选' | '待校验'
  summary: string
}

const datasetTabs: { id: DatasetId; label: string; count: number }[] = [
  { id: 'jd', label: 'JD 库', count: 1284 },
  { id: 'terms', label: '技术词库', count: 2151 },
  { id: 'milestones', label: '里程碑事件', count: 146 },
  { id: 'documents', label: '原始文档', count: 3862 },
]

const initialRecords: DataRecord[] = [
  { id: 'JD-2026-01284', dataset: 'jd', title: '具身智能系统集成工程师', category: '岗位 JD', source: '某头部机器人企业', updatedAt: '今天 11:42', version: 'v3', status: '正式', summary: '负责机器人感知、规划和控制模块的系统集成、联调与性能验证。' },
  { id: 'JD-2026-01271', dataset: 'jd', title: '机器人运动规划算法工程师', category: '岗位 JD', source: '重点企业官网', updatedAt: '今天 10:36', version: 'v2', status: '正式', summary: '负责移动操作机器人的路径规划、轨迹优化和避障算法。' },
  { id: 'JD-2026-01256', dataset: 'jd', title: '具身数据合成工程师', category: '岗位 JD', source: '智联招聘', updatedAt: '今天 09:51', version: 'v1', status: '候选', summary: '建设仿真场景、合成数据管线以及仿真到真实的数据验证闭环。' },
  { id: 'TERM-L3-083', dataset: 'terms', title: 'Sim2Real', category: 'L3 标准技术点', source: '技术词主数据', updatedAt: '昨天 18:22', version: 'v7', status: '正式', summary: '从仿真环境到真实系统的模型、策略或控制能力迁移方法。' },
  { id: 'TERM-CAND-019', dataset: 'terms', title: '4D 高斯溅射', category: '候选技术词', source: 'GitHub / arXiv', updatedAt: '今天 09:45', version: 'v1', status: '候选', summary: '用于动态三维场景表达与重建的新技术表达，等待领域映射审核。' },
  { id: 'MILE-2026-0146', dataset: 'milestones', title: '通用机器人仿真评测基准发布', category: '技术里程碑', source: '企业官网', updatedAt: '昨天 16:08', version: 'v2', status: '待校验', summary: '公开多场景仿真评测基准并完成三类机器人平台验证。' },
  { id: 'DOC-2026-03862', dataset: 'documents', title: '机器人系统集成工程师招聘详情页', category: '网页快照', source: '企业招聘官网', updatedAt: '今天 10:21', version: 'v4', status: '正式', summary: '来源页面快照、正文、发布时间、内容哈希和解析结果。' },
]

export function DataManagementPage({ notify }: { notify: (message: string) => void }) {
  const [dataset, setDataset] = useState<DatasetId>('jd')
  const [query, setQuery] = useState('')
  const [records, setRecords] = useState(initialRecords)
  const [selected, setSelected] = useState<DataRecord | null>(null)
  const [editing, setEditing] = useState(false)

  const visibleRecords = useMemo(
    () => records.filter((record) => record.dataset === dataset && `${record.title}${record.id}${record.source}`.toLowerCase().includes(query.toLowerCase())),
    [dataset, query, records],
  )

  const saveRecord = (form: HTMLFormElement) => {
    if (!selected) return
    const data = new FormData(form)
    const title = String(data.get('title') ?? selected.title)
    const summary = String(data.get('summary') ?? selected.summary)
    setRecords((items) => items.map((item) => item.id === selected.id ? { ...item, title, summary, version: `v${Number(item.version.slice(1)) + 1}`, updatedAt: '刚刚' } : item))
    setSelected(null)
    setEditing(false)
    notify('数据记录已保存为新版本，原版本仍可追溯')
  }

  return (
    <div className="page-stack">
      <div className="page-intro">
        <div><h2>数据管理中心</h2><p>统一查询、查看和编辑结构化数据；编辑操作自动生成新版本并保留原始证据。</p></div>
        <div className="intro-actions"><button className="secondary-button"><Download size={15} />导出当前数据集</button><button className="primary-button" onClick={() => notify('Mock：已创建一条空白数据记录')}><Plus size={15} />新建记录</button></div>
      </div>

      <MetricStrip items={[
        { label: '有效 JD', value: '1,284', delta: '36 个聚类' },
        { label: '技术词记录', value: '2,151', delta: 'L3 + L4' },
        { label: '里程碑事件', value: '146', delta: '12 个待校验' },
        { label: '原始文档', value: '3,862', delta: '96.8% 已解析' },
      ]} />

      <Panel title="数据库内容" subtitle="当前展示 Mock 数据；正式版本由统一查询 API 提供" action={<div className="management-tools"><label className="inline-search"><Search size={15} /><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="搜索编号、名称或来源" /></label><button className="secondary-button"><Filter size={14} />高级筛选</button></div>}>
        <div className="dataset-tabs">
          {datasetTabs.map((tab) => <button className={dataset === tab.id ? 'active' : ''} onClick={() => setDataset(tab.id)} key={tab.id}><span>{tab.label}</span><em>{tab.count.toLocaleString()}</em></button>)}
        </div>
        <div className="table-wrap">
          <table className="data-table management-table">
            <thead><tr><th>编号 / 名称</th><th>数据类型</th><th>来源</th><th>版本</th><th>更新时间</th><th>状态</th><th>操作</th></tr></thead>
            <tbody>{visibleRecords.map((record) => (
              <tr key={record.id}>
                <td><strong>{record.title}</strong><small>{record.id}</small></td><td>{record.category}</td><td>{record.source}</td><td>{record.version}</td><td>{record.updatedAt}</td>
                <td><StatusTag tone={record.status === '正式' ? 'success' : record.status === '候选' ? 'warning' : 'info'}>{record.status}</StatusTag></td>
                <td><div className="record-actions"><button title="查看" onClick={() => { setSelected(record); setEditing(false) }}><Eye size={15} /></button><button title="编辑" onClick={() => { setSelected(record); setEditing(true) }}><Pencil size={14} /></button><button title="版本历史" onClick={() => notify(`${record.id} 当前为 ${record.version}，历史版本入口已打开`)}><History size={14} /></button></div></td>
              </tr>
            ))}</tbody>
          </table>
          {visibleRecords.length === 0 ? <div className="empty-state"><TableProperties size={25} /><strong>没有匹配的数据记录</strong><span>尝试切换数据集或修改搜索条件。</span></div> : null}
        </div>
      </Panel>

      <Panel title="数据编辑原则" subtitle="正式数据采用追加版本，不直接覆盖历史">
        <div className="management-rules"><div><strong>证据锁定</strong><span>来源、原文片段和内容哈希不可由普通编辑直接修改。</span></div><div><strong>版本递增</strong><span>保存修改后生成新版本，旧版本继续用于历史结果复现。</span></div><div><strong>高影响审核</strong><span>标准技术点、岗位定义和领域归属修改需要进入数据审核中心。</span></div></div>
      </Panel>

      {selected ? <Modal title={editing ? '编辑数据记录' : '查看数据记录'} onClose={() => { setSelected(null); setEditing(false) }}>
        <form className="record-detail-form" onSubmit={(event) => { event.preventDefault(); saveRecord(event.currentTarget) }}>
          <div className="record-meta"><StatusTag tone={selected.status === '正式' ? 'success' : 'warning'}>{selected.status}</StatusTag><span>{selected.id}</span><span>{selected.version}</span><span>{selected.source}</span></div>
          <label>名称<input name="title" defaultValue={selected.title} readOnly={!editing} /></label>
          <label>摘要<textarea name="summary" defaultValue={selected.summary} readOnly={!editing} /></label>
          <label>证据与来源<input value={`${selected.source} · 已关联原始证据`} readOnly /></label>
          <div className="modal-actions"><button type="button" className="secondary-button" onClick={() => { setSelected(null); setEditing(false) }}>关闭</button>{editing ? <button className="primary-button">保存为新版本</button> : <button type="button" className="primary-button" onClick={() => setEditing(true)}>进入编辑</button>}</div>
        </form>
      </Modal> : null}
    </div>
  )
}
