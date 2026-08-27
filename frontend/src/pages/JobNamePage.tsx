import { ArrowRight, CheckCircle2, FileSearch, RefreshCw, Search, ShieldAlert, Sparkles } from 'lucide-react'
import { useState } from 'react'
import { classificationLabels, discoveryApi, type CandidateListItem, type CandidateSnapshot, type DiscoveryRun } from '../api/discovery'
import { Panel, StatusTag } from '../components/ui'

function todayISO(): string {
  return new Date().toISOString().slice(0, 10)
}

const conclusionText: Record<string, string> = {
  existing_role: '正式岗位定义库中存在同名或别名一致的岗位，建议查看既有岗位簇与能力演化。',
  existing_candidate: '推演候选库中已有同名候选，可直接进入候选证据完善与专项审批。',
  potential_new_role: '当前未发现同名正式岗位，任务组合与技术条件已形成，可建立持续跟踪任务。',
  insufficient_evidence: '名称本身不构成市场证据；系统已登记为证据不足结论，需要真实 JD 与里程碑支撑后再评估。',
}

export function JobNamePage({ notify }: { notify: (message: string) => void }) {
  const [query, setQuery] = useState('')
  const [description, setDescription] = useState('')
  const [run, setRun] = useState<DiscoveryRun | null>(null)
  const [result, setResult] = useState<CandidateListItem | null>(null)
  const [detail, setDetail] = useState<CandidateSnapshot | null>(null)
  const [running, setRunning] = useState(false)
  const [error, setError] = useState('')

  const runInference = async () => {
    const value = query.trim()
    if (!value) return
    setRunning(true)
    setError('')
    setRun(null)
    setResult(null)
    setDetail(null)
    try {
      const created = await discoveryApi.createRun({
        mode_code: 'name_inference',
        target_date: todayISO(),
        query_role_name: value,
        query_description: description.trim() || undefined,
      })
      setRun(created)
      const page = await discoveryApi.candidates({ runCode: created.run_code, limit: 5 })
      const first = page.items[0] ?? null
      setResult(first)
      if (first) {
        const detailPage = await discoveryApi.candidateDetail(first.candidate_code)
        setDetail(detailPage.candidate)
      }
      notify(created.already_completed ? `相同名称推演已存在（${created.run_code}），返回既有结论` : `已完成“${value}”的存在性与形成可能性推演`)
    } catch (reason) {
      setError((reason as Error).message)
    } finally {
      setRunning(false)
    }
  }

  const classification = result?.classification_code ?? null
  const tone = classification === 'existing_role' ? 'success' : classification === 'existing_candidate' ? 'warning' : 'info'

  return (
    <div className="page-stack discovery-page">
      <div className="page-intro"><div><h2>岗位名称推演</h2><p>输入设想中的岗位名称，依次检索正式岗位、历史候选与 JD 标题；结论只允许是已有岗位、已有候选、潜在新岗位或证据不足。</p></div></div>

      <Panel title="输入岗位名称" subtitle="名称新颖本身不能证明新岗位存在；推演运行会保存到记录库">
        <div className="role-existence-search">
          <label>
            <Search size={17} />
            <input value={query} onChange={(event) => { setQuery(event.target.value); setRun(null); setResult(null) }} onKeyDown={(event) => { if (event.key === 'Enter') runInference() }} placeholder="例如：具身世界模型评测工程师" />
            <button onClick={runInference} disabled={running || !query.trim()}>{running ? <RefreshCw className="spin" size={15} /> : '检索与推演'}</button>
          </label>
        </div>
        <label className="record-description">补充描述（可选，用于语义比较）<textarea rows={2} value={description} onChange={(event) => setDescription(event.target.value)} placeholder="例如：负责世界模型评测基准建设与机器人任务集构建" /></label>
      </Panel>

      {error ? <div className="empty-state"><ShieldAlert size={24} /><strong>推演失败</strong><span>{error}</span></div> : null}

      {run && result ? (
        <div className="name-inference-layout">
          <Panel title="推演结论" subtitle={`运行 ${run.run_code} · 截点 ${run.target_date}`}>
            <div className={`name-inference-conclusion name-inference-conclusion--${classification === 'existing_role' ? 'existing' : classification === 'existing_candidate' ? 'candidate' : 'potential'}`}>
              {classification === 'existing_role' ? <CheckCircle2 size={28} /> : classification === 'existing_candidate' ? <FileSearch size={28} /> : <Sparkles size={28} />}
              <div>
                <StatusTag tone={tone}>{classificationLabels[classification ?? ''] ?? classification}</StatusTag>
                <h3>{result.proposed_name}</h3>
                <p>{conclusionText[classification ?? ''] ?? '推演已完成。'}</p>
              </div>
            </div>
          </Panel>
          <Panel title="检索证据" subtitle="机械事实卡，不使用 LLM 生成结论">
            <div className="name-inference-scores">
              <div><span>同名 JD 标题数（截点前）</span><strong>{Number(detail?.mechanical_card?.exact_jd_title_count ?? 0).toLocaleString()}</strong></div>
              <div><span>命中的正式岗位</span><strong>{String(detail?.mechanical_card?.formal_role_match ?? '无')}</strong></div>
              <div><span>命中的历史候选</span><strong>{String(detail?.mechanical_card?.historical_candidate_match ?? '无')}</strong></div>
              <div><span>结论码</span><strong>{String(detail?.mechanical_card?.conclusion ?? '—')}</strong></div>
            </div>
            <div className="management-rules">
              <div><strong>工作流状态</strong><span>{result.workflow_status_code}（{result.workflow_status_code === 'merged' ? '已归并到既有岗位或候选' : '可进入专项审批队列'}）</span></div>
              <div><strong>成熟阶段</strong><span>{result.maturity_stage_code}</span></div>
              <div><strong>风险标签</strong><span>{result.risk_flags.length > 0 ? result.risk_flags.join('、') : '无'}</span></div>
            </div>
          </Panel>
        </div>
      ) : run ? <div className="inference-empty inference-empty--standalone"><FileSearch size={28} /><strong>本次推演未生成结论记录</strong><span>请稍后在推演结果记录库查看。</span></div>
        : <div className="inference-empty inference-empty--standalone"><FileSearch size={28} /><strong>等待岗位名称推演</strong><span>输入岗位名并执行推演后，这里将显示存在性结论与检索证据。</span></div>}

      {result && classification !== 'existing_role' && classification !== 'existing_candidate' ? (
        <div className="name-inference-action">
          <div><strong>建议下一步</strong><span>创建持续跟踪任务，观察后续真实 JD 与技术里程碑变化；证据充分后由自动预测生成正式候选。</span></div>
          <button className="primary-button" onClick={() => notify('名称推演记录已保存；正式候选需由证据驱动的自动预测或定向推演产生')}><ArrowRight size={15} />了解证据要求</button>
        </div>
      ) : null}
    </div>
  )
}
