"use client"

import { useState } from "react"
import {
  dashboardStats,
  graphNodes,
  graphEdges,
  techTerms,
  jobClusters,
} from "@/lib/mock-data"
import {
  FileText,
  Tags,
  Layers,
  Sparkles,
  TrendingUp,
  TrendingDown,
  Minus,
  ChevronRight,
} from "lucide-react"
import { cn } from "@/lib/utils"

const statCards = [
  { label: "已采集JD", value: dashboardStats.totalJDs, icon: FileText, color: "text-blue-600 bg-blue-50" },
  { label: "技术词总数", value: dashboardStats.totalTerms, icon: Tags, color: "text-green-600 bg-green-50" },
  { label: "岗位聚类数", value: dashboardStats.totalClusters, icon: Layers, color: "text-purple-600 bg-purple-50" },
  { label: "新发现岗位", value: dashboardStats.totalNewPositions, icon: Sparkles, color: "text-orange-600 bg-orange-50" },
]

function TrendIcon({ trend }: { trend: string }) {
  if (trend === "rising") return <TrendingUp className="h-3.5 w-3.5 text-green-500" />
  if (trend === "declining") return <TrendingDown className="h-3.5 w-3.5 text-red-500" />
  return <Minus className="h-3.5 w-3.5 text-gray-400" />
}

export default function DashboardPage() {
  const [selectedNode, setSelectedNode] = useState<string | null>(null)
  const [viewMode, setViewMode] = useState<"overview" | "association" | "heatmap" | "evolution">("overview")

  const selectedNodeData = graphNodes.find((n) => n.id === selectedNode)
  const relatedEdges = graphEdges.filter(
    (e) => e.source === selectedNode || e.target === selectedNode
  )

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">数据总览</h1>
          <p className="text-sm text-gray-500 mt-1">
            最近更新：{dashboardStats.lastUpdated}
          </p>
        </div>
        <div className="flex gap-2">
          {(["overview", "association", "heatmap", "evolution"] as const).map((mode) => (
            <button
              key={mode}
              onClick={() => setViewMode(mode)}
              className={cn(
                "px-3 py-1.5 text-sm rounded-md transition-colors",
                viewMode === mode
                  ? "bg-blue-600 text-white"
                  : "bg-white text-gray-600 border border-gray-200 hover:bg-gray-50"
              )}
            >
              {mode === "overview" && "全景"}
              {mode === "association" && "关联图"}
              {mode === "heatmap" && "热力图"}
              {mode === "evolution" && "演进图"}
            </button>
          ))}
        </div>
      </div>

      {/* Stats Cards */}
      <div className="grid grid-cols-4 gap-4">
        {statCards.map((card) => (
          <div key={card.label} className="bg-white rounded-xl border border-gray-200 p-4 flex items-center gap-3">
            <div className={cn("p-2.5 rounded-lg", card.color)}>
              <card.icon className="h-5 w-5" />
            </div>
            <div>
              <p className="text-2xl font-bold text-gray-900">{card.value}</p>
              <p className="text-xs text-gray-500">{card.label}</p>
            </div>
          </div>
        ))}
      </div>

      {/* Three Panel Layout */}
      <div className="grid grid-cols-12 gap-4 h-[560px]">
        {/* Left Panel - Node List */}
        <div className="col-span-3 bg-white rounded-xl border border-gray-200 flex flex-col overflow-hidden">
          <div className="px-4 py-3 border-b border-gray-100">
            <h3 className="text-sm font-semibold text-gray-700">节点列表</h3>
          </div>
          <div className="flex-1 overflow-y-auto p-2">
            {/* Clusters Section */}
            <div className="mb-3">
              <p className="text-xs font-medium text-gray-400 uppercase tracking-wide px-2 mb-1">岗位聚类</p>
              {jobClusters.map((cluster) => (
                <button
                  key={cluster.id}
                  onClick={() => setSelectedNode(`c${cluster.id}`)}
                  className={cn(
                    "w-full text-left px-2 py-1.5 rounded-md text-sm transition-colors flex items-center justify-between",
                    selectedNode === `c${cluster.id}` ? "bg-blue-50 text-blue-700" : "hover:bg-gray-50 text-gray-700"
                  )}
                >
                  <span>{cluster.name}</span>
                  <span className="text-xs text-gray-400">{cluster.jdCount}条JD</span>
                </button>
              ))}
            </div>
            {/* Terms Section */}
            <div>
              <p className="text-xs font-medium text-gray-400 uppercase tracking-wide px-2 mb-1">技术词</p>
              {techTerms.map((term) => (
                <button
                  key={term.id}
                  onClick={() => setSelectedNode(`t${term.id}`)}
                  className={cn(
                    "w-full text-left px-2 py-1.5 rounded-md text-sm transition-colors flex items-center justify-between",
                    selectedNode === `t${term.id}` ? "bg-blue-50 text-blue-700" : "hover:bg-gray-50 text-gray-700"
                  )}
                >
                  <span>{term.name}</span>
                  <TrendIcon trend={term.trend} />
                </button>
              ))}
            </div>
          </div>
        </div>

        {/* Center Panel - Graph Area */}
        <div className="col-span-6 bg-white rounded-xl border border-gray-200 flex flex-col overflow-hidden">
          <div className="flex-1 flex items-center justify-center relative">
            {/* Mock Graph Visualization */}
            <div className="absolute inset-0 p-4">
              <svg className="w-full h-full" viewBox="0 0 600 400">
                {/* Edges */}
                {graphEdges.map((edge, i) => {
                  const source = graphNodes.find((n) => n.id === edge.source)
                  const target = graphNodes.find((n) => n.id === edge.target)
                  if (!source || !target) return null
                  const sx = getNodePosition(source.id).x
                  const sy = getNodePosition(source.id).y
                  const tx = getNodePosition(target.id).x
                  const ty = getNodePosition(target.id).y
                  return (
                    <line
                      key={i}
                      x1={sx} y1={sy} x2={tx} y2={ty}
                      stroke="#e5e7eb"
                      strokeWidth={edge.weight || 1}
                    />
                  )
                })}
                {/* Nodes */}
                {graphNodes.map((node) => {
                  const pos = getNodePosition(node.id)
                  const isSelected = selectedNode === node.id
                  return (
                    <g
                      key={node.id}
                      onClick={() => setSelectedNode(node.id)}
                      className="cursor-pointer"
                    >
                      <circle
                        cx={pos.x}
                        cy={pos.y}
                        r={node.size || 15}
                        fill={getNodeColor(node.type)}
                        opacity={isSelected ? 1 : 0.7}
                        stroke={isSelected ? "#2563eb" : "none"}
                        strokeWidth={isSelected ? 3 : 0}
                      />
                      <text
                        x={pos.x}
                        y={pos.y + (node.size || 15) + 14}
                        textAnchor="middle"
                        fontSize="10"
                        fill="#6b7280"
                      >
                        {node.label}
                      </text>
                    </g>
                  )
                })}
              </svg>
            </div>
          </div>
          <div className="px-4 py-2 border-t border-gray-100 flex justify-between items-center">
            <span className="text-xs text-gray-400">
              节点: {graphNodes.length} | 边: {graphEdges.length}
            </span>
            <span className="text-xs text-gray-400">Mock图谱渲染（后续替换为AntV G6）</span>
          </div>
        </div>

        {/* Right Panel - Node Detail */}
        <div className="col-span-3 bg-white rounded-xl border border-gray-200 flex flex-col overflow-hidden">
          <div className="px-4 py-3 border-b border-gray-100">
            <h3 className="text-sm font-semibold text-gray-700">节点详情</h3>
          </div>
          <div className="flex-1 p-4 overflow-y-auto">
            {selectedNodeData ? (
              <div className="space-y-4">
                <div>
                  <span className="inline-block px-2 py-0.5 text-xs rounded-full bg-blue-50 text-blue-600 mb-2">
                    {selectedNodeData.type === "cluster" ? "岗位聚类" : selectedNodeData.type === "term" ? "技术词" : "里程碑"}
                  </span>
                  <h4 className="text-lg font-semibold text-gray-900">{selectedNodeData.label}</h4>
                </div>
                {selectedNodeData.category && (
                  <div>
                    <p className="text-xs text-gray-500">分类</p>
                    <p className="text-sm text-gray-900">{selectedNodeData.category}</p>
                  </div>
                )}
                <div>
                  <p className="text-xs text-gray-500 mb-2">关联节点 ({relatedEdges.length})</p>
                  <div className="space-y-1.5">
                    {relatedEdges.map((edge, i) => {
                      const otherId = edge.source === selectedNode ? edge.target : edge.source
                      const otherNode = graphNodes.find((n) => n.id === otherId)
                      return (
                        <div key={i} className="flex items-center justify-between py-1 px-2 bg-gray-50 rounded text-sm">
                          <span>{otherNode?.label}</span>
                          <span className="text-xs text-gray-400">{edge.label}</span>
                        </div>
                      )
                    })}
                  </div>
                </div>
                <button className="w-full mt-2 px-3 py-2 bg-blue-600 text-white text-sm rounded-lg hover:bg-blue-700 transition-colors flex items-center justify-center gap-1">
                  查看详情 <ChevronRight className="h-4 w-4" />
                </button>
              </div>
            ) : (
              <div className="h-full flex items-center justify-center text-sm text-gray-400">
                点击左侧节点或图谱查看详情
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}

// Helper functions for mock graph layout
function getNodePosition(id: string): { x: number; y: number } {
  const positions: Record<string, { x: number; y: number }> = {
    c1: { x: 150, y: 100 },
    c2: { x: 350, y: 80 },
    c3: { x: 100, y: 250 },
    c4: { x: 450, y: 200 },
    c5: { x: 280, y: 280 },
    t1: { x: 200, y: 180 },
    t2: { x: 120, y: 160 },
    t3: { x: 220, y: 230 },
    t4: { x: 400, y: 120 },
    t5: { x: 320, y: 150 },
    t6: { x: 500, y: 250 },
    t7: { x: 180, y: 310 },
    t8: { x: 420, y: 60 },
    t9: { x: 80, y: 310 },
    t10: { x: 330, y: 340 },
    m1: { x: 480, y: 100 },
    m2: { x: 400, y: 320 },
  }
  return positions[id] || { x: 300, y: 200 }
}

function getNodeColor(type: string): string {
  switch (type) {
    case "cluster": return "#3b82f6"
    case "term": return "#10b981"
    case "milestone": return "#f59e0b"
    default: return "#6b7280"
  }
}
