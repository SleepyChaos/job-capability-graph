import { useEffect, useMemo, useState } from 'react'
import type { CSSProperties } from 'react'
import { ArrowLeft, ArrowRight, BarChart3, Building2, ChevronLeft, ChevronRight, ExternalLink, FileText, FileUser, Globe2, Layers3, MapPinned, Search, WalletCards, X, ZoomIn, ZoomOut } from 'lucide-react'
import { loadIndustryGraph, type IndustryEnterprise, type IndustryGraphData } from '../api/industryGraph'
import type { JobEcosystemGraph, JobRecord, StandardRole } from '../api/jobGraph'
import { Panel, StatusTag } from './ui'
import './IndustryJobGraph.css'

type View = 'overview' | 'chain' | 'financing' | 'map'
const STAGE_COLORS: Record<string, string> = { 上游: '#2474cb', 中游: '#0a958c', 下游: '#a173ce', 横向支撑: '#d79739' }
const REGION_COLORS: Record<string, string> = { 华北: '#b9d4f2', 东北: '#c6d0ec', 华东: '#aadbd4', 华中: '#cfdef0', 华南: '#acd3e1', 西南: '#d3cce6', 西北: '#e3dcc5', 海外: '#b4bfd1', 待核实: '#e8edf2' }
const fmt = (n: number) => n.toLocaleString()
const safeUrl = (value: string) => /^https?:\/\//i.test(value) ? value : undefined
const colorStyle = (color: string) => ({ '--industry-color': color } as CSSProperties)
const TAB_ITEMS = [{ id: 'overview', label: '企业增强总览', icon: BarChart3 }, { id: 'chain', label: '产业链图谱', icon: Layers3 }, { id: 'financing', label: '融资阶段', icon: WalletCards }, { id: 'map', label: '所属地区 · 总部地图', icon: MapPinned }] as const

function Pagination({ page, count, size, onChange, label }: { page: number; count: number; size: number; onChange: (page: number) => void; label: string }) {
  const pages = Math.max(1, Math.ceil(count / size))
  return <div className="industry-pagination"><span>共 {fmt(count)} {label} · 第 {page + 1}/{pages} 页</span><div><button aria-label={`${label}上一页`} disabled={page === 0} onClick={() => onChange(page - 1)}><ChevronLeft size={16} /></button><button aria-label={`${label}下一页`} disabled={page + 1 >= pages} onClick={() => onChange(page + 1)}><ChevronRight size={16} /></button></div></div>
}

function Overview({ data, onStage }: { data: IndustryGraphData; onStage: (stage: string) => void }) {
  const maxStage = Math.max(1, ...data.overview.stageDemand.map(x => x.count))
  const maxFinance = Math.max(1, ...data.overview.financingDemand.map(x => x.count))
  const maxCell = Math.max(1, ...data.overview.directionStage.flatMap(x => x.values))
  return <div className="industry-overview">
    <div className="industry-overview-lead"><div><span>ENTERPRISE-ENRICHED INSIGHTS</span><h3>把岗位需求，放回产业坐标</h3><p>企业库提供产业、融资与地区属性；企业增强表将 v4 岗位事实映射回企业，形成可追溯的需求分析。</p></div><div><strong>{fmt(data.metadata.mappedJobCount)}</strong><span>条已关联岗位样本</span><small>来自 {fmt(data.metadata.jobCount)} 条 v4 岗位</small></div></div>
    <div className="industry-overview-pair">
      <Panel title="岗位主要集中在哪个产业链层级" subtitle="按企业增强表统计 · 每条岗位 JD 计一次">
        <div className="industry-stage-bars">{data.overview.stageDemand.map(item => <button key={item.name} onClick={() => onStage(item.name)} style={colorStyle(STAGE_COLORS[item.name])}><div><span><i />{item.name}</span><strong>{fmt(item.count)}<small> 条JD</small></strong></div><div className="industry-bar-track"><i style={{ width: `${item.count / maxStage * 100}%` }} /></div><em>{(item.count / data.metadata.mappedJobCount * 100).toFixed(1)}% · 查看产业类别 <ArrowRight size={13} /></em></button>)}</div>
      </Panel>
      <Panel title="不同融资阶段的岗位需求" subtitle="保留企业增强表的融资分类口径 · 非实时招聘总量">
        <div className="industry-finance-bars">{data.overview.financingDemand.map(item => <div key={item.name}><span title={item.name}>{item.name}</span><div><i style={{ width: `${item.count / maxFinance * 100}%` }} /></div><strong>{fmt(item.count)}</strong></div>)}</div>
      </Panel>
    </div>
    <Panel title="职业方向 × 产业链层级：岗位需求落点" subtitle="颜色越深，表示该组合下的已关联岗位样本越多；0 表示当前样本未覆盖">
      <div className="industry-matrix-wrap"><table className="industry-matrix"><thead><tr><th>职业方向</th>{data.stages.map(s => <th key={s}><i style={{ background: STAGE_COLORS[s] }} />{s}</th>)}<th>合计</th></tr></thead><tbody>{data.overview.directionStage.map(row => <tr key={row.direction}><th>{row.direction}</th>{row.values.map((count, index) => <td key={data.stages[index]} style={{ background: count ? `rgba(15, 137, 135, ${0.08 + 0.68 * Math.sqrt(count / maxCell)})` : '#f5f7fa', color: count / maxCell > .45 ? '#fff' : '#23505e' }} title={`${row.direction} × ${data.stages[index]}：${count}条JD`}>{fmt(count)}</td>)}<td>{fmt(row.values.reduce((a, b) => a + b, 0))}</td></tr>)}</tbody></table></div>
      <p className="industry-footnote">{data.metadata.overviewNote} 另有 {data.metadata.pendingJobCount} 条岗位待核验企业映射，不纳入以上分布。</p>
    </Panel>
  </div>
}

function EnterpriseDirectory({ items, selected, page, onPage, onSelect, emptyMessage }: { items: IndustryEnterprise[]; selected: string; page: number; onPage: (n: number) => void; onSelect: (e: IndustryEnterprise) => void; emptyMessage?: string }) {
  const size = 10
  const safePage = Math.min(page, Math.max(0, Math.ceil(items.length / size) - 1))
  const pageItems = items.slice(safePage * size, (safePage + 1) * size)
  return <div className="industry-directory">
    {!items.length ? <div className="industry-empty"><Building2 size={28} /><strong>{emptyMessage || '当前筛选没有企业'}</strong><span>企业库全部记录均可检索，清空筛选可继续浏览。</span></div> :
      <div className="industry-enterprise-table-wrap">
        <table className="industry-enterprise-table">
          <thead>
            <tr>
              <th>企业名称</th>
              <th>产业链</th>
              <th>融资轮次</th>
              <th>总部/地区</th>
              <th>在聘</th>
              <th>岗位</th>
            </tr>
          </thead>
          <tbody>
            {pageItems.map(e => <tr className={selected === e.id ? 'selected' : ''} key={e.id} onClick={() => onSelect(e)} data-enterprise-id={e.id}>
              <td>
                <div className="enterprise-table-name">
                  <div className="industry-company-icon"><Building2 size={14} /></div>
                  <div>
                    <strong>{e.name}</strong>
                    {e.aliases && <small className="enterprise-alias-tip">别名：{e.aliases}</small>}
                  </div>
                </div>
              </td>
              <td>
                <span className="etag etag-stage" style={colorStyle(STAGE_COLORS[e.industryStage] || '#888')}>{e.industryStage}</span>
                <div className="etag-sub">{e.industryCategory}</div>
              </td>
              <td>
                <div className="finance-text">{e.financingRound || '—'}</div>
                {e.reportedOpeningsRaw && <div className="etag-sub">源表 {e.reportedOpeningsRaw}</div>}
              </td>
              <td>
                <div>{e.headquartersCity || e.city || '—'}</div>
                <div className="etag-sub">{e.companyRegion || ''}</div>
              </td>
              <td className="openings-cell">
                {e.reportedOpeningsRaw ? <span className="openings-num">{e.reportedOpeningsRaw}</span> : <span className="cell-muted">—</span>}
              </td>
              <td className="job-count-cell">
                {e.jobCount ? <strong>{fmt(e.jobCount)}</strong> : e.recruitmentLinks.length ? <span className="recruiting-only">招聘渠道</span> : <span className="cell-muted">—</span>}
                <ChevronRight size={13} className="chev" />
              </td>
            </tr>)}
          </tbody>
        </table>
      </div>}
    <Pagination count={items.length} page={safePage} size={size} onChange={onPage} label="家企业" />
  </div>
}

function EnterpriseDetail({ enterprise: e, graph, onRole, onOpenPortrait }: { enterprise: IndustryEnterprise | null; graph: JobEcosystemGraph; onRole: (role: StandardRole) => void; onOpenPortrait: (job: JobRecord) => void }) {
  const [jobPage, setJobPage] = useState(0)
  const [query, setQuery] = useState('')
  const [selectedJob, setSelectedJob] = useState<JobRecord | null>(null)
  useEffect(() => { setJobPage(0); setQuery(''); setSelectedJob(null) }, [e?.id])
  const jobs = useMemo(() => { const ids = new Set(e?.jobIds || []); return graph.jobs.filter(j => ids.has(j.id)) }, [e, graph.jobs])
  const matchingJobs = jobs.filter(j => `${j.title} ${j.standardRoleName} ${j.categoryName}`.toLowerCase().includes(query.toLowerCase()))
  const roleCounts = new Map<string, number>()
  jobs.forEach(j => { if (j.standardRoleId) roleCounts.set(j.standardRoleId, (roleCounts.get(j.standardRoleId) || 0) + 1) })
  const roles = graph.standardRoles.filter(r => roleCounts.has(r.id))
  if (!e) return <div className="industry-detail-intro"><div className="industry-detail-icon"><Building2 size={32} /></div><h3>企业，是通往岗位的入口</h3><p>从产业类别、融资阶段或地图选择企业，在这里查看业务信息、岗位映射和招聘渠道。</p><ol><li><b>企业画像</b><span>产业类别、细分领域、融资与总部</span></li><li><b>岗位证据</b><span>企业增强映射 → 标准岗位 → 具体 JD</span></li><li><b>招聘入口</b><span>没有 JD 映射，也保留官网与招聘渠道</span></li></ol></div>
  if (selectedJob) return <div className="industry-jd-detail"><button className="industry-text-button" onClick={() => setSelectedJob(null)}><ArrowLeft size={14} />返回企业岗位</button><StatusTag tone="info">企业增强映射证据</StatusTag><h3>{selectedJob.title}</h3><p>{e.name}</p><div className="industry-detail-tags"><span>{selectedJob.categoryName}</span><span>{selectedJob.education || '学历未说明'}</span><span>{selectedJob.experience || '经验未说明'}</span></div>{selectedJob.standardRoleName && <p>标准岗位：{selectedJob.standardRoleName}</p>}<button type="button" className="standard-role-profile-button" onClick={() => onOpenPortrait(selectedJob)}><FileUser size={15} />进入该岗位的岗位画像图谱</button><pre className="industry-full-jd">{selectedJob.jd || selectedJob.jdSnippet || '本条未提供完整JD'}</pre>{safeUrl(selectedJob.url) && <a className="industry-outbound" href={selectedJob.url} target="_blank" rel="noreferrer">打开岗位来源 <ExternalLink size={14} /></a>}<small>证据 ID：{selectedJob.occId}</small></div>
  const pillSplit = (v?: string) => v ? v.split(/[,，、；;/\s]+/).filter(Boolean) : []
  return <div className="industry-company-detail"><StatusTag tone="info">企业库第 {e.sourceRow} 行</StatusTag><h3>{e.name}</h3>{e.aliases && <p className="industry-alias">{e.aliases}</p>}<div className="industry-detail-tags"><span>{e.industryStage}</span><span>{e.industryCategory}</span><span>{e.companyRegion}</span></div>
    <dl className="industry-facts"><div><dt>融资轮次</dt><dd>{e.financingRound || '待补全'}</dd></div><div><dt>总部地区</dt><dd>{e.headquartersCity || '待补全'}</dd></div><div><dt>所属地区</dt><dd>{[e.country, e.province, e.city].filter(Boolean).join(' · ') || '待补全'}</dd></div></dl>

    <section className="industry-product-card">
      <h4 className="ipc-title"><Layers3 size={15} />业务 · 产品画像</h4>
      <div className="ipc-grid">
        <div className="ipc-block ipc-specialty">
          <span className="ipc-label">细分领域</span>
          <p className="ipc-value">{e.companySpecialty || <span className="muted-val">源表未填写</span>}</p>
        </div>
        <div className="ipc-block ipc-products">
          <span className="ipc-label">代表产品</span>
          <p className="ipc-value">{e.products || <span className="muted-val">源表未填写</span>}</p>
        </div>
        <div className="ipc-block ipc-tags">
          <span className="ipc-label">产品类型</span>
          <div className="ipc-pill-row">
            {pillSplit(e.productType).length ? pillSplit(e.productType).map((p, i) => <span key={i} className="ipc-pill pill-product">{p}</span>) : <span className="muted-val">源表未填写</span>}
          </div>
        </div>
        <div className="ipc-block ipc-features">
          <span className="ipc-label">关键特性 / 参数</span>
          <p className="ipc-value">{e.features || <span className="muted-val">源表未填写</span>}</p>
        </div>
        <div className="ipc-block ipc-tags">
          <span className="ipc-label">量产进展</span>
          <div className="ipc-pill-row">
            {pillSplit(e.production).length ? pillSplit(e.production).map((p, i) => <span key={i} className="ipc-pill pill-production">{p}</span>) : <span className="muted-val">源表未填写</span>}
          </div>
        </div>
        <div className="ipc-block ipc-tags">
          <span className="ipc-label">运营路径</span>
          <div className="ipc-pill-row">
            {pillSplit(e.operatingPath).length ? pillSplit(e.operatingPath).map((p, i) => <span key={i} className="ipc-pill pill-operation">{p}</span>) : <span className="muted-val">源表未填写</span>}
          </div>
        </div>
      </div>
    </section>

    <div className="industry-recruiting-stats"><div><span>库载在聘岗位</span><strong>{e.reportedOpeningsRaw || '待补'}</strong><small>岗位数量 · 非招聘人数</small></div><div><span>本项目已映射 JD</span><strong>{fmt(e.jobCount)}</strong><small>逐条证据可查看</small></div></div>
    <section className="industry-recruitment"><h4><Globe2 size={16} />招聘官网与渠道</h4><div>{e.website && <a href={safeUrl(e.website)} target="_blank" rel="noreferrer">企业官网 <ExternalLink size={13} /></a>}{e.recruitmentLinks.map((link, i) => <a key={link.url} href={safeUrl(link.url)} target="_blank" rel="noreferrer" title={link.url}>{link.label}{e.recruitmentLinks.filter(l => l.label === link.label).length > 1 ? ` ${i + 1}` : ''}<ExternalLink size={13} /></a>)}</div>{!e.recruitmentLinks.length && <p>源表未提供可打开的招聘链接，暂不推测。</p>}<small>企业库收录快照，非实时招聘数据；库载岗位数量与已映射 JD 不相加。</small></section>
    {!e.jobCount ? <div className="industry-no-jd"><FileText size={20} /><div><strong>暂无本项目 JD 映射</strong><p>仍可通过以上渠道了解招聘需求。“未映射”不代表企业没有招聘。</p></div></div> : <section className="industry-job-section"><h4>企业 → 岗位 → JD 证据</h4>{roles.length > 0 && <div className="industry-role-links">{roles.map(role => <button key={role.id} onClick={() => onRole(role)}><span>{role.name}</span><small>{roleCounts.get(role.id)} JD</small><ArrowRight size={13} /></button>)}</div>}<label className="industry-search industry-job-search"><Search size={14} /><input aria-label="筛选企业岗位" placeholder="搜索全部已映射岗位" value={query} onChange={event => { setQuery(event.target.value); setJobPage(0) }} /></label><div className="industry-job-list">{matchingJobs.slice(jobPage * 8, jobPage * 8 + 8).map(j => <button key={j.id} onClick={() => setSelectedJob(j)}><FileText size={15} /><div><strong>{j.title}</strong><span>{j.categoryName} · {j.experience || '经验未说明'}</span></div><ChevronRight size={14} /></button>)}</div>{!matchingJobs.length && <p>未找到符合搜索条件的岗位。</p>}<Pagination page={jobPage} count={matchingJobs.length} size={8} onChange={setJobPage} label="条岗位JD" /></section>}
    <details className="industry-source-details"><summary>融资、招聘与数据来源备注</summary><dl>{[['融资原文', e.financingDetail], ['招聘备注', e.recruitmentNotes], ['数据来源', e.sourceNotes]].map(([label, value]) => value && <div key={label}><dt>{label}</dt><dd>{value}</dd></div>)}{!e.financingDetail && !e.recruitmentNotes && !e.sourceNotes && <div className="muted-val" style={{gridColumn:'1 / -1', padding:'4px 0'}}>本条无额外备注信息。</div>}</dl></details>
  </div>
}

function RegionMap({ data, region, city, onRegion, onCity }: { data: IndustryGraphData; region: string; city: string; onRegion: (r: string) => void; onCity: (c: string) => void }) {
  const [zoom, setZoom] = useState(1)
  const [hover, setHover] = useState('')
  const cities = useMemo(() => {
    const values = new Map<string, { name: string; point: [number, number]; count: number; jobs: number; region: string }>()
    data.enterprises.forEach(e => { if (!e.headquartersPoint) return; const item = values.get(e.city) || { name: e.city, point: e.headquartersPoint, count: 0, jobs: 0, region: e.companyRegion }; item.count += 1; item.jobs += e.jobCount; values.set(e.city, item) })
    return [...values.values()].sort((a, b) => a.count - b.count)
  }, [data])
  const bigCities = new Set([...cities].sort((a, b) => b.count - a.count).slice(0, zoom < 1.5 ? 3 : 7).map(c => c.name))
  const selectedCity = cities.find(c => c.name === city)
  const centre = selectedCity?.point || [690, 280]
  const viewWidth = data.map.width / zoom, viewHeight = data.map.height / zoom
  const left = zoom === 1 ? 0 : Math.min(data.map.width - viewWidth, Math.max(0, centre[0] - viewWidth / 2))
  const top = zoom === 1 ? 0 : Math.min(data.map.height - viewHeight, Math.max(0, centre[1] - viewHeight / 2))
  return <div className="industry-map-area"><div className="industry-map-controls"><span>分区底色 = 所属地区　◆ = 总部城市</span><div><button aria-label="地图缩小" onClick={() => setZoom(z => Math.max(1, z - .4))} disabled={zoom === 1}><ZoomOut size={16} /></button><button aria-label="地图放大" onClick={() => setZoom(z => Math.min(2.6, z + .4))} disabled={zoom >= 2.6}><ZoomIn size={16} /></button><button onClick={() => setZoom(1)}>复位</button></div></div>
    <svg className="industry-map" viewBox={`${left} ${top} ${viewWidth} ${viewHeight}`} role="group" aria-label="企业所属地区与总部城市地图">
      <defs><pattern id="industry-map-dots" width="22" height="22" patternUnits="userSpaceOnUse"><circle cx="1" cy="1" r=".7" fill="#d2deea" /></pattern></defs><rect width={920} height={690} fill="url(#industry-map-dots)" />
      {data.map.features.map((feature, i) => <path key={`${feature.name}-${i}`} d={feature.path} fill={REGION_COLORS[feature.region] || '#edf1f5'} stroke={region && region === feature.region ? '#29717e' : '#fff'} strokeWidth={region && region === feature.region ? 1.4 : .9} opacity={region && region !== feature.region ? .35 : 1} role={feature.name ? 'button' : undefined} tabIndex={feature.name ? 0 : undefined} aria-label={`${feature.name} · ${feature.region}`} onClick={() => feature.name && onRegion(feature.region)} onKeyDown={event => { if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); onRegion(feature.region) } }}><title>{feature.name} · {feature.region} · 点击查看企业</title></path>)}
      {cities.map(c => { const [x, y] = c.point; const radius = 3.3 + Math.log2(c.count + 1) * .65; const selected = city === c.name; return <g key={c.name} role="button" tabIndex={0} aria-label={`${c.name}总部，${c.count}家企业`} className="industry-hq-marker" opacity={region && region !== c.region ? .2 : 1} onMouseEnter={() => setHover(`${c.name} · ${c.count} 家企业 · ${fmt(c.jobs)} 条已映射JD`)} onMouseLeave={() => setHover('')} onClick={() => onCity(c.name)} onKeyDown={event => { if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); onCity(c.name) } }}><circle cx={x} cy={y} r={radius + 8} fill="transparent" />{selected && <circle cx={x} cy={y} r={radius + 5} fill="#f5b64d55" stroke="#ca8721" />}<path d={`M${x},${y - radius}l${radius},${radius}l${-radius},${radius}l${-radius},${-radius}Z`} fill={selected ? '#d5942b' : '#165a87'} stroke="#fff" strokeWidth="1.2" /><title>{c.name}：{c.count}家企业，总部城市中心示意</title>{(bigCities.has(c.name) || selected) && <text x={x + radius + 3} y={y + 3} fontSize="10" paintOrder="stroke" stroke="#fff" strokeWidth="3" fill="#21425b">{c.name}</text>}</g> })}
    </svg>
    <div className="industry-map-hover">{hover || (city ? `${city} · 已选择总部城市` : region ? `${region} · 已选择所属地区` : '点击分区筛选所属地区；点击菱形标记查看总部企业')}</div>
    <div className="industry-map-legend">{Object.entries(REGION_COLORS).filter(([r]) => r !== '海外' && r !== '待核实').map(([r, color]) => <button key={r} className={region === r ? 'active' : ''} onClick={() => onRegion(region === r ? '' : r)}><i style={{ background: color }} />{r}</button>)}<button onClick={() => onRegion('海外')}>海外企业</button><button onClick={() => onRegion('未定位')}>未定位总部</button></div>
    <p className="industry-footnote">总部按企业库“城市”字段定位至城市中心，不是企业精确地址；海外及暂无城市坐标的主体仍在列表保留。底图：<a href={safeUrl(data.metadata.geographySourceUrl)} target="_blank" rel="noreferrer">DataV.GeoAtlas</a>。</p>
  </div>
}

export function IndustryJobGraph({ graph, onRole, onOpenPortrait }: { graph: JobEcosystemGraph; onRole: (role: StandardRole) => void; onOpenPortrait: (job: JobRecord) => void }) {
  const [data, setData] = useState<IndustryGraphData | null>(null)
  const [error, setError] = useState('')
  const [view, setView] = useState<View>('overview')
  const [stage, setStage] = useState('上游')
  const [category, setCategory] = useState('')
  const [financing, setFinancing] = useState('')
  const [region, setRegion] = useState('')
  const [city, setCity] = useState('')
  const [query, setQuery] = useState('')
  const [onlyUnmapped, setOnlyUnmapped] = useState(false)
  const [enterpriseId, setEnterpriseId] = useState('')
  const [page, setPage] = useState(0)
  useEffect(() => { const abort = new AbortController(); loadIndustryGraph(abort.signal).then(setData).catch(e => { if (e.name !== 'AbortError') setError(String(e.message)) }); return () => abort.abort() }, [])
  useEffect(() => { setPage(0); setEnterpriseId('') }, [view, stage, category, financing, region, city, query, onlyUnmapped])
  const filtered = useMemo(() => {
    if (!data) return []
    return data.enterprises.filter(e => {
      if (onlyUnmapped && e.jobCount) return false
      if (query) return `${e.name} ${e.aliases} ${e.companySpecialty} ${e.industryCategory} ${e.city}`.toLowerCase().includes(query.toLowerCase())
      if (view === 'chain') return !!category && e.industryStage === stage && e.industryCategory === category
      if (view === 'financing') return !financing || e.financingRound === financing
      if (view === 'map') return (!region || (region === '未定位' ? !e.headquartersPoint : e.companyRegion === region)) && (!city || e.city === city)
      return true
    }).sort((a, b) => a.name.localeCompare(b.name, 'zh-CN'))
  }, [data, view, stage, category, financing, region, city, query, onlyUnmapped])
  if (error) return <div className="empty-state"><strong>{error}</strong><span>请先生成企业库图谱数据。</span></div>
  if (!data) return <div className="empty-state"><strong>正在读取完整企业库与岗位增强映射…</strong></div>
  const selectedEnterprise = data.enterprises.find(e => e.id === enterpriseId) || null
  const categories = data.categories.filter(c => c.primaryStage === stage || data.enterprises.some(e => e.industryStage === stage && e.industryCategory === c.name))
  const financeValues = [...new Set(data.enterprises.map(e => e.financingRound))].sort((a, b) => a.localeCompare(b, 'zh-CN'))
  const locationLabel = city ? `${city} · 总部企业` : region ? `${region} · 企业` : '全国与海外企业'
  const clear = () => { setQuery(''); setOnlyUnmapped(false); setCategory(''); setFinancing(''); setRegion(''); setCity(''); setEnterpriseId(''); setPage(0) }
  const selectRegion = (r: string) => { setRegion(r); setCity(''); setQuery('') }
  return <div className="industry-job-module">
    <div className="industry-library-summary"><div><Building2 size={22} /><span>完整企业库<strong>{fmt(data.metadata.enterpriseCount)}<small> 个企业条目</small></strong></span></div><div><Layers3 size={22} /><span>实际产业类别<strong>{data.categories.length}<small> 类</small></strong></span></div><div><FileText size={22} /><span>企业增强岗位映射<strong>{fmt(data.metadata.mappedJobCount)}<small> 条 JD</small></strong></span></div><div><Globe2 size={22} /><span>有招聘入口的企业<strong>{data.metadata.enterprisesWithRecruitmentLinks}<small> 个</small></strong></span></div></div>
    <nav className="industry-view-tabs" aria-label="产业图谱视图">{TAB_ITEMS.map(tab => { const Icon = tab.icon; return <button key={tab.id} className={view === tab.id ? 'active' : ''} onClick={() => { setView(tab.id); clear() }}><Icon size={17} />{tab.label}</button> })}</nav>
    {view === 'overview' ? <Overview data={data} onStage={value => { setStage(value); setCategory(''); setView('chain') }} /> : <>
      <div className="industry-browser-toolbar"><div className="industry-breadcrumb"><button onClick={clear}>完整企业库</button><ChevronRight size={14} /><span>{query ? '全库搜索' : view === 'chain' ? stage : view === 'map' ? locationLabel : financing || '全部融资阶段'}</span>{!query && view === 'chain' && category && <><ChevronRight size={14} /><span>{category}</span></>}</div><div><label className="industry-search"><Search size={15} /><input value={query} onChange={event => setQuery(event.target.value)} placeholder="搜索全库企业、别名、产品领域" aria-label="搜索完整企业库" />{query && <button aria-label="清空企业搜索" onClick={() => setQuery('')}><X size={14} /></button>}</label><label className="industry-unmapped"><input type="checkbox" checked={onlyUnmapped} onChange={event => setOnlyUnmapped(event.target.checked)} />仅看暂无 JD 映射</label></div></div>
      <div className="industry-workspace"><div className="industry-main">
        {view === 'chain' && !query && <Panel title="产业链层级 → 产业类别 → 企业" subtitle="类别按你的人工产业标准组织；AI 大模型以中游为主，保留源表中的横向支撑主体。"><div className="industry-stage-select">{data.stages.map(s => <button key={s} className={stage === s ? 'active' : ''} style={colorStyle(STAGE_COLORS[s])} onClick={() => { setStage(s); setCategory('') }}><span>{s}</span><strong>{data.enterprises.filter(e => e.industryStage === s).length}<small> 企业条目</small></strong><ChevronRight size={17} /></button>)}</div><div className="industry-category-heading"><span>产业类别</span><ArrowRight size={16} /><small>点击类别后右侧展开企业列表</small></div><div className="industry-category-select">{categories.map(c => { const items = data.enterprises.filter(e => e.industryStage === stage && e.industryCategory === c.name); return <button key={c.name} className={category === c.name ? 'active' : ''} onClick={() => setCategory(c.name)} style={colorStyle(STAGE_COLORS[stage])}><span>{c.name}</span><strong>{items.length}<small> 家企业</small></strong>{c.note && <em>{c.note}</em>}<ChevronRight size={14} /></button> })}</div></Panel>}
        {view === 'financing' && !query && <Panel title="按融资阶段浏览完整企业库" subtitle="保留源表分类；具体融资说明与企业列表在右侧面板展开。"><div className="industry-financing-filter"><label>融资轮次<select value={financing} onChange={event => setFinancing(event.target.value)}><option value="">全部融资阶段</option>{financeValues.map(f => <option key={f} value={f}>{f} · {data.enterprises.filter(e => e.financingRound === f).length} 家</option>)}</select></label><span>有无岗位映射，均保留企业与招聘信息；右侧查看企业列表</span></div></Panel>}
        {view === 'map' && <Panel title="企业分布地图 · 地区底色与总部标记" subtitle="省域按所属大区着色，总部城市以菱形聚合；点击后右侧联动企业列表与详情。"><RegionMap data={data} region={region} city={city} onRegion={selectRegion} onCity={value => { setCity(value); setRegion(''); setQuery('') }} /></Panel>}
        {query && <Panel title={`全库搜索 · ${filtered.length} 个结果`} subtitle="搜索结果已同步至右侧企业卡片列表。"><div className="industry-search-summary"><p>关键词：<strong>{query}</strong></p><p>命中 <strong>{fmt(filtered.length)}</strong> 家企业，右侧翻页浏览</p></div></Panel>}
      </div>
        <div className="industry-right-panel">
          <Panel title={query ? `搜索结果 · ${filtered.length} 家企业` : view === 'chain' ? category ? `${category} · 企业卡片（${fmt(filtered.length)}）` : '企业卡片列表' : view === 'map' ? `${locationLabel}（${fmt(filtered.length)}）` : `${financing || '全部融资阶段'} · 企业卡片（${fmt(filtered.length)}）`} subtitle="点击卡片行查看岗位详情与招聘入口" className="industry-right-list-panel">
            <EnterpriseDirectory items={filtered} selected={enterpriseId} page={page} onPage={setPage} onSelect={e => setEnterpriseId(e.id)} emptyMessage={view === 'chain' && !category && !query ? '请先在左侧选择产业链层级与产业类别' : undefined} />
          </Panel>
          <Panel title={selectedEnterprise ? '企业与岗位详情' : '企业 → 岗位 / 招聘入口'} subtitle="企业属性来自完整企业库，JD 连接来自企业增强表" className="industry-evidence-panel">
            <EnterpriseDetail enterprise={selectedEnterprise} graph={graph} onRole={onRole} onOpenPortrait={onOpenPortrait} />
          </Panel>
        </div>
      </div>
    </>}
    <details className="industry-method-note"><summary>数据来源与统计口径</summary><p>企业源：{data.metadata.libraryFile}；岗位连接源：{data.metadata.enhancementFile}。{data.metadata.countNote}</p><p>{data.metadata.libraryDataRows} 行源表中排除 {data.metadata.blankRowsExcluded.length} 行空白企业名；{data.metadata.enterpriseCount} 个非空企业条目全部保留。源表中的同名标点差异保留审计，不擅自合并。</p></details>
  </div>
}
