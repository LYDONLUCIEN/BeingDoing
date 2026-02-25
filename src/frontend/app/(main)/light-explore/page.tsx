'use client';

import { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { apiClient } from '@/lib/api/client';
import MessageContent from '@/components/explore/MessageContent';
import SurveyForm from '@/components/survey/SurveyForm';
import { surveyApi } from '@/lib/api/survey';
import type { SurveyData } from '@/lib/survey/schema';

interface SimpleMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
}

const PHASES: { key: 'values' | 'strengths' | 'interests_goals'; label: string }[] = [
  { key: 'values', label: '重要的事（价值观）' },
  { key: 'strengths', label: '擅长的事（才能）' },
  { key: 'interests_goals', label: '喜欢的事 & 目标' },
];

export default function LightExplorePage() {
  const router = useRouter();
  const [activationCode, setActivationCode] = useState('');
  const [activationInfo, setActivationInfo] = useState<any | null>(null);
  const [activating, setActivating] = useState(false);
  const [activationError, setActivationError] = useState<string | null>(null);

  const [activePhase, setActivePhase] = useState<'values' | 'strengths' | 'interests_goals'>('values');
  const [messagesByPhase, setMessagesByPhase] = useState<
    Record<'values' | 'strengths' | 'interests_goals', SimpleMessage[]>
  >({
    values: [],
    strengths: [],
    interests_goals: [],
  });
  const [input, setInput] = useState('');
  const [sending, setSending] = useState(false);
  const [chatError, setChatError] = useState<string | null>(null);
  const [streamAbortController, setStreamAbortController] = useState<AbortController | null>(null);

  // 调研问卷：激活后有数据则跳过，无数据则先展示问卷
  const [surveyData, setSurveyData] = useState<SurveyData | null | undefined>(undefined);
  const [surveyCompleted, setSurveyCompleted] = useState(false);
  const [surveyLoading, setSurveyLoading] = useState(false);

  const currentMessages = messagesByPhase[activePhase];

  // 激活成功后加载调研数据
  useEffect(() => {
    if (!activationInfo?.activation_code) return;
    let cancelled = false;
    (async () => {
      try {
        const res = await surveyApi.getForActivation(activationInfo.activation_code);
        if (!cancelled && res.data?.survey_data) {
          const data = res.data.survey_data;
          const hasData = Object.keys(data).some((k) => {
            const v = (data as Record<string, unknown>)[k];
            return v !== undefined && v !== null && v !== '' && (Array.isArray(v) ? v.length > 0 : true);
          });
          if (hasData) setSurveyCompleted(true);
          setSurveyData(data);
        } else {
          setSurveyData({});
        }
      } catch {
        if (!cancelled) setSurveyData({});
      }
    })();
    return () => { cancelled = true; };
  }, [activationInfo?.activation_code]);

  const loadPhaseHistoryOrInit = async (
    code: string,
    phase: 'values' | 'strengths' | 'interests_goals'
  ) => {
    try {
      // 先尝试加载历史
      const historyRes = await apiClient.get(`/simple-chat/history`, {
        params: {
          activation_code: code,
          phase,
        },
      });
      const history: any[] = historyRes.data.messages ?? [];
      if (history.length > 0) {
        setMessagesByPhase((prev) => ({
          ...prev,
          [phase]: history.map((m, idx) => ({
            id: `${phase}_${idx}_${m.id ?? idx}`,
            role: (m.role as 'user' | 'assistant') || 'assistant',
            content: m.content ?? '',
          })),
        }));
        return;
      }

      // 没有历史，则初始化首轮引导问题
      const initRes = await apiClient.post('/simple-chat/init', {
        activation_code: code,
        phase,
      });
      const initMsgs: any[] = initRes.data.messages ?? [];
      if (initMsgs.length > 0) {
        setMessagesByPhase((prev) => ({
          ...prev,
          [phase]: initMsgs.map((m, idx) => ({
            id: `${phase}_init_${idx}`,
            role: (m.role as 'user' | 'assistant') || 'assistant',
            content: m.content ?? '',
          })),
        }));
      }
    } catch (err) {
      // 静默失败，保持当前状态
    }
  };

  const handleActivate = async () => {
    setActivationError(null);
    setActivating(true);
    try {
      const res = await apiClient.post('/simple-auth/activate', {
        code: activationCode.trim(),
      });
      setActivationInfo(res.data);
      // 每次切换激活码时清空当前对话（三个阶段）
      setMessagesByPhase({
        values: [],
        strengths: [],
        interests_goals: [],
      });

      const code = res.data.activation_code as string;
      setSurveyCompleted(false);
      setSurveyData(undefined);
      // 激活成功后，分别为三个阶段加载历史或生成首轮引导问题
      await Promise.all(
        PHASES.map((p) => loadPhaseHistoryOrInit(code, p.key))
      );
    } catch (err: any) {
      const detail =
        err?.response?.data?.detail ||
        err?.response?.data?.message ||
        '激活失败，请检查激活码是否正确';
      setActivationError(String(detail));
      setActivationInfo(null);
    } finally {
      setActivating(false);
    }
  };

  const handleSend = async () => {
    if (!activationInfo?.activation_code) {
      setChatError('请先输入激活码并完成激活。');
      return;
    }
    if (!input.trim()) return;

    const userMsg: SimpleMessage = {
      id: `u_${Date.now()}`,
      role: 'user',
      content: input.trim(),
    };
    setMessagesByPhase((prev) => ({
      ...prev,
      [activePhase]: [...prev[activePhase], userMsg],
    }));
    setInput('');
    setChatError(null);
    // 在当前阶段插入一个空的 assistant 占位，用于流式填充
    const assistantId = `a_${Date.now()}`;
    setMessagesByPhase((prev) => ({
      ...prev,
      [activePhase]: [
        ...prev[activePhase],
        {
          id: assistantId,
          role: 'assistant',
          content: '',
        },
      ],
    }));
    setSending(true);

    const controller = new AbortController();
    setStreamAbortController(controller);

    try {
      const baseURL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
      const url = `${baseURL}/api/v1/simple-chat/message/stream`;
      const res = await fetch(url, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          activation_code: activationInfo.activation_code,
          message: userMsg.content,
          phase: activePhase,
        }),
        signal: controller.signal,
      });
      if (!res.body) {
        throw new Error(res.statusText || '流式接口返回为空');
      }
      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';
      let fullReply = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() || '';
        for (const line of lines) {
          if (!line.startsWith('data: ')) continue;
          try {
            const payload = JSON.parse(line.slice(6));
            if (payload.error) {
              setChatError(String(payload.error));
              reader.cancel();
              break;
            }
            if (payload.chunk) {
              const chunk: string = payload.chunk;
              fullReply += chunk;
              // 追加到当前阶段最后一条 assistant 消息上
              setMessagesByPhase((prev) => {
                const list = prev[activePhase];
                const updated = list.map((m) =>
                  m.id === assistantId
                    ? { ...m, content: (m.content || '') + chunk }
                    : m
                );
                return { ...prev, [activePhase]: updated };
              });
            }
            if (payload.done && payload.response != null) {
              fullReply = payload.response;
              setMessagesByPhase((prev) => {
                const list = prev[activePhase];
                const updated = list.map((m) =>
                  m.id === assistantId ? { ...m, content: fullReply } : m
                );
                return { ...prev, [activePhase]: updated };
              });
              break;
            }
          } catch {
            // ignore parse errors
          }
        }
      }
    } catch (err: any) {
      if (err?.name === 'AbortError') {
        // 用户中断，不视为错误
      } else {
        const msg = err?.message || '流式发送失败，请稍后重试';
        setChatError(msg);
      }
    } finally {
      setSending(false);
      setStreamAbortController(null);
    }
  };

  return (
    <div className="min-h-screen bg-gradient-to-b from-slate-900 via-slate-900 to-slate-800 text-white">
      <div className="max-w-5xl mx-auto px-4 pt-20 pb-8 space-y-8">
        {/* 头部介绍 */}
        <section className="space-y-3">
          <h1 className="text-3xl md:text-4xl font-bold">快速探索模式</h1>
          <p className="text-sm text-white/60">
            这是基于激活码的简化体验版本。你可以在不注册账号的情况下，直接开始一段关于「喜欢、擅长、价值观与目标」的深度对话。
          </p>
          <p className="text-xs text-white/40">
            提示：激活码用于区分不同会话，在有效期内，你可以多次回来继续这段对话；过期后，历史记录仍会保留，用于回放或导出。
          </p>
        </section>

        {/* 激活码区域 */}
        <section className="rounded-xl border border-white/10 bg-white/5 p-4 md:p-5 space-y-4">
          <div className="flex flex-col md:flex-row md:items-center gap-3">
            <div className="flex-1">
              <label className="block text-sm text-white/70 mb-1">激活码</label>
              <input
                type="text"
                value={activationCode}
                onChange={(e) => setActivationCode(e.target.value)}
                placeholder="请输入你获得的激活码"
                className="w-full rounded-md border border-white/10 bg-slate-900/60 px-3 py-2 text-sm outline-none focus:border-primary-400"
              />
            </div>
            <button
              type="button"
              onClick={handleActivate}
              disabled={activating || !activationCode.trim()}
              className="inline-flex items-center justify-center rounded-md bg-primary-500 hover:bg-primary-400 disabled:bg-primary-500/40 px-4 py-2 text-sm font-medium transition-colors"
            >
              {activating ? '激活中…' : '激活会话'}
            </button>
          </div>
          {activationError && <p className="text-sm text-rose-400">{activationError}</p>}
          {activationInfo && (
            <div className="text-xs text-white/50 space-y-1">
              <p>
                当前模式：<span className="font-medium text-primary-300">{activationInfo.mode}</span>
              </p>
              <p>
                状态：<span className="font-medium text-emerald-300">{activationInfo.status}</span>
              </p>
            </div>
          )}
        </section>

        {/* 调研问卷加载中 */}
        {activationInfo && surveyData === undefined && (
          <section className="rounded-xl border border-white/10 bg-slate-900/60 p-8 text-center text-white/60">
            加载调研问卷…
          </section>
        )}

        {/* 调研问卷（激活后、未完成时展示） */}
        {activationInfo && surveyData !== undefined && !surveyCompleted && (
          <section className="rounded-xl border border-white/10 bg-slate-900/60 p-4 md:p-5">
            <h2 className="text-lg font-semibold text-white mb-2">调研问卷</h2>
            <p className="text-sm text-white/60 mb-4">
              请填写以下基本信息（选填），便于我们更好地为你提供咨询服务。填写后可跳过直接开始对话。
            </p>
            <SurveyForm
              initialData={surveyData || {}}
              loading={surveyLoading}
              submitLabel="提交并开始对话"
              showSkip
              onSubmit={async (data: SurveyData) => {
                setSurveyLoading(true);
                try {
                  await surveyApi.saveForActivation(activationInfo.activation_code, data);
                  setSurveyCompleted(true);
                } catch (e) {
                  setChatError((e as Error)?.message || '保存失败');
                } finally {
                  setSurveyLoading(false);
                }
              }}
              onSkip={async () => {
                setSurveyLoading(true);
                try {
                  await surveyApi.saveForActivation(activationInfo.activation_code, {});
                  setSurveyCompleted(true);
                } catch {
                  setSurveyCompleted(true);
                } finally {
                  setSurveyLoading(false);
                }
              }}
            />
          </section>
        )}

        {/* 对话区域（激活且调研完成时展示） */}
        {activationInfo && surveyCompleted && (
        <section className="rounded-xl border border-white/10 bg-slate-900/60 p-4 md:p-5 flex flex-col min-h-[380px]">
          {/* 阶段 tabs */}
          <div className="flex gap-2 mb-3 border-b border-white/10 pb-2">
            {PHASES.map((p) => (
              <button
                key={p.key}
                type="button"
                onClick={async () => {
                  setActivePhase(p.key);
                  setChatError(null);
                  if (activationInfo?.activation_code && messagesByPhase[p.key].length === 0) {
                    await loadPhaseHistoryOrInit(activationInfo.activation_code, p.key);
                  }
                }}
                className={`px-3 py-1.5 rounded-md text-xs font-medium transition-colors ${
                  activePhase === p.key
                    ? 'bg-primary-500 text-white'
                    : 'bg-slate-800 text-white/70 hover:bg-slate-700'
                }`}
              >
                {p.label}
              </button>
            ))}
          </div>
          <div className="flex-1 overflow-y-auto space-y-3 pr-1 mb-3">
            {currentMessages.length === 0 && (
              <p className="text-sm text-white/50">
                （{PHASES.find((p) => p.key === activePhase)?.label}）的第一轮引导问题会自动出现，请先阅读并回答；
                激活码有效期内，你可以在三个阶段之间自由切换，历史对话会被完整保留。
              </p>
            )}
            {currentMessages.map((m) => (
              <div
                key={m.id}
                className={`flex ${
                  m.role === 'user' ? 'justify-end' : 'justify-start'
                }`}
              >
                <div
                  className={`max-w-[80%] rounded-lg px-3 py-2 text-sm leading-relaxed overflow-x-auto ${
                    m.role === 'user'
                      ? 'bg-primary-500 text-white'
                      : 'bg-slate-800 text-white/90'
                  } ${m.role === 'assistant' ? '' : 'whitespace-pre-wrap'}`}
                >
                  {m.role === 'assistant' ? (
                    <MessageContent content={m.content} markdown />
                  ) : (
                    m.content
                  )}
                </div>
              </div>
            ))}
          </div>
          {chatError && <p className="text-xs text-rose-400 mb-2">{chatError}</p>}
          <div className="flex items-center gap-2">
            <textarea
              rows={1}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder="和智能向导聊聊你现在的想法吧……"
              className="flex-1 resize-none rounded-md border border-white/10 bg-slate-900/80 px-3 py-2 text-sm outline-none focus:border-primary-400"
              onKeyDown={(e) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                  e.preventDefault();
                  if (!sending) handleSend();
                }
              }}
            />
            <button
              type="button"
              onClick={handleSend}
              disabled={sending || !input.trim()}
              className="inline-flex items-center justify-center rounded-md bg-primary-500 hover:bg-primary-400 disabled:bg-primary-500/40 px-4 py-2 text-sm font-medium transition-colors"
            >
              {sending ? '发送中…' : '发送'}
            </button>
          </div>
        </section>
        )}

        {/* 未激活时显示占位提示 */}
        {!activationInfo && (
          <section className="rounded-xl border border-white/10 bg-slate-900/60 p-8 text-center text-white/50">
            请先输入激活码并完成激活，激活后需先填写调研问卷，然后即可开始对话。
          </section>
        )}

        {/* 额外导航提示 */}
        <section className="text-xs text-white/40 flex flex-col md:flex-row md:items-center justify-between gap-2 pb-8">
          <p>
            想了解背后的理论和方法？你可以在顶部导航中访问「理论介绍」「关于我们」等页面。
          </p>
          <button
            type="button"
            onClick={() => router.push('/about')}
            className="underline underline-offset-4 hover:text-white/80 transition-colors"
          >
            了解项目背景 →
          </button>
        </section>
      </div>
    </div>
  );
}

