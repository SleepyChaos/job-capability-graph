"use client"

import { useState } from "react"
import { mockResumeProfile, mockMatchResult, jobClusters } from "@/lib/mock-data"
import { cn } from "@/lib/utils"
import {
  Upload,
  FileText,
  User,
  MessageCircle,
  Target,
  CheckCircle2,
  XCircle,
  AlertCircle,
  Send,
  BookOpen,
  GraduationCap,
  Briefcase,
  Lightbulb,
} from "lucide-react"

export default function ResumePage() {
  const [activeTab, setActiveTab] = useState<"upload" | "profile" | "chat" | "match">("upload")

  const tabs = [
    { id: "upload" as const, label: "上传简历", icon: Upload },
    { id: "profile" as const, label: "求职者画像", icon: User },
    { id: "chat" as const, label: "对话交互", icon: MessageCircle },
    { id: "match" as const, label: "匹配分析", icon: Target },
  ]

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">简历匹配</h1>
        <p className="text-sm text-gray-500 mt-1">上传简历，AI解析画像，精准匹配目标岗位</p>
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

      {/* Upload Tab */}
      {activeTab === "upload" && (
        <div className="max-w-2xl mx-auto">
          <div className="bg-white rounded-xl border border-gray-200 p-8">
            <div className="border-2 border-dashed border-gray-200 rounded-lg p-16 text-center hover:border-blue-300 transition-colors cursor-pointer">
              <FileText className="h-12 w-12 text-gray-300 mx-auto mb-4" />
              <p className="text-sm text-gray-600 font-medium">拖拽简历文件到此处</p>
              <p className="text-xs text-gray-400 mt-1">支持 PDF / DOC / DOCX / TXT</p>
              <button className="mt-4 px-4 py-2 bg-blue-600 text-white text-sm rounded-lg hover:bg-blue-700">
                选择文件
              </button>
            </div>
            <div className="mt-6">
              <p className="text-sm text-gray-600 mb-2">或直接输入文本：</p>
              <textarea
                className="w-full h-40 px-4 py-3 border border-gray-200 rounded-lg text-sm resize-none focus:outline-none focus:ring-2 focus:ring-blue-500"
                placeholder="粘贴简历内容..."
              />
              <div className="flex justify-end mt-3">
                <button
                  onClick={() => setActiveTab("profile")}
                  className="px-5 py-2.5 bg-blue-600 text-white text-sm rounded-lg hover:bg-blue-700"
                >
                  开始解析
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Profile Tab */}
      {activeTab === "profile" && (
        <div className="grid grid-cols-3 gap-4">
          {/* Structured Data */}
          <div className="col-span-2 space-y-4">
            <div className="bg-white rounded-xl border border-gray-200 p-5">
              <h3 className="text-sm font-semibold text-gray-700 mb-3">基本信息</h3>
              <div className="grid grid-cols-2 gap-4">
                <div><p className="text-xs text-gray-400">求职意向</p><p className="text-sm text-gray-900 font-medium">{mockResumeProfile.targetPosition}</p></div>
                <div><p className="text-xs text-gray-400">工作年限</p><p className="text-sm text-gray-900 font-medium">{mockResumeProfile.totalYears}年</p></div>
                <div><p className="text-xs text-gray-400">学历</p><p className="text-sm text-gray-900 font-medium">{mockResumeProfile.education.degree} · {mockResumeProfile.education.school}</p></div>
                <div><p className="text-xs text-gray-400">专业</p><p className="text-sm text-gray-900 font-medium">{mockResumeProfile.education.major}</p></div>
              </div>
            </div>

            <div className="bg-white rounded-xl border border-gray-200 p-5">
              <h3 className="text-sm font-semibold text-gray-700 mb-3">技术能力</h3>
              <div className="flex flex-wrap gap-2">
                {mockResumeProfile.skills.map((skill) => (
                  <span key={skill.name} className="px-3 py-1.5 text-sm bg-blue-50 text-blue-700 rounded-lg">
                    {skill.name}
                    <span className="ml-1.5 text-xs text-blue-400">{skill.level}</span>
                  </span>
                ))}
              </div>
            </div>

            <div className="bg-white rounded-xl border border-gray-200 p-5">
              <h3 className="text-sm font-semibold text-gray-700 mb-3">工作经历</h3>
              <div className="space-y-3">
                {mockResumeProfile.workExperience.map((exp, i) => (
                  <div key={i} className="flex items-center gap-3 p-3 bg-gray-50 rounded-lg">
                    <Briefcase className="h-4 w-4 text-gray-400" />
                    <div>
                      <p className="text-sm font-medium text-gray-900">{exp.company} · {exp.role}</p>
                      <p className="text-xs text-gray-400">{exp.duration}</p>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>

          {/* Semantic Profile */}
          <div className="space-y-4">
            <div className="bg-white rounded-xl border border-gray-200 p-5">
              <h3 className="text-sm font-semibold text-gray-700 mb-3 flex items-center gap-1.5">
                <Lightbulb className="h-4 w-4 text-amber-500" /> 语义画像
              </h3>
              <div className="space-y-4">
                <div>
                  <p className="text-xs text-gray-400">工作风格</p>
                  <p className="text-sm text-gray-700">{mockResumeProfile.workStyle}</p>
                </div>
                <div>
                  <p className="text-xs text-gray-400">发展方向</p>
                  <p className="text-sm text-gray-700">{mockResumeProfile.developmentDirection}</p>
                </div>
                <div>
                  <p className="text-xs text-gray-400">学习潜力</p>
                  <p className="text-sm text-gray-700">{mockResumeProfile.learningPotential}</p>
                </div>
              </div>
            </div>
            <div className="bg-gradient-to-br from-blue-50 to-purple-50 rounded-xl border border-blue-100 p-5">
              <h3 className="text-sm font-semibold text-blue-800 mb-2">综合优势</h3>
              <p className="text-sm text-blue-700">{mockResumeProfile.strengthSummary}</p>
            </div>
          </div>
        </div>
      )}

      {/* Chat Tab */}
      {activeTab === "chat" && (
        <div className="max-w-3xl mx-auto bg-white rounded-xl border border-gray-200 h-[500px] flex flex-col">
          <div className="flex-1 overflow-y-auto p-6 space-y-4">
            <div className="flex gap-3">
              <div className="w-8 h-8 rounded-full bg-blue-100 flex items-center justify-center shrink-0">
                <span className="text-xs font-bold text-blue-600">AI</span>
              </div>
              <div className="bg-gray-50 rounded-lg rounded-tl-none px-4 py-3 max-w-md">
                <p className="text-sm text-gray-700">我已经解析了您的简历。为了更准确地评估您的能力，想了解一下：您在运动规划方面的具体项目经验是怎样的？是否有使用MoveIt或类似框架的经历？</p>
              </div>
            </div>
            <div className="flex gap-3 justify-end">
              <div className="bg-blue-600 text-white rounded-lg rounded-tr-none px-4 py-3 max-w-md">
                <p className="text-sm">我在之前的项目中接触过MoveIt的基础使用，主要做过机械臂路径规划的demo，但没有深入生产环境使用。</p>
              </div>
              <div className="w-8 h-8 rounded-full bg-gray-200 flex items-center justify-center shrink-0">
                <span className="text-xs font-bold text-gray-600">我</span>
              </div>
            </div>
            <div className="flex gap-3">
              <div className="w-8 h-8 rounded-full bg-blue-100 flex items-center justify-center shrink-0">
                <span className="text-xs font-bold text-blue-600">AI</span>
              </div>
              <div className="bg-gray-50 rounded-lg rounded-tl-none px-4 py-3 max-w-md">
                <p className="text-sm text-gray-700">明白了。我已更新您的画像：运动规划从"了解"调整为"基础实践"。另外想确认一下，您提到对具身智能方向感兴趣，是否有关注过大模型与机器人结合的最新进展？</p>
              </div>
            </div>
          </div>
          <div className="border-t border-gray-100 p-4">
            <div className="flex gap-2">
              <input
                className="flex-1 px-4 py-2.5 border border-gray-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                placeholder="输入回复..."
              />
              <button className="p-2.5 bg-blue-600 text-white rounded-lg hover:bg-blue-700">
                <Send className="h-4 w-4" />
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Match Tab */}
      {activeTab === "match" && (
        <div className="space-y-4">
          {/* Target Selection */}
          <div className="flex items-center gap-3">
            <span className="text-sm text-gray-600">目标岗位：</span>
            <select className="px-3 py-2 border border-gray-200 rounded-lg text-sm bg-white">
              {jobClusters.map((c) => (
                <option key={c.id} value={c.id}>{c.name}</option>
              ))}
            </select>
            <button className="px-4 py-2 bg-blue-600 text-white text-sm rounded-lg hover:bg-blue-700">
              执行匹配
            </button>
          </div>

          {/* Score Overview */}
          <div className="grid grid-cols-6 gap-3">
            {[
              { label: "总分", value: mockMatchResult.overallScore, color: "text-blue-600" },
              { label: "硬性技能", value: mockMatchResult.hardSkillScore, color: "text-green-600" },
              { label: "技能深度", value: mockMatchResult.depthScore, color: "text-purple-600" },
              { label: "经验匹配", value: mockMatchResult.experienceScore, color: "text-amber-600" },
              { label: "软性匹配", value: mockMatchResult.softMatchScore, color: "text-pink-600" },
              { label: "发展潜力", value: mockMatchResult.potentialScore, color: "text-cyan-600" },
            ].map((score) => (
              <div key={score.label} className="bg-white rounded-xl border border-gray-200 p-4 text-center">
                <p className={cn("text-2xl font-bold", score.color)}>{score.value}</p>
                <p className="text-xs text-gray-500 mt-1">{score.label}</p>
              </div>
            ))}
          </div>

          <div className="grid grid-cols-2 gap-4">
            {/* Skills Analysis */}
            <div className="bg-white rounded-xl border border-gray-200 p-5">
              <h3 className="text-sm font-semibold text-gray-700 mb-4">技能分析</h3>
              <div className="space-y-3">
                <div>
                  <p className="text-xs text-green-600 font-medium mb-1.5 flex items-center gap-1"><CheckCircle2 className="h-3.5 w-3.5" /> 已匹配</p>
                  <div className="flex flex-wrap gap-1.5">
                    {mockMatchResult.matchedSkills.map((s) => (
                      <span key={s} className="px-2 py-0.5 text-xs bg-green-50 text-green-700 rounded">{s}</span>
                    ))}
                  </div>
                </div>
                <div>
                  <p className="text-xs text-red-600 font-medium mb-1.5 flex items-center gap-1"><XCircle className="h-3.5 w-3.5" /> 缺失</p>
                  <div className="flex flex-wrap gap-1.5">
                    {mockMatchResult.missingSkills.map((s) => (
                      <span key={s} className="px-2 py-0.5 text-xs bg-red-50 text-red-700 rounded">{s}</span>
                    ))}
                  </div>
                </div>
                <div>
                  <p className="text-xs text-amber-600 font-medium mb-1.5 flex items-center gap-1"><AlertCircle className="h-3.5 w-3.5" /> 不足</p>
                  <div className="flex flex-wrap gap-1.5">
                    {mockMatchResult.insufficientSkills.map((s) => (
                      <span key={s} className="px-2 py-0.5 text-xs bg-amber-50 text-amber-700 rounded">{s}</span>
                    ))}
                  </div>
                </div>
              </div>
            </div>

            {/* Improvement Plan */}
            <div className="bg-white rounded-xl border border-gray-200 p-5">
              <h3 className="text-sm font-semibold text-gray-700 mb-4 flex items-center gap-1.5">
                <GraduationCap className="h-4 w-4 text-blue-500" /> 提升规划
              </h3>
              <div className="space-y-4">
                <div>
                  <p className="text-xs font-medium text-blue-600 mb-1">短期（1-3月）</p>
                  <ul className="space-y-1">
                    {mockMatchResult.improvementPlan.shortTerm.map((item, i) => (
                      <li key={i} className="text-sm text-gray-600 flex items-start gap-1.5">
                        <BookOpen className="h-3.5 w-3.5 text-gray-400 mt-0.5 shrink-0" /> {item}
                      </li>
                    ))}
                  </ul>
                </div>
                <div>
                  <p className="text-xs font-medium text-purple-600 mb-1">中期（3-6月）</p>
                  <ul className="space-y-1">
                    {mockMatchResult.improvementPlan.midTerm.map((item, i) => (
                      <li key={i} className="text-sm text-gray-600 flex items-start gap-1.5">
                        <BookOpen className="h-3.5 w-3.5 text-gray-400 mt-0.5 shrink-0" /> {item}
                      </li>
                    ))}
                  </ul>
                </div>
                <div>
                  <p className="text-xs font-medium text-green-600 mb-1">长期（6-12月）</p>
                  <ul className="space-y-1">
                    {mockMatchResult.improvementPlan.longTerm.map((item, i) => (
                      <li key={i} className="text-sm text-gray-600 flex items-start gap-1.5">
                        <BookOpen className="h-3.5 w-3.5 text-gray-400 mt-0.5 shrink-0" /> {item}
                      </li>
                    ))}
                  </ul>
                </div>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
