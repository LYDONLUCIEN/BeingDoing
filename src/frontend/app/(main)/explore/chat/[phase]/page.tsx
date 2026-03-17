'use client';

import { useState, useEffect, useRef, useCallback } from 'react';
import { useRouter, useParams } from 'next/navigation';
import { motion } from 'framer-motion';
import { ChevronRight, ChevronDown, ArrowUp, Square, Copy } from 'lucide-react';
import FlowAiMessage from '@/components/explore/FlowAiMessage';
import DimensionConclusionCard, { type DimensionConclusionData } from '@/components/explore/DimensionConclusionCard';
import ChatPhaseBackground from '@/components/explore/ChatPhaseBackground';
import ChatPhaseSidebar from '@/components/explore/ChatPhaseSidebar';
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
import {
  getThreads,
  saveThread,
  addThread,
  removeThread,
  getActiveThreadId,
  setActiveThreadId,
  createThreadId,
  type ChatThread,
  type ThreadMessage,
} from '@/lib/explore/threads';

// Phase metadata
const PHASE_META: Record<PhaseKey, { color: string; desc: string; hint: string }> = {
  values: {
    color: 'text-bd-phase-values',
    desc: '探索你最深层的信念。什么对你最重要？哪些原则是你绝不妥协的？',
    hint: '这一步帮你发现5个核心价值观关键词。',
  },
  strengths: {
    color: 'text-bd-phase-strengths',
    desc: '探索你的天赋与禀赋。有些事你做起来不费力，却让别人惊叹。',
    hint: '这一步帮你发现10件真正擅长的事。',
  },
  interests: {
    color: 'text-bd-phase-interests',
    desc: '探索你的热忱。什么话题让你停不下来？什么场景让时间消失？',
    hint: '这一步帮你找到真正让你忘我的事。',
  },
  purpose: {
    color: 'text-bd-phase-purpose',
    desc: '探索你的使命。你想为谁而做？你希望在这个世界留下什么？',
    hint: '这一步帮你找到职业背后更深的驱动力。',
  },
};

const BACKEND_PHASE: Record<PhaseKey, string> = {
  values: 'values',
  strengths: 'strengths',
  interests: 'interests',
  purpose: 'purpose',
};

export default function ChatPhasePage() {
  const router = useRouter();
  const params = useParams();
  const phase = (params.phase as string) as PhaseKey;

  const [session, setSession] = useState<ExploreSession | null>(null);
  const [activationCode, setActivationCode] = useState<string | null>(null);
  const [threads, setThreads] = useState<ChatThread[]>([]);
  const [activeThreadId, setActiveThreadIdState] = useState<string | null>(null);
  const [backendSyncedThreadId, setBackendSyncedThreadId] = useState<string | null>(null);
  const [messages, setMessages] = useState<ThreadMessage[]>([]);
  const [input, setInput] = useState('');
  const [sending, setSending] = useState(false);
  const [initLoading, setInitLoading] = useState(true);
  const [chatError, setChatError] = useState<string | null>(null);
  const [backendSessionId, setBackendSessionId] = useState<string | null>(null);

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const chatBodyRef = useRef<HTMLDivElement>(null);
  const [showScrollBottom, setShowScrollBottom] = useState(false);
  const abortControllerRef = useRef<AbortController | null>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  const phaseMeta = PHASE_META[phase];
  const phaseInfo = PHASES.find((p) => p.key === phase);

  // Auth & redirect
  useEffect(() => {
    if (!PHASES.find((p) => p.key === phase)) {
      router.replace('/explore/activate');
      return;
    }
    const code = getLastActivationCode();
    if (!code) {
      router.replace('/explore/activate');
      return;
    }
    setActivationCode(code);
    const s = loadSession(code);
    setSession(s);
    if (!s?.surveyCompleted) {
      router.replace('/explore/survey');
      return;
    }
    if (!s.unlockedPhases.includes(phase)) {
      router.replace(`/explore/chat/${s.currentPhase}`);
      return;
    }
  }, [phase, router]);

  // Load threads for this phase
  useEffect(() => {
    if (!activationCode || !phase) return;
    const list = getThreads(activationCode, phase);
    setThreads(list);
    const activeId = getActiveThreadId(activationCode, phase);
    setActiveThreadIdState(activeId);
  }, [activationCode, phase]);

  // Load messages for active thread (from backend or from thread)
  useEffect(() => {
    if (!activationCode || !phase) return;
    let cancelled = false;
    setInitLoading(true);

    const list = getThreads(activationCode, phase);
    const activeId = getActiveThreadId(activationCode, phase);

    if (list.length === 0) {
      // No threads: 新建全新对话，后端按 thread_id 创建独立存储
      const tid = createThreadId();
      (async () => {
        try {
          const initRes = await apiClient.post('/simple-chat/init', {
            activation_code: activationCode,
            phase: BACKEND_PHASE[phase],
            thread_id: tid,
          });
          const initMsgs: any[] = initRes.data.messages ?? [];
          const sessId = initRes.data?.activation?.session_id;
          if (sessId && !cancelled) {
            setBackendSessionId(sessId);
            const s = loadSession(activationCode);
            saveSession({ ...s, sessionId: sessId });
          }
          const now = Date.now();
          const msgs: ThreadMessage[] = initMsgs.map((m, i) => ({
            id: `init_${i}`,
            role: m.role as 'user' | 'assistant',
            content: m.content ?? '',
            createdAt: now,
          }));
          const thread: ChatThread = {
            id: tid,
            title: '对话 1',
            status: 'in-progress',
            messages: msgs,
            createdAt: Date.now(),
          };
          addThread(activationCode, phase, thread);
          setActiveThreadId(activationCode, phase, tid);
          if (!cancelled) {
            setThreads(getThreads(activationCode, phase));
            setActiveThreadIdState(tid);
            setBackendSyncedThreadId(tid);
            setMessages(msgs);
          }
        } catch {}
        if (!cancelled) setInitLoading(false);
      })();
      return;
    }

    if (activeId) {
      const thread = list.find((t) => t.id === activeId);
      if (thread) {
        // Load from backend for active thread (backend is source of truth for active)
        (async () => {
          try {
            const historyRes = await apiClient.get('/simple-chat/history', {
              params: { activation_code: activationCode, phase: BACKEND_PHASE[phase], thread_id: activeId },
            });
            const history: any[] = historyRes.data.messages ?? [];
            const meta = historyRes.data?.metadata ?? {};
            const sessId = meta?.session_id;
            if (sessId && !cancelled) {
              setBackendSessionId(sessId);
              const s = loadSession(activationCode);
              saveSession({ ...s, sessionId: sessId });
            }
            if (!cancelled && history.length > 0) {
              const baseMsgs: ThreadMessage[] = history.map((m, i) => ({
                id: `h_${i}_${m.id ?? i}`,
                role: m.role as 'user' | 'assistant',
                content: m.content ?? '',
                createdAt: m.created_at ? new Date(m.created_at).getTime() : undefined,
              }));
              const concl = meta.dimension_conclusion as DimensionConclusionData | undefined;
              const msgs =
                concl && !baseMsgs.some((x) => x.type === 'dimension_conclusion')
                  ? [
                      ...baseMsgs,
                      {
                        id: `concl_${Date.now()}`,
                        role: 'assistant' as const,
                        content: '',
                        type: 'dimension_conclusion' as const,
                        conclusionData: concl,
                        conclusionCollapsed: !meta.thread_completed,
                        createdAt: Date.now(),
                      } satisfies ThreadMessage,
                    ]
                  : baseMsgs;
              setMessages(msgs);
              setBackendSyncedThreadId(activeId);
              const updated = {
                ...thread,
                messages: msgs,
                dimensionConclusion: concl ?? thread.dimensionConclusion,
                ...(meta.thread_completed ? { status: 'completed' as const } : {}),
              };
              saveThread(activationCode, phase, updated);
              setThreads(getThreads(activationCode, phase));
            } else {
              setMessages(thread.messages);
              setBackendSyncedThreadId(activeId);
            }
          } catch {
            setMessages(thread.messages);
            setBackendSyncedThreadId(activeId);
          }
          if (!cancelled) setInitLoading(false);
        })();
      } else {
        setMessages([]);
        setInitLoading(false);
      }
    } else {
      const first = list[0];
      const firstId = first?.id ?? null;
      setActiveThreadIdState(firstId);
      setActiveThreadId(activationCode, phase, firstId);
      setBackendSyncedThreadId(firstId);
      (async () => {
        try {
          const historyRes = await apiClient.get('/simple-chat/history', {
            params: { activation_code: activationCode, phase: BACKEND_PHASE[phase], thread_id: firstId },
          });
          const history: any[] = historyRes.data.messages ?? [];
          const meta = historyRes.data?.metadata ?? {};
          const sessId = meta?.session_id;
          if (sessId && !cancelled) {
            setBackendSessionId(sessId);
            const s = loadSession(activationCode);
            saveSession({ ...s, sessionId: sessId });
          }
          if (!cancelled && history.length > 0 && firstId) {
            const baseMsgs: ThreadMessage[] = history.map((m, i) => ({
              id: `h_${i}_${m.id ?? i}`,
              role: m.role as 'user' | 'assistant',
              content: m.content ?? '',
              createdAt: m.created_at ? new Date(m.created_at).getTime() : undefined,
            }));
            const concl = meta.dimension_conclusion as DimensionConclusionData | undefined;
            const msgs =
              concl && !baseMsgs.some((x) => x.type === 'dimension_conclusion')
                ? [
                    ...baseMsgs,
                    {
                      id: `concl_${Date.now()}`,
                      role: 'assistant' as const,
                      content: '',
                      type: 'dimension_conclusion' as const,
                      conclusionData: concl,
                      conclusionCollapsed: !meta.thread_completed,
                      createdAt: Date.now(),
                    } satisfies ThreadMessage,
                  ]
                : baseMsgs;
            setMessages(msgs);
            const updated = {
              ...first,
              messages: msgs,
              dimensionConclusion: concl ?? first.dimensionConclusion,
              ...(meta.thread_completed ? { status: 'completed' as const } : {}),
            };
            saveThread(activationCode, phase, updated);
            setThreads(getThreads(activationCode, phase));
          } else if (first) {
            setMessages(first.messages);
          }
        } catch {
          if (first) setMessages(first.messages);
        }
        if (!cancelled) setInitLoading(false);
      })();
    }

    return () => { cancelled = true; };
  }, [activationCode, phase, threads.length]);

  // Persist messages + dimensionConclusion to active (backend-synced) thread when they change
  useEffect(() => {
    if (!activationCode || !phase || !activeThreadId || initLoading || activeThreadId !== backendSyncedThreadId) return;
    const t = threads.find((x) => x.id === activeThreadId);
    if (t && messages.length > 0) {
      if (t.status === 'completed') return;
      const lastConcl = messages.filter((m) => m.type === 'dimension_conclusion').pop();
      const toSave: ChatThread = { ...t, messages };
      if (lastConcl?.conclusionData) toSave.dimensionConclusion = lastConcl.conclusionData;
      saveThread(activationCode, phase, toSave);
      setThreads(getThreads(activationCode, phase));
    }
  }, [messages, activeThreadId, backendSyncedThreadId, initLoading, activationCode, phase, threads]);

  const selectedThread = threads.find((t) => t.id === activeThreadId);
  // 输入锁定规则：1) 从未出现过结论卡 → 可输入；2) 结论卡出现且用户已确认完成 → 锁定；
  // 3) 用户选择「继续完善」后 → 折叠结论卡，可输入
  const isSelectedCompleted = selectedThread?.status === 'completed';
  const isBackendSynced = activeThreadId === backendSyncedThreadId;
  const hasCollapsedConclusion = messages.some(
    (m) => m.type === 'dimension_conclusion' && m.conclusionCollapsed
  );
  const isReadOnly =
    isSelectedCompleted || // 用户已确认完成，锁定
    (!isBackendSynced && !!activeThreadId); // 切到其它 thread 时暂不输入（未同步）
  const canContinue = !!selectedThread && isSelectedCompleted;

  const checkScrollPosition = useCallback(() => {
    const el = chatBodyRef.current;
    if (!el) return;
    setShowScrollBottom(el.scrollHeight - el.scrollTop - el.clientHeight > 80);
  }, []);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  useEffect(() => {
    const el = chatBodyRef.current;
    if (!el) return;
    el.addEventListener('scroll', checkScrollPosition);
    checkScrollPosition();
    return () => el.removeEventListener('scroll', checkScrollPosition);
  }, [checkScrollPosition, messages]);

  const scrollToBottom = useCallback(() => {
    chatBodyRef.current?.scrollTo({ top: chatBodyRef.current.scrollHeight, behavior: 'smooth' });
  }, []);

  useEffect(() => {
    const ta = inputRef.current;
    if (!ta) return;
    ta.style.height = 'auto';
    ta.style.height = Math.min(ta.scrollHeight, 24 * 7) + 'px';
    ta.style.overflowY = ta.scrollHeight > 24 * 7 ? 'auto' : 'hidden';
  }, [input]);

  const handleSend = async (prefill?: string, skipAddUser?: boolean) => {
    const text = prefill ?? input.trim();
    if (!activationCode || !text || sending || isReadOnly) return;
    if (!prefill) setInput('');
    const now = Date.now();
    const userMsg: ThreadMessage = { id: `u_${now}`, role: 'user', content: text, createdAt: now };
    const assistantId = `a_${now}`;
    const toAdd = skipAddUser
      ? [{ id: assistantId, role: 'assistant' as const, content: '', createdAt: now }]
      : [userMsg, { id: assistantId, role: 'assistant' as const, content: '', createdAt: now }];
    setMessages((prev) => [...prev, ...toAdd]);
    setChatError(null);
    setSending(true);

    abortControllerRef.current = new AbortController();
    try {
      const apiBase = (process.env.NEXT_PUBLIC_API_URL || '').trim();
      const streamUrl = `${apiBase ? apiBase.replace(/\/+$/, '') : ''}/api/v1/simple-chat/message/stream`;
      const res = await fetch(streamUrl, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          activation_code: activationCode,
          message: userMsg.content,
          phase: BACKEND_PHASE[phase],
          thread_id: activeThreadId || undefined,
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
            if (payload.error) {
              setChatError(String(payload.error));
              reader.cancel();
              break;
            }
            if (payload.chunk) {
              fullReply += payload.chunk;
              setMessages((prev) =>
                prev.map((m) =>
                  m.id === assistantId ? { ...m, content: (m.content || '') + payload.chunk } : m
                )
              );
            }
            if (payload.dimension_conclusion) {
              const concl = payload.dimension_conclusion as DimensionConclusionData;
              const conclMsg: ThreadMessage = {
                id: `concl_${Date.now()}`,
                role: 'assistant',
                content: '',
                type: 'dimension_conclusion',
                conclusionData: concl,
                conclusionCollapsed: false,
                createdAt: Date.now(),
              };
              setMessages((prev) => [...prev, conclMsg]);
            }
            if (payload.done && payload.response != null) {
              fullReply = payload.response;
              const doneAt = Date.now();
              setMessages((prev) =>
                prev.map((m) =>
                  m.id === assistantId ? { ...m, content: fullReply, createdAt: m.createdAt ?? doneAt } : m
                )
              );
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

  const handleRegenerate = useCallback(
    (aiIdx: number) => {
      if (sending || isReadOnly) return;
      const lastUser = messages.slice(0, aiIdx).filter((m) => m.role === 'user').pop();
      if (!lastUser) return;
      setMessages((prev) => prev.slice(0, aiIdx));
      setChatError(null);
      handleSend(lastUser.content, true);
    },
    [messages, sending, isReadOnly]
  );

  const handleSelectThread = (thread: ChatThread) => {
    setActiveThreadId(activationCode!, phase, thread.id);
    setActiveThreadIdState(thread.id);
    setMessages(thread.messages);
    setBackendSyncedThreadId(thread.id);
  };

  const handleNewChat = async () => {
    if (!activationCode || !phase) return;
    const list = getThreads(activationCode, phase);
    if (list.length >= 5) return;

    // Save current thread if has messages
    if (selectedThread && messages.length > 0) {
      saveThread(activationCode, phase, { ...selectedThread, messages });
    }

    setInitLoading(true);
    const tid = createThreadId();
    try {
      const initRes = await apiClient.post('/simple-chat/init', {
        activation_code: activationCode,
        phase: BACKEND_PHASE[phase],
        thread_id: tid,
      });
      const initMsgs: any[] = initRes.data.messages ?? [];
      const now = Date.now();
      const msgs: ThreadMessage[] = initMsgs.map((m, i) => ({
        id: `init_${now}_${i}`,
        role: m.role as 'user' | 'assistant',
        content: m.content ?? '',
        createdAt: now,
      }));
      const thread: ChatThread = {
        id: tid,
        title: `对话 ${list.length + 1}`,
        status: 'in-progress',
        messages: msgs,
        createdAt: Date.now(),
      };
      addThread(activationCode, phase, thread);
      setActiveThreadId(activationCode, phase, tid);
      setBackendSyncedThreadId(tid);
      setThreads(getThreads(activationCode, phase));
      setActiveThreadIdState(tid);
      setMessages(msgs);
    } catch {}
    setInitLoading(false);
  };

  const handleMarkComplete = () => {
    if (!activationCode || !phase || !selectedThread) return;
    const updated: ChatThread = { ...selectedThread, status: 'completed', messages };
    saveThread(activationCode, phase, updated);
    setThreads(getThreads(activationCode, phase));
  };

  const handleConfirmConclusion = async () => {
    if (!activationCode || !phase || !activeThreadId) return;
    const th = threads.find((t) => t.id === activeThreadId);
    if (!th) return;
    const lastConcl = messages.filter((m) => m.type === 'dimension_conclusion').pop();
    if (!lastConcl?.conclusionData) return;
    try {
      await apiClient.post('/simple-chat/thread/complete', {
        activation_code: activationCode,
        phase: BACKEND_PHASE[phase],
        thread_id: activeThreadId,
      });
    } catch (e) {
      console.warn('thread/complete API failed:', e);
    }
    const updated: ChatThread = {
      ...th,
      status: 'completed',
      messages,
      dimensionConclusion: lastConcl.conclusionData,
    };
    saveThread(activationCode, phase, updated);
    // 使用 functional update 直接更新 state，避免依赖 getThreads 被 persist effect 覆盖
    setThreads((prev) => prev.map((t) => (t.id === activeThreadId ? updated : t)));
  };

  const handleContinueChat = async (conclusionMsg?: ThreadMessage) => {
    const lastConcl = messages.filter((m) => m.type === 'dimension_conclusion').pop();
    const toCollapse = conclusionMsg ?? lastConcl;
    if (toCollapse && toCollapse.type === 'dimension_conclusion') {
      setMessages((prev) =>
        prev.map((m) =>
          m.id === toCollapse.id ? { ...m, conclusionCollapsed: true } : m
        )
      );
    }
    if (isSelectedCompleted && activationCode && phase && activeThreadId) {
      try {
        await apiClient.post('/simple-chat/thread/reopen', {
          activation_code: activationCode,
          phase: BACKEND_PHASE[phase],
          thread_id: activeThreadId,
        });
      } catch {}
      if (selectedThread) {
        const updated: ChatThread = { ...selectedThread, status: 'in-progress' };
        saveThread(activationCode, phase, updated);
        setThreads(getThreads(activationCode, phase));
      }
    }
  };

  const handleCompleteAndContinue = () => {
    if (!activationCode || !session || !canContinue) return;
    const updated = unlockNextPhase({ ...session, currentPhase: phase });
    saveSession(updated);
    setSession(updated);
    router.push(`/explore/transition?from=${phase}`);
  };

  const handleDeleteThread = (thread: ChatThread) => {
    if (!activationCode || !phase) return;
    const list = removeThread(activationCode, phase, thread.id);
    setThreads(list);
    if (thread.id === activeThreadId) {
      if (list.length > 0) {
        const next = list[0];
        setActiveThreadIdState(next.id);
        setActiveThreadId(activationCode, phase, next.id);
        setMessages(next.messages);
        setBackendSyncedThreadId(next.id);
      } else {
        setActiveThreadIdState(null);
        setMessages([]);
        setBackendSyncedThreadId(null);
        handleNewChat();
      }
    }
  };

  const handleStopStream = () => abortControllerRef.current?.abort();

  if (!session || !phaseMeta || !phaseInfo) return null;

  const dimName = { values: '信念', strengths: '禀赋', interests: '热忱', purpose: '使命' }[phase];
  const phaseClass: 'values' | 'strength' | 'interest' | 'purpose' =
    phase === 'values' ? 'values' : phase === 'strengths' ? 'strength' : phase === 'interests' ? 'interest' : 'purpose';

  return (
    <div className="flow-light h-screen flex flex-col overflow-hidden" data-phase={phase}>
      <ChatPhaseBackground phase={phase} />
      <div className="flex-1 flex min-h-0 relative z-10 pt-14 overflow-hidden">
        <ChatPhaseSidebar
          phase={phase}
          phaseLabel={dimName}
          threads={threads}
          activeThreadId={activeThreadId}
          onSelectThread={handleSelectThread}
          onNewChat={handleNewChat}
          onDeleteThread={handleDeleteThread}
          canNewChat={threads.length < 5}
        />
        <div className="flex-1 flex flex-col min-w-0 min-h-0 overflow-hidden">
          <header className="flex-shrink-0 backdrop-blur border-b border-black/[0.05] bg-white/70 px-6 py-4 flex items-center justify-between">
            <h1 className={`text-lg font-semibold ${phaseMeta.color}`}>
              {phaseInfo.num} {phaseInfo.label}
            </h1>
            <button
              type="button"
              onClick={handleCompleteAndContinue}
              disabled={!canContinue}
              title={!canContinue ? '请选中一个已完成的对话' : ''}
              className={`px-5 py-2 rounded-full text-sm font-medium transition-all ${
                canContinue ? 'bg-bd-ui-accent text-white' : 'opacity-50 cursor-not-allowed bg-neutral-300'
              }`}
            >
              完成并继续 <ChevronRight size={14} className="inline" />
            </button>
          </header>

          <div className="flex-1 flex flex-col min-h-0 overflow-hidden px-6 py-4">
            <div className="max-w-3xl mx-auto w-full flex-1 flex flex-col min-h-0 min-w-0">
            <motion.div key={phase} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} className="space-y-1 flex-shrink-0 mb-3">
              <p className="text-sm text-neutral-600 leading-relaxed">{phaseMeta.desc}</p>
              <p className="text-xs text-neutral-500 italic">{phaseMeta.hint}</p>
            </motion.div>
            {/* 对话展示框：占据剩余空间，内部滚动；下方为输入框 */}
            <div className="flow-chat-box flex-1 min-h-0 min-w-0 flex flex-col relative">
              <div ref={chatBodyRef} className="flow-chat-body flex-1 min-h-0 overflow-y-auto">
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
                    <div key={m.id} className={m.role === 'user' || m.type === 'dimension_conclusion' ? (m.role === 'user' ? 'flow-msg-user' : '') : ''}>
                      {m.type === 'dimension_conclusion' && m.conclusionData ? (
                        <div className="flow-msg-conclusion-wrap">
                          <DimensionConclusionCard
                            phase={phaseClass}
                            data={m.conclusionData}
                            isCompleted={isSelectedCompleted}
                            inline
                            collapsed={!!m.conclusionCollapsed}
                            onCollapsedChange={(collapsed) =>
                              setMessages((prev) =>
                                prev.map((msg) =>
                                  msg.id === m.id ? { ...msg, conclusionCollapsed: collapsed } : msg
                                )
                              )
                            }
                            showActions={
                              !m.conclusionCollapsed &&
                              m.id === messages.filter((x) => x.type === 'dimension_conclusion').pop()?.id
                            }
                            onConfirm={handleConfirmConclusion}
                            onContinueChat={() => handleContinueChat(m)}
                          />
                        </div>
                      ) : m.role === 'user' ? (
                        <div className="flow-msg-user-wrap">
                          {m.createdAt !== undefined && (
                            <span className="flow-msg-time text-[10px] text-[var(--flow-text-muted)] mb-1 block">
                              {`${new Date(m.createdAt).getHours().toString().padStart(2, '0')}:${new Date(m.createdAt).getMinutes().toString().padStart(2, '0')}`}
                            </span>
                          )}
                          <div className="flow-msg-user-content">
                            <span className="flow-msg-user-text">
                              {(() => {
                                const s = m.content || '';
                                const lines = s.split(/\r?\n/);
                                if (lines.length > 1 && lines.every((l) => l.length <= 2)) {
                                  return lines.join('');
                                }
                                return s;
                              })()}
                            </span>
                          </div>
                          <div className="flow-msg-user-toolbar">
                            <button type="button" className="flow-toolbar-btn" title="复制" onClick={() => copyToClipboard(m.content)}>
                              <Copy size={14} strokeWidth={1.6} />
                            </button>
                          </div>
                        </div>
                      ) : (
                        <FlowAiMessage
                          content={m.content}
                          phase={phaseClass}
                          streaming={sending && idx === messages.length - 1}
                          timestamp={m.createdAt}
                          onRegenerate={() => handleRegenerate(idx)}
                          sessionId={backendSessionId ?? undefined}
                          logIndex={messages.slice(0, idx).filter((x) => x.role === 'assistant' && x.type !== 'dimension_conclusion').length}
                          dimension={phase}
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
                      onClick={() => {
                        setChatError(null);
                        const lastUser = [...messages].filter((m) => m.role === 'user').pop();
                        if (lastUser) handleSend(lastUser.content, true);
                      }}
                    >
                      重新尝试
                    </button>
                  </div>
                )}
                <div ref={messagesEndRef} />
              </div>

              <button
                type="button"
                aria-label="滚动到底部"
                className={`flow-scroll-bottom-btn ${showScrollBottom ? 'visible' : ''}`}
                onClick={scrollToBottom}
              >
                <ChevronDown size={22} strokeWidth={2.5} />
              </button>
            </div>
            </div>
          </div>

          {/* 对话输入框：固定在最底部 */}
          <div className="flex-shrink-0 max-w-3xl mx-auto w-full px-6 pb-4 pt-2 bg-bd-bg/95 backdrop-blur-sm border-t border-black/[0.05]">
            <div className="flow-input-area">
              <form onSubmit={(e) => { e.preventDefault(); handleSend(); }} className="w-full">
                <div className="flow-input-box">
                  <textarea
                    ref={inputRef}
                    value={input}
                    onChange={(e) => setInput(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter' && !e.shiftKey) {
                        e.preventDefault();
                        if (!sending && !isReadOnly) handleSend();
                      }
                    }}
                    placeholder={
                      isReadOnly
                        ? '此对话已完成'
                        : hasCollapsedConclusion
                          ? '继续完善，说说你想补充或深化的…'
                          : '说说你的想法...'
                    }
                    rows={1}
                    disabled={sending || isReadOnly}
                    className="flow-input-field"
                  />
                  <div className="flow-send-btn-wrap">
                    {sending && <div className="flow-send-glow" aria-hidden />}
                    <button
                      type="button"
                      onClick={sending ? handleStopStream : () => handleSend()}
                      disabled={(sending || !input.trim() || isReadOnly) as boolean}
                      className={`flow-send-btn ${sending ? 'is-stop' : ''}`}
                    >
                      {sending ? <Square size={16} strokeWidth={0} fill="white" /> : <ArrowUp size={16} strokeWidth={2.2} />}
                    </button>
                  </div>
                </div>
              </form>
            </div>
            <div className="py-3 flex items-center justify-between">
              <p className="text-xs text-neutral-500">对话记录自动保存</p>
              <button
                type="button"
                onClick={handleMarkComplete}
                disabled={isSelectedCompleted || messages.length === 0}
                className={`flex items-center gap-1.5 px-4 py-2 rounded-xl text-sm font-medium transition-all ${
                  isSelectedCompleted
                    ? 'bg-emerald-100 text-emerald-700 cursor-default'
                    : 'bd-btn-black text-white hover:opacity-90 disabled:opacity-50 disabled:cursor-not-allowed'
                }`}
              >
                {isSelectedCompleted ? '✓ 已完成' : '确认完成'}
                {!isSelectedCompleted && <ChevronRight size={14} />}
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
