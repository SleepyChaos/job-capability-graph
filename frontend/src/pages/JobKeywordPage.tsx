import { Check, Play, Save, Tags } from 'lucide-react'
import { useMemo, useState } from 'react'
import { Panel, StatusTag } from '../components/ui'
import { roleCandidates } from '../data/mockData'

const keywordOptions = [
  { name: 'Sim2Real', domain: 'T5', level: 'L3' },
  { name: '合成数据', domain: 'T5', level: 'L3' },
  { name: '多模态模型', domain: 'T3', level: 'L3' },
  { name: '模仿学习', domain: 'T3', level: 'L3' },
  { name: '触觉感知', domain: 'T2', level: 'L3' },
  { name: '现场调试', domain: 'T7', level: 'L3' },
]

export function JobKeywordPage({ notify }: { notify: (message: string) => void }) {
  const [selectedTerms, setSelectedTerms] = useState(['Sim2Real', '合成数据'])
  const [hasRun, setHasRun] = useState(true)
  const inferredRoles = useMemo(() => {
    if (selectedTerms.some((item) => ['Sim2Real', '合成数据'].includes(item))) return [roleCandidates[0], roleCandidates[1]]
    if (selectedTerms.some((item) => ['多模态模型', '模仿学习'].includes(item))) return [roleCandidates[1], roleCandidates[0]]
    return [roleCandidates[2]]
  }, [selectedTerms])

  const toggleTerm = (term: string) => {
    setSelectedTerms((items) => items.includes(term) ? items.filter((item) => item !== term) : [...items, term])
    setHasRun(false)
  }

  const runInference = () => {
    setHasRun(true)
    notify(`已基于 ${selectedTerms.length} 个技术关键词完成定向岗位推演`)
  }

  return (
    <div className="page-stack discovery-page">
      <div className="page-intro"><div><h2>技术词定向推演</h2><p>从 T1–T7、L1–L4 技术词标准库中选择组合，针对性分析可能形成的新岗位。</p></div><button className="primary-button" disabled={selectedTerms.length === 0} onClick={runInference}><Play size={15} />执行定向推演</button></div>

      <Panel title="选择技术关键词" subtitle="所有词项均来自已审核的技术词主数据">
        <div className="keyword-discovery-workbench">
          <div className="keyword-picker">{keywordOptions.map((term) => <button className={selectedTerms.includes(term.name) ? 'selected' : ''} key={term.name} onClick={() => toggleTerm(term.name)}><span>{term.name}</span><small>{term.domain} · {term.level}</small>{selectedTerms.includes(term.name) ? <Check size={14} /> : null}</button>)}</div>
          <div className="keyword-inference-summary"><strong>当前组合推演</strong><span>{selectedTerms.length ? selectedTerms.join(' + ') : '请选择至少一个技术关键词'}</span><div><i>JD 任务共现</i><b>0.74</b></div><div><i>里程碑推进度</i><b>0.81</b></div><div><i>既有岗位覆盖缺口</i><b>0.63</b></div></div>
        </div>
      </Panel>

      <Panel title="定向推演结果" subtitle={hasRun ? `组合 ${selectedTerms.join(' + ')} 产生 ${inferredRoles.length} 个关联候选` : '关键词组合已变化，请重新执行推演'} action={hasRun ? <button className="secondary-button" onClick={() => notify('本次技术词定向推演已保存到记录库')}><Save size={15} />保存结果</button> : undefined}>
        {hasRun ? <div className="inference-result-grid">{inferredRoles.map((role, index) => <article key={role.id}><div><StatusTag tone={index === 0 ? 'warning' : 'info'}>{index === 0 ? '高度相关' : '关联候选'}</StatusTag><b>{role.score - index * 4}</b></div><Tags size={20} /><h3>{role.name}</h3><p>{role.summary}</p><footer><span>{role.primaryDomain}</span><span>{role.jdCount} 条 JD 证据</span></footer></article>)}</div> : <div className="inference-empty"><Tags size={26} /><strong>等待重新推演</strong><span>执行后将根据新的技术词组合更新岗位候选与证据评分。</span></div>}
      </Panel>
    </div>
  )
}
