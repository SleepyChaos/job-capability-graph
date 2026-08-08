'use client';

import React from 'react';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import {
  Network,
  Sparkles,
  RefreshCw,
  UserCheck,
  Database,
  Search,
  Bell,
  ChevronDown,
  Settings,
} from 'lucide-react';

const navModules = [
  { id: 'atlas', label: '岗位图谱', icon: Network, path: '/atlas' },
  { id: 'discovery', label: '岗位发现', icon: Sparkles, path: '/discovery' },
  { id: 'matching', label: '人岗诊断', icon: UserCheck, path: '/matching' }, // 阶段 3：已接真实 API
  { id: 'evolution', label: '动态演化', icon: RefreshCw, path: '/evolution' }, // 阶段 5：已接真实 API
  { id: 'governance', label: '数据治理', icon: Database, path: '/governance' }, // 阶段 4：已接真实 API
  // 以下模块尚未接入真实后端数据，暂不展示（页面已隔离至 src/app-disabled/）：
  // { id: 'reports', label: '报告中心', icon: FileText, path: '/reports' },        // 阶段 6（测试报告见 docs/测试报告.md）
];

export function TopNavbar() {
  const pathname = usePathname();

  return (
    <header className="fixed top-0 left-0 right-0 z-50 h-14 bg-[#0F172A] border-b border-slate-700/50 flex items-center px-4">
      {/* Logo */}
      <div className="flex items-center gap-3 mr-8">
        <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-blue-500 to-violet-500 flex items-center justify-center">
          <Network className="w-5 h-5 text-white" />
        </div>
        <span className="text-white font-semibold text-base whitespace-nowrap">
          岗位图谱系统
        </span>
      </div>

      {/* Nav modules */}
      <nav className="flex items-center gap-1 flex-1">
        {navModules.map((mod) => {
          const isActive = pathname.startsWith(mod.path);
          return (
            <Link
              key={mod.id}
              href={mod.path}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md text-sm transition-colors ${
                isActive
                  ? 'bg-white/10 text-white'
                  : 'text-slate-400 hover:text-white hover:bg-white/5'
              }`}
            >
              <mod.icon className="w-4 h-4" />
              {mod.label}
            </Link>
          );
        })}
      </nav>

      {/* Right section */}
      <div className="flex items-center gap-3">
        <div className="relative">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
          <input
            type="text"
            placeholder="搜索岗位/技能..."
            className="w-52 h-8 pl-9 pr-3 rounded-md bg-white/5 border border-slate-600/50 text-sm text-white placeholder:text-slate-500 focus:outline-none focus:border-blue-500/50 focus:bg-white/10 transition-colors"
          />
        </div>
        <button className="relative p-2 rounded-md text-slate-400 hover:text-white hover:bg-white/5 transition-colors">
          <Bell className="w-4 h-4" />
          <span className="absolute top-1 right-1 w-2 h-2 bg-red-500 rounded-full" />
        </button>
        <Link
          href="/settings"
          className={`p-2 rounded-md transition-colors ${
            pathname.startsWith('/settings')
              ? 'text-white bg-white/10'
              : 'text-slate-400 hover:text-white hover:bg-white/5'
          }`}
          title="系统设置（LLM 配置）"
        >
          <Settings className="w-4 h-4" />
        </Link>
        <button className="flex items-center gap-2 px-2 py-1 rounded-md text-slate-300 hover:bg-white/5 transition-colors">
          <div className="w-7 h-7 rounded-full bg-gradient-to-br from-blue-400 to-violet-400 flex items-center justify-center text-white text-xs font-medium">
            管
          </div>
          <span className="text-sm">管理员</span>
          <ChevronDown className="w-3 h-3" />
        </button>
      </div>
    </header>
  );
}
