import { BriefcaseBusiness, CheckCircle2, FileSearch, GitBranch, RotateCcw, Search, ShieldCheck, Tags, Workflow } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { loadJobEcosystemGraph, type JobEcosystemGraph, type StandardRole } from '../api/jobGraph'
import { MetricStrip, Panel, StatusTag } from '../components/ui'

function gateOf(role: StandardRole): { tone: 'success' | 'neutral'; label: string } {
  if (role.jdCount > 0) return { tone: 'success', label: '通过双重闸门' }
  return { tone: 'neutral', label: '待补证·无JD证据' }
}

const METHOD_CHAIN = ['搜索词包标准岗位', '类内真实标题归并', '候选标准岗位', '专家校准闸门']

export function JobDiscoveryPage() {
  const [data, setData] = useState<JobEcosystemGraph | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [directionId, setDirectionId] = useState<string | null>(null)
  const [categoryId, setCategoryId] = useState<string | null>(null)
  const [selectedRoleId, setSelectedRoleId] = useState<string | null>(null)
  const [query, setQuery] = useState('')

  useEffect(() => {
    const controller = new AbortController()
    loadJobEcosystemGraph(controller.signal)
      .then(setData)
      .catch((reason: Error) => { if (reason.name !== 'AbortError') setError(reason.message) })
    return () => controller.abort()
  }, [])

  const direction = data?.directions.find((d) => d.id === directionId) ?? null
  const category = data?.categories.find((c) => c.id === categoryId) ?? null

  const roles = useMemo(() => {
    if (!data) return []
    return data.standardRoles
      .filter((r) => (!directionId || r.directionId === directionId) && (!categoryId || r.categoryId === categoryId))
      .sort((a, b) => b.jdCount - a.jdCount || b.jobCount - a.jobCount)
  }, [data, directionId, categoryId])

  const visibleRoles = useMemo(() => {
    const q = query.trim().toLowerCase()
    if (!q) return roles
    return roles.filter((r) => [r.name, r.clusterName, ...r.seedVariants, ...r.observedVariants.map((v) => v.name)].some((t) => t.toLowerCase().includes(q)))
  }, [roles, query])

  const selectedRole = roles.find((r) => r.id === selectedRoleId) ?? null

  const stats = useMemo(() => {
    const mergedTitles = roles.reduce((sum, r) => sum + r.observedVariants.reduce((s, v) => s + v.count, 0), 0)
    const passed = roles.filter((r) => r.jdCount > 0).length
    return { packages: roles.length, mergedTitles, roles: roles.length, passed }
  }, [roles])

  const selectDirection = (id: string | null) => { setDirectionId(id); setCategoryId(null); setSelectedRoleId(null) }
  const selectCategory = (id: string | null) => { setCategoryId(id); setSelectedRoleId(null) }
  const reset = () => { setDirectionId(null); setCategoryId(null); setQuery(''); setSelectedRoleId(null) }

  if (error) return <div className="empty-state"><strong>发现流水线加载失败</strong><span>{error}</span></div>
  if (!data) return <div className="empty-state"><strong>正在生成标准岗位发现流水线</strong><span>读取搜索词包、真实标题归并与校准闸门。</span></div>

  return <div className="page-stack job-discovery-page">
    <div className="page-intro"><div><h2>标准岗位发现流水线图</h2><p>搜索词包先按6方向、17种类、岗位簇归层；类内把真实出现的岗位标题归并到候选标准岗位，再经校准闸门决定是否发布。</p></div><div className="job-ecosystem-intro-actions"><StatusTag tone="warning">候选版 v0.4</StatusTag><button className="secondary-button" onClick={reset}><RotateCcw size={15} />重置</button></div></div>
    <div className="job-ecosystem-toolbar">
      <div className="graph-scope-selectors">
        <label>职业方向<select value={directionId ?? ''} onChange={(e) => selectDirection(e.target.value || null)}><option value="">全部方向</option>{data.directions.map((d) => <option key={d.id} value={d.id}>{d.name} · {d.jobCount}岗位</option>)}</select></label>
        <label>职业种类<select value={categoryId ?? ''} onChange={(e) => selectCategory(e.target.value || null)}><option value="">全部种类</option>{data.categories.filter((c) => !directionId || c.directionId === directionId).map((c) => <option key={c.id} value={c.id}>{c.name} · {c.jobCount}岗位</option>)}</select></label>
      </div>
      <div className="job-ecosystem-search"><Search size={15} /><input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="搜索标准岗位或名称变体" aria-label="搜索标准岗位或名称变体" />{query ? <button onClick={() => setQuery('')}>清空</button> : null}</div>
    </div>
    <MetricStrip items={[
      { label: '搜索词包', value: String(stats.packages), delta: '标准岗位输入' },
      { label: '类内归并真实标题', value: stats.mergedTitles.toLocaleString(), delta: '真实出现岗位标题' },
      { label: '候选标准岗位', value: String(stats.roles), delta: '本范围落点' },
      { label: '通过校准闸门', value: String(stats.passed), delta: `${stats.roles - stats.passed}个待补证` },
    ]} />
    <div className="job-ecosystem-method"><div><strong>本图主链</strong>{METHOD_CHAIN.map((item, index) => <span key={item} className="job-method-step">{index ? <Workflow size={14} /> : null}<b>{item}</b></span>)}</div><p>每个标准岗位由搜索词包生成，类内归并真实标题后成为候选标准岗位；仅有JD证据通过双重闸门的才进入可发布状态，其余保留待专家补证。</p></div>
    <div className="job-ecosystem-workspace">
      <Panel
        title={category ? `${category.name} · 标准岗位发现流水线` : direction ? `${direction.name} · 标准岗位发现流水线` : '全部标准岗位发现流水线'}
        subtitle={`${visibleRoles.length}个标准岗位 · 左→右：搜索词包 → 类内归并 → 候选标准岗位 → 校准闸门`}
        className="discovery-board-panel"
      >
        <div className="discovery-board">
          <div className="discovery-board-head">
            <div><span>01</span>搜索词包</div>
            <div><span>02</span>类内归并</div>
            <div><span>03</span>候选标准岗位</div>
            <div><span>04</span>校准闸门</div>
          </div>
          {visibleRoles.length ? visibleRoles.map((role) => {
            const gate = gateOf(role)
            const merged = role.observedVariants.reduce((s, v) => s + v.count, 0)
            const selected = selectedRole?.id === role.id
            return (
              <button key={role.id} type="button" className={`discovery-row${selected ? ' is-selected' : ''}`} onClick={() => setSelectedRoleId(role.id)}>
                <div className="discovery-cell cell-package">
                  <strong>{role.name}</strong>
                  <div className="job-cluster-skill-tags">{role.seedVariants.slice(0, 3).map((variant) => <span key={variant}>{variant}</span>)}{role.seedVariants.length > 3 ? <span>+{role.seedVariants.length - 3}</span> : null}</div>
                </div>
                <div className="discovery-cell cell-merge">
                  {merged > 0 ? <><strong>{merged} 条</strong><span>真实标题已归并</span></> : <span className="job-cluster-muted">暂无真实标题</span>}
                </div>
                <div className="discovery-cell cell-role">
                  <strong>{role.name}</strong>
                  <span>{role.jobCount} 条JD证据 · {role.jdCount} 有效JD</span>
                </div>
                <div className="discovery-cell cell-gate"><StatusTag tone={gate.tone}>{gate.label}</StatusTag></div>
              </button>
            )
          }) : <div className="empty-state"><span>没有匹配的标准岗位。</span></div>}
        </div>
      </Panel>
      <Panel title={selectedRole ? '候选标准岗位校准详情' : '发现流水线说明'} subtitle={selectedRole ? `${selectedRole.code} · ${selectedRole.clusterName}` : '点击左侧任意标准岗位查看归并与校准证据'}>
        {selectedRole ? <DiscoveryDetail role={selectedRole} onOpenPortrait={(roleId) => { window.location.hash = `#/job-graph?view=portrait&role=${encodeURIComponent(roleId)}` }} /> : (
          <div className="job-ecosystem-guide">
            <div><span>01</span><p><strong>搜索词包</strong>每个标准岗位由一组搜索词与名称变体生成，先在6方向、17种类和岗位簇中归层。</p></div>
            <div><span>02</span><p><strong>类内归并</strong>在本职业种类内，把真实出现的岗位标题归并到对应标准岗位，形成多JD证据。</p></div>
            <div><span>03</span><p><strong>候选标准岗位</strong>归并结果是标准岗位，是主图与五维画像的业务落点。</p></div>
            <div><span>04</span><p><strong>校准闸门</strong>仅有JD证据通过双重闸门的进入可发布状态；无证据的保留待专家补证，不强行生成画像。</p></div>
          </div>
        )}
      </Panel>
    </div>
  </div>
}

function DiscoveryDetail({ role, onOpenPortrait }: { role: StandardRole; onOpenPortrait: (roleId: string) => void }) {
  const gate = gateOf(role)
  const merged = role.observedVariants.reduce((s, v) => s + v.count, 0)
  return (
    <div className="job-cluster-detail discovery-detail">
      <div className="job-cluster-detail-head"><div><StatusTag tone={gate.tone}>{gate.label}</StatusTag><h3>{role.name}</h3><p>{role.code} · {role.clusterName}</p></div><span className="job-cluster-total">{role.jobCount}<small>JD证据</small></span></div>
      <section><h4><Tags size={15} />搜索词包 · 名称变体</h4><div className="job-cluster-skill-tags discovery-variant-tags">{role.seedVariants.map((variant) => <span key={variant}>{variant}</span>)}</div></section>
      <section><h4><FileSearch size={15} />类内归并 · 真实出现的标题</h4>{role.observedVariants.length ? <div className="role-observed-variants">{role.observedVariants.slice(0, 8).map((variant) => <span key={variant.name}><strong>{variant.name}</strong><em>{variant.count}条</em></span>)}</div> : <p className="job-cluster-muted">当前v4中尚无高置信JD证据，保留为待补证标准岗位。</p>}<p className="job-cluster-muted">共归并 {merged} 条真实标题到该标准岗位。</p></section>
      <div className="job-cluster-facts"><div><BriefcaseBusiness size={16} /><span>覆盖企业</span><strong>{role.companyCount}</strong></div><div><CheckCircle2 size={16} /><span>有效JD</span><strong>{role.jdCount}</strong></div></div>
      <button type="button" className="standard-role-profile-button" onClick={() => onOpenPortrait(role.id)}><GitBranch size={15} />在标准岗位五维画像图中查看</button>
      <section className="job-cluster-governance"><ShieldCheck size={16} /><p><strong>校准闸门</strong>{role.releaseStatus}。{role.profileMethod}。证据不足的标准岗位保留待补，不用相似职级词强行匹配。</p></section>
    </div>
  )
}
