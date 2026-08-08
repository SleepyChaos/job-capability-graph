"use client"

import Link from "next/link"
import { usePathname } from "next/navigation"
import { cn } from "@/lib/utils"
import {
  LayoutDashboard,
  Radio,
  Search,
  Tags,
  Network,
  FileText,
  Settings,
  Bot,
} from "lucide-react"

const navItems = [
  { href: "/", label: "数据总览", icon: LayoutDashboard },
  { href: "/crawl", label: "数据采集", icon: Radio },
  { href: "/discovery", label: "新岗位发现", icon: Search },
  { href: "/cluster", label: "岗位聚类管理", icon: Tags },
  { href: "/graph", label: "能力图谱", icon: Network },
  { href: "/resume", label: "简历匹配", icon: FileText },
  { href: "/settings", label: "系统设置", icon: Settings },
]

export function Sidebar() {
  const pathname = usePathname()

  return (
    <aside className="fixed left-0 top-0 z-40 h-screen w-60 border-r border-gray-200 bg-white flex flex-col">
      {/* Logo */}
      <div className="flex h-16 items-center gap-2 px-5 border-b border-gray-100">
        <Bot className="h-7 w-7 text-blue-600" />
        <div>
          <h1 className="text-sm font-bold text-gray-900">具身智能</h1>
          <p className="text-xs text-gray-500">岗位能力图谱系统</p>
        </div>
      </div>

      {/* Navigation */}
      <nav className="flex-1 px-3 py-4 space-y-1 overflow-y-auto">
        {navItems.map((item) => {
          const isActive = pathname === item.href
          return (
            <Link
              key={item.href}
              href={item.href}
              className={cn(
                "flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition-colors",
                isActive
                  ? "bg-blue-50 text-blue-700"
                  : "text-gray-600 hover:bg-gray-50 hover:text-gray-900"
              )}
            >
              <item.icon className={cn("h-4.5 w-4.5", isActive ? "text-blue-600" : "text-gray-400")} />
              {item.label}
            </Link>
          )
        })}
      </nav>

      {/* Footer */}
      <div className="border-t border-gray-100 px-5 py-4">
        <p className="text-xs text-gray-400">XH-202621 赛题项目</p>
        <p className="text-xs text-gray-400">v0.1.0-mock</p>
      </div>
    </aside>
  )
}
