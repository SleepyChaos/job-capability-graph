import { ArrowRight, CheckCircle2, FileSearch, Search, Sparkles } from 'lucide-react'
import { useState } from 'react'
import { Panel, ScoreBar, StatusTag } from '../components/ui'
import { roleCandidates } from '../data/mockData'

type SearchResult = 'existing' | 'candidate' | 'potential'

export function JobNamePage({ notify }: { notify: (message: string) => void }) {
  const [query, setQuery] = useState('具身世界模型评测工程师')
  const [result, setResult] = useState<SearchResult | null>('potential')

  const runInference = () => {
    const value = query.trim()
    if (!value) return
    if (value.includes('系统集成') || value.includes('导航工程师')) setResult('existing')
    else if (roleCandidates.some((item) => item.name.includes(value) || value.includes(item.name.slice(2, 6)))) setResult('candidate')
    else setResult('potential')
    notify(`已完成“${value}”的岗位存在性与形成可能性推演`)
  }

  return (
    <div className="page-stack discovery-page">
      <div className="page-intro"><div><h2>岗位名称推演</h2><p>输入设想中的岗位名称，同时检索正式岗位库、JD 别名和预测候选，并分析未来形成可能。</p></div></div>

      <Panel title="输入岗位名称" subtitle="名称只是推演起点，系统会结合语义近邻、技术组合和任务覆盖缺口判断">
        <div className="role-existence-search"><label><Search size={17} /><input value={query} onChange={(event) => { setQuery(event.target.value); setResult(null) }} onKeyDown={(event) => { if (event.key === 'Enter') runInference() }} placeholder="例如：具身世界模型评测工程师" /><button onClick={runInference}>检索与推演</button></label></div>
      </Panel>

      {result ? (
        <div className="name-inference-layout">
          <Panel title="推演结论" subtitle="名称存在性与岗位形成可能性综合判断">
            <div className={`name-inference-conclusion name-inference-conclusion--${result}`}>
              {result === 'existing' ? <CheckCircle2 size={28} /> : result === 'candidate' ? <FileSearch size={28} /> : <Sparkles size={28} />}
              <div><StatusTag tone={result === 'existing' ? 'success' : result === 'candidate' ? 'warning' : 'info'}>{result === 'existing' ? '已有岗位' : result === 'candidate' ? '已有预测候选' : '具备形成可能'}</StatusTag><h3>{query}</h3><p>{result === 'existing' ? '正式岗位定义库中存在高度相似岗位，建议查看既有岗位簇与能力演化。' : result === 'candidate' ? '综合自动预测中已有相近候选，可直接进入候选证据完善与专项审批。' : '当前未发现同名正式岗位，但任务组合与技术条件已形成，可建立持续跟踪任务。'}</p></div>
            </div>
          </Panel>
          <Panel title="形成可能性证据" subtitle="仅用于创新推演，不改变正式数据库中的事实记录">
            <div className="name-inference-scores"><div><span>语义近邻岗位重合度</span><ScoreBar value={result === 'existing' ? 93 : 61} /></div><div><span>技术里程碑成熟度</span><ScoreBar value={78} tone="blue" /></div><div><span>真实 JD 任务覆盖缺口</span><ScoreBar value={result === 'potential' ? 72 : 48} /></div><div><span>岗位独立性</span><ScoreBar value={result === 'existing' ? 18 : 69} tone="blue" /></div></div>
          </Panel>
        </div>
      ) : <div className="inference-empty inference-empty--standalone"><FileSearch size={28} /><strong>等待岗位名称推演</strong><span>输入岗位名并执行推演后，这里将显示存在性、形成概率与证据解释。</span></div>}

      {result && result !== 'existing' ? <div className="name-inference-action"><div><strong>建议下一步</strong><span>{result === 'candidate' ? '对比现有候选定义并完善证据。' : '创建持续跟踪任务，观察后续 JD 和技术里程碑变化。'}</span></div><button className="primary-button" onClick={() => notify(result === 'candidate' ? '已转入候选定义完善流程' : '已创建岗位形成跟踪任务')}>{result === 'candidate' ? '进入候选分析' : '创建跟踪任务'} <ArrowRight size={15} /></button></div> : null}
    </div>
  )
}
