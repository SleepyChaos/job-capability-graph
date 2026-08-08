"use client"

import { useState } from "react"
import { jobClusters, capabilityUpdates, techTerms } from "@/lib/mock-data"
import { cn } from "@/lib/utils"
import {
  Tags,
  Check,
  X,
  TrendingUp,
  TrendingDown,
  Minus,
  Plus,
  AlertTriangle,
  ArrowUpCircle,
  ArrowDownCircle,
  Edit3,
} from "lucide-react"

const changeTypeConfig = {
  added: { label: "新增", icon: Plus, color: "text-green-600 bg-green-50" },
  removed: { label: "删除", icon: X, color: "text-red-600 bg-red-50" },
  modified: { label: "修改", icon: Edit3, color: "text-blue-600 bg-blue-50" },
}

export default function ClusterPage() {
  const [activeTab, setActiveTab] = useState<"overview" | "detail" | "updates" | "approval" | "trend">("overview")
  const [selectedCluster, setSelectedCluster] = useState<number | null>(null)

  const tabs = [
    { id: "overview" as const, label: "聚类总览" },
    { id: "detail" as const, label: "聚类详情" },
    { id: "updates" as const, label: "能力更新" },
    { id: "approval" as const, label: "审批队列" },
    { id: "trend" as const, label: "趋势分析" },
  ]

  const pendingClusters = jobClusters.filter((c) => c.status === "pending_review")
  const selected = jobClusters.find((c) => c.id === selectedCluster)

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">岗位聚类管理</h1>
        <p className="text-sm text-gray-500 mt-1">管理既有岗位聚类，追踪能力需求动态更新</p>
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
            {tab.id === "approval" && pendingClusters.length > 0 && (
              <span className="ml-1.5 px-1.5 py-0.5 text-xs bg-red-500 text-white rounded-full">{pendingClusters.length}</span>
            )}
          </button>
        ))}
      </div>

      {/* Overview */}
      {activeTab === "overview" && (
        <div className="grid grid-cols-2 gap-4">
          {jobClusters.map((cluster) => (
            <div
              key={cluster.id}
              className="bg-white rounded-xl border border-gray-200 p-5 hover:shadow-md transition-shadow cursor-pointer"
              onClick={() => { setSelectedCluster(cluster.id); setActiveTab("detail") }}
            >
              <div className="flex items-start justify-between">
                <div className="flex items-center gap-2">
                  <Tags className="h-5 w-5 text-purple-500" />
                  <h3 className="text-base font-semibold text-gray-900">{cluster.name}</h3>
                </div>
                <div className="flex items-center gap-2">
                  {cluster.isPredefined && (
                    <span className="px-2 py-0.5 text-xs bg-gray-100 text-gray-500 rounded">预定义</span>
                  )}
                  <span className={cn(
                    "px-2 py-0.5 text-xs rounded-full",
                    cluster.status === "active" ? "bg-green-50 text-green-600" : "bg-yellow-50 text-yellow-600"
                  )}>
                    {cluster.status === "active" ? "活跃" : "待审批"}
                  </span>
                </div>
              </div>

              <div className="mt-3 grid grid-cols-3 gap-3">
                <div className="text-center p-2 bg-gray-50 rounded-lg">
                  <p className="text-lg font-bold text-gray-900">{cluster.jdCount}</p>
                  <p className="text-xs text-gray-500">关联JD</p>
                </div>
                <div className="text-center p-2 bg-gray-50 rounded-lg">
                  <p className="text-lg font-bold text-gray-900">{cluster.termCount}</p>
                  <p className="text-xs text-gray-500">技术词</p>
                </div>
                <div className="text-center p-2 bg-gray-50 rounded-lg">
                  <p className="text-lg font-bold text-gray-900">{(cluster.confidence * 100).toFixed(0)}%</p>
                  <p className="text-xs text-gray-500">置信度</p>
                </div>
              </div>

              <div className="mt-3 flex flex-wrap gap-1.5">
                {cluster.topSkills.map((skill) => (
                  <span key={skill} className="px-2 py-0.5 text-xs bg-purple-50 text-purple-600 rounded-md">{skill}</span>
                ))}
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Detail */}
      {activeTab === "detail" && (
        <div>
          {selected ? (
            <div className="bg-white rounded-xl border border-gray-200 p-6">
              <div className="flex items-center justify-between mb-4">
                <h2 className="text-lg font-bold text-gray-900">{selected.name}</h2>
                <button onClick={() => setActiveTab("overview")} className="text-sm text-blue-600 hover:underline">← 返回</button>
              </div>
              <p className="text-sm text-gray-600 mb-4">分类：{selected.category} | JD数量：{selected.jdCount} | 置信度：{(selected.confidence * 100).toFixed(0)}%</p>
              <div className="space-y-3">
                <h4 className="text-sm font-medium text-gray-700">核心技能需求</h4>
                <div className="grid grid-cols-2 gap-2">
                  {selected.topSkills.map((skill) => {
                    const term = techTerms.find((t) => t.name === skill)
                    return (
                      <div key={skill} className="flex items-center justify-between p-3 bg-gray-50 rounded-lg">
                        <span className="text-sm text-gray-900">{skill}</span>
                        {term && (
                          <span className="text-xs text-gray-400">频率: {term.frequency}</span>
                        )}
                      </div>
                    )
                  })}
                </div>
              </div>
            </div>
          ) : (
            <div className="bg-white rounded-xl border border-gray-200 p-12 text-center text-gray-400">
              请在聚类总览中选择一个聚类查看详情
            </div>
          )}
        </div>
      )}

      {/* Updates */}
      {activeTab === "updates" && (
        <div className="space-y-3">
          {capabilityUpdates.map((update) => {
            const config = changeTypeConfig[update.changeType]
            const Icon = config.icon
            return (
              <div key={update.id} className="bg-white rounded-xl border border-gray-200 p-4">
                <div className="flex items-start justify-between">
                  <div className="flex items-start gap-3">
                    <div className={cn("p-2 rounded-lg", config.color)}>
                      <Icon className="h-4 w-4" />
                    </div>
                    <div>
                      <div className="flex items-center gap-2">
                        <span className="text-sm font-medium text-gray-900">{update.clusterName}</span>
                        <span className={cn("px-2 py-0.5 text-xs rounded-full", config.color)}>{config.label}</span>
                        <span className="text-sm text-gray-700 font-medium">{update.termName}</span>
                      </div>
                      <p className="text-sm text-gray-500 mt-1">{update.description}</p>
                      <p className="text-xs text-gray-400 mt-1">来源：{update.evidenceSource}</p>
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    <span className={cn(
                      "px-2 py-0.5 text-xs rounded-full",
                      update.status === "pending" ? "bg-yellow-50 text-yellow-600" : update.status === "confirmed" ? "bg-green-50 text-green-600" : "bg-red-50 text-red-600"
                    )}>
                      {update.status === "pending" ? "待确认" : update.status === "confirmed" ? "已确认" : "已拒绝"}
                    </span>
                  </div>
                </div>
                {update.status === "pending" && (
                  <div className="mt-3 pt-3 border-t border-gray-100 flex justify-end gap-2">
                    <button className="flex items-center gap-1 px-3 py-1.5 text-xs text-white bg-green-600 rounded-md hover:bg-green-700">
                      <Check className="h-3 w-3" /> 确认
                    </button>
                    <button className="flex items-center gap-1 px-3 py-1.5 text-xs text-red-600 border border-red-200 rounded-md hover:bg-red-50">
                      <X className="h-3 w-3" /> 拒绝
                    </button>
                  </div>
                )}
              </div>
            )
          })}
        </div>
      )}

      {/* Approval */}
      {activeTab === "approval" && (
        <div className="space-y-3">
          {pendingClusters.length > 0 ? (
            pendingClusters.map((cluster) => (
              <div key={cluster.id} className="bg-white rounded-xl border border-yellow-200 p-5">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-3">
                    <AlertTriangle className="h-5 w-5 text-yellow-500" />
                    <div>
                      <h3 className="text-base font-semibold text-gray-900">{cluster.name}</h3>
                      <p className="text-sm text-gray-500">LLM评分：{(cluster.confidence * 100).toFixed(0)}%（低于自动通过阈值）</p>
                    </div>
                  </div>
                  <div className="flex gap-2">
                    <button className="flex items-center gap-1 px-4 py-2 text-sm text-white bg-green-600 rounded-lg hover:bg-green-700">
                      <Check className="h-4 w-4" /> 通过
                    </button>
                    <button className="flex items-center gap-1 px-4 py-2 text-sm text-red-600 border border-red-200 rounded-lg hover:bg-red-50">
                      <X className="h-4 w-4" /> 拒绝
                    </button>
                  </div>
                </div>
                <div className="mt-3 flex flex-wrap gap-1.5">
                  {cluster.topSkills.map((skill) => (
                    <span key={skill} className="px-2 py-0.5 text-xs bg-gray-100 text-gray-600 rounded-md">{skill}</span>
                  ))}
                </div>
              </div>
            ))
          ) : (
            <div className="bg-white rounded-xl border border-gray-200 p-12 text-center text-gray-400">
              暂无待审批的聚类
            </div>
          )}
        </div>
      )}

      {/* Trend */}
      {activeTab === "trend" && (
        <div className="bg-white rounded-xl border border-gray-200 p-6">
          <h3 className="text-sm font-semibold text-gray-700 mb-4">技术词趋势分析</h3>
          <div className="space-y-3">
            {techTerms.map((term) => (
              <div key={term.id} className="flex items-center justify-between py-2 border-b border-gray-50 last:border-0">
                <div className="flex items-center gap-3">
                  {term.trend === "rising" && <TrendingUp className="h-4 w-4 text-green-500" />}
                  {term.trend === "declining" && <TrendingDown className="h-4 w-4 text-red-500" />}
                  {term.trend === "stable" && <Minus className="h-4 w-4 text-gray-400" />}
                  <span className="text-sm text-gray-900">{term.name}</span>
                  <span className="text-xs text-gray-400">{term.category}</span>
                </div>
                <div className="flex items-center gap-4">
                  <div className="w-32 h-2 bg-gray-100 rounded-full overflow-hidden">
                    <div
                      className={cn("h-full rounded-full", term.trend === "rising" ? "bg-green-500" : term.trend === "declining" ? "bg-red-400" : "bg-gray-300")}
                      style={{ width: `${(term.frequency / 100) * 100}%` }}
                    />
                  </div>
                  <span className="text-sm text-gray-600 w-8">{term.frequency}</span>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
