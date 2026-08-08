'use client';

// 设置页：LLM 接入配置（DeepSeek API Key / 接口地址 / 模型）
// Key 保存后内存立即生效并持久化到项目根 .env（不入代码库）；接口只返回掩码

import React, { useEffect, useState } from 'react';
import { Settings, KeyRound, CheckCircle2, XCircle, Loader2, Eye, EyeOff, PlugZap } from 'lucide-react';
import { fetchLlmSettings, saveLlmSettings, testLlmConnection, type LlmSettings } from '@/lib/api';

export default function SettingsPage() {
  const [settings, setSettings] = useState<LlmSettings | null>(null);
  const [apiKey, setApiKey] = useState('');
  const [baseUrl, setBaseUrl] = useState('https://api.deepseek.com/v1');
  const [model, setModel] = useState('deepseek-chat');
  const [showKey, setShowKey] = useState(false);
  const [busy, setBusy] = useState(false);
  const [testing, setTesting] = useState(false);
  const [message, setMessage] = useState<{ ok: boolean; text: string } | null>(null);

  useEffect(() => {
    fetchLlmSettings()
      .then(s => {
        setSettings(s);
        setBaseUrl(s.baseUrl);
        setModel(s.model);
      })
      .catch(() => setMessage({ ok: false, text: '无法读取设置，请确认后端已启动' }));
  }, []);

  const doSave = async () => {
    setBusy(true);
    setMessage(null);
    try {
      const saved = await saveLlmSettings({
        apiKey: apiKey.trim() || undefined,
        baseUrl: baseUrl.trim() || undefined,
        model: model.trim() || undefined,
      });
      setSettings(saved);
      setApiKey('');
      setMessage({ ok: true, text: '配置已保存并立即生效' });
    } catch (e) {
      setMessage({ ok: false, text: e instanceof Error ? e.message : '保存失败' });
    } finally {
      setBusy(false);
    }
  };

  const doTest = async () => {
    setTesting(true);
    setMessage(null);
    try {
      const r = await testLlmConnection();
      setMessage(
        r.ok
          ? { ok: true, text: `连接成功（模型 ${r.model}）：${r.reply}` }
          : { ok: false, text: r.error || '连接失败' }
      );
    } catch (e) {
      setMessage({ ok: false, text: e instanceof Error ? e.message : '测试失败' });
    } finally {
      setTesting(false);
    }
  };

  return (
    <div className="pt-14 min-h-screen bg-slate-50">
      <div className="max-w-2xl mx-auto px-6 py-8 space-y-5">
        <div>
          <h1 className="text-xl font-bold text-slate-800 flex items-center gap-2">
            <Settings className="w-5 h-5 text-blue-600" /> 系统设置
          </h1>
          <p className="text-sm text-slate-500 mt-1">
            LLM 接入配置影响：岗位发现的 LLM 动态任务生成与岗位命名、岗位定义生成、简历结构化提取
          </p>
        </div>

        {/* 当前状态卡 */}
        <div className="bg-white rounded-xl border border-slate-200 p-5">
          <div className="flex items-center justify-between">
            <p className="text-sm font-medium text-slate-700 flex items-center gap-2">
              <KeyRound className="w-4 h-4 text-slate-400" /> 当前 LLM 状态
            </p>
            {settings && (
              <span
                className={`px-2.5 py-1 rounded-full text-xs font-medium inline-flex items-center gap-1 ${
                  settings.configured
                    ? 'bg-emerald-50 text-emerald-700'
                    : 'bg-amber-50 text-amber-700'
                }`}
              >
                {settings.configured ? <CheckCircle2 className="w-3.5 h-3.5" /> : <XCircle className="w-3.5 h-3.5" />}
                {settings.configured ? '已配置 Key' : '未配置 Key（LLM 功能自动降级为规则模式）'}
              </span>
            )}
          </div>
          {settings && (
            <div className="mt-3 grid grid-cols-3 gap-3 text-sm">
              <div className="bg-slate-50 rounded-lg px-3 py-2">
                <p className="text-xs text-slate-400 mb-0.5">API Key</p>
                <p className="font-mono text-slate-700">{settings.keyMasked || '—'}</p>
              </div>
              <div className="bg-slate-50 rounded-lg px-3 py-2">
                <p className="text-xs text-slate-400 mb-0.5">接口地址</p>
                <p className="text-slate-700 truncate">{settings.baseUrl}</p>
              </div>
              <div className="bg-slate-50 rounded-lg px-3 py-2">
                <p className="text-xs text-slate-400 mb-0.5">模型</p>
                <p className="text-slate-700">{settings.model}</p>
              </div>
            </div>
          )}
        </div>

        {/* 配置表单 */}
        <div className="bg-white rounded-xl border border-slate-200 p-5 space-y-4">
          <div>
            <label className="text-sm text-slate-600 mb-1.5 block">DeepSeek API Key</label>
            <div className="relative">
              <input
                type={showKey ? 'text' : 'password'}
                value={apiKey}
                onChange={e => setApiKey(e.target.value)}
                placeholder={settings?.keyMasked ? `已配置（${settings.keyMasked}），留空则保持不变` : 'sk-...'}
                className="w-full h-10 px-3 pr-10 rounded-lg border border-slate-200 text-sm font-mono focus:outline-none focus:border-blue-400"
              />
              <button
                onClick={() => setShowKey(v => !v)}
                className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-600"
                type="button"
              >
                {showKey ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
              </button>
            </div>
            <p className="text-xs text-slate-400 mt-1">Key 仅保存于服务端 .env 文件（不入代码库），接口传输与展示均为掩码</p>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="text-sm text-slate-600 mb-1.5 block">接口地址（OpenAI 兼容）</label>
              <input
                value={baseUrl}
                onChange={e => setBaseUrl(e.target.value)}
                className="w-full h-10 px-3 rounded-lg border border-slate-200 text-sm focus:outline-none focus:border-blue-400"
              />
            </div>
            <div>
              <label className="text-sm text-slate-600 mb-1.5 block">模型</label>
              <input
                value={model}
                onChange={e => setModel(e.target.value)}
                className="w-full h-10 px-3 rounded-lg border border-slate-200 text-sm focus:outline-none focus:border-blue-400"
              />
            </div>
          </div>

          <div className="flex gap-2 pt-1">
            <button
              onClick={doSave}
              disabled={busy}
              className="px-4 h-9 rounded-lg bg-blue-600 text-white text-sm font-medium hover:bg-blue-700 disabled:opacity-50 inline-flex items-center gap-1.5"
            >
              {busy ? <Loader2 className="w-4 h-4 animate-spin" /> : <CheckCircle2 className="w-4 h-4" />}
              保存配置
            </button>
            <button
              onClick={doTest}
              disabled={testing}
              className="px-4 h-9 rounded-lg border border-slate-200 text-sm text-slate-700 hover:bg-slate-50 disabled:opacity-50 inline-flex items-center gap-1.5"
            >
              {testing ? <Loader2 className="w-4 h-4 animate-spin" /> : <PlugZap className="w-4 h-4" />}
              测试连接
            </button>
          </div>

          {message && (
            <div
              className={`rounded-lg px-3.5 py-2.5 text-sm flex items-start gap-2 ${
                message.ok ? 'bg-emerald-50 text-emerald-700' : 'bg-red-50 text-red-600'
              }`}
            >
              {message.ok ? <CheckCircle2 className="w-4 h-4 shrink-0 mt-0.5" /> : <XCircle className="w-4 h-4 shrink-0 mt-0.5" />}
              {message.text}
            </div>
          )}
        </div>

        {/* 降级说明 */}
        <div className="rounded-lg border border-blue-100 bg-blue-50/60 px-4 py-3 text-xs leading-relaxed text-blue-600">
          未配置 Key 或调用失败时，系统自动降级为规则模式（知识库任务 + 规则拼装岗位名），不会伪造 LLM 结果；
          所有 LLM 生成内容仍受「未审核不入正式表」约束，需在数据治理页人工审核后生效。
        </div>
      </div>
    </div>
  );
}
