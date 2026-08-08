"use client"

import { useState } from "react"
import { newPositions, milestones } from "@/lib/mock-data"
import { cn } from "@/lib/utils"
import {
  Sparkles,
  Check,
  X,
  Edit3,
  FileText,
  Zap,
  ChevronRight,
} from "lucide-react"

export default function DiscoveryPage() {
  const [activeTab, setActiveTab] = useState<"candidates" | "detail" | "history">("candidates")
  const [selectedPosition, setSelectedPosition] = useState<number | null>(null)

  const tabs = [
    { id: "candidates" as const, label: "候选岗位" },
    { id: "detail" as const, label: "岗位详情" },
    { id: "history" as const, label: "发现历史" },
  ]

  const selected = newPositions.find((p) => p.id === selectedPosition)

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">新岗位发现</h1>
        <p className="text-sm text-gray-500 mt-1">基于算法检测的潜在新岗位，等待确认入库</p>
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

      {/* Candidates */}
      {activeTab === "candidates" && (
        <div className="grid grid-cols-1 gap-4">
          {newPositions.map((position) => (
            <div key={position.id} className="bg-white rounded-xl border border-gray-200 p-5 hover:shadow-md transition-shadow">
              <div className="flex items-start justify-between">
                <div className="flex items-center gap-3">
                  <div className="p-2 bg-orange-50 rounded-lg">
                    <Sparkles className="h-5 w-5 text-orange-500" />
                  </div>
                  <div>
                    <h3 className="text-base font-semibold text-gray-900">{position.name}</h3>
                    <p className="text-sm text-gray-500 mt-0.5 line-clamp-1">{position.coreResponsibilities}</p>
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  <span className={cn(
                    "px-2.5 py-1 text-xs font-medium rounded-full",
                    position.confidence >= 0.85 ? "bg-green-50 text-green-700" : "bg-yellow-50 text-yellow-700"
                  )}>
                    置信度 {(position.confidence * 100).toFixed(0)}%
                  </span>
                  <span className={cn(
                    "px-2.5 py-1 text-xs rounded-full",
                    position.status === "candidate" ? "bg-blue-50 text-blue-600" : "bg-gray-100 text-gray-500"
                  )}>
                    {position.status === "candidate" ? "待确认" : position.status === "confirmed" ? "已确认" : "已拒绝"}
                  </span>
                </div>
              </div>

              {/* Skills */}
              <div className="mt-4 flex flex-wrap gap-1.5">
                {position.requiredSkills.map((skill) => (
                  <span key={skill} className="px-2 py-0.5 text-xs bg-blue-50 text-blue-700 rounded-md">{skill}</span>
                ))}
                {position.bonusSkills.map((skill) => (
                  <span key={skill} className="px-2 py-0.5 text-xs bg-gray-100 text-gray-600 rounded-md">{skill}</span>
                ))}
              </div>

              {/* Milestones */}
              <div className="mt-3 flex items-center gap-2">
                <Zap className="h-3.5 w-3.5 text-amber-500" />
                <span className="text-xs text-gray-500">
                  关联里程碑：{position.relatedMilestones.join("、")}
                </span>
              </div>

              {/* Actions */}
              <div className="mt-4 pt-3 border-t border-gray-100 flex items-center justify-between">
                <span className="text-xs text-gray-400">发现时间：{position.createdAt}</span>
                <div className="flex gap-2">
                  <button
                    onClick={() => { setSelectedPosition(position.id); setActiveTab("detail") }}
                    className="flex items-center gap-1 px-3 py-1.5 text-xs text-gray-600 border border-gray-200 rounded-md hover:bg-gray-50"
                  >
                    <Edit3 className="h-3 w-3" /> 编辑
                  </button>
                  <button className="flex items-center gap-1 px-3 py-1.5 text-xs text-white bg-green-600 rounded-md hover:bg-green-700">
                    <Check className="h-3 w-3" /> 确认入库
                  </button>
                  <button className="flex items-center gap-1 px-3 py-1.5 text-xs text-red-600 border border-red-200 rounded-md hover:bg-red-50">
                    <X className="h-3 w-3" /> 拒绝
                  </button>
                  <button className="flex items-center gap-1 px-3 py-1.5 text-xs text-blue-600 border border-blue-200 rounded-md hover:bg-blue-50">
                    <FileText className="h-3 w-3" /> 细化为JD
                  </button>
                </div>
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
              <div className="flex items-center justify-between mb-6">
                <h2 className="text-xl font-bold text-gray-900">{selected.name}</h2>
                <button onClick={() => setActiveTab("candidates")} className="text-sm text-blue-600 hover:underline">
                  ← 返回列表
                </button>
              </div>
              <div className="grid grid-cols-2 gap-6">
                <div className="space-y-4">
                  <div>
                    <h4 className="text-sm font-medium text-gray-700 mb-1">核心职责</h4>
                    <p className="text-sm text-gray-600">{selected.coreResponsibilities}</p>
                  </div>
                  <div>
                    <h4 className="text-sm font-medium text-gray-700 mb-1">典型行业应用场景</h4>
                    <p className="text-sm text-gray-600">{selected.industryScenarios}</p>
                  </div>
                  <div>
                    <h4 className="text-sm font-medium text-gray-700 mb-2">关联里程碑</h4>
                    {selected.relatedMilestones.map((m) => (
                      <div key={m} className="flex items-center gap-2 py-1">
                        <Zap className="h-3.5 w-3.5 text-amber-500" />
                        <span className="text-sm text-gray-600">{m}</span>
                      </div>
                    ))}
                  </div>
                </div>
                <div className="space-y-4">
                  <div>
                    <h4 className="text-sm font-medium text-gray-700 mb-2">必备技能</h4>
                    <div className="flex flex-wrap gap-1.5">
                      {selected.requiredSkills.map((s) => (
                        <span key={s} className="px-2.5 py-1 text-sm bg-blue-50 text-blue-700 rounded-md">{s}</span>
                      ))}
                    </div>
                  </div>
                  <div>
                    <h4 className="text-sm font-medium text-gray-700 mb-2">加分技能</h4>
                    <div className="flex flex-wrap gap-1.5">
                      {selected.bonusSkills.map((s) => (
                        <span key={s} className="px-2.5 py-1 text-sm bg-gray-100 text-gray-600 rounded-md">{s}</span>
                      ))}
                    </div>
                  </div>
                  <div className="pt-4">
                    <button className="w-full px-4 py-2.5 bg-blue-600 text-white text-sm rounded-lg hover:bg-blue-700">
                      保存修改
                    </button>
                  </div>
                </div>
              </div>
            </div>
          ) : (
            <div className="bg-white rounded-xl border border-gray-200 p-12 text-center text-gray-400">
              请先选择一个候选岗位查看详情
            </div>
          )}
        </div>
      )}

      {/* History */}
      {activeTab === "history" && (
        <div className="bg-white rounded-xl border border-gray-200 p-8 text-center text-gray-400">
          <p className="text-sm">已确认的新岗位历史记录</p>
          <p className="text-xs mt-1">暂无数据（Mock阶段）</p>
        </div>
      )}
    </div>
  )
}
