'use client';

import { useState, useEffect, useRef, useCallback } from 'react';
import { useRouter, useParams } from 'next/navigation';
import { motion } from 'framer-motion';
import { Lock, CheckCircle2, ChevronRight, ChevronDown, ArrowUp, Square, Copy } from 'lucide-react';
import Link from 'next/link';
import FlowAiMessage from '@/components/explore/FlowAiMessage';
import { copyToClipboard } from '@/lib/utils/clipboard';
import { apiClient } from '@/lib/api/client';
import {
  PHASES,
  loadSession,
  saveSession,
  unlockNextPhase,
  getLastActivationCode,
  type PhaseKey,
  type ExploreSession,
} from '@/lib/explore/session';

interface SimpleMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
}

// Phase metadata (colors follow design_principle.md: values=蓝, strengths=绿, interests=红, purpose=黄)
const PHASE_META: Record<PhaseKey, {
  color: string;
  bg: string;
  bgLight: string;
  ring: string;
  desc: string;
  hint: string;
  unlockHint: string;
}> = {
  values: {
    color: 'text-bd-phase-values',
    bg: 'border border-bd-phase-values',
    bgLight: 'bg-bd-phase-values/10',
    ring: 'ring-bd-phase-values/50',
    desc: '探索你最深层的信念。什么对你最重要？哪些原则是你绝不妥协的？',
    hint: '这一步帮你发现5个核心价值观关键词。',
    unlockHint: '',
  },
  strengths: {
    color: 'text-bd-phase-strengths',
    bg: 'border border-bd-phase-strengths',
    bgLight: 'bg-bd-phase-strengths/10',
    ring: 'ring-bd-phase-strengths/50',
    desc: '探索你的天赋与禀赋。有些事你做起来不费力，却让别人惊叹。',
    hint: '这一步帮你发现10件真正擅长的事。',
    unlockHint: '完成「信念」探索后解锁',
  },
  interests: {
    color: 'text-bd-phase-interests',
    bg: 'border border-bd-phase-interests',
    bgLight: 'bg-bd-phase-interests/10',
    ring: 'ring-bd-phase-interests/50',
    desc: '探索你的热忱。什么话题让你停不下来？什么场景让时间消失？',
    hint: '这一步帮你找到真正让你忘我的事。',
    unlockHint: '完成「禀赋」探索后解锁',
  },
  purpose: {
    color: 'text-bd-phase-purpose',
    bg: 'border border-bd-phase-purpose',
    bgLight: 'bg-bd-phase-purpose/10',
    ring: 'ring-bd-phase-purpose/50',
    desc: '探索你的使命。你想为谁而做？你希望在这个世界留下什么？',
    hint: '这一步帮你找到职业背后更深的驱动力。',
    unlockHint: '完成「热忱」探索后解锁',
  },
};

// Map new phase keys to backend phase keys
const BACKEND_PHASE: Record<PhaseKey, string> = {
  values: 'values',
  strengths: 'strengths',
  interests: 'interests_goals',
  purpose: 'purpose',
};

export default function ChatPhasePage() {
  const router = useRouter();
  const params = useParams();
  const phaseParam = params.phase as string;

  const [session, setSession] = useState<ExploreSession | null>(null);
  const [activationCode, setActivationCode] = useState<string | null>(null);
  const [messages, setMessages] = useState<SimpleMessage[]>([]);
  const [input, setInput] = useState('');
  const [sending, setSending] = useState(false);
  const [initLoading, setInitLoading] = useState(true);
  const [chatError, setChatError] = useState<string | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const chatBodyRef = useRef<HTMLDivElement>(null);
  const [showScrollBottom, setShowScrollBottom] = useState(false);
  const abortControllerRef = useRef<AbortController | null>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  const phase = phaseParam as PhaseKey;
  const phaseMeta = PHASE_META[phase];
  const phaseInfo = PHASES.find((p) => p.key === phase);

  // Redirect if invalid phase
  useEffect(() => {
    if (!PHASES.find((p) => p.key === phase)) {
      router.replace('/explore/activate');
    }
  }, [phase, router]);

  // Load session and check access
  useEffect(() => {
    const code = getLastActivationCode();
    if (!code) {
      router.replace('/explore/activate');
      return;
    }
    setActivationCode(code);
    const s = loadSession(code);
    setSession(s);

    if (!s.surveyCompleted) {
      router.replace('/explore/survey');
      return;
    }
    if (!s.unlockedPhases.includes(phase)) {
      // Redirect to the latest unlocked phase
      router.replace(`/explore/chat/${s.currentPhase}`);
      return;
    }
  }, [phase, router]);

  // Load history or init for current phase
  useEffect(() => {
    if (!activationCode || !phase) return;
    let cancelled = false;
    setInitLoading(true);

    (async () => {
      try {
        const backendPhase = BACKEND_PHASE[phase];
        const historyRes = await apiClient.get('/simple-chat/history', {
          params: { activation_code: activationCode, phase: backendPhase },
        });
        const history: any[] = historyRes.data.messages ?? [];
        if (!cancelled && history.length > 0) {
          setMessages(history.map((m, i) => ({
            id: `h_${i}_${m.id ?? i}`,
            role: m.role as 'user' | 'assistant',
            content: m.content ?? '',
          })));
          return;
        }

        // No history: init
        const initRes = await apiClient.post('/simple-chat/init', {
          activation_code: activationCode,
          phase: backendPhase,
        });
        const initMsgs: any[] = initRes.data.messages ?? [];
        if (!cancelled && initMsgs.length > 0) {
          setMessages(initMsgs.map((m, i) => ({
            id: `init_${i}`,
            role: m.role as 'user' | 'assistant',
            content: m.content ?? '',
          })));
        }
      } catch (err) {
        // silent
      } finally {
        if (!cancelled) setInitLoading(false);
      }
    })();

    return () => { cancelled = true; };
  }, [activationCode, phase]);

  // Auto-scroll
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const checkScrollPosition = useCallback(() => {
    const el = chatBodyRef.current;
    if (!el) return;
    const dist = el.scrollHeight - el.scrollTop - el.clientHeight;
    setShowScrollBottom(dist > 80);
  }, []);

  useEffect(() => {
    const el = chatBodyRef.current;
    if (!el) return;
    el.addEventListener('scroll', checkScrollPosition);
    checkScrollPosition();
    return () => el.removeEventListener('scroll', checkScrollPosition);
  }, [checkScrollPosition, messages]);

  // 内容变化（含流式）后延迟检测是否需显示「滚动到底部」按钮
  useEffect(() => {
    const t = setTimeout(checkScrollPosition, 80);
    return () => clearTimeout(t);
  }, [messages, sending, checkScrollPosition]);

  const scrollToBottom = useCallback(() => {
    chatBodyRef.current?.scrollTo({ top: chatBodyRef.current.scrollHeight, behavior: 'smooth' });
  }, []);

  const handleStopStream = () => {
    abortControllerRef.current?.abort();
  };

  // 输入框：自适应高度，约 7 行后固定并显示滚动条
  useEffect(() => {
    const ta = inputRef.current;
    if (!ta) return;
    ta.style.height = 'auto';
    const sh = ta.scrollHeight;
    const lineH = 24;
    const maxH = lineH * 7;
    ta.style.height = Math.min(sh, maxH) + 'px';
    ta.style.overflowY = sh > maxH ? 'auto' : 'hidden';
  }, [input]);

  const handleRegenerate = useCallback(
    (aiIdx: number) => {
      if (sending) return;
      const prev = [...messages];
      const lastUser = prev.slice(0, aiIdx).filter((m) => m.role === 'user').pop();
      if (!lastUser) return;
      setMessages(prev.slice(0, aiIdx));
      setChatError(null);
      handleSend(lastUser.content, true);
    },
    [messages, sending]
  );

  const handleSend = async (prefill?: string, skipAddUser?: boolean) => {
    const text = prefill ?? input.trim();
    if (!activationCode || !text || sending) return;
    if (!prefill) setInput('');
    const userMsg: SimpleMessage = {
      id: `u_${Date.now()}`,
      role: 'user',
      content: text,
    };
    const assistantId = `a_${Date.now()}`;
    const toAdd = skipAddUser ? [{ id: assistantId, role: 'assistant' as const, content: '' }] : [userMsg, { id: assistantId, role: 'assistant' as const, content: '' }];
    setMessages((prev) => [...prev, ...toAdd]);
    setChatError(null);
    setSending(true);

    abortControllerRef.current = new AbortController();
    try {
      const baseURL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
      const url = `${baseURL}/api/v1/simple-chat/message/stream`;
      const res = await fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          activation_code: activationCode,
          message: userMsg.content,
          phase: BACKEND_PHASE[phase],
        }),
        signal: abortControllerRef.current.signal,
      });
      if (!res.body) throw new Error('流式接口返回为空');

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
            if (payload.error) { setChatError(String(payload.error)); reader.cancel(); break; }
            if (payload.chunk) {
              const chunk: string = payload.chunk;
              fullReply += chunk;
              setMessages((prev) => prev.map((m) =>
                m.id === assistantId ? { ...m, content: (m.content || '') + chunk } : m
              ));
            }
            if (payload.done && payload.response != null) {
              fullReply = payload.response;
              setMessages((prev) => prev.map((m) =>
                m.id === assistantId ? { ...m, content: fullReply } : m
              ));
              break;
            }
          } catch {}
        }
      }
    } catch (err: any) {
      if (err?.name !== 'AbortError') setChatError(err?.message || '发送失败，请重试');
    } finally {
      setSending(false);
      abortControllerRef.current = null;
    }
  };

  const handleCompletePhase = () => {
    if (!activationCode || !session) return;
    const updated = unlockNextPhase({ ...session, currentPhase: phase });
    setSession(updated);
    const keys = PHASES.map((p) => p.key);
    const nextIdx = keys.indexOf(phase) + 1;
    if (nextIdx < keys.length) {
      router.push(`/explore/chat/${keys[nextIdx]}`);
    } else {
      router.push('/explore/report');
    }
  };

  if (!session || !phaseMeta || !phaseInfo) return null;

  const isLocked = !session.unlockedPhases.includes(phase);
  const currentPhaseIdx = PHASES.findIndex((p) => p.key === phase);

  const dimName = { values: '信念', strengths: '禀赋', interests: '热忱', purpose: '使命' }[phase];
  const phaseClass = { values: 'values', strengths: 'strength', interests: 'interest', purpose: 'purpose' }[phase];

  return (
    <div
      className="flow-light min-h-screen h-screen flex flex-col bg-bd-gradient text-bd-fg overflow-hidden"
      data-phase={phase}
    >
      {/* 顶部进度条：信念→禀赋→热忱→使命，明显提示 + 解锁逻辑 */}
      <div className="fixed top-14 left-0 right-0 z-40 backdrop-blur border-b border-black/[0.05] bg-bd-bg/95">
        <div className="max-w-3xl mx-auto px-4 py-3 flex items-center justify-center gap-1 overflow-x-auto">
          {PHASES.map((p, idx) => {
            const unlocked = session.unlockedPhases.includes(p.key);
            const isActive = p.key === phase;
            return (
              <span key={p.key} className="flex items-center gap-1 flex-shrink-0">
                {idx > 0 && (
                  <ChevronRight size={14} className="text-bd-ui-accent/60 flex-shrink-0" aria-hidden />
                )}
                <button
                  type="button"
                  disabled={!unlocked}
                  onClick={() => unlocked && router.push(`/explore/chat/${p.key}`)}
                  className={`flex items-center gap-2 px-4 py-2 rounded-full text-sm font-medium transition-all ${
                    isActive ? `${PHASE_META[p.key].bg} ${PHASE_META[p.key].color} ${PHASE_META[p.key].bgLight}` : ''
                  } ${unlocked && !isActive ? 'text-[var(--bd-ui-accent)]/80 hover:text-[var(--bd-ui-accent)] hover:bg-[var(--bd-ui-accent)]/5' : ''} ${!unlocked ? 'text-[var(--bd-ui-accent)]/40 cursor-not-allowed' : ''}`}
                >
                  {unlocked && !isActive ? <CheckCircle2 size={14} className="text-[var(--bd-ui-accent)]" /> : null}
                  {!unlocked && <Lock size={14} className="text-[var(--bd-ui-accent)]/60" />}
                  <span className="font-mono text-xs opacity-60">{p.num}</span>
                  {p.label}
                </button>
              </span>
            );
          })}
        </div>
      </div>

      {/* 阶段说明 + 内容区（无固定 pb，与底部输入区紧邻） */}
      <div className="flex-1 max-w-3xl mx-auto w-full px-4 pt-28 pb-3 flex flex-col gap-4 min-h-0 overflow-hidden">
        {/* 阶段标题与提示（大而明显） */}
        <motion.div
          key={phase}
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          className="space-y-1 flex-shrink-0"
        >
          <div className="flex items-center gap-2">
            <span className="text-xs font-mono text-neutral-500">{phaseInfo.num}</span>
            <h1 className={`text-xl font-bold ${phaseMeta.color}`}>{phaseInfo.label}</h1>
          </div>
          <p className="text-sm text-neutral-600 leading-relaxed">{phaseMeta.desc}</p>
          <p className="text-xs text-neutral-500 italic">{phaseMeta.hint}</p>
        </motion.div>

        {/* 内容展示框（内部可滚动，超出时显示侧边滚动条 + 一键向下按钮） */}
        <div className="flow-chat-box flex-1 min-w-0 flex flex-col relative">
          <div ref={chatBodyRef} className="flow-chat-body flex-1 min-h-0 overflow-y-auto">
          {/* 维度标签：● 正在探索 · 信念维度 */}
          <div className="flow-dimension-label">
            <span className="flow-dimension-dot" />
            正在探索 · {dimName}维度
          </div>

          {initLoading ? (
            <div className="flex justify-center py-12">
              <div className="flex gap-1.5">
                {[0, 1, 2].map((i) => (
                  <motion.div
                    key={i}
                    className="w-2 h-2 rounded-full bg-neutral-400"
                    animate={{ opacity: [0.3, 1, 0.3] }}
                    transition={{ duration: 1.2, delay: i * 0.2, repeat: Infinity }}
                  />
                ))}
              </div>
            </div>
          ) : messages.length === 0 ? (
            <p className="flow-progress-text text-center py-8 text-sm">正在准备第一个问题…</p>
          ) : (
            messages.map((m, idx) => (
              <div key={m.id} className={m.role === 'user' ? 'flow-msg-user' : ''}>
                {m.role === 'user' ? (
                  <div className="flow-msg-user-wrap">
                    <div className="flow-msg-user-content">
                      <span className="whitespace-pre-wrap">{m.content}</span>
                    </div>
                    <div className="flow-msg-user-toolbar">
                      <button
                        type="button"
                        className="flow-toolbar-btn"
                        title="复制"
                        onClick={() => copyToClipboard(m.content)}
                      >
                        <Copy size={14} strokeWidth={1.6} />
                      </button>
                    </div>
                  </div>
                ) : (
                  <FlowAiMessage
                    content={m.content}
                    phase={(phaseClass ?? 'values') as 'values' | 'strength' | 'interest' | 'purpose'}
                    streaming={sending && idx === messages.length - 1}
                    onRegenerate={() => handleRegenerate(idx)}
                  />
                )}
              </div>
            ))
          )}

          {chatError && (
            <div className="flow-msg-error">
              <div className="flow-msg-error-text">{chatError}</div>
              <button
                type="button"
                className="flow-retry-btn"
                onClick={() => { setChatError(null); const lastUser = [...messages].filter((m) => m.role === 'user').pop(); if (lastUser) handleSend(lastUser.content, true); }}
              >
                重新尝试
              </button>
            </div>
          )}
          <div ref={messagesEndRef} />
        </div>

          {/* 向下箭头：不在最底部时显示，点击滚动到底部 */}
          <button
            type="button"
            aria-label="滚动到底部"
            className={`flow-scroll-bottom-btn ${showScrollBottom ? 'visible' : ''}`}
            onClick={scrollToBottom}
            title="滚动到底部"
          >
            <ChevronDown size={22} strokeWidth={2.5} />
          </button>
        </div>

      </div>

      {/* 底部输入区（flex 流式布局，随输入变高而升高，与展示框保持固定间距） */}
      <div className="flex-shrink-0 max-w-3xl mx-auto w-full px-4 pb-4 pt-2 bg-bd-bg/95 backdrop-blur-sm border-t border-black/[0.05]">
        <div className="max-w-3xl mx-auto px-4 w-full">
        <div className="flow-input-area">
          <form
            onSubmit={(e) => { e.preventDefault(); handleSend(); }}
            className="w-full"
          >
            <div className="flow-input-box">
              <textarea
                ref={inputRef}
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault();
                    if (!sending) handleSend();
                  }
                }}
                placeholder="说说你的想法..."
                rows={1}
                disabled={sending}
                className="flow-input-field"
              />
              <div className="flow-send-btn-wrap">
                {sending && <div className="flow-send-glow" aria-hidden />}
                <button
                  type="button"
                  onClick={sending ? handleStopStream : () => handleSend()}
                  disabled={!sending && !input.trim()}
                  className={`flow-send-btn ${sending ? 'is-stop' : ''}`}
                >
                  {sending ? (
                    <Square size={16} strokeWidth={0} fill="white" />
                  ) : (
                    <ArrowUp size={16} strokeWidth={2.2} />
                  )}
                </button>
              </div>
            </div>
          </form>
        </div>
        {/* 完成此步 */}
        <div className="py-3">
          <div className="flex items-center justify-between">
            <p className="text-xs text-neutral-500">对话记录自动保存</p>
            <button
              type="button"
              onClick={handleCompletePhase}
              className="flex items-center gap-1.5 px-4 py-2 rounded-xl text-sm font-medium text-white"
              style={{ background: 'var(--bd-ui-accent)' }}
            >
              完成此步，进入下一步
              <ChevronRight size={14} />
            </button>
          </div>
        </div>
        </div>
      </div>
    </div>
  );
}
