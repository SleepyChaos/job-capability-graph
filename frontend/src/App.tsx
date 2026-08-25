import { useCallback, useEffect, useState } from 'react'
import { dataCenterApi } from './api/dataCenter'
import { talentApi, type LearningPath, type MatchResult, type ProfileDetail, type ProfileSummary } from './api/talent'
import { AppShell } from './components/AppShell'
import { DataHubPage } from './pages/DataHubPage'
import { DataManagementPage } from './pages/DataManagementPage'
import { GraphPage } from './pages/GraphPage'
import { GraphClusterPage } from './pages/GraphClusterPage'
import { GraphHeatmapPage } from './pages/GraphHeatmapPage'
import { GraphRelationsPage } from './pages/GraphRelationsPage'
import { JobKeywordPage } from './pages/JobKeywordPage'
import { JobNamePage } from './pages/JobNamePage'
import { JobRecordsPage } from './pages/JobRecordsPage'
import { CandidateCardPage } from './pages/CandidateCardPage'
import { CandidateReviewPage } from './pages/CandidateReviewPage'
import { JobsPage } from './pages/JobsPage'
import { LearningPage } from './pages/LearningPage'
import { MatchPage } from './pages/MatchPage'
import { OverviewPage } from './pages/OverviewPage'
import { ResumePage } from './pages/ResumePage'
import { ReviewPage } from './pages/ReviewPage'
import { SourcesPage } from './pages/SourcesPage'
import { TaxonomyPage } from './pages/TaxonomyPage'
import { TalentMatchPage } from './pages/TalentMatchPage'
import type { PageId } from './types'

const pageTitles: Record<PageId, string> = {
  overview: '系统总览',
  data: '数据中心',
  sources: '数据采集中枢',
  management: '数据管理中心',
  taxonomy: '技术词标准管理',
  jobs: '新岗位发现',
  candidate: '岗位数据卡',
  'candidate-review': '新岗位审核台',
  'job-keyword': '技术词定向推演',
  'job-name': '岗位名称推演',
  'job-records': '推演结果记录库',
  graph: '动态岗位能力图谱',
  'graph-heatmap': '能力热力图',
  'graph-relations': '岗位—能力关联图',
  'graph-clusters': '聚类岗位能力图谱',
  talent: '人岗匹配',
  resume: '求职者画像',
  match: '匹配分析',
  learning: '发展路径',
  review: '数据审核中心',
}

/**
 * 解析 hash 路由。
 *
 * 形如 `#/candidate/candidate_xxx` 的路由带一个参数段——岗位数据卡需要能被直接
 * 分享，也要能从图谱的候选节点跳过来，因此候选编码必须落在 URL 上而不是组件状态里。
 */
function parseHash(): { page: PageId; param: string | null } {
  const [rawPage, rawParam] = window.location.hash.replace('#/', '').split('/')
  const page = rawPage as PageId
  return {
    page: page in pageTitles ? page : 'overview',
    param: rawParam ? decodeURIComponent(rawParam) : null,
  }
}

export default function App() {
  const [{ page, param }, setRoute] = useState(parseHash)
  const setPage = useCallback(
    (next: PageId, nextParam: string | null = null) => setRoute({ page: next, param: nextParam }),
    [],
  )
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false)
  const [toast, setToast] = useState('')
  const [profiles, setProfiles] = useState<ProfileSummary[]>([])
  const [selectedVersionCode, setSelectedVersionCode] = useState('')
  const [selectedMatchResult, setSelectedMatchResult] = useState<MatchResult | null>(null)
  const [learningPath, setLearningPath] = useState<LearningPath | null>(null)
  const [notificationCount, setNotificationCount] = useState(0)
  const [managementQuery, setManagementQuery] = useState('')

  useEffect(() => {
    const next = param ? `/${page}/${encodeURIComponent(param)}` : `/${page}`
    if (window.location.hash !== `#${next}`) window.location.hash = next
    window.scrollTo({ top: 0, behavior: 'smooth' })
  }, [page, param])

  useEffect(() => {
    const handleHashChange = () => setRoute(parseHash())
    window.addEventListener('hashchange', handleHashChange)
    return () => window.removeEventListener('hashchange', handleHashChange)
  }, [])

  useEffect(() => {
    if (!toast) return
    const timer = window.setTimeout(() => setToast(''), 3200)
    return () => window.clearTimeout(timer)
  }, [toast])

  useEffect(() => {
    const controller = new AbortController()
    talentApi.profiles(controller.signal).then((items) => {
      setProfiles(items)
      setSelectedVersionCode((current) => current || items[0]?.version_code || '')
    }).catch((reason: Error) => { if (reason.name !== 'AbortError') setToast(`画像库加载失败：${reason.message}`) })
    return () => controller.abort()
  }, [])

  useEffect(() => {
    const controller = new AbortController()
    dataCenterApi.reviews('queued', controller.signal)
      .then((tasks) => setNotificationCount(tasks.length))
      .catch(() => undefined)
    return () => controller.abort()
  }, [page])

  const notify = (message: string) => setToast(message)
  const selectedProfile = profiles.find((profile) => profile.version_code === selectedVersionCode) ?? profiles[0]
  const upsertProfile = (profile: ProfileSummary | ProfileDetail) => {
    setProfiles((items) => [profile, ...items.filter((item) => item.version_code !== profile.version_code)])
    setSelectedVersionCode(profile.version_code)
  }
  const useProfileForMatch = (versionCode: string) => {
    setSelectedVersionCode(versionCode)
    setSelectedMatchResult(null); setLearningPath(null)
    setPage('match')
  }

  let content
  switch (page) {
    case 'data': content = <DataHubPage onNavigate={setPage} />; break
    case 'sources': content = <SourcesPage notify={notify} />; break
    case 'management': content = <DataManagementPage notify={notify} initialQuery={managementQuery} />; break
    case 'taxonomy': content = <TaxonomyPage notify={notify} />; break
    case 'jobs': content = <JobsPage notify={notify} onOpenCandidate={(code) => setPage('candidate', code)} />; break
    case 'candidate': content = <CandidateCardPage candidateCode={param} onNavigate={setPage} notify={notify} />; break
    case 'candidate-review': content = <CandidateReviewPage onNavigate={setPage} notify={notify} />; break
    case 'job-keyword': content = <JobKeywordPage notify={notify} />; break
    case 'job-name': content = <JobNamePage notify={notify} />; break
    case 'job-records': content = <JobRecordsPage notify={notify} />; break
    case 'graph': content = <GraphPage onNavigate={setPage} />; break
    case 'graph-heatmap': content = <GraphHeatmapPage notify={notify} />; break
    case 'graph-relations': content = <GraphRelationsPage notify={notify} />; break
    case 'graph-clusters': content = <GraphClusterPage notify={notify} />; break
    case 'talent': content = <TalentMatchPage hasProfiles={profiles.length > 0} onProfileCreated={upsertProfile} onNavigate={setPage} notify={notify} />; break
    case 'resume': content = <ResumePage profiles={profiles} selectedVersionCode={selectedVersionCode} onSelectProfile={setSelectedVersionCode} onProfilesChanged={upsertProfile} onUseForMatch={useProfileForMatch} onNavigate={setPage} notify={notify} />; break
    case 'match': content = selectedProfile ? <MatchPage profile={selectedProfile} onPathGenerated={(result, path) => { setSelectedMatchResult(result); setLearningPath(path) }} onNavigate={setPage} notify={notify} /> : <ResumePage profiles={profiles} selectedVersionCode={selectedVersionCode} onSelectProfile={setSelectedVersionCode} onProfilesChanged={upsertProfile} onUseForMatch={useProfileForMatch} onNavigate={setPage} notify={notify} />; break
    case 'learning': content = selectedProfile ? <LearningPage profile={selectedProfile} result={selectedMatchResult} path={learningPath} onNavigate={setPage} notify={notify} /> : <OverviewPage onNavigate={setPage} />; break
    case 'review': content = <ReviewPage notify={notify} />; break
    default: content = <OverviewPage onNavigate={setPage} />
  }

  return (
    <AppShell
      page={page}
      pageTitle={pageTitles[page]}
      onNavigate={setPage}
      notificationCount={notificationCount}
      onSearch={(value) => { setManagementQuery(value); setPage('management'); setToast(`已在数据管理中心搜索“${value}”`) }}
      sidebarOpen={sidebarOpen}
      onSidebarOpenChange={setSidebarOpen}
      sidebarCollapsed={sidebarCollapsed}
      onSidebarCollapsedChange={setSidebarCollapsed}
      toast={toast}
      onDismissToast={() => setToast('')}
    >
      {content}
    </AppShell>
  )
}
