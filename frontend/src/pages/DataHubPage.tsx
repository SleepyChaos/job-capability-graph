import {
  ArrowRight,
  CheckCircle2,
  Database,
  DatabaseZap,
  FileCheck2,
  GitBranch,
  ShieldCheck,
  TableProperties,
} from 'lucide-react'
import { MetricStrip, MiniLineChart, Panel, StatusTag } from '../components/ui'
import type { PageId } from '../types'

const sections = [
  {
    id: 'sources' as const,
    title: '数据采集中枢',
    description: '维护多源采集入口、定时任务、增量发现和解析质量。',
    icon: DatabaseZap,
    metric: '12 个数据源',
    detail: '今日新增 1,442 条',
    tone: 'teal',
  },
  {
    id: 'management' as const,
    title: '数据管理中心',
    description: '查询、查看和编辑 JD、技术词、里程碑与原始文档。',
    icon: TableProperties,
    metric: '4 类核心数据集',
    detail: '共 4,868 条结构化记录',
    tone: 'blue',
  },
  {
    id: 'taxonomy' as const,
    title: '技术词标准管理',
    description: '维护技术词标准、L1–L4 知识层级、T1–T7 领域映射与候选词版本。',
    icon: GitBranch,
    metric: '229 个标准技术点',
    detail: '8 个候选词待治理',
    tone: 'purple',
  },
  {
    id: 'review' as const,
    title: '数据审核中心',
    description: '审核低置信度 JD、关键词、里程碑及聚类或 T/L 分类。',
    icon: ShieldCheck,
    metric: '5 项待审核',
    detail: '平均处理时间 4.2h',
    tone: 'amber',
  },
]

export function DataHubPage({ onNavigate }: { onNavigate: (page: PageId) => void }) {
  return (
    <div className="page-stack">
      <div className="page-intro">
        <div><h2>数据中心</h2><p>负责从真实来源采集、清洗、抽取和治理可信数据；不在此处生成或定义新岗位。</p></div>
        <StatusTag tone="success">数据链路正常</StatusTag>
      </div>

      <MetricStrip items={[
        { label: '原始文档', value: '3,862', delta: '↑ 184' },
        { label: '有效 JD', value: '1,284', delta: '↑ 12.6%' },
        { label: '标准技术点', value: '229', delta: '8 个候选' },
        { label: '待审核事项', value: '5', delta: '今日减少 7' },
      ]} />

      <section className="data-hub-sections" aria-label="数据中心功能分区">
        {sections.map(({ id, title, description, icon: Icon, metric, detail, tone }) => (
          <button className={`data-hub-entry data-hub-entry--${tone}`} key={id} onClick={() => onNavigate(id)}>
            <div className="data-hub-entry-icon"><Icon size={22} /></div>
            <div className="data-hub-entry-copy"><span>{title}</span><strong>{metric}</strong><p>{description}</p><small>{detail}</small></div>
            <ArrowRight size={18} />
          </button>
        ))}
      </section>

      <div className="data-hub-grid">
        <Panel title="数据资产构成" subtitle="正式数据与原始证据保持版本关联">
          <div className="asset-composition">
            {[['原始文档', 3862, 100], ['标准化 JD', 1284, 72], ['技术表面词', 1872, 86], ['技术里程碑', 146, 36]].map(([label, value, width]) => (
              <div key={String(label)}><span>{label}</span><div><i style={{ width: `${width}%` }} /></div><strong>{Number(value).toLocaleString()}</strong></div>
            ))}
          </div>
        </Panel>
        <Panel title="近 14 天数据流入" subtitle="去重后的新增记录">
          <div className="hub-trend"><MiniLineChart values={[28, 41, 36, 52, 48, 63, 58, 72, 69, 81, 76, 88, 83, 96]} /><div><span>07-27</span><span>08-09</span></div></div>
        </Panel>
        <Panel title="治理状态" subtitle="从采集到发布的质量关口">
          <div className="governance-list">
            <div><CheckCircle2 size={17} /><span>来源合规信息完整</span><strong>12 / 12</strong></div>
            <div><CheckCircle2 size={17} /><span>结构化解析通过</span><strong>96.8%</strong></div>
            <div><FileCheck2 size={17} /><span>证据关联完整</span><strong>93.6%</strong></div>
            <div><Database size={17} /><span>待发布数据版本</span><strong>3</strong></div>
          </div>
        </Panel>
      </div>

      <Panel title="最近数据变更" subtitle="所有编辑、审核和版本发布均保留审计记录">
        <table className="compact-table data-change-table">
          <thead><tr><th>时间</th><th>数据对象</th><th>变更</th><th>操作者</th><th>结果</th></tr></thead>
          <tbody>
            <tr><td>今天 11:42</td><td>JD-2026-01284</td><td>修正岗位级别：高级 → 中级</td><td>研究员 张明</td><td><StatusTag tone="success">已生效</StatusTag></td></tr>
            <tr><td>今天 10:18</td><td>JD-RAW-01892</td><td>岗位级别缺失，进入低置信度审核</td><td>JD 抽取任务</td><td><StatusTag tone="warning">待审核</StatusTag></td></tr>
            <tr><td>今天 09:45</td><td>TERM-CAND-019</td><td>新增候选技术词“4D 高斯溅射”</td><td>技术抽取任务</td><td><StatusTag tone="warning">待审核</StatusTag></td></tr>
          </tbody>
        </table>
      </Panel>
    </div>
  )
}
