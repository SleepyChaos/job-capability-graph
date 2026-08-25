import { FileSearch, Tags } from 'lucide-react'
import { useState } from 'react'
import { JobKeywordPage } from './JobKeywordPage'
import { JobNamePage } from './JobNamePage'

/**
 * 定向推演：把「技术词定向」与「岗位名称核验」合成一个页面。
 *
 * 两者都是**按用户给定的入口做定向查询**，与自动发现的批量推演是两回事——
 * 后者扫全库产出候选，前者回答「我指定这组技术/这个岗位名，系统怎么说」。
 * 它们此前各占一个导航项，把主流程（发现 → 数据卡 → 审核台）挤到了一边；
 * 合成一页后导航回到主流程的节奏上，功能一个没少。
 *
 * 两种模式的输入方式差别足够大（多选技术词 vs 输入岗位名 + 描述），共用一套
 * 表单只会互相迁就，因此保留各自的实现，这里只做入口切换与状态隔离——
 * 切换标签时对应子页面卸载，不会把上一次的查询结果串到另一种模式里。
 */
type DirectedMode = 'technology' | 'name'

const MODES: { id: DirectedMode; label: string; hint: string; icon: typeof Tags }[] = [
  {
    id: 'technology',
    label: '按技术词定向',
    hint: '指定一组 L3 技术点，看系统据此推演出什么岗位组合',
    icon: Tags,
  },
  {
    id: 'name',
    label: '按岗位名称核验',
    hint: '输入一个岗位名，看它在正式岗位库与候选库中是否已存在',
    icon: FileSearch,
  },
]

export function DirectedDiscoveryPage({ notify }: { notify: (message: string) => void }) {
  const [mode, setMode] = useState<DirectedMode>('technology')
  const active = MODES.find((item) => item.id === mode) ?? MODES[0]

  return (
    <div className="page-stack directed-discovery">
      <div className="directed-mode-bar">
        {MODES.map((item) => {
          const Icon = item.icon
          return (
            <button
              key={item.id}
              className={item.id === mode ? 'active' : ''}
              onClick={() => setMode(item.id)}
            >
              <Icon size={15} />
              {item.label}
            </button>
          )
        })}
      </div>
      <p className="directed-mode-hint">{active.hint}</p>

      {mode === 'technology' ? <JobKeywordPage notify={notify} /> : <JobNamePage notify={notify} />}
    </div>
  )
}
