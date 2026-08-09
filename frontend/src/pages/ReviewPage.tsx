import { Check, Eye, Filter, Search, ShieldCheck, X } from 'lucide-react'
import { useMemo, useState } from 'react'
import { initialReviews } from '../data/mockData'
import { MetricStrip, Panel, StatusTag } from '../components/ui'
import type { ReviewItem } from '../types'

export function ReviewPage({ notify }: { notify: (message: string) => void }) {
  const [items, setItems] = useState<ReviewItem[]>(initialReviews)
  const [status, setStatus] = useState('待审核')
  const [query, setQuery] = useState('')
  const filtered = useMemo(() => items.filter((item) => (status === '全部' || item.status === status) && item.content.includes(query)), [items, query, status])
  const decide = (id: number, next: ReviewItem['status']) => { setItems((all) => all.map((item) => item.id === id ? { ...item, status: next } : item)); notify(`审核结果已记录：${next}`) }
  return (
    <div className="page-stack">
      <div className="page-intro"><div><h2>数据审核中心</h2><p>只处理数据采集与抽取阶段的低置信度结果；新岗位定义在“新岗位发现”中执行专项审批。</p></div><button className="secondary-button"><ShieldCheck size={16} />置信度与分流规则</button></div>
      <MetricStrip items={[
        { label: '待审核', value: String(items.filter((item) => item.status === '待审核').length) },
        { label: '观察中', value: String(items.filter((item) => item.status === '观察').length) },
        { label: '本周已通过', value: '23' },
        { label: '平均处理时间', value: '4.2h' },
      ]} />
      <Panel title="低置信度抽取审核队列" subtitle="JD 条目、关键词候选、里程碑候选及其聚类或 T/L 分类" action={<div className="review-filters"><label className="inline-search"><Search size={15} /><input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="搜索审核内容" /></label><button><Filter size={14} />置信度</button></div>}>
        <div className="review-status-tabs">{['待审核', '观察', '已通过', '已驳回', '全部'].map((item) => <button className={status === item ? 'active' : ''} onClick={() => setStatus(item)} key={item}>{item}</button>)}</div>
        <div className="table-wrap"><table className="data-table"><thead><tr><th>类型 / 内容</th><th>来源证据</th><th>置信度</th><th>提交时间</th><th>状态</th><th>操作</th></tr></thead><tbody>{filtered.map((item) => <tr key={item.id}><td><strong>{item.content}</strong><small>{item.type} · review-{item.id.toString().padStart(3, '0')}</small></td><td>{item.source}</td><td><span className="confidence-cell"><i style={{ width: `${item.confidence * 100}%` }} />{Math.round(item.confidence * 100)}%</span></td><td>{item.submittedAt}</td><td><StatusTag tone={item.status === '待审核' ? 'warning' : item.status === '已通过' ? 'success' : item.status === '已驳回' ? 'danger' : 'info'}>{item.status}</StatusTag></td><td><div className="review-actions"><button title="查看证据"><Eye size={15} /></button><button title="通过" onClick={() => decide(item.id, '已通过')}><Check size={15} /></button><button title="观察" onClick={() => decide(item.id, '观察')}>·</button><button title="驳回" onClick={() => decide(item.id, '已驳回')}><X size={15} /></button></div></td></tr>)}</tbody></table>{filtered.length === 0 ? <div className="empty-state"><ShieldCheck size={26} /><strong>当前筛选下没有审核项</strong><span>切换状态或清除搜索条件查看其他记录。</span></div> : null}</div>
      </Panel>
    </div>
  )
}
