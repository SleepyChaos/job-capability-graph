import { Check, Play, RefreshCw, Save, Search, ShieldAlert, Tags } from 'lucide-react'
import { useEffect, useState } from 'react'
import { discoveryApi, maturityStageLabels, type CandidateListItem, type DiscoveryRun } from '../api/discovery'
import { taxonomyApi, type TechnologyNode } from '../api/taxonomy'
import { Panel, StatusTag } from '../components/ui'

function todayISO(): string {
  return new Date().toISOString().slice(0, 10)
}

export function JobKeywordPage({ notify }: { notify: (message: string) => void }) {
  const [query, setQuery] = useState('')
  const [options, setOptions] = useState<TechnologyNode[]>([])
  const [searching, setSearching] = useState(false)
  const [selected, setSelected] = useState<TechnologyNode[]>([])
  const [run, setRun] = useState<DiscoveryRun | null>(null)
  const [results, setResults] = useState<CandidateListItem[]>([])
  const [running, setRunning] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    const controller = new AbortController()
    setSearching(true)
    taxonomyApi.nodes({ level: 'L3', search: query || undefined, limit: 24 }, controller.signal)
      .then((page) => setOptions(page.items))
      .catch((reason: Error) => { if (reason.name !== 'AbortError') setError(reason.message) })
      .finally(() => setSearching(false))
    return () => controller.abort()
  }, [query])

  const toggleTerm = (node: TechnologyNode) => {
    setSelected((items) => items.some((item) => item.node_id === node.node_id)
      ? items.filter((item) => item.node_id !== node.node_id)
      : items.length >= 6 ? items : [...items, node])
    setRun(null)
    setResults([])
  }

  const runInference = async () => {
    if (selected.length === 0) return
    setRunning(true)
    setError('')
    try {
      const result = await discoveryApi.createRun({
        mode_code: 'technology_directed',
        target_date: todayISO(),
        selected_technology_ids: selected.map((node) => node.node_id),
      })
      setRun(result)
      const page = await discoveryApi.candidates({ runCode: result.run_code, limit: 50 })
      setResults(page.items)
      notify(result.already_completed
        ? `相同技术组合已推演过（${result.run_code}），返回既有结果`
        : `定向推演完成：${result.task_count} 项任务、${result.candidate_count} 个候选，已自动保存到记录库`)
    } catch (reason) {
      setError((reason as Error).message)
    } finally {
      setRunning(false)
    }
  }

  return (
    <div className="page-stack discovery-page">
      <div className="page-intro">
        <div><h2>技术词定向推演</h2><p>从 L3 标准技术点中选择组合（最多 6 个），针对性分析可能形成的新岗位；运行输入快照会整体冻结。</p></div>
        <button className="primary-button" disabled={selected.length === 0 || running} onClick={runInference}>{running ? <RefreshCw className="spin" size={15} /> : <Play size={15} />}执行定向推演</button>
      </div>

      {error ? <div className="empty-state"><ShieldAlert size={24} /><strong>推演失败</strong><span>{error}</span></div> : null}

      <Panel title="选择技术关键词" subtitle="词项来自已发布的技术词主数据（/taxonomy/nodes · L3）" action={<label className="inline-search"><Search size={15} /><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="搜索 L3 技术点" /></label>}>
        <div className="keyword-discovery-workbench">
          <div className="keyword-picker">
            {searching ? <div className="empty-state"><RefreshCw className="spin" size={20} /><strong>检索中…</strong></div> : options.map((node) => {
              const active = selected.some((item) => item.node_id === node.node_id)
              return (
                <button className={active ? 'selected' : ''} key={node.node_id} onClick={() => toggleTerm(node)}>
                  <span>{node.name}</span><small>{node.code} · {node.domain_code}</small>{active ? <Check size={14} /> : null}
                </button>
              )
            })}
          </div>
          <div className="keyword-inference-summary">
            <strong>当前组合</strong>
            <span>{selected.length ? selected.map((node) => node.name).join(' + ') : '请选择至少一个 L3 技术点'}</span>
            <div><i>已选词数</i><b>{selected.length} / 6</b></div>
            <div><i>运行模式</i><b>technology_directed</b></div>
            <div><i>输入快照</i><b>target_date={todayISO()}</b></div>
          </div>
        </div>
      </Panel>

      <Panel
        title="定向推演结果"
        subtitle={run ? `运行 ${run.run_code}：${results.length} 个候选（截点 ${run.target_date}${run.evidence_limited ? '，证据受限' : ''}）` : '选择技术词组合后执行推演'}
        action={run ? <StatusTag tone="success"><Save size={13} /> 已自动进入记录库</StatusTag> : undefined}
      >
        {run ? (
          results.length > 0 ? (
            <div className="inference-result-grid">
              {results.map((candidate) => (
                <article key={candidate.candidate_code}>
                  <div>
                    <StatusTag tone="warning">{maturityStageLabels[candidate.maturity_stage_code] ?? candidate.maturity_stage_code}</StatusTag>
                    <b>{Number(candidate.candidate_score).toFixed(1)}</b>
                  </div>
                  <Tags size={20} />
                  <h3>{candidate.proposed_name}</h3>
                  <p>{candidate.classification_code} · 风险标签 {candidate.risk_flags.length > 0 ? candidate.risk_flags.join('、') : '无'}</p>
                  <footer><span>{candidate.candidate_code}</span><span>工作流：{candidate.workflow_status_code}</span></footer>
                </article>
              ))}
            </div>
          ) : <div className="inference-empty"><Tags size={26} /><strong>本次组合未产生候选</strong><span>任务组合缺少跨企业证据或与既有岗位重合度过高；可更换技术词组合再试。</span></div>
        ) : <div className="inference-empty"><Tags size={26} /><strong>等待推演</strong><span>执行后将基于冻结快照计算任务社区、覆盖缺口与候选评分。</span></div>}
      </Panel>
    </div>
  )
}
