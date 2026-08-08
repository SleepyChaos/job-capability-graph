"use client"

import { useState } from "react"
import { graphNodes, graphEdges, techTerms, jobClusters } from "@/lib/mock-data"
import { cn } from "@/lib/utils"
import { Search, ZoomIn, ZoomOut, Maximize2, Download } from "lucide-react"

export default function GraphPage() {
  const [selectedCategory, setSelectedCategory] = useState<string>("all")
  const [selectedLevel, setSelectedLevel] = useState<string>("all")

  const categories = ["all", ...new Set(techTerms.map((t) => t.category))]
  const levels = ["all", "basic", "intermediate", "advanced", "expert"]
  const levelLabels: Record<string, string> = { all: "全部", basic: "初级", intermediate: "中级", advanced: "高级", expert: "专家" }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">能力图谱</h1>
          <p className="text-sm text-gray-500 mt-1">全景可视化展示岗位与能力的关联关系</p>
        </div>
        <div className="flex items-center gap-2">
          <button className="p-2 rounded-lg border border-gray-200 hover:bg-gray-50"><ZoomIn className="h-4 w-4" /></button>
          <button className="p-2 rounded-lg border border-gray-200 hover:bg-gray-50"><ZoomOut className="h-4 w-4" /></button>
          <button className="p-2 rounded-lg border border-gray-200 hover:bg-gray-50"><Maximize2 className="h-4 w-4" /></button>
          <button className="p-2 rounded-lg border border-gray-200 hover:bg-gray-50"><Download className="h-4 w-4" /></button>
        </div>
      </div>

      {/* Filters */}
      <div className="flex items-center gap-4">
        <div className="flex items-center gap-2">
          <span className="text-sm text-gray-600">技术栈：</span>
          <div className="flex gap-1">
            {categories.slice(0, 6).map((cat) => (
              <button
                key={cat}
                onClick={() => setSelectedCategory(cat)}
                className={cn(
                  "px-3 py-1 text-xs rounded-full transition-colors",
                  selectedCategory === cat ? "bg-blue-600 text-white" : "bg-gray-100 text-gray-600 hover:bg-gray-200"
                )}
              >
                {cat === "all" ? "全部" : cat}
              </button>
            ))}
          </div>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-sm text-gray-600">级别：</span>
          <div className="flex gap-1">
            {levels.map((level) => (
              <button
                key={level}
                onClick={() => setSelectedLevel(level)}
                className={cn(
                  "px-3 py-1 text-xs rounded-full transition-colors",
                  selectedLevel === level ? "bg-purple-600 text-white" : "bg-gray-100 text-gray-600 hover:bg-gray-200"
                )}
              >
                {levelLabels[level]}
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* Graph Area */}
      <div className="bg-white rounded-xl border border-gray-200 h-[600px] relative overflow-hidden">
        <svg className="w-full h-full" viewBox="0 0 800 600">
          {/* Edges */}
          {graphEdges.map((edge, i) => {
            const sourcePos = getGraphPosition(edge.source)
            const targetPos = getGraphPosition(edge.target)
            return (
              <line
                key={i}
                x1={sourcePos.x} y1={sourcePos.y}
                x2={targetPos.x} y2={targetPos.y}
                stroke="#d1d5db"
                strokeWidth={(edge.weight || 1) * 0.8}
                opacity={0.6}
              />
            )
          })}
          {/* Nodes */}
          {graphNodes.map((node) => {
            const pos = getGraphPosition(node.id)
            const color = node.type === "cluster" ? "#3b82f6" : node.type === "term" ? "#10b981" : "#f59e0b"
            return (
              <g key={node.id} className="cursor-pointer hover:opacity-80">
                <circle cx={pos.x} cy={pos.y} r={(node.size || 15) * 1.2} fill={color} opacity={0.8} />
                <text x={pos.x} y={pos.y + (node.size || 15) * 1.2 + 16} textAnchor="middle" fontSize="11" fill="#374151">
                  {node.label}
                </text>
              </g>
            )
          })}
        </svg>

        {/* Legend */}
        <div className="absolute bottom-4 left-4 bg-white/90 backdrop-blur rounded-lg p-3 border border-gray-100">
          <div className="flex items-center gap-4 text-xs">
            <div className="flex items-center gap-1.5">
              <div className="w-3 h-3 rounded-full bg-blue-500" />
              <span>岗位聚类</span>
            </div>
            <div className="flex items-center gap-1.5">
              <div className="w-3 h-3 rounded-full bg-green-500" />
              <span>技术词</span>
            </div>
            <div className="flex items-center gap-1.5">
              <div className="w-3 h-3 rounded-full bg-amber-500" />
              <span>里程碑</span>
            </div>
          </div>
        </div>

        {/* Search */}
        <div className="absolute top-4 right-4">
          <div className="flex items-center gap-2 bg-white border border-gray-200 rounded-lg px-3 py-2 shadow-sm">
            <Search className="h-4 w-4 text-gray-400" />
            <input className="text-sm outline-none w-40" placeholder="搜索节点..." />
          </div>
        </div>
      </div>
    </div>
  )
}

function getGraphPosition(id: string): { x: number; y: number } {
  const positions: Record<string, { x: number; y: number }> = {
    c1: { x: 200, y: 150 }, c2: { x: 480, y: 120 }, c3: { x: 140, y: 350 },
    c4: { x: 620, y: 280 }, c5: { x: 380, y: 400 },
    t1: { x: 280, y: 250 }, t2: { x: 160, y: 230 }, t3: { x: 300, y: 330 },
    t4: { x: 540, y: 170 }, t5: { x: 430, y: 200 }, t6: { x: 680, y: 350 },
    t7: { x: 240, y: 440 }, t8: { x: 570, y: 90 }, t9: { x: 100, y: 440 },
    t10: { x: 440, y: 490 }, m1: { x: 650, y: 140 }, m2: { x: 540, y: 450 },
  }
  return positions[id] || { x: 400, y: 300 }
}
