import { Archive, Eye, FileClock, RefreshCw } from 'lucide-react'
import { useMemo, useState } from 'react'
import { Modal, Panel, StatusTag } from '../components/ui'

const inferenceRecords = [
  { id: 'AUTO-20260809-004', type: '综合自动预测', input: '正式数据库快照 2026.08.09', result: '3 个新岗位候选', status: '已完成', time: '今天 11:42', owner: '系统任务' },
  { id: 'KEY-20260809-018', type: '技术词定向推演', input: 'Sim2Real + 合成数据', result: '2 个关联候选', status: '已保存', time: '今天 10:36', owner: '研究员 张明' },
  { id: 'NAME-20260809-011', type: '岗位名称推演', input: '具身世界模型评测工程师', result: '具备形成可能', status: '跟踪中', time: '今天 09:58', owner: '研究员 张明' },
  { id: 'KEY-20260808-017', type: '技术词定向推演', input: '触觉感知 + 模仿学习', result: '1 个关联候选', status: '已完成', time: '昨天 16:24', owner: '研究员 李然' },
  { id: 'NAME-20260808-010', type: '岗位名称推演', input: '机器人现场智能工程师', result: '已有预测候选', status: '已归并', time: '昨天 14:10', owner: '研究员 李然' },
]

export function JobRecordsPage({ notify }: { notify: (message: string) => void }) {
  const [filter, setFilter] = useState('全部')
  const [selectedRecord, setSelectedRecord] = useState<(typeof inferenceRecords)[number] | null>(null)
  const filteredRecords = useMemo(() => filter === '全部' ? inferenceRecords : inferenceRecords.filter((record) => record.type === filter), [filter])

  return (
    <div className="page-stack discovery-page">
      <div className="page-intro"><div><h2>推演结果记录库</h2><p>统一保存综合自动预测、技术词定向推演和岗位名称推演的输入、结果与后续处置。</p></div><button className="secondary-button" onClick={() => notify('记录库已同步到最新状态')}><RefreshCw size={15} />刷新记录</button></div>

      <div className="record-summary-strip"><div><span>累计推演</span><strong>128</strong></div><div><span>本周新增</span><strong>21</strong></div><div><span>转为候选</span><strong>17</strong></div><div><span>持续跟踪</span><strong>9</strong></div></div>

      <Panel title="推演记录" subtitle={`当前显示 ${filteredRecords.length} 条 Mock 记录`} action={<div className="record-filter" aria-label="记录类型筛选">{['全部', '综合自动预测', '技术词定向推演', '岗位名称推演'].map((item) => <button className={filter === item ? 'active' : ''} key={item} onClick={() => setFilter(item)}>{item}</button>)}</div>}>
        <div className="records-table-wrap"><table className="records-table"><thead><tr><th>记录编号</th><th>推演类型</th><th>输入条件</th><th>推演结果</th><th>状态</th><th>执行时间</th><th>操作</th></tr></thead><tbody>{filteredRecords.map((record) => <tr key={record.id}><td><strong>{record.id}</strong><span>{record.owner}</span></td><td>{record.type}</td><td>{record.input}</td><td>{record.result}</td><td><StatusTag tone={record.status === '跟踪中' ? 'info' : record.status === '已归并' ? 'neutral' : 'success'}>{record.status}</StatusTag></td><td>{record.time}</td><td><button className="table-action" onClick={() => setSelectedRecord(record)}><Eye size={14} />查看</button></td></tr>)}</tbody></table></div>
      </Panel>

      {selectedRecord ? <Modal title="推演记录详情" onClose={() => setSelectedRecord(null)}><div className="record-detail"><FileClock size={25} /><div><StatusTag tone="info">{selectedRecord.type}</StatusTag><h3>{selectedRecord.id}</h3><p>{selectedRecord.input}</p></div><dl><div><dt>执行主体</dt><dd>{selectedRecord.owner}</dd></div><div><dt>执行时间</dt><dd>{selectedRecord.time}</dd></div><div><dt>推演结果</dt><dd>{selectedRecord.result}</dd></div><div><dt>当前状态</dt><dd>{selectedRecord.status}</dd></div></dl><div className="modal-actions"><button className="secondary-button" onClick={() => { setSelectedRecord(null); notify('记录已归档') }}><Archive size={15} />归档记录</button><button className="primary-button" onClick={() => notify('已基于原始参数创建新的推演任务')}>使用原参数再次推演</button></div></div></Modal> : null}
    </div>
  )
}
