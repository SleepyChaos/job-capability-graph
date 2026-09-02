import type { ComponentType, ReactNode } from 'react'
import {
  ClipboardCheck,
  Library,
  Activity,
  Bell,
  BookOpen,
  BookOpenCheck,
  BriefcaseBusiness,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  CircleUserRound,
  Database,
  DatabaseZap,
  FileClock,
  FileUser,
  GitBranch,
  GitCommitVertical,
  LayoutDashboard,
  Menu,
  Network,
  Search,
  Settings2,
  ShieldCheck,
  Sparkles,
  Tags,
  X,
} from 'lucide-react'
import type { PageId } from '../types'

interface NavItem {
  id: PageId
  label: string
  icon: ComponentType<{ size?: number; strokeWidth?: number }>
}

const navItems: NavItem[] = [
  { id: 'overview', label: '系统总览', icon: LayoutDashboard },
]

const dataPages: PageId[] = ['data', 'sources', 'management', 'literature', 'taxonomy', 'review']
const dataChildren: NavItem[] = [
  { id: 'sources', label: '数据采集中枢', icon: DatabaseZap },
  { id: 'management', label: '数据管理中心', icon: Database },
  { id: 'literature', label: '论文文献检索', icon: BookOpen },
  { id: 'taxonomy', label: '技术词标准管理', icon: GitBranch },
  { id: 'review', label: '数据标注审核中心', icon: ShieldCheck },
]

const talentPages: PageId[] = ['talent', 'resume', 'match', 'learning']
const talentChildren: NavItem[] = [
  { id: 'resume', label: '求职者画像', icon: FileUser },
  { id: 'match', label: '匹配分析', icon: Activity },
  { id: 'learning', label: '发展路径', icon: BookOpenCheck },
]

const jobPages: PageId[] = [
  'jobs',
  'candidate-review',
  'discovery-library',
  'role-evolution',
  'candidate',
  'job-records',
]
const jobChildren: NavItem[] = [
  // 审核台紧跟发现页：发现 → 看数据卡 → 处置，是审核者的主路径。
  // 数据卡不进导航——它按候选编码路由，只能从列表或图谱点进去。
  // 三页对应候选的三个阶段：发现（这一轮推演出了什么）→ 审核（能不能入库）
  // → 发现库（判定成立的）。混在一页会让「提议」与「已成立的岗位」看起来
  // 是一回事，而这两者差着一次人工判断。
  { id: 'candidate-review', label: '新岗位审核台', icon: ClipboardCheck },
  { id: 'discovery-library', label: '新岗位发现库', icon: Library },
  // 演变与发现同属一个模块：发现回答「有没有新岗位」，演变回答「既有岗位变了什么」。
  { id: 'role-evolution', label: '岗位能力演变', icon: GitCommitVertical },
  // 「定向推演」暂不进导航：技术词定向与岗位名称核验都需要使用者先给出入口词，
  // 与本模块「由数据自动发现」的主线不是一回事，放在这里会被当成主流程的一步。
  // 路由仍保留，既有链接不会失效，只是不再从侧边栏进入。
  { id: 'job-records', label: '推演结果记录库', icon: FileClock },
]

// 图谱对外保留产业、技术与岗位—能力关联三个入口。
// 岗位画像图谱暂不进入导航，但路由继续保留，既有深链接不会失效。
// 「岗位—能力关联图」是新岗位候选叠加所在的页面，必须留在导航里，
// 否则候选节点只能靠直接改 hash 才能看到。
//
// 「能力热力图」与「聚类岗位能力图谱」不再进导航：前者是关联图的一种聚合读法，
// 后者与关联图看的是同一批聚类，三张并列只会让人反复确认它们的差别。
// 路由保留，既有链接不失效。
const graphPages: PageId[] = [
  'industry-job-graph',
  'technology-job-graph',
  'job-portrait-graph',
  'graph',
  'graph-heatmap',
  'graph-relations',
  'graph-clusters',
]
const graphChildren: NavItem[] = [
  { id: 'industry-job-graph', label: '产业—岗位图谱', icon: BriefcaseBusiness },
  { id: 'technology-job-graph', label: '技术—岗位图谱', icon: Tags },
  { id: 'graph-relations', label: '岗位—能力关联图', icon: Network },
]

interface AppShellProps {
  page: PageId
  pageTitle: string
  onNavigate: (page: PageId) => void
  notificationCount?: number
  onSearch?: (query: string) => void
  sidebarOpen: boolean
  onSidebarOpenChange: (open: boolean) => void
  sidebarCollapsed: boolean
  onSidebarCollapsedChange: (collapsed: boolean) => void
  children: ReactNode
  toast?: string
  onDismissToast?: () => void
}

export function AppShell({
  page,
  pageTitle,
  onNavigate,
  notificationCount = 0,
  onSearch,
  sidebarOpen,
  onSidebarOpenChange,
  sidebarCollapsed,
  onSidebarCollapsedChange,
  children,
  toast,
  onDismissToast,
}: AppShellProps) {
  return (
    <div className="app-shell">
      <aside className={`sidebar ${sidebarOpen ? 'sidebar--open' : ''} ${sidebarCollapsed ? 'sidebar--collapsed' : ''}`} aria-label="主导航">
        <div className="brand">
          <div className="brand-mark" aria-hidden="true"><Sparkles size={21} /></div>
          <div>
            <strong>具身图谱</strong>
            <span>岗位与能力演化研究平台</span>
          </div>
          <button className="icon-button sidebar-close" onClick={() => onSidebarOpenChange(false)} aria-label="关闭导航"><X size={19} /></button>
        </div>
        <nav className="nav-list">
          {navItems.slice(0, 1).map(({ id, label, icon: Icon }) => (
            <button
              type="button"
              key={id}
              className={`nav-item ${page === id ? 'nav-item--active' : ''}`}
              title={sidebarCollapsed ? label : undefined}
              onClick={() => { onNavigate(id); onSidebarOpenChange(false) }}
              aria-current={page === id ? 'page' : undefined}
            >
              <Icon size={19} strokeWidth={1.8} />
              <span>{label}</span>
            </button>
          ))}
          <div className={`nav-group ${dataPages.includes(page) ? 'nav-group--active' : ''}`}>
            <button
              type="button"
              className={`nav-item nav-parent ${page === 'data' ? 'nav-item--active' : ''}`}
              title={sidebarCollapsed ? '数据中心' : undefined}
              onClick={() => { onNavigate('data'); onSidebarOpenChange(false) }}
              aria-current={page === 'data' ? 'page' : undefined}
            >
              <Database size={19} strokeWidth={1.8} />
              <span>数据中心</span>
              <ChevronDown className="nav-parent-chevron" size={15} />
            </button>
            <div className="nav-sublist" aria-label="数据中心子页面">
              {dataChildren.map(({ id, label, icon: Icon }) => (
                <button
                  type="button"
                  key={id}
                  className={`nav-item nav-subitem ${page === id ? 'nav-item--active' : ''}`}
                  title={sidebarCollapsed ? label : undefined}
                  onClick={() => { onNavigate(id); onSidebarOpenChange(false) }}
                  aria-current={page === id ? 'page' : undefined}
                >
                  <Icon size={15} strokeWidth={1.8} />
                  <span>{label}</span>
                </button>
              ))}
            </div>
          </div>
          <div className={`nav-group ${jobPages.includes(page) ? 'nav-group--active' : ''}`}>
            <button
              type="button"
              className={`nav-item nav-parent ${page === 'jobs' ? 'nav-item--active' : ''}`}
              title={sidebarCollapsed ? '新岗位发现' : undefined}
              onClick={() => { onNavigate('jobs'); onSidebarOpenChange(false) }}
              aria-current={page === 'jobs' ? 'page' : undefined}
            >
              <BriefcaseBusiness size={19} strokeWidth={1.8} />
              <span>新岗位发现</span>
              <ChevronDown className="nav-parent-chevron" size={15} />
            </button>
            <div className="nav-sublist" aria-label="新岗位发现子页面">
              {jobChildren.map(({ id, label, icon: Icon }) => (
                <button
                  type="button"
                  key={id}
                  className={`nav-item nav-subitem ${page === id ? 'nav-item--active' : ''}`}
                  title={sidebarCollapsed ? label : undefined}
                  onClick={() => { onNavigate(id); onSidebarOpenChange(false) }}
                  aria-current={page === id ? 'page' : undefined}
                >
                  <Icon size={15} strokeWidth={1.8} />
                  <span>{label}</span>
                </button>
              ))}
            </div>
          </div>
          <div className={`nav-group ${graphPages.includes(page) ? 'nav-group--active' : ''}`}>
            <button
              type="button"
              className="nav-item nav-parent"
              title={sidebarCollapsed ? '能力图谱' : undefined}
              onClick={() => { onNavigate('industry-job-graph'); onSidebarOpenChange(false) }}
            >
              <Network size={19} strokeWidth={1.8} />
              <span>能力图谱</span>
              <ChevronDown className="nav-parent-chevron" size={15} />
            </button>
            <div className="nav-sublist" aria-label="能力图谱子页面">
              {graphChildren.map(({ id, label, icon: Icon }) => (
                <button
                  type="button"
                  key={id}
                  className={`nav-item nav-subitem ${page === id ? 'nav-item--active' : ''}`}
                  title={sidebarCollapsed ? label : undefined}
                  onClick={() => { onNavigate(id); onSidebarOpenChange(false) }}
                  aria-current={page === id ? 'page' : undefined}
                >
                  <Icon size={15} strokeWidth={1.8} />
                  <span>{label}</span>
                </button>
              ))}
            </div>
          </div>
          <div className={`nav-group ${talentPages.includes(page) ? 'nav-group--active' : ''}`}>
            <button
              type="button"
              className={`nav-item nav-parent ${page === 'talent' ? 'nav-item--active' : ''}`}
              title={sidebarCollapsed ? '人岗匹配' : undefined}
              onClick={() => { onNavigate('talent'); onSidebarOpenChange(false) }}
              aria-current={page === 'talent' ? 'page' : undefined}
            >
              <FileUser size={19} strokeWidth={1.8} />
              <span>人岗匹配</span>
              <ChevronDown className="nav-parent-chevron" size={15} />
            </button>
            <div className="nav-sublist" aria-label="人岗匹配子页面">
              {talentChildren.map(({ id, label, icon: Icon }) => (
                <button
                  type="button"
                  key={id}
                  className={`nav-item nav-subitem ${page === id ? 'nav-item--active' : ''}`}
                  title={sidebarCollapsed ? label : undefined}
                  onClick={() => { onNavigate(id); onSidebarOpenChange(false) }}
                  aria-current={page === id ? 'page' : undefined}
                >
                  <Icon size={15} strokeWidth={1.8} />
                  <span>{label}</span>
                </button>
              ))}
            </div>
          </div>
        </nav>
        <button
          type="button"
          className="sidebar-collapse-control"
          onClick={() => onSidebarCollapsedChange(!sidebarCollapsed)}
          aria-label={sidebarCollapsed ? '展开侧边栏' : '收起侧边栏'}
          title={sidebarCollapsed ? '展开菜单' : undefined}
        >
          {sidebarCollapsed ? <ChevronRight size={17} /> : <ChevronLeft size={17} />}
          <span>{sidebarCollapsed ? '展开菜单' : '收起菜单'}</span>
        </button>
        <div className="sidebar-foot">
          <button className="nav-item" title="系统设置待接入（阶段 D 认证上线后开放）" disabled><Settings2 size={19} /><span>系统设置</span></button>
          <div className="workspace-user">
            <CircleUserRound size={28} />
            <div><strong>研究空间</strong><span>具身智能专项</span></div>
            <ChevronDown size={15} />
          </div>
        </div>
      </aside>

      {sidebarOpen ? <button className="sidebar-scrim" aria-label="关闭导航" onClick={() => onSidebarOpenChange(false)} /> : null}

      <main className={`main-area ${sidebarCollapsed ? 'main-area--sidebar-collapsed' : ''}`}>
        <header className="topbar">
          <div className="topbar-title">
            <button className="icon-button mobile-menu" onClick={() => onSidebarOpenChange(true)} aria-label="打开导航"><Menu size={21} /></button>
            <h1>{pageTitle}</h1>
          </div>
          <div className="topbar-actions">
            <label className="search-box">
              <Search size={17} />
              <input
                aria-label="全局搜索"
                placeholder="搜索岗位或技术词，回车进入数据管理中心"
                onKeyDown={(event) => {
                  if (event.key === 'Enter') {
                    const value = event.currentTarget.value.trim()
                    if (value) {
                      onSearch?.(value)
                      event.currentTarget.value = ''
                    }
                  }
                }}
              />
            </label>
            <button className="filter-button" disabled title="全局时间筛选待接入（阶段 C 后开放）"><span>近 90 天</span><ChevronDown size={15} /></button>
            <button className="filter-button" disabled title="全局 T 领域筛选待接入（阶段 C 后开放）"><span>全部 T 领域</span><ChevronDown size={15} /></button>
            <button className="icon-button notification" aria-label="待审核任务" title="进入数据标注审核中心" onClick={() => onNavigate('review')}><Bell size={18} />{notificationCount > 0 ? <i>{notificationCount > 99 ? '99+' : notificationCount}</i> : null}</button>
          </div>
        </header>
        <div className="page-content">{children}</div>
      </main>

      {toast ? (
        <div className="toast" role="status">
          <ShieldCheck size={18} />
          <span>{toast}</span>
          <button className="icon-button" aria-label="关闭提示" onClick={onDismissToast}><X size={16} /></button>
        </div>
      ) : null}
    </div>
  )
}
