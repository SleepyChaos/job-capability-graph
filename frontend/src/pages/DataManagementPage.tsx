import { Download, Eye, Plus, RefreshCw, Search, ShieldAlert, TableProperties } from 'lucide-react'
import { useCallback, useEffect, useState } from 'react'
import { dataCenterApi, type DocumentItem, type MilestoneItem } from '../api/dataCenter'
import { jobsApi, type JobDetail, type JobListItem, type JobSummary } from '../api/jobs'
import { taxonomyApi, type TechnologyNode } from '../api/taxonomy'
import { MetricStrip, Modal, Panel, StatusTag } from '../components/ui'

type DatasetId = 'jd' | 'terms' | 'milestones' | 'documents'
const PAGE_SIZE = 50

const documentTypeLabels: Record<string, string> = {
  job: '岗位 JD',
  paper: '论文文献',
  milestone_material: '里程碑材料',
}

const milestoneStatusLabels: Record<string, string> = {
  candidate: '候选',
  reviewing: '审核中',
  verified: '已验证',
  rejected: '已驳回',
  superseded: '已被替代',
}

export function DataManagementPage({ notify, initialQuery = '' }: { notify: (message: string) => void; initialQuery?: string }) {
  const [dataset, setDataset] = useState<DatasetId>('jd')
  const [query, setQuery] = useState(initialQuery)
  const [summary, setSummary] = useState<JobSummary | null>(null)

  // 标签页上的计数是各数据集的全量规模，不能被当次搜索结果覆盖——否则搜过一次
  // 「技术词库」再切回来，标签上显示的就是上次的命中数而不是库里的总量。
  const [totals, setTotals] = useState<Record<DatasetId, number>>({ jd: 0, terms: 0, milestones: 0, documents: 0 })
  // 当前数据集在当前筛选条件下的命中数，只用于分页。
  const [filteredTotal, setFilteredTotal] = useState(0)
  const [offset, setOffset] = useState(0)

  const [jobs, setJobs] = useState<JobListItem[]>([])
  const [jobDetail, setJobDetail] = useState<JobDetail | null>(null)
  const [terms, setTerms] = useState<TechnologyNode[]>([])
  const [milestones, setMilestones] = useState<MilestoneItem[]>([])
  const [documents, setDocuments] = useState<DocumentItem[]>([])

  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    setQuery(initialQuery)
  }, [initialQuery])

  useEffect(() => {
    const controller = new AbortController()
    Promise.all([
      jobsApi.summary(controller.signal),
      taxonomyApi.nodes({ limit: 1 }, controller.signal),
      dataCenterApi.milestones({ limit: 1 }, controller.signal),
      dataCenterApi.documentFacets(controller.signal),
    ])
      .then(([jobSummary, termPage, milestonePage, facets]) => {
        setSummary(jobSummary)
        setTotals({
          jd: jobSummary.total_jobs,
          terms: termPage.total,
          milestones: milestonePage.total,
          documents: facets.total,
        })
      })
      .catch((reason: Error) => { if (reason.name !== 'AbortError') setError(reason.message) })
    return () => controller.abort()
  }, [])

  const loadDataset = useCallback((signal?: AbortSignal) => {
    setLoading(true)
    setError('')
    const search = query || undefined
    const task = dataset === 'jd'
      ? jobsApi.list({ search, limit: PAGE_SIZE, offset }, signal).then((page) => { setJobs(page.items); setFilteredTotal(page.total) })
      : dataset === 'terms'
        ? taxonomyApi.nodes({ search, limit: PAGE_SIZE, offset }, signal).then((page) => { setTerms(page.items); setFilteredTotal(page.total) })
        : dataset === 'milestones'
          ? dataCenterApi.milestones({ search, limit: PAGE_SIZE, offset }, signal).then((page) => { setMilestones(page.items); setFilteredTotal(page.total) })
          : dataCenterApi.documents({ search, limit: PAGE_SIZE, offset }, signal).then((page) => { setDocuments(page.items); setFilteredTotal(page.total) })
    task
      .catch((reason: Error) => { if (reason.name !== 'AbortError') setError(reason.message) })
      .finally(() => setLoading(false))
  }, [dataset, query, offset])

  useEffect(() => {
    const controller = new AbortController()
    const timer = window.setTimeout(() => loadDataset(controller.signal), query ? 300 : 0)
    return () => { window.clearTimeout(timer); controller.abort() }
  }, [loadDataset, query])

  const openJobDetail = async (jobCode: string) => {
    try {
      setJobDetail(await jobsApi.detail(jobCode))
    } catch (reason) {
      notify(`JD 详情加载失败：${(reason as Error).message}`)
    }
  }

  const switchDataset = (next: DatasetId) => { setDataset(next); setQuery(''); setOffset(0) }
  // 改关键词必须回到第一页：停在第 5 页时输入搜索，命中只有 3 条的话页面会整屏空白。
  const updateQuery = (value: string) => { setQuery(value); setOffset(0) }

  const Pagination = () => (
    <div className="pagination-row">
      <button className="secondary-button" disabled={offset === 0} onClick={() => setOffset((value) => Math.max(0, value - PAGE_SIZE))}>上一页</button>
      <span>{filteredTotal === 0 ? 0 : offset + 1}–{Math.min(offset + PAGE_SIZE, filteredTotal)} / {filteredTotal.toLocaleString()}</span>
      <button className="secondary-button" disabled={offset + PAGE_SIZE >= filteredTotal} onClick={() => setOffset((value) => value + PAGE_SIZE)}>下一页</button>
    </div>
  )

  const datasetTabs: { id: DatasetId; label: string; count: string }[] = [
    { id: 'jd', label: 'JD 库', count: totals.jd.toLocaleString() },
    { id: 'terms', label: '技术词库', count: totals.terms.toLocaleString() },
    { id: 'milestones', label: '里程碑事件', count: totals.milestones.toLocaleString() },
    { id: 'documents', label: '原始文档', count: totals.documents.toLocaleString() },
  ]

  return (
    <div className="page-stack">
      <div className="page-intro">
        <div><h2>数据管理中心</h2><p>统一查询与查看结构化数据；编辑能力随版本化审核流程逐步开放。</p></div>
        <div className="intro-actions">
          <button className="secondary-button" onClick={() => notify('导出功能待接入（阶段 D 隐私脱敏导出完成后开放）')}><Download size={15} />导出当前数据集</button>
          <button className="primary-button" onClick={() => notify('新建记录入口待接入：JD 来自采集入库，技术词来自主数据导入，里程碑来自数据审核中心')}><Plus size={15} />新建记录</button>
        </div>
      </div>

      <MetricStrip items={[
        { label: '正式 JD', value: (summary?.total_jobs ?? 0).toLocaleString(), delta: `${summary?.organization_count ?? 0} 家机构` },
        { label: '技术词记录', value: totals.terms.toLocaleString(), delta: 'L1–L4' },
        { label: '里程碑事件', value: totals.milestones.toLocaleString(), delta: '人工整理集' },
        { label: '原始文档', value: totals.documents.toLocaleString(), delta: 'JD / 论文 / 里程碑材料' },
      ]} />

      <Panel title="数据库内容" subtitle="全部数据来自后端查询接口" action={<label className="inline-search"><Search size={15} /><input value={query} onChange={(event) => updateQuery(event.target.value)} placeholder={dataset === 'documents' ? '搜索标题或正文' : '搜索名称、编码或机构'} /></label>}>
        <div className="dataset-tabs">
          {datasetTabs.map((tab) => <button className={dataset === tab.id ? 'active' : ''} onClick={() => switchDataset(tab.id)} key={tab.id}><span>{tab.label}</span><em>{tab.count}</em></button>)}
        </div>

        {error ? <div className="empty-state"><ShieldAlert size={25} /><strong>加载失败</strong><span>{error}</span></div> : loading ? <div className="empty-state"><RefreshCw className="spin" size={22} /><strong>正在加载…</strong></div> : (
          <div className="table-wrap">
            {dataset === 'jd' ? (
              <>
                <table className="data-table management-table">
                  <thead><tr><th>编号 / 岗位名称</th><th>机构</th><th>级别</th><th>时间质量</th><th>技术证据</th><th>重复簇</th><th>操作</th></tr></thead>
                  <tbody>{jobs.map((job) => (
                    <tr key={job.job_code}>
                      <td><strong>{job.title}</strong><small>{job.job_code}{job.source_job_id ? ` · ${job.source_job_id}` : ''}</small></td>
                      <td>{job.company ?? '—'}</td>
                      <td>{job.level ?? '—'}</td>
                      <td><StatusTag tone={job.time_quality === 'source_collected' ? 'success' : 'info'}>{job.time_quality === 'source_collected' ? '来源时间' : '仅迁移时间'}</StatusTag></td>
                      <td>{job.technology_count} 项</td>
                      <td>{job.duplicate_group_code ? <StatusTag tone="warning">{job.duplicate_group_code}</StatusTag> : '—'}</td>
                      <td><div className="record-actions"><button title="查看详情" onClick={() => openJobDetail(job.job_code)}><Eye size={15} /></button><button title="编辑（待接入岗位版本审核流程）" disabled onClick={() => notify('JD 编辑将通过岗位版本审核流程开放')}>编</button></div></td>
                    </tr>
                  ))}</tbody>
                </table>
                <Pagination />
              </>
            ) : null}

            {dataset === 'terms' ? (
              <>
                <table className="data-table management-table">
                  <thead><tr><th>编码 / 名称</th><th>层级</th><th>上级编码</th><th>T 领域</th><th>语义角色</th><th>别名数</th></tr></thead>
                  <tbody>{terms.map((node) => (
                    <tr key={node.code}>
                      <td><strong>{node.name}</strong><small>{node.code}</small></td>
                      <td><StatusTag tone="info">{node.level}</StatusTag></td>
                      <td>{node.parent_code ?? '—'}</td>
                      <td>{node.domain_code} {node.domain_name}</td>
                      <td>{node.semantic_role ?? '—'}</td>
                      <td>{node.alias_count}</td>
                    </tr>
                  ))}</tbody>
                </table>
                <Pagination />
              </>
            ) : null}

            {dataset === 'milestones' ? (
              milestones.length === 0 ? (
                <div className="empty-state"><TableProperties size={25} /><strong>没有匹配的里程碑</strong><span>尝试修改搜索条件；新的候选可在数据审核中心提交。</span></div>
              ) : (
                <>
                <table className="data-table management-table">
                  <thead><tr><th>编号 / 名称</th><th>类型</th><th>年份 / 日期</th><th>技术编码</th><th>状态</th></tr></thead>
                  <tbody>{milestones.map((milestone) => (
                    <tr key={milestone.milestone_code}>
                      <td><strong>{milestone.milestone_name}</strong><small>{milestone.milestone_code}</small></td>
                      <td>{milestone.milestone_type_code}</td>
                      <td>{milestone.event_date ?? milestone.event_year}</td>
                      <td>{milestone.technology_codes.slice(0, 3).join('、')}{milestone.technology_codes.length > 3 ? ` 等 ${milestone.technology_codes.length} 项` : ''}</td>
                      <td><StatusTag tone={milestone.verification_status_code === 'verified' ? 'success' : 'warning'}>{milestoneStatusLabels[milestone.verification_status_code] ?? milestone.verification_status_code}</StatusTag></td>
                    </tr>
                  ))}</tbody>
                </table>
                <Pagination />
                </>
              )
            ) : null}

            {dataset === 'documents' ? (
              documents.length === 0 ? (
                <div className="empty-state"><TableProperties size={25} /><strong>没有匹配的原始文档</strong><span>尝试修改搜索条件。</span></div>
              ) : (
                <>
                <table className="data-table management-table">
                  <thead><tr><th>标题</th><th>类型</th><th>来源</th><th>记录键</th><th>发表日期</th><th>操作</th></tr></thead>
                  <tbody>{documents.map((document) => (
                    <tr key={document.document_code}>
                      <td><strong>{document.title ?? '（无标题）'}</strong><small>{document.document_code}</small></td>
                      <td><StatusTag tone={document.document_type_code === 'paper' ? 'info' : 'neutral'}>{documentTypeLabels[document.document_type_code] ?? document.document_type_code}</StatusTag></td>
                      <td>{document.source_name}</td>
                      <td>{document.source_record_key ?? '—'}</td>
                      <td>{document.published_at ?? '—'}</td>
                      <td>{document.canonical_url ? <a href={document.canonical_url} target="_blank" rel="noreferrer noopener">原文</a> : '—'}</td>
                    </tr>
                  ))}</tbody>
                </table>
                <Pagination />
                </>
              )
            ) : null}

            {(dataset === 'jd' && jobs.length === 0) || (dataset === 'terms' && terms.length === 0) ? (
              <div className="empty-state"><TableProperties size={25} /><strong>没有匹配的数据记录</strong><span>尝试修改搜索条件。</span></div>
            ) : null}
          </div>
        )}
      </Panel>

      <Panel title="数据管理原则" subtitle="正式数据采用追加版本，不直接覆盖历史">
        <div className="management-rules"><div><strong>证据锁定</strong><span>来源、原文片段和内容哈希不可由普通编辑直接修改。</span></div><div><strong>版本递增</strong><span>保存修改后生成新版本，旧版本继续用于历史结果复现。</span></div><div><strong>高影响审核</strong><span>标准技术点、岗位定义和领域归属修改需要进入数据审核中心。</span></div></div>
      </Panel>

      {jobDetail ? (
        <Modal title={`JD 详情 · ${jobDetail.job_code}`} onClose={() => setJobDetail(null)}>
          <div className="record-detail-form">
            <div className="record-meta">
              <StatusTag tone="success">{jobDetail.title}</StatusTag>
              <span>{jobDetail.company ?? '未知机构'}</span>
              <span>{jobDetail.region ?? '地点未识别'}</span>
              <span>证据权重 {Number(jobDetail.evidence_weight).toFixed(2)}</span>
            </div>
            <div className="mini-grid" style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px 20px', marginBottom: '16px' }}>
              <div><small style={{ color: '#64748b' }}>级别</small><div style={{ fontWeight: 600 }}>{jobDetail.level_code ?? '—'}</div></div>
              <div><small style={{ color: '#64748b' }}>时间质量</small><div style={{ fontWeight: 600 }}>{jobDetail.time_quality_code ?? '—'}</div></div>
              <div><small style={{ color: '#64748b' }}>采集日期</small><div style={{ fontWeight: 600 }}>{jobDetail.source_collected_at_date ?? '—'}</div></div>
              <div><small style={{ color: '#64748b' }}>发布日期</small><div style={{ fontWeight: 600 }}>{jobDetail.published_at_date ?? '—'}</div></div>
              <div><small style={{ color: '#64748b' }}>来源岗位ID</small><div style={{ fontWeight: 600 }}>{jobDetail.source_job_id ?? '—'}</div></div>
              <div><small style={{ color: '#64748b' }}>重复簇</small><div style={{ fontWeight: 600 }}>{jobDetail.duplicate_group_code ?? '—'}</div></div>
              <div><small style={{ color: '#64748b' }}>解析状态</small><div style={{ fontWeight: 600 }}>{jobDetail.parse_status_code ?? '—'}</div></div>
              <div><small style={{ color: '#64748b' }}>歧义待复核数</small><div style={{ fontWeight: 600 }}>{jobDetail.ambiguity_review_count ?? 0} {jobDetail.review_required ? <StatusTag tone="warning" style={{ marginLeft: '6px' }}>待复核</StatusTag> : null}</div></div>
            </div>
            <label>JD 正文<textarea rows={6} readOnly value={jobDetail.jd_text} /></label>
            <label>来源编码<input value={jobDetail.source_codes.join('、') || '—'} readOnly /></label>
            <div className="table-wrap">
              <table className="data-table">
                <thead><tr><th>#</th><th>技术点</th><th>类型</th><th>状态</th><th>歧义原因</th><th>原词</th><th>置信度</th><th>证据片段</th></tr></thead>
                <tbody>{jobDetail.technologies.map((tech) => (
                  <tr key={`${jobDetail.job_code}-${tech.requirement_no}`}>
                    <td>{tech.requirement_no}</td>
                    <td><strong>{tech.technology_name}</strong><small>{tech.technology_code}</small></td>
                    <td><StatusTag tone={tech.requirement_type === 'required' ? 'warning' : 'info'}>{tech.requirement_type === 'required' ? '必需' : '加分'}</StatusTag></td>
                    <td>{tech.assessment_status ? <StatusTag tone={tech.assessment_status === 'accepted' ? 'success' : tech.assessment_status === 'rejected' ? 'danger' : 'warning'}>{tech.assessment_status === 'accepted' ? '已采纳' : tech.assessment_status === 'rejected' ? '已驳回' : '待复核'}</StatusTag> : '—'}</td>
                    <td>{tech.ambiguity_reason_label ?? '—'}</td>
                    <td>{tech.raw_term ?? '—'}</td>
                    <td>{Number(tech.confidence).toFixed(2)}</td>
                    <td><small>{tech.evidence[0] ?? '—'}{tech.evidence.length > 1 ? ` 等 ${tech.evidence.length} 条` : ''}</small></td>
                  </tr>
                ))}</tbody>
              </table>
            </div>
            <div className="modal-actions"><button type="button" className="secondary-button" onClick={() => setJobDetail(null)}>关闭</button></div>
          </div>
        </Modal>
      ) : null}
    </div>
  )
}
