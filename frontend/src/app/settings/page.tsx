"use client"

import { useState } from "react"
import { cn } from "@/lib/utils"
import { Save, Key, Clock, SlidersHorizontal, Database } from "lucide-react"

export default function SettingsPage() {
  const [activeTab, setActiveTab] = useState<"llm" | "crawl" | "algorithm" | "data">("llm")

  const tabs = [
    { id: "llm" as const, label: "LLM配置", icon: Key },
    { id: "crawl" as const, label: "调度配置", icon: Clock },
    { id: "algorithm" as const, label: "算法参数", icon: SlidersHorizontal },
    { id: "data" as const, label: "数据管理", icon: Database },
  ]

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">系统设置</h1>
        <p className="text-sm text-gray-500 mt-1">配置LLM、调度、算法参数与数据管理</p>
      </div>

      {/* Tabs */}
      <div className="flex gap-1 bg-gray-100 p-1 rounded-lg w-fit">
        {tabs.map((tab) => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            className={cn(
              "flex items-center gap-1.5 px-4 py-2 text-sm rounded-md transition-colors",
              activeTab === tab.id ? "bg-white text-gray-900 shadow-sm" : "text-gray-500 hover:text-gray-700"
            )}
          >
            <tab.icon className="h-4 w-4" />
            {tab.label}
          </button>
        ))}
      </div>

      {/* LLM Settings */}
      {activeTab === "llm" && (
        <div className="max-w-xl space-y-4">
          <div className="bg-white rounded-xl border border-gray-200 p-5 space-y-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">API Key</label>
              <input type="password" className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm" placeholder="sk-..." defaultValue="sk-mock-key" />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">API Base URL</label>
              <input className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm" defaultValue="https://api.deepseek.com/v1" />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">模型</label>
              <select className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm bg-white">
                <option>deepseek-chat</option>
                <option>deepseek-reasoner</option>
                <option>gpt-4o</option>
              </select>
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Temperature</label>
              <input type="number" className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm" defaultValue="0.7" step="0.1" min="0" max="2" />
            </div>
            <button className="flex items-center gap-1.5 px-4 py-2 bg-blue-600 text-white text-sm rounded-lg hover:bg-blue-700">
              <Save className="h-4 w-4" /> 保存配置
            </button>
          </div>
        </div>
      )}

      {/* Crawl Settings */}
      {activeTab === "crawl" && (
        <div className="max-w-xl space-y-4">
          <div className="bg-white rounded-xl border border-gray-200 p-5 space-y-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">默认爬取频率</label>
              <select className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm bg-white">
                <option>每小时</option>
                <option>每日</option>
                <option>每周</option>
              </select>
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">爬取超时（秒）</label>
              <input type="number" className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm" defaultValue="30" />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">最大重试次数</label>
              <input type="number" className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm" defaultValue="3" />
            </div>
            <button className="flex items-center gap-1.5 px-4 py-2 bg-blue-600 text-white text-sm rounded-lg hover:bg-blue-700">
              <Save className="h-4 w-4" /> 保存配置
            </button>
          </div>
        </div>
      )}

      {/* Algorithm Settings */}
      {activeTab === "algorithm" && (
        <div className="max-w-xl space-y-4">
          <div className="bg-white rounded-xl border border-gray-200 p-5 space-y-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">聚类相似度阈值（高）</label>
              <input type="number" className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm" defaultValue="0.85" step="0.05" min="0" max="1" />
              <p className="text-xs text-gray-400 mt-1">高于此值自动归入聚类</p>
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">聚类相似度阈值（低）</label>
              <input type="number" className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm" defaultValue="0.6" step="0.05" min="0" max="1" />
              <p className="text-xs text-gray-400 mt-1">低于此值进入新聚类候选</p>
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">新岗位自动通过置信度阈值</label>
              <input type="number" className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm" defaultValue="0.9" step="0.05" min="0" max="1" />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">时间衰减系数</label>
              <input type="number" className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm" defaultValue="0.95" step="0.01" min="0" max="1" />
              <p className="text-xs text-gray-400 mt-1">每日衰减比例，用于技术词权重计算</p>
            </div>
            <button className="flex items-center gap-1.5 px-4 py-2 bg-blue-600 text-white text-sm rounded-lg hover:bg-blue-700">
              <Save className="h-4 w-4" /> 保存配置
            </button>
          </div>
        </div>
      )}

      {/* Data Management */}
      {activeTab === "data" && (
        <div className="max-w-xl space-y-4">
          <div className="bg-white rounded-xl border border-gray-200 p-5 space-y-4">
            <h3 className="text-sm font-semibold text-gray-700">数据操作</h3>
            <div className="grid grid-cols-2 gap-3">
              <button className="px-4 py-3 border border-gray-200 rounded-lg text-sm hover:bg-gray-50 text-left">
                <p className="font-medium text-gray-900">导出数据</p>
                <p className="text-xs text-gray-400 mt-0.5">导出全量数据为JSON</p>
              </button>
              <button className="px-4 py-3 border border-gray-200 rounded-lg text-sm hover:bg-gray-50 text-left">
                <p className="font-medium text-gray-900">导入数据</p>
                <p className="text-xs text-gray-400 mt-0.5">从JSON文件导入</p>
              </button>
              <button className="px-4 py-3 border border-yellow-200 rounded-lg text-sm hover:bg-yellow-50 text-left">
                <p className="font-medium text-yellow-700">重新聚类</p>
                <p className="text-xs text-gray-400 mt-0.5">全量重新执行JD聚类</p>
              </button>
              <button className="px-4 py-3 border border-red-200 rounded-lg text-sm hover:bg-red-50 text-left">
                <p className="font-medium text-red-600">重置数据</p>
                <p className="text-xs text-gray-400 mt-0.5">清空所有数据（不可逆）</p>
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
