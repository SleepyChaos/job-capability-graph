import { Boxes, FileText, Layers, RotateCcw, Search, Tag, Workflow } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { loadJobEcosystemGraph, type JobEcosystemGraph, type JobRecord, type StandardRole } from '../api/jobGraph'
import { MetricStrip, Modal, Panel, StatusTag } from '../components/ui'

type Dim = 'responsibilities' | 'skills' | 'abilities' | 'scenarios' | 'conditions'
const DIMS: Dim[] = ['responsibilities', 'skills', 'abilities', 'scenarios', 'conditions']
const DIM_LABEL: Record<Dim, string> = { responsibilities: '职责', skills: '技能', abilities: '能力', scenarios: '场景', conditions: '任职条件' }

interface SkillView {
  id: string
  label: string
  jobCount: number
  directionId: string
  directionName: string
  color: string
}

interface RoleHit {
  role: StandardRole
  jobIds: string[]
  jobs: JobRecord[]
  dims: Dim[]
}

interface ClusterHit {
  clusterName: string
  directionName: string
  jobIds: string[]
}

function matchDims(role: StandardRole, term: string): Dim[] {
  const t = term.toLowerCase()
  return DIMS.filter((d) => (role.standardProfile[d] ?? []).some((p) => p.name.toLowerCase().includes(t)))
}

export function TechToRolePage() {
  const [data, setData] = useState<JobEcosystemGraph | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [query, setQuery] = useState('')
  const [selectedSkillId, setSelectedSkillId] = useState<string | null>(null)
  const [selectedRoleId, setSelectedRoleId] = useState<string | null>(null)
  const [jobDetail, setJobDetail] = useState<JobRecord | null>(null)

  useEffect(() => {
    const controller = new AbortController()
    loadJobEcosystemGraph(controller.signal)
      .then(setData)
      .catch((reason: Error) => { if (reason.name !== 'AbortError') setError(reason.message) })
    return () => controller.abort()
  }, [])

  const indexes = useMemo(() => {
    if (!data) return null
    const jobById = new Map<string, JobRecord>(data.jobs.map((j) => [j.id, j]))
    const roleById = new Map<string, StandardRole>(data.standardRoles.map((r) => [r.id, r]))
    const directionColor = new Map(data.directions.map((d) => [d.id, d.color]))
    const directionName = new Map(data.directions.map((d) => [d.id, d.name]))
    // Governed L4 term -> v4 job ids. Only exact-evidence relations are used.
    const skillToJobs = new Map<string, string[]>()
    for (const job of data.jobs) {
      for (const technologyId of job.technologyTermIds) {
        const arr = skillToJobs.get(technologyId)
        if (arr) arr.push(job.id)
        else skillToJobs.set(technologyId, [job.id])
      }
    }
    // Active L4 terms with dominant job-direction color.
    const skills: SkillView[] = []
    for (const n of data.technologyNodes) {
      if (n.level !== 'L4' || n.jobCount === 0) continue
      const jobIds = skillToJobs.get(n.id) ?? []
      const dirTally = new Map<string, number>()
      for (const jid of jobIds) {
        const j = jobById.get(jid)
        if (j?.directionId) dirTally.set(j.directionId, (dirTally.get(j.directionId) ?? 0) + 1)
      }
      let topDir = ''
      let topCount = -1
      for (const [d, c] of dirTally) if (c > topCount) { topCount = c; topDir = d }
      skills.push({
        id: n.id,
        label: n.name,
        jobCount: n.jobCount,
        directionId: topDir,
        directionName: topDir ? (directionName.get(topDir) ?? '') : '未归类',
        color: topDir ? (directionColor.get(topDir) ?? '#0d5ba0') : '#8aa0b6',
      })
    }
    skills.sort((a, b) => b.jobCount - a.jobCount)
    return { jobById, roleById, skillToJobs, skills }
  }, [data])

  const selectedSkill = useMemo(
    () => (indexes && selectedSkillId ? indexes.skills.find((s) => s.id === selectedSkillId) ?? null : null),
    [indexes, selectedSkillId],
  )

  const hit = useMemo(() => {
    if (!data || !indexes || !selectedSkill) return null
    const jobIds = indexes.skillToJobs.get(selectedSkill.id) ?? []
    const roleHits = new Map<string, RoleHit>()
    const clusterHits = new Map<string, ClusterHit>()
    for (const jid of jobIds) {
      const j = indexes.jobById.get(jid)
      if (!j) continue
        if (j.standardRoleId) {
          const existing = roleHits.get(j.standardRoleId)
          if (existing) { existing.jobIds.push(jid); existing.jobs.push(j) }
          else {
            const role = indexes.roleById.get(j.standardRoleId)
            roleHits.set(j.standardRoleId, { role: role ?? ({ id: j.standardRoleId, name: j.standardRoleName } as StandardRole), jobIds: [jid], jobs: [j], dims: role ? matchDims(role, selectedSkill.label) : [] })
          }
        } else {
        const key = j.clusterName
        const existing = clusterHits.get(key)
        if (existing) existing.jobIds.push(jid)
        else clusterHits.set(key, { clusterName: j.clusterName, directionName: j.directionName, jobIds: [jid] })
      }
    }
    const roles = [...roleHits.values()].sort((a, b) => b.jobIds.length - a.jobIds.length)
    const clusters = [...clusterHits.values()].sort((a, b) => b.jobIds.length - a.jobIds.length)
    return { jobIds, roles, clusters, mappedJobs: jobIds.filter((id) => indexes.jobById.get(id)?.standardRoleId).length }
  }, [data, indexes, selectedSkill])

  const selectedRoleHit = useMemo(
    () => (hit && selectedRoleId ? hit.roles.find((r) => r.role.id === selectedRoleId) ?? null : null),
    [hit, selectedRoleId],
  )

  const stats = useMemo(() => {
    if (!indexes) return { skills: 0, linkedJobs: 0, roles: 0 }
    const linkedJobs = indexes.skills.reduce((s, sk) => s + (indexes.skillToJobs.get(sk.id)?.length ?? 0), 0)
    const roles = new Set<string>()
    for (const [, ids] of indexes.skillToJobs) for (const id of ids) { const j = indexes.jobById.get(id); if (j?.standardRoleId) roles.add(j.standardRoleId) }
    return { skills: indexes.skills.length, linkedJobs, roles: roles.size }
  }, [indexes])

  const visibleSkills = useMemo(() => {
    if (!indexes) return []
    const q = query.trim().toLowerCase()
    if (!q) return indexes.skills
    return indexes.skills.filter((s) => s.label.toLowerCase().includes(q))
  }, [indexes, query])

  const reset = () => { setSelectedSkillId(null); setSelectedRoleId(null); setJobDetail(null) }
  const selectSkill = (id: string) => { setSelectedSkillId(id); setSelectedRoleId(null); setJobDetail(null) }

  if (error) return <div className="empty-state"><strong>技术词岗位图谱加载失败</strong><span>{error}</span></div>
  if (!data || !indexes) return <div className="empty-state"><strong>正在生成技术词岗位图谱</strong><span>读取技术词、岗位与标准岗位映射。</span></div>

  return <div className="page-stack tech-to-role-page">
    <div className="page-intro"><div><h2>L4技术词反向岗位证据</h2><p>从技术主数据的1,872个L4技术词中，展示已有安全岗位证据的技术词，反向引出标准岗位与具体招聘JD；完整L1–L4层级请进入“产业·技术·岗位三图谱”。</p></div><div className="job-ecosystem-intro-actions"><StatusTag tone="warning">证据候选版 v0.5</StatusTag><button className="secondary-button" onClick={reset}><RotateCcw size={15} />重置</button></div></div>
    <div className="tech-to-role-toolbar">
      <div className="job-ecosystem-search"><Search size={15} /><input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="搜索技术词（如 嵌入式、强化学习、伺服）" aria-label="搜索技术词" />{query ? <button onClick={() => setQuery('')}>清空</button> : null}</div>
    </div>
    <MetricStrip items={[
      { label: '活跃L4技术词', value: String(stats.skills), delta: `主数据共${data.technologyAudit.levelCounts.L4}个` },
      { label: '技术—岗位关系', value: stats.linkedJobs.toLocaleString(), delta: '精确证据关系' },
      { label: '引出的标准岗位', value: String(stats.roles), delta: '已映射岗位归并' },
      { label: '已映射岗位率', value: `${((data.metadata.standardRoleMappingRate ?? 0) * 100).toFixed(1)}%`, delta: `${data.metadata.standardRoleMappedJobCount ?? 0}/${(data.metadata.standardRoleMappedJobCount ?? 0) + Math.max(0, data.metadata.jobCount - (data.metadata.standardRoleMappedJobCount ?? 0))} 岗位` },
    ]} />
    <div className="tech-to-role-workspace">
      <Panel title="技术词" subtitle={`${visibleSkills.length} 个 · 按关联岗位数排序`} className="tech-word-panel">
        <div className="tech-word-list">{visibleSkills.map((s) => <button key={s.id} type="button" className={`tech-word-item${selectedSkillId === s.id ? ' is-selected' : ''}`} onClick={() => selectSkill(s.id)}><i style={{ background: s.color }} /><strong>{s.label}</strong><span>{s.jobCount} 岗位</span></button>)}{!visibleSkills.length ? <div className="empty-state"><span>没有匹配的技术词。</span></div> : null}</div>
      </Panel>
      <Panel title={selectedSkill ? `「${selectedSkill.label}」引出的岗位` : '技术词引出岗位'} subtitle={selectedSkill ? `${hit?.jobIds.length ?? 0} 条招聘岗位 · 左→右：技术词 → 标准岗位 / 岗位簇 → 招聘岗位` : '从左侧选择一个技术词，查看它反向引出的岗位网络'} className="tech-role-board-panel">
        {selectedSkill && hit ? <div className="tech-role-board">
          <div className="tech-role-board-head"><Tag size={15} /><div><strong>{selectedSkill.label}</strong><span>主导方向：{selectedSkill.directionName} · 共 {hit.jobIds.length} 条招聘岗位</span></div></div>
          <section className="tech-role-section">
            <h4><Boxes size={14} />引出的标准岗位（{hit.roles.length}）</h4>
            {hit.roles.length ? <div className="tech-role-rows">{hit.roles.map((rh) => <button key={rh.role.id} type="button" className={`tech-role-row${selectedRoleId === rh.role.id ? ' is-selected' : ''}`} onClick={() => setSelectedRoleId(rh.role.id)}><div><strong>{rh.role.name}</strong><span>{rh.role.clusterName}</span></div><div className="tech-role-row-meta">{rh.dims.length ? <div className="job-cluster-skill-tags tech-dim-tags">{rh.dims.map((d) => <span key={d}>{DIM_LABEL[d]}</span>)}</div> : null}<em>{rh.jobIds.length} 岗位</em></div></button>)}</div> : <p className="job-cluster-muted">该技术词暂无已映射到标准岗位的招聘岗位；可看下方岗位簇分布。</p>}
          </section>
          <section className="tech-role-section">
            <h4><Layers size={14} />未映射招聘岗位（按岗位簇 · {hit.clusters.length}）</h4>
            {hit.clusters.length ? <div className="tech-cluster-hits">{hit.clusters.map((c) => <div key={c.clusterName} className="tech-cluster-hit"><span><strong>{c.clusterName}</strong><em>{c.directionName}</em></span><small>{c.jobIds.length} 条</small></div>)}</div> : <p className="job-cluster-muted">全部关联岗位已映射到标准岗位。</p>}
          </section>
        </div> : <div className="job-ecosystem-guide"><div><span>01</span><p><strong>技术主数据</strong>入口来自正式L4技术词，不把普通技能标签冒充技术分类体系。</p></div><div><span>02</span><p><strong>安全回接</strong>仅通过JD全文一致或L4精确命中连接v4岗位。</p></div><div><span>03</span><p><strong>归并标准岗位</strong>已映射的招聘记录归并到标准岗位，未映射记录继续保留在岗位簇。</p></div><div><span>04</span><p><strong>双向查询</strong>主三图谱负责L1–L4下钻，本页负责“一个L4词究竟支撑哪些岗位”的反向核验。</p></div></div>}
      </Panel>
      <Panel title={selectedRoleHit ? `${selectedRoleHit.role.name} · 相关岗位` : jobDetail ? '招聘岗位详情' : '岗位与画像'} subtitle={selectedRoleHit ? `${selectedRoleHit.jobIds.length} 条岗位要求该技术词` : jobDetail ? jobDetail.title : '选择一个标准岗位查看其要求该技术词的岗位'} className="tech-role-detail-panel">
        {selectedRoleHit ? <RoleDetail hit={selectedRoleHit} term={selectedSkill?.label ?? ''} onOpenJob={(j) => setJobDetail(j)} /> : <div className="job-ecosystem-guide"><div><span>·</span><p>点击中间「引出的标准岗位」查看该岗位下要求该技术词的具体招聘记录，再点单条岗位查看完整 JD。</p></div></div>}
      </Panel>
    </div>
    {jobDetail ? <Modal title={`${jobDetail.title} · 完整 JD`} onClose={() => setJobDetail(null)}><div className="tech-job-modal">
      <div className="tech-job-modal-facts"><div><span>企业</span><strong>{jobDetail.company || jobDetail.enterpriseName || '—'}</strong></div><div><span>方向 / 岗位簇</span><strong>{jobDetail.directionName} / {jobDetail.clusterName}</strong></div><div><span>标准岗位映射</span><strong>{jobDetail.standardRoleName || '待映射'}{jobDetail.standardRoleId ? `（${(jobDetail.standardRoleMappingConfidence * 100).toFixed(0)}%）` : ''}</strong></div><div><span>学历 / 经验</span><strong>{jobDetail.education || '—'} · {jobDetail.experience || '—'}</strong></div></div>
      <a className="tech-job-modal-link" href={jobDetail.url} target="_blank" rel="noreferrer"><FileText size={14} />查看原始招聘链接</a>
      <pre className="tech-job-jd">{jobDetail.jd}</pre>
    </div></Modal> : null}
  </div>
}

function RoleDetail({ hit, term, onOpenJob }: { hit: RoleHit; term: string; onOpenJob: (j: JobRecord) => void }) {
  const role = hit.role
  const dims = matchDims(role, term)
  return (
    <div className="job-cluster-detail tech-role-detail">
      <div className="job-cluster-detail-head"><div><StatusTag tone={role.jdCount > 0 ? 'success' : 'neutral'}>{role.jdCount > 0 ? '有JD证据' : '待补证'}</StatusTag><h3>{role.name}</h3><p>{role.code} · {role.clusterName}</p></div><span className="job-cluster-total">{hit.jobIds.length}<small>相关岗位</small></span></div>
      {dims.length ? <section><h4>该技术词落点（五维）</h4><div className="job-cluster-skill-tags tech-dim-tags">{dims.map((d) => <span key={d}>{DIM_LABEL[d]}</span>)}</div></section> : null}
      <section><h4>要求「{term}」的招聘岗位</h4><div className="tech-role-job-list">{hit.jobs.map((job) => <JobLine job={job} onOpen={onOpenJob} />)}</div></section>
    </div>
  )
}

function JobLine({ job, onOpen }: { job: JobRecord; onOpen: (j: JobRecord) => void }) {
  return (
    <button type="button" className="tech-role-job" onClick={() => onOpen(job)}>
      <strong>{job.title}</strong>
      <span>{job.company || job.enterpriseName || '企业未标注'}</span>
      <em>{job.standardRoleName ? `→ ${job.standardRoleName}` : '待映射标准岗位'}</em>
    </button>
  )
}
