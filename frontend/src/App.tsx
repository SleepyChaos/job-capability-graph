import { useEffect, useState } from 'react'
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
import { JobsPage } from './pages/JobsPage'
import { LearningPage } from './pages/LearningPage'
import { MatchPage } from './pages/MatchPage'
import { OverviewPage } from './pages/OverviewPage'
import { ResumePage } from './pages/ResumePage'
import { ReviewPage } from './pages/ReviewPage'
import { SourcesPage } from './pages/SourcesPage'
import { TaxonomyPage } from './pages/TaxonomyPage'
import { TalentMatchPage } from './pages/TalentMatchPage'
import type { CandidateProfile, PageId } from './types'

const initialProfiles: CandidateProfile[] = [
  { id: 'lin-v3', name: '林舟', version: 3, sourceFile: '林舟_具身智能方向简历.pdf', createdAt: '2026-08-09 11:18', updatedAt: '今天 11:18', status: '已确认', direction: '具身智能系统集成工程师', education: '硕士 · 控制科学与工程', summary: '系统集成 + 感知定位复合能力，具备跨模块联调和问题闭环证据。', skills: ['ROS 2', 'SLAM', '传感器融合', 'Python', '运动规划'], completeness: 88, factsCount: 19, conversationRounds: 4, matchRuns: 3 },
  { id: 'lin-v2', name: '林舟', version: 2, sourceFile: '林舟_机器人算法简历_修订版.docx', createdAt: '2026-07-26 16:42', updatedAt: '07-26 16:42', status: '已确认', direction: '机器人感知与定位算法工程师', education: '硕士 · 控制科学与工程', summary: '以定位建图为主，系统集成信息尚不完整。', skills: ['SLAM', '传感器融合', 'Python', 'C++'], completeness: 76, factsCount: 15, conversationRounds: 2, matchRuns: 2 },
  { id: 'chen-v1', name: '陈岚', version: 1, sourceFile: '陈岚_运动控制方向.txt', createdAt: '2026-06-18 09:30', updatedAt: '06-18 09:30', status: '待确认', direction: '机器人运动控制工程师', education: '本科 · 自动化', summary: '具备控制理论与嵌入式开发基础，项目结果证据仍需补充。', skills: ['C++', '控制理论', '嵌入式开发', 'Linux'], completeness: 64, factsCount: 11, conversationRounds: 3, matchRuns: 0 },
]

const pageTitles: Record<PageId, string> = {
  overview: '系统总览',
  data: '数据中心',
  sources: '数据采集中枢',
  management: '数据管理中心',
  taxonomy: '技术词标准管理',
  jobs: '新岗位发现',
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

function getInitialPage(): PageId {
  const value = window.location.hash.replace('#/', '') as PageId
  return value in pageTitles ? value : 'overview'
}

export default function App() {
  const [page, setPage] = useState<PageId>(getInitialPage)
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false)
  const [toast, setToast] = useState('')
  const [profiles, setProfiles] = useState<CandidateProfile[]>(initialProfiles)
  const [selectedProfileId, setSelectedProfileId] = useState('lin-v3')
  const [selectedJob, setSelectedJob] = useState('')

  useEffect(() => {
    window.location.hash = `/${page}`
    window.scrollTo({ top: 0, behavior: 'smooth' })
  }, [page])

  useEffect(() => {
    const handleHashChange = () => setPage(getInitialPage())
    window.addEventListener('hashchange', handleHashChange)
    return () => window.removeEventListener('hashchange', handleHashChange)
  }, [])

  useEffect(() => {
    if (!toast) return
    const timer = window.setTimeout(() => setToast(''), 3200)
    return () => window.clearTimeout(timer)
  }, [toast])

  const notify = (message: string) => setToast(message)
  const selectedProfile = profiles.find((profile) => profile.id === selectedProfileId) ?? profiles[0]

  const createProfile = (sourceFile: string, conversationRounds: number) => {
    const nextVersion = Math.max(...profiles.filter((profile) => profile.name === initialProfiles[0].name).map((profile) => profile.version), 0) + 1
    const nextProfile: CandidateProfile = {
      ...initialProfiles[0],
      id: `profile-${Date.now()}`,
      sourceFile,
      version: nextVersion,
      createdAt: '刚刚',
      updatedAt: '刚刚',
      status: '待确认',
      conversationRounds,
      matchRuns: 0,
    }
    setProfiles((items) => [nextProfile, ...items])
    setSelectedProfileId(nextProfile.id)
    setSelectedJob('')
  }

  const createProfileVersion = (baseId: string, updates: Pick<CandidateProfile, 'name' | 'direction' | 'education' | 'summary' | 'skills'>) => {
    const base = profiles.find((profile) => profile.id === baseId)
    if (!base) return
    const nextVersion = Math.max(...profiles.filter((profile) => profile.name === base.name).map((profile) => profile.version), 0) + 1
    const nextProfile: CandidateProfile = {
      ...base,
      ...updates,
      id: `profile-${Date.now()}`,
      version: nextVersion,
      createdAt: '刚刚',
      updatedAt: '刚刚',
      status: '待确认',
      matchRuns: 0,
    }
    setProfiles((items) => [nextProfile, ...items])
    setSelectedProfileId(nextProfile.id)
    setSelectedJob('')
  }

  const useProfileForMatch = (profileId: string) => {
    setSelectedProfileId(profileId)
    setSelectedJob('')
    setPage('match')
  }

  let content
  switch (page) {
    case 'data': content = <DataHubPage onNavigate={setPage} />; break
    case 'sources': content = <SourcesPage notify={notify} />; break
    case 'management': content = <DataManagementPage notify={notify} />; break
    case 'taxonomy': content = <TaxonomyPage notify={notify} />; break
    case 'jobs': content = <JobsPage notify={notify} />; break
    case 'job-keyword': content = <JobKeywordPage notify={notify} />; break
    case 'job-name': content = <JobNamePage notify={notify} />; break
    case 'job-records': content = <JobRecordsPage notify={notify} />; break
    case 'graph': content = <GraphPage onNavigate={setPage} />; break
    case 'graph-heatmap': content = <GraphHeatmapPage notify={notify} />; break
    case 'graph-relations': content = <GraphRelationsPage notify={notify} />; break
    case 'graph-clusters': content = <GraphClusterPage notify={notify} />; break
    case 'talent': content = <TalentMatchPage hasProfiles={profiles.length > 0} onProfileCreated={createProfile} onNavigate={setPage} notify={notify} />; break
    case 'resume': content = <ResumePage profiles={profiles} selectedProfileId={selectedProfileId} onSelectProfile={setSelectedProfileId} onCreateVersion={createProfileVersion} onUseForMatch={useProfileForMatch} onNavigate={setPage} notify={notify} />; break
    case 'match': content = <MatchPage profile={selectedProfile} selectedJob={selectedJob} onSelectJob={setSelectedJob} onNavigate={setPage} notify={notify} />; break
    case 'learning': content = <LearningPage profile={selectedProfile} selectedJob={selectedJob} onNavigate={setPage} notify={notify} />; break
    case 'review': content = <ReviewPage notify={notify} />; break
    default: content = <OverviewPage onNavigate={setPage} />
  }

  return (
    <AppShell
      page={page}
      pageTitle={pageTitles[page]}
      onNavigate={setPage}
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
