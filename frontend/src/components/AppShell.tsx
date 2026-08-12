import type { ComponentType, ReactNode } from 'react'
import {
  Activity,
  Bell,
  BookOpenCheck,
  BriefcaseBusiness,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  CircleUserRound,
  Database,
  DatabaseZap,
  FileClock,
  FileSearch,
  FileUser,
  GitBranch,
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

const dataPages: PageId[] = ['data', 'sources', 'management', 'taxonomy', 'review']
const dataChildren: NavItem[] = [
  { id: 'sources', label: '数据采集中枢', icon: DatabaseZap },
  { id: 'management', label: '数据管理中心', icon: Database },
  { id: 'taxonomy', label: '技术词标准管理', icon: GitBranch },
  { id: 'review', label: '数据审核中心', icon: ShieldCheck },
]

const talentPages: PageId[] = ['talent', 'resume', 'match', 'learning']
const talentChildren: NavItem[] = [
  { id: 'resume', label: '求职者画像', icon: FileUser },
  { id: 'match', label: '匹配分析', icon: Activity },
  { id: 'learning', label: '发展路径', icon: BookOpenCheck },
]

const jobPages: PageId[] = ['jobs', 'job-keyword', 'job-name', 'job-records']
const jobChildren: NavItem[] = [
  { id: 'job-keyword', label: '技术词定向推演', icon: Tags },
  { id: 'job-name', label: '岗位名称推演', icon: FileSearch },
  { id: 'job-records', label: '推演结果记录库', icon: FileClock },
]

const graphPages: PageId[] = ['graph', 'graph-heatmap', 'graph-relations', 'graph-clusters']
const graphChildren: NavItem[] = [
  { id: 'graph-heatmap', label: '能力热力图', icon: Activity },
  { id: 'graph-relations', label: '岗位—能力关联图', icon: Network },
  { id: 'graph-clusters', label: '聚类岗位能力图谱', icon: GitBranch },
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
              className={`nav-item nav-parent ${page === 'graph' ? 'nav-item--active' : ''}`}
              title={sidebarCollapsed ? '能力图谱' : undefined}
              onClick={() => { onNavigate('graph'); onSidebarOpenChange(false) }}
              aria-current={page === 'graph' ? 'page' : undefined}
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
            <button className="icon-button notification" aria-label="待审核任务" title="进入数据审核中心" onClick={() => onNavigate('review')}><Bell size={18} />{notificationCount > 0 ? <i>{notificationCount > 99 ? '99+' : notificationCount}</i> : null}</button>
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
