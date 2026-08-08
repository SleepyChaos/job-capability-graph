"use client"

import { useState } from "react"
import { crawlTargets, crawlRecords } from "@/lib/mock-data"
import { cn } from "@/lib/utils"
import {
  Globe,
  Building2,
  Landmark,
  Play,
  Pause,
  Plus,
  Upload,
  CheckCircle2,
  XCircle,
  Loader2,
} from "lucide-react"

const typeIcons = {
  recruitment: Globe,
  company: Building2,
  government: Landmark,
}

const typeLabels = {
  recruitment: "招聘网站",
  company: "企业官网",
  government: "政府网站",
}

const statusColors = {
  active: "bg-green-50 text-green-700",
  paused: "bg-yellow-50 text-yellow-700",
  disabled: "bg-gray-100 text-gray-500",
}

const statusLabels = {
  active: "运行中",
  paused: "已暂停",
  disabled: "已禁用",
}

export default function CrawlPage() {
  const [activeTab, setActiveTab] = useState<"targets" | "records" | "preview" | "import">("targets")

  const tabs = [
    { id: "targets" as const, label: "爬取目标" },
    { id: "records" as const, label: "采集记录" },
    { id: "preview" as const, label: "数据预览" },
    { id: "import" as const, label: "手动导入" },
  ]

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">数据采集</h1>
        <p className="text-sm text-gray-500 mt-1">管理爬取目标，查看采集记录与数据</p>
      </div>

      {/* Tabs */}
      <div className="flex gap-1 bg-gray-100 p-1 rounded-lg w-fit">
        {tabs.map((tab) => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            className={cn(
              "px-4 py-2 text-sm rounded-md transition-colors",
              activeTab === tab.id ? "bg-white text-gray-900 shadow-sm" : "text-gray-500 hover:text-gray-700"
            )}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* Tab Content */}
      {activeTab === "targets" && (
        <div className="space-y-4">
          <div className="flex justify-between items-center">
            <p className="text-sm text-gray-600">共 {crawlTargets.length} 个爬取目标</p>
            <button className="flex items-center gap-1.5 px-3 py-2 bg-blue-600 text-white text-sm rounded-lg hover:bg-blue-700">
              <Plus className="h-4 w-4" /> 新增目标
            </button>
          </div>
          <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
            <table className="w-full">
              <thead className="bg-gray-50 border-b border-gray-200">
                <tr>
                  <th className="text-left px-4 py-3 text-xs font-medium text-gray-500 uppercase">名称</th>
                  <th className="text-left px-4 py-3 text-xs font-medium text-gray-500 uppercase">类型</th>
                  <th className="text-left px-4 py-3 text-xs font-medium text-gray-500 uppercase">频率</th>
                  <th className="text-left px-4 py-3 text-xs font-medium text-gray-500 uppercase">状态</th>
                  <th className="text-left px-4 py-3 text-xs font-medium text-gray-500 uppercase">上次爬取</th>
                  <th className="text-left px-4 py-3 text-xs font-medium text-gray-500 uppercase">数据量</th>
                  <th className="text-left px-4 py-3 text-xs font-medium text-gray-500 uppercase">操作</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {crawlTargets.map((target) => {
                  const TypeIcon = typeIcons[target.type]
                  return (
                    <tr key={target.id} className="hover:bg-gray-50">
                      <td className="px-4 py-3">
                        <div className="flex items-center gap-2">
                          <TypeIcon className="h-4 w-4 text-gray-400" />
                          <span className="text-sm font-medium text-gray-900">{target.name}</span>
                        </div>
                        <p className="text-xs text-gray-400 ml-6">{target.url}</p>
                      </td>
                      <td className="px-4 py-3 text-sm text-gray-600">{typeLabels[target.type]}</td>
                      <td className="px-4 py-3 text-sm text-gray-600">{target.frequency}</td>
                      <td className="px-4 py-3">
                        <span className={cn("px-2 py-0.5 text-xs rounded-full", statusColors[target.status])}>
                          {statusLabels[target.status]}
                        </span>
                      </td>
                      <td className="px-4 py-3 text-sm text-gray-600">{target.lastCrawlAt}</td>
                      <td className="px-4 py-3 text-sm text-gray-900 font-medium">{target.itemsCount}</td>
                      <td className="px-4 py-3">
                        <button className="p-1.5 rounded hover:bg-gray-100 text-gray-500">
                          {target.status === "active" ? <Pause className="h-4 w-4" /> : <Play className="h-4 w-4" />}
                        </button>
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {activeTab === "records" && (
        <div className="space-y-3">
          {crawlRecords.map((record) => (
            <div key={record.id} className="bg-white rounded-xl border border-gray-200 p-4 flex items-center justify-between">
              <div className="flex items-center gap-3">
                {record.status === "success" && <CheckCircle2 className="h-5 w-5 text-green-500" />}
                {record.status === "failed" && <XCircle className="h-5 w-5 text-red-500" />}
                {record.status === "running" && <Loader2 className="h-5 w-5 text-blue-500 animate-spin" />}
                <div>
                  <p className="text-sm font-medium text-gray-900">{record.targetName}</p>
                  <p className="text-xs text-gray-500">{record.startedAt} → {record.finishedAt}</p>
                </div>
              </div>
              <div className="text-right">
                <p className="text-sm font-medium text-gray-900">+{record.newItems} 条新数据</p>
                {record.error && <p className="text-xs text-red-500">{record.error}</p>}
              </div>
            </div>
          ))}
        </div>
      )}

      {activeTab === "preview" && (
        <div className="bg-white rounded-xl border border-gray-200 p-8 text-center text-gray-400">
          <p className="text-sm">数据预览区域（开发中）</p>
          <p className="text-xs mt-1">展示原始数据 vs LLM提取结果对比</p>
        </div>
      )}

      {activeTab === "import" && (
        <div className="bg-white rounded-xl border border-gray-200 p-8">
          <div className="border-2 border-dashed border-gray-200 rounded-lg p-12 text-center hover:border-blue-300 transition-colors cursor-pointer">
            <Upload className="h-10 w-10 text-gray-300 mx-auto mb-3" />
            <p className="text-sm text-gray-600">拖拽文件到此处，或点击上传</p>
            <p className="text-xs text-gray-400 mt-1">支持 .txt, .csv, .json 格式</p>
          </div>
          <div className="mt-4">
            <textarea
              className="w-full h-32 px-3 py-2 border border-gray-200 rounded-lg text-sm resize-none focus:outline-none focus:ring-2 focus:ring-blue-500"
              placeholder="或直接粘贴文本内容..."
            />
            <div className="flex justify-end mt-2">
              <button className="px-4 py-2 bg-blue-600 text-white text-sm rounded-lg hover:bg-blue-700">
                提交导入
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
