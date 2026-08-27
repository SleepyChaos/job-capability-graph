import { ArrowRight, BrainCircuit, Database, FileCheck2, FileText, Milestone, Network, Play, Plus, RefreshCw, ShieldAlert, Tags } from 'lucide-react'
import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  dataCenterApi,
  type CollectionPolicy,
  type CollectionRun,
  type DataSourceItem,
} from '../api/dataCenter'
import { MetricStrip, Modal, Panel, StatusTag } from '../components/ui'

const sourceTypeLabels: Record<string, string> = {
  recruitment: '招聘网站',
  enterprise: '企业官网',
  government: '政府网站',
  research: '研究动态',
  other: '其他',
}

const contentTypeLabels: Record<string, string> = {
  job: '岗位 JD',
  industry: '产业动态',
  milestone: '技术里程碑',
  mixed: '混合内容',
}

export function SourcesPage({ notify }: { notify: (message: string) => void }) {
  const [sources, setSources] = useState<DataSourceItem[]>([])
  const [policies, setPolicies] = useState<CollectionPolicy[]>([])
  const [runs, setRuns] = useState<CollectionRun[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [runningCode, setRunningCode] = useState('')
  const [showSourceForm, setShowSourceForm] = useState(false)
  const [showPolicyForm, setShowPolicyForm] = useState(false)
  const [submitting, setSubmitting] = useState(false)

  const reload = useCallback(async (signal?: AbortSignal) => {
    const [sourceRows, policyRows, runRows] = await Promise.all([
      dataCenterApi.sources(signal),
      dataCenterApi.policies(signal),
      dataCenterApi.runs(signal),
    ])
    setSources(sourceRows)
    setPolicies(policyRows)
    setRuns(runRows)
  }, [])

  useEffect(() => {
    const controller = new AbortController()
    setLoading(true)
    reload(controller.signal)
      .catch((reason: Error) => { if (reason.name !== 'AbortError') setError(reason.message) })
      .finally(() => setLoading(false))
    return () => controller.abort()
  }, [reload])

  const policyBySource = useMemo(() => {
    const map = new Map<string, CollectionPolicy>()
    for (const policy of policies) {
      const existing = map.get(policy.source_code)
      if (!existing || policy.policy_version > existing.policy_version) map.set(policy.source_code, policy)
    }
    return map
  }, [policies])

  const latestRunBySource = useMemo(() => {
    const map = new Map<string, CollectionRun>()
    for (const run of runs) if (!map.has(run.source_code)) map.set(run.source_code, run)
    return map
  }, [runs])

  const discoveredTotal = runs.reduce((sum, run) => sum + run.discovered_count, 0)

  const runSource = async (source: DataSourceItem) => {
    const policy = policyBySource.get(source.source_code)
    if (!policy) {
      notify('该数据源尚未配置采集策略，请先新建策略')
      return
    }
    setRunningCode(source.source_code)
    try {
      const run = await dataCenterApi.createRun({ source_code: source.source_code, policy_version: policy.policy_version })
      const executed = await dataCenterApi.executeRun(run.run_code)
      notify(
        executed.run_status_code === 'success'
          ? `采集完成：发现 ${executed.discovered_count} · 变化 ${executed.changed_count} · 未变 ${executed.unchanged_count} · 失败 ${executed.failed_count}`
          : `采集运行 ${executed.run_code} 失败：${executed.error_summary ?? '入口页不可达'}`
      )
      await reload()
    } catch (reason) {
      notify(`采集执行失败：${(reason as Error).message}`)
      await reload().catch(() => undefined)
    } finally {
      setRunningCode('')
    }
  }

  const submitSource = async (form: HTMLFormElement) => {
    const data = new FormData(form)
    setSubmitting(true)
    try {
      await dataCenterApi.createSource({
        source_code: String(data.get('source_code') ?? '').trim(),
        source_name: String(data.get('source_name') ?? '').trim(),
        source_type_code: String(data.get('source_type_code') ?? 'other') as 'recruitment' | 'enterprise' | 'government' | 'research' | 'other',
        entry_url: String(data.get('entry_url') ?? '').trim() || null,
        content_type_code: String(data.get('content_type_code') ?? 'mixed') as 'job' | 'industry' | 'milestone' | 'mixed',
        default_reliability_score: Number(data.get('reliability') ?? 70),
      })
      setShowSourceForm(false)
      notify('数据源已登记到注册表')
      await reload()
    } catch (reason) {
      notify(`登记失败：${(reason as Error).message}`)
    } finally {
      setSubmitting(false)
    }
  }

  const submitPolicy = async (form: HTMLFormElement) => {
    const data = new FormData(form)
    setSubmitting(true)
    try {
      await dataCenterApi.createPolicy({
        source_code: String(data.get('source_code') ?? ''),
        policy_version: String(data.get('policy_version') ?? '').trim(),
        schedule_cron: String(data.get('schedule_cron') ?? '').trim() || null,
        robots_status_code: String(data.get('robots_status_code') ?? 'unchecked') as 'unchecked' | 'allowed',
        terms_checked: data.get('terms_checked') === 'on',
      })
      setShowPolicyForm(false)
      notify('采集策略已保存')
      await reload()
    } catch (reason) {
      notify(`策略保存失败：${(reason as Error).message}`)
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="page-stack">
      <div className="page-intro">
        <div><h2>数据采集中枢</h2><p>维护招聘、企业、政府和技术动态入口，所有结果保留快照与证据链。</p></div>
        <div className="intro-actions">
          <button className="secondary-button" onClick={() => setShowPolicyForm(true)}>新建采集策略</button>
          <button className="primary-button" onClick={() => setShowSourceForm(true)}><Plus size={16} />新增数据源</button>
        </div>
      </div>
      <MetricStrip items={[
        { label: '注册数据源', value: String(sources.length) },
        { label: '启用采集策略', value: String(policies.filter((policy) => policy.is_active).length) },
        { label: '采集运行记录', value: String(runs.length) },
        { label: '累计发现内容', value: discoveredTotal.toLocaleString() },
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
      <Panel title="数据源注册表" subtitle="列表页默认只深入一层到岗位或文章详情页；数据来自 /sources 接口">
        {error ? <div className="empty-state"><ShieldAlert size={25} /><strong>加载失败</strong><span>{error}</span></div> : loading ? <div className="empty-state"><RefreshCw className="spin" size={22} /><strong>正在加载数据源…</strong></div> : (
          <div className="table-wrap">
            <table className="data-table">
              <thead><tr><th>数据源</th><th>类型</th><th>采集范围</th><th>策略</th><th>最近运行</th><th>发现</th><th>状态</th><th>操作</th></tr></thead>
              <tbody>{sources.map((source) => {
                const policy = policyBySource.get(source.source_code)
                const latestRun = latestRunBySource.get(source.source_code)
                return (
                  <tr key={source.source_code}>
                    <td><strong>{source.source_name}</strong><small>{source.source_code}</small></td>
                    <td>{sourceTypeLabels[source.source_type_code] ?? source.source_type_code}</td>
                    <td>{contentTypeLabels[source.content_type_code] ?? source.content_type_code}{source.entry_url ? <small>{source.entry_url}</small> : null}</td>
                    <td>{policy ? <>{policy.policy_version}<small>{policy.schedule_cron ?? '未设周期'} · robots {policy.robots_status_code}</small></> : <StatusTag tone="warning">未配置</StatusTag>}</td>
                    <td>{latestRun ? `${latestRun.run_code}` : '尚无运行'}</td>
                    <td>{latestRun ? latestRun.discovered_count : '—'}</td>
                    <td><StatusTag tone={source.source_status_code === 'active' ? 'success' : 'warning'}>{source.source_status_code}</StatusTag></td>
                    <td><button className="table-action" disabled={runningCode !== '' || !policy} onClick={() => runSource(source)}>{runningCode === source.source_code ? <RefreshCw className="spin" size={15} /> : <Play size={15} />}运行</button></td>
                  </tr>
                )
              })}</tbody>
            </table>
            {sources.length === 0 ? <div className="empty-state"><Database size={25} /><strong>尚未登记数据源</strong><span>点击右上角"新增数据源"完成登记。</span></div> : null}
          </div>
        )}
      </Panel>
      <div className="two-columns">
        <Panel title="最近采集运行" subtitle="来自 /collection-runs 接口；真实网页采集器将在阶段 D 接入">
          {runs.length === 0 ? <div className="empty-state"><FileText size={24} /><strong>暂无采集运行记录</strong><span>配置策略后可在数据源表格中发起运行。</span></div> : (
            <div className="table-wrap"><table className="data-table"><thead><tr><th>运行编号</th><th>数据源</th><th>发现</th><th>变化</th><th>未变</th><th>失败</th><th>状态</th></tr></thead>
              <tbody>{runs.slice(0, 8).map((run) => (
                <tr key={run.run_code}><td><strong>{run.run_code}</strong></td><td>{run.source_code}</td><td>{run.discovered_count}</td><td>{run.changed_count}</td><td>{run.unchanged_count}</td><td>{run.failed_count}</td><td><StatusTag tone={run.run_status_code === 'success' ? 'success' : run.run_status_code === 'failed' ? 'danger' : 'info'}>{run.run_status_code}</StatusTag></td></tr>
              ))}</tbody></table></div>
          )}
        </Panel>
        <Panel title="质量告警" subtitle="由策略合规状态与失败运行推导">
          {(() => {
            const alerts = [
              ...policies.filter((policy) => policy.robots_status_code === 'restricted' || policy.robots_status_code === 'disallowed').map((policy) => ({ tone: 'danger' as const, title: policy.source_code, detail: `robots 状态为 ${policy.robots_status_code}，不允许自动采集` })),
              ...runs.filter((run) => run.failed_count > 0).map((run) => ({ tone: 'warning' as const, title: run.run_code, detail: `${run.failed_count} 个请求失败` })),
            ]
            return alerts.length === 0
              ? <div className="empty-state"><ShieldAlert size={24} /><strong>当前无告警</strong><span>策略受限或运行失败时将在此提示。</span></div>
              : <div className="alert-list">{alerts.map((alert) => <div key={`${alert.title}-${alert.detail}`}><StatusTag tone={alert.tone}>{alert.tone === 'danger' ? '合规' : '运行'}</StatusTag><div><strong>{alert.title}</strong><span>{alert.detail}</span></div></div>)}</div>
          })()}
        </Panel>
      </div>

      {showSourceForm ? (
        <Modal title="新增数据源" onClose={() => setShowSourceForm(false)}>
          <form className="record-detail-form" onSubmit={(event) => { event.preventDefault(); submitSource(event.currentTarget) }}>
            <label>数据源编码<input name="source_code" required placeholder="如 career_site_demo" /></label>
            <label>数据源名称<input name="source_name" required placeholder="如 示例企业招聘官网" /></label>
            <label>来源类型<select name="source_type_code" defaultValue="recruitment"><option value="recruitment">招聘网站</option><option value="enterprise">企业官网</option><option value="government">政府网站</option><option value="research">研究动态</option><option value="other">其他</option></select></label>
            <label>内容类型<select name="content_type_code" defaultValue="job"><option value="job">岗位 JD</option><option value="industry">产业动态</option><option value="milestone">技术里程碑</option><option value="mixed">混合内容</option></select></label>
            <label>入口 URL<input name="entry_url" placeholder="https://…" /></label>
            <label>默认可靠度（0–100）<input name="reliability" type="number" min={0} max={100} defaultValue={70} /></label>
            <div className="modal-actions"><button type="button" className="secondary-button" onClick={() => setShowSourceForm(false)}>取消</button><button className="primary-button" disabled={submitting}>{submitting ? '保存中…' : '保存登记'}</button></div>
          </form>
        </Modal>
      ) : null}

      {showPolicyForm ? (
        <Modal title="新建采集策略" onClose={() => setShowPolicyForm(false)}>
          <form className="record-detail-form" onSubmit={(event) => { event.preventDefault(); submitPolicy(event.currentTarget) }}>
            <label>数据源<select name="source_code" required>{sources.map((source) => <option key={source.source_code} value={source.source_code}>{source.source_name}</option>)}</select></label>
            <label>策略版本<input name="policy_version" required placeholder="如 v1" /></label>
            <label>调度表达式（可空）<input name="schedule_cron" placeholder="如 0 9 * * *" /></label>
            <label>robots 状态<select name="robots_status_code" defaultValue="unchecked"><option value="unchecked">未检查</option><option value="allowed">允许采集</option></select></label>
            <label className="inline-check"><input type="checkbox" name="terms_checked" />已核对访问条款</label>
            <div className="modal-actions"><button type="button" className="secondary-button" onClick={() => setShowPolicyForm(false)}>取消</button><button className="primary-button" disabled={submitting || sources.length === 0}>{submitting ? '保存中…' : '保存策略'}</button></div>
          </form>
        </Modal>
      ) : null}
    </div>
  )
}
