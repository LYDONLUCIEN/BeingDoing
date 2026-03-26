'use client';

import { useState, useEffect, useRef, useCallback, useMemo } from 'react';
import { useRouter, useParams } from 'next/navigation';
import { motion } from 'framer-motion';
import { ChevronRight, ChevronDown, ArrowUp, Square, Copy } from 'lucide-react';
import FlowAiMessage from '@/components/explore/FlowAiMessage';
import DimensionConclusionCard, { type DimensionConclusionData } from '@/components/explore/DimensionConclusionCard';
import ChatPhaseBackground from '@/components/explore/ChatPhaseBackground';
import ChatPhaseSidebar from '@/components/explore/ChatPhaseSidebar';
import RuminationSectionProgress from '@/components/explore/RuminationSectionProgress';
import RuminationTableWidget from '@/components/explore/RuminationTableWidget';
import { copyToClipboard } from '@/lib/utils/clipboard';
import { apiClient, getApiErrorMessage } from '@/lib/api/client';
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
  setThreadsForPhase,
  saveThread,
  addThread,
  removeThread,
  getActiveThreadId,
  setActiveThreadId,
  createThreadId,
  type ChatThread,
  type ThreadMessage,
} from '@/lib/explore/threads';
import { ruminationApi } from '@/lib/api/rumination';
import { useLocale } from '@/hooks/useLocale';

// Phase metadata (color only; desc/hint come from i18n)
const PHASE_COLORS: Record<PhaseKey, string> = {
  values: 'text-bd-phase-values',
  strengths: 'text-bd-phase-strengths',
  interests: 'text-bd-phase-interests',
  purpose: 'text-bd-phase-purpose',
  rumination: 'text-bd-phase-rumination',
};

const BACKEND_PHASE: Record<PhaseKey, string> = {
  values: 'values',
  strengths: 'strengths',
  interests: 'interests',
  purpose: 'purpose',
  rumination: 'rumination',
};

export default function ChatPhasePage() {
  const router = useRouter();
  const params = useParams();
  const { t } = useLocale();
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
  const [threadsFetched, setThreadsFetched] = useState(false);
  const [chatError, setChatError] = useState<string | null>(null);
  const [backendSessionId, setBackendSessionId] = useState<string | null>(null);
  const [conclusionLoading, setConclusionLoading] = useState(false);

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const chatBodyRef = useRef<HTMLDivElement>(null);
  const [showScrollBottom, setShowScrollBottom] = useState(false);
  const abortControllerRef = useRef<AbortController | null>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  const phaseMeta = {
    color: PHASE_COLORS[phase],
    desc: t(`explore.chat.phaseMeta.${phase}.desc`),
    hint: t(`explore.chat.phaseMeta.${phase}.hint`),
  };
  const phaseInfo = PHASES.find((p) => p.key === phase);
  const phaseLabel = t(`explore.chat.phaseLabels.${phase}`);

  /** 仅在线程 id 集合变化时触发「加载消息」effect，避免因 threads 引用反复变（persist / save 后 getThreads）而重复 init */
  const threadListSignature = useMemo(() => threads.map((t) => t.id).join('|'), [threads]);

  /** 侧栏预览：当前选中线程的消息以 React state 为准（列表里的 thread 可能仍是 messages:[]） */
  const threadsForSidebar = useMemo(() => {
    if (!activeThreadId) return threads;
    return threads.map((th) => (th.id === activeThreadId ? { ...th, messages } : th));
  }, [threads, activeThreadId, messages]);

  const mapHistoryToThreadMessages = useCallback(
    (history: any[], meta: any): ThreadMessage[] =>
      history.map((m, i) => {
        const id = `h_${i}_${m.id ?? i}`;
        const createdAt = m.created_at ? new Date(m.created_at).getTime() : undefined;
        if (m.role === 'conclusion_card') {
          let conclusionData: DimensionConclusionData | undefined = undefined;
          if (m.card_payload && typeof m.card_payload === 'object') {
            conclusionData = m.card_payload as DimensionConclusionData;
          } else if (typeof m.content === 'string' && m.content.trim()) {
            try {
              conclusionData = JSON.parse(m.content) as DimensionConclusionData;
            } catch {
              conclusionData = undefined;
            }
          }
          return {
            id,
            role: 'assistant',
            content: '',
            type: 'dimension_conclusion',
            conclusionData,
            conclusionCollapsed: false,
            conclusionConfirmed: !!meta?.thread_completed,
            createdAt,
          } satisfies ThreadMessage;
        }

        const role = (m.role === 'table_widget' ? 'assistant' : m.role) as 'user' | 'assistant';
        const base: ThreadMessage = {
          id,
          role,
          content: m.content ?? '',
          thinkContent: m.think_content ?? undefined,
          createdAt,
        };
        if (m.role === 'table_widget' && m.card_payload) {
          base.type = 'table_widget';
          base.tablePayload = m.card_payload as ThreadMessage['tablePayload'];
        }
        return base;
      }),
    []
  );

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

  // 从后端同步线程列表（主数据源，支持跨设备）
  useEffect(() => {
    if (!activationCode || !phase) return;
    setThreadsFetched(false);
    let cancelled = false;
    (async () => {
      try {
        const res = await apiClient.get('/simple-chat/threads', {
          params: { activation_code: activationCode, phase: BACKEND_PHASE[phase] },
        });
        const raw = (res.data?.threads ?? []) as Array<{
          id: string;
          title: string;
          status: string;
          createdAt: number;
          dimensionConclusion?: DimensionConclusionData;
        }>;
        const list: ChatThread[] = raw.map((t) => ({
          id: t.id,
          title: t.title,
          status: t.status as 'in-progress' | 'completed',
          messages: [],
          createdAt: t.createdAt,
          dimensionConclusion: t.dimensionConclusion,
        }));
        // 进入页面时为每个会话预加载历史，侧栏可直接显示首行与轮数
        const sessionIdByThread: Record<string, string> = {};
        const hydratedList: ChatThread[] = await Promise.all(
          list.map(async (th) => {
            try {
              const h = await apiClient.get('/simple-chat/history', {
                params: { activation_code: activationCode, phase: BACKEND_PHASE[phase], thread_id: th.id },
              });
              const history: any[] = h.data.messages ?? [];
              const meta = h.data?.metadata ?? {};
              if (meta?.session_id) sessionIdByThread[th.id] = String(meta.session_id);
              const msgs = mapHistoryToThreadMessages(history, meta);
              const concl = meta.dimension_conclusion as DimensionConclusionData | undefined;
              return {
                ...th,
                messages: msgs,
                dimensionConclusion: concl ?? th.dimensionConclusion,
                ...(meta.thread_completed ? { status: 'completed' as const } : {}),
              };
            } catch {
              return th;
            }
          })
        );
        // 先持久化（即便后续被 cancelled 也写入），供请求失败时 fallback
        setThreadsForPhase(activationCode, phase, hydratedList);
        if (cancelled) return;
        setThreads(hydratedList);
        const localActiveId = getActiveThreadId(activationCode, phase);
        const activeId =
          hydratedList.length > 0
            ? (hydratedList.some((x) => x.id === localActiveId) ? localActiveId : hydratedList[0].id)
            : null;
        setActiveThreadIdState(activeId);
        if (activeId) setActiveThreadId(activationCode, phase, activeId);
        const activeThread = hydratedList.find((x) => x.id === activeId) || null;
        if (activeThread) {
          setMessages(activeThread.messages);
          setBackendSyncedThreadId(activeThread.id);
          const sessId = sessionIdByThread[activeThread.id];
          if (sessId) {
            setBackendSessionId(sessId);
            const s = loadSession(activationCode);
            saveSession({ ...s, sessionId: sessId });
          }
        } else {
          setMessages([]);
          setBackendSyncedThreadId(null);
        }
      } catch (err: any) {
        if (cancelled) return;
        if (err?.code === 'ERR_NETWORK' || err?.message?.includes('Network')) {
          setChatError('网络连接失败，若后端正在重启请稍后刷新页面');
        }
        // 网络失败时回退到 localStorage（离线兜底）
        const list = getThreads(activationCode, phase);
        setThreads(list);
        const activeId = getActiveThreadId(activationCode, phase);
        setActiveThreadIdState(activeId);
      }
      if (!cancelled) setThreadsFetched(true);
    })();
    return () => {
      cancelled = true;
    };
  }, [activationCode, phase, mapHistoryToThreadMessages]);

  // 激活线程切换：优先直接使用已预加载内容；仅在“完全首次进入且无会话”时才触发 init。
  useEffect(() => {
    if (!activationCode || !phase || !threadsFetched) return;
    let cancelled = false;
    setInitLoading(true);

    const list = threads;
    const activeId = activeThreadId;

    if (list.length === 0) {
      // 若该 step 已有历史（无 thread_id 默认会话），优先恢复，不主动 init 创建新会话
      (async () => {
        try {
          const historyRes = await apiClient.get('/simple-chat/history', {
            params: { activation_code: activationCode, phase: BACKEND_PHASE[phase] },
          });
          const history: any[] = historyRes.data.messages ?? [];
          const meta = historyRes.data?.metadata ?? {};
          const sessId = historyRes.data?.activation?.session_id || meta?.session_id;
          if (sessId && !cancelled) {
            setBackendSessionId(sessId);
            const s = loadSession(activationCode);
            saveSession({ ...s, sessionId: sessId });
          }
          if (!cancelled && history.length > 0) {
            const recoveredId = getActiveThreadId(activationCode, phase) || createThreadId();
            const msgs = mapHistoryToThreadMessages(history, meta);
            const recoveredThread: ChatThread = {
              id: recoveredId,
              title: '对话 1',
              status: meta.thread_completed ? 'completed' : 'in-progress',
              messages: msgs,
              createdAt: Date.now(),
              dimensionConclusion: (meta.dimension_conclusion as DimensionConclusionData | undefined) || undefined,
            };
            addThread(activationCode, phase, recoveredThread);
            const merged = getThreads(activationCode, phase);
            setThreads(merged);
            setActiveThreadIdState(recoveredId);
            setActiveThreadId(activationCode, phase, recoveredId);
            setBackendSyncedThreadId(recoveredId);
            setMessages(msgs);
          } else {
            // 仅首次且无历史时才触发 init 生成首轮问题
            const tid = createThreadId();
            const initRes = await apiClient.post('/simple-chat/init', {
              activation_code: activationCode,
              phase: BACKEND_PHASE[phase],
              thread_id: tid,
            });
            const initMsgs: any[] = initRes.data.messages ?? [];
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
            setThreads(getThreads(activationCode, phase));
            setActiveThreadId(activationCode, phase, tid);
            setActiveThreadIdState(tid);
            setBackendSyncedThreadId(tid);
            setMessages(msgs);
          }
        } catch (err: any) {
          if (!cancelled && (err?.code === 'ERR_NETWORK' || err?.message?.includes('Network'))) {
            setChatError('网络连接失败，若后端正在重启请稍后刷新页面');
          }
        }
        if (!cancelled) setInitLoading(false);
      })();
      return;
    }

    if (activeId) {
      const thread = list.find((t) => t.id === activeId);
      if (thread) {
        setMessages(thread.messages);
        setBackendSyncedThreadId(activeId);
        setInitLoading(false);
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
      if (first) setMessages(first.messages);
      setInitLoading(false);
    }

    return () => { cancelled = true; };
  }, [activationCode, phase, threadsFetched, threadListSignature, activeThreadId, mapHistoryToThreadMessages]);

  // Persist messages + dimensionConclusion to active (backend-synced) thread when they change
  // 注意：不要在此调用 setThreads(getThreads())，否则会改变 threads 引用并触发上方加载 effect，造成 initLoading 反复与界面闪烁
  useEffect(() => {
    if (!activationCode || !phase || !activeThreadId || initLoading || activeThreadId !== backendSyncedThreadId) return;
    const t = threads.find((x) => x.id === activeThreadId);
    if (t && messages.length > 0) {
      if (t.status === 'completed') return;
      const lastConcl = messages.filter((m) => m.type === 'dimension_conclusion').pop();
      const toSave: ChatThread = { ...t, messages };
      if (lastConcl?.conclusionData) toSave.dimensionConclusion = lastConcl.conclusionData;
      saveThread(activationCode, phase, toSave);
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
    setConclusionLoading(false);
    setSending(true);

    abortControllerRef.current = new AbortController();
    try {
      const apiBase = (process.env.NEXT_PUBLIC_API_URL || '').trim();
      const streamUrl = `${apiBase ? apiBase.replace(/\/+$/, '') : ''}/api/v1/simple-chat/message/stream`;
      const token = typeof window !== 'undefined' ? localStorage.getItem('token') : null;
      const res = await fetch(streamUrl, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify({
          activation_code: activationCode,
          message: userMsg.content,
          phase: BACKEND_PHASE[phase],
          thread_id: activeThreadId || undefined,
        }),
        signal: abortControllerRef.current.signal,
      });
      if (!res.ok) {
        if (res.status === 401) {
          throw new Error('登录状态已失效，请重新登录后继续对话');
        }
        let detail = '';
        try {
          const errPayload = await res.json();
          detail = errPayload?.detail || errPayload?.message || '';
        } catch {}
        throw new Error(detail || `请求失败（${res.status}）`);
      }
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
            if (payload.think_start) {
              setMessages((prev) =>
                prev.map((m) =>
                  m.id === assistantId ? { ...m, thinkStreaming: true, thinkChunkContent: '' } : m
                )
              );
            }
            if (payload.think_chunk) {
              const chunk = typeof payload.think_chunk === 'string' ? payload.think_chunk : '';
              if (chunk) {
                setMessages((prev) =>
                  prev.map((m) =>
                    m.id === assistantId
                      ? { ...m, thinkChunkContent: (m.thinkChunkContent || '') + chunk }
                      : m
                  )
                );
              }
            }
            if (payload.think_end != null) {
              const thinkContent = typeof payload.think_end === 'string' ? payload.think_end : '';
              setMessages((prev) =>
                prev.map((m) =>
                  m.id === assistantId
                    ? { ...m, thinkContent, thinkStreaming: false, thinkChunkContent: undefined }
                    : m
                )
              );
            }
            if (payload.chunk) {
              fullReply += payload.chunk;
              setMessages((prev) =>
                prev.map((m) =>
                  m.id === assistantId ? { ...m, content: (m.content || '') + payload.chunk } : m
                )
              );
            }
            if (payload.conclusion_loading) {
              setConclusionLoading(true);
            }
            if (payload.dimension_conclusion) {
              setConclusionLoading(false);
              const concl = payload.dimension_conclusion as DimensionConclusionData;
              const conclMsg: ThreadMessage = {
                id: `concl_${Date.now()}`,
                role: 'assistant',
                content: '',
                type: 'dimension_conclusion',
                conclusionData: concl,
                conclusionCollapsed: false,
                conclusionConfirmed: false,
                createdAt: Date.now(),
              };
              setMessages((prev) => [...prev, conclMsg]);
            }
            if (payload.table_widget) {
              const tablePayload = payload.table_widget as ThreadMessage['tablePayload'];
              const tableMsg: ThreadMessage = {
                id: `table_${Date.now()}`,
                role: 'assistant',
                content: '',
                type: 'table_widget',
                tablePayload: tablePayload ?? undefined,
                createdAt: Date.now(),
              };
              setMessages((prev) => [...prev, tableMsg]);
            }
            if (payload.done && payload.response != null) {
              fullReply = payload.response;
              const doneAt = Date.now();
              setMessages((prev) =>
                prev.map((m) =>
                  m.id === assistantId
                    ? { ...m, content: fullReply, thinkStreaming: false, createdAt: m.createdAt ?? doneAt }
                    : m
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
      setConclusionLoading(false);
      setMessages((prev) =>
        prev.map((m) =>
          m.id === assistantId && m.thinkStreaming ? { ...m, thinkStreaming: false, thinkChunkContent: undefined } : m
        )
      );
      abortControllerRef.current = null;
      // 发送完成后将焦点还给输入框，支持连续 Enter 对话无需再点鼠标。
      requestAnimationFrame(() => {
        if (!isReadOnly) inputRef.current?.focus();
      });
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

  const handleConfirmConclusion = async () => {
    if (!activationCode || !phase) return;
    const targetThreadId = activeThreadId || backendSyncedThreadId;
    if (!targetThreadId) return;
    const th = threads.find((t) => t.id === targetThreadId) || selectedThread;
    if (!th) return;
    const lastConcl = messages.filter((m) => m.type === 'dimension_conclusion').pop();
    if (!lastConcl?.conclusionData) return;
    try {
      await apiClient.post('/simple-chat/thread/complete', {
        activation_code: activationCode,
        phase: BACKEND_PHASE[phase],
        thread_id: targetThreadId,
      });
    } catch (e) {
      console.warn('thread/complete API failed:', e);
    }
    const confirmedMessages = messages.map((m) =>
      m.type === 'dimension_conclusion'
        ? { ...m, conclusionConfirmed: true, conclusionCollapsed: false }
        : m
    );
    setMessages(confirmedMessages);
    const updated: ChatThread = {
      ...th,
      status: 'completed',
      messages: confirmedMessages,
      dimensionConclusion: lastConcl.conclusionData,
    };
    saveThread(activationCode, phase, updated);
    // 使用 functional update 直接更新 state，避免依赖 getThreads 被 persist effect 覆盖
    setThreads((prev) => {
      const idx = prev.findIndex((t) => t.id === targetThreadId);
      if (idx < 0) return [...prev, updated];
      return prev.map((t) => (t.id === targetThreadId ? updated : t));
    });
  };

  const handleContinueChat = async (conclusionMsg?: ThreadMessage) => {
    const lastConcl = messages.filter((m) => m.type === 'dimension_conclusion').pop();
    const toCollapse = conclusionMsg ?? lastConcl;
    if (toCollapse && toCollapse.type === 'dimension_conclusion') {
      setMessages((prev) =>
        prev.map((m) =>
          m.id === toCollapse.id ? { ...m, conclusionCollapsed: true, conclusionConfirmed: false } : m
        )
      );
    }
    if (activationCode && phase && activeThreadId) {
      try {
        await apiClient.post('/simple-chat/thread/reopen', {
          activation_code: activationCode,
          phase: BACKEND_PHASE[phase],
          thread_id: activeThreadId,
        });
      } catch (err: any) {
        if (err?.response?.status === 401 || err?.message?.includes('401')) {
          setChatError(t('explore.chat.tokenExpired') || '登录已失效，请重新登录后刷新页面');
          return;
        }
        if (err?.response?.status === 400) {
          setChatError(getApiErrorMessage(err, '无法继续对话，请刷新页面后重试'));
          return;
        }
        setChatError(getApiErrorMessage(err, '网络异常，请稍后重试'));
        return;
      }
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

  const handleTableConfirm = useCallback(
    async (_msgId: string, payload: { step?: number }, rows: Record<string, unknown>[]) => {
      if (!activationCode || !activeThreadId || phase !== 'rumination' || sending) return;
      try {
        const res = await ruminationApi.submitTable(
          activationCode,
          activeThreadId,
          payload.step ?? 1,
          rows as Record<string, unknown>[]
        );
        const nextTable = (res?.data as { next_table_widget?: ThreadMessage['tablePayload'] })
          ?.next_table_widget;
        if (nextTable) {
          const tableMsg: ThreadMessage = {
            id: `table_${Date.now()}`,
            role: 'assistant',
            content: '',
            type: 'table_widget',
            tablePayload: nextTable,
            createdAt: Date.now(),
          };
          setMessages((prev) => [...prev, tableMsg]);
        }
        handleSend('我已确认表格，请继续。', false);
      } catch {
        setChatError('提交失败，请重试');
      }
    },
    [activationCode, activeThreadId, phase, sending, handleSend]
  );

  if (!session || !phaseMeta || !phaseInfo) return null;

  const phaseClass =
    phase === 'values'
      ? 'values'
      : phase === 'strengths'
        ? 'strength'
        : phase === 'interests'
          ? 'interest'
          : phase === 'purpose'
            ? 'purpose'
            : 'rumination';

  return (
    <div className="flow-light h-screen flex flex-col overflow-hidden" data-phase={phase}>
      <ChatPhaseBackground phase={phase} />
      <div className="flex-1 flex min-h-0 relative z-10 pt-14 overflow-hidden">
        <ChatPhaseSidebar
          phase={phase}
          phaseLabel={phaseLabel}
          threads={threadsForSidebar}
          activeThreadId={activeThreadId}
          onSelectThread={handleSelectThread}
          onNewChat={handleNewChat}
          onDeleteThread={handleDeleteThread}
          canNewChat={threads.length < 5}
        />
        <div className="flex-1 flex flex-col min-w-0 min-h-0 overflow-hidden">
          <header className="flex-shrink-0 backdrop-blur border-b border-black/[0.05] bg-white/70 px-6 py-4">
            <div className="flex items-start justify-between gap-4 max-w-4xl mx-auto">
              <div className="flex-1 min-w-0">
                <h1 className={`text-lg font-semibold ${phaseMeta.color}`}>
                  {phaseInfo.num} {phaseLabel}
                </h1>
                <p className="text-sm text-neutral-600 leading-relaxed mt-1">
                  {phaseMeta.desc} {phaseMeta.hint}
                </p>
                {phase === 'rumination' && activationCode && (
                  <RuminationSectionProgress activationCode={activationCode} className="mt-2" />
                )}
              </div>
              <button
                type="button"
                onClick={handleCompleteAndContinue}
                disabled={!canContinue}
                title={!canContinue ? t('explore.chat.selectCompletedHint') : ''}
                className={`flex-shrink-0 px-5 py-2 rounded-full text-sm font-medium transition-all ${
                  canContinue ? 'bg-bd-ui-accent text-white' : 'opacity-50 cursor-not-allowed bg-neutral-300'
                }`}
              >
                {t('explore.chat.completeAndContinue')} <ChevronRight size={14} className="inline" />
              </button>
            </div>
          </header>

          <div className="flex-1 flex flex-col min-h-0 overflow-hidden px-6 py-4">
            {/* 全宽对话区：滚动条贴右侧，消息气泡浮在背景之上 */}
            <div className="flow-chat-box flex-1 min-h-0 min-w-0 flex flex-col relative">
              <div ref={chatBodyRef} className="flow-chat-body flex-1 min-h-0 overflow-y-auto">
                <div className="flow-dimension-label">
                  <span className="flow-dimension-dot" />
                  {t('explore.chat.exploringWithDim', { dim: phaseLabel })}
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
                  <p className="flow-progress-text text-center py-8 text-sm">{t('explore.chat.preparingFirstQuestion')}</p>
                ) : (
                  messages.map((m, idx) => (
                    <div key={m.id} className={m.role === 'user' || m.type === 'dimension_conclusion' ? (m.role === 'user' ? 'flow-msg-user' : '') : ''}>
                      {m.type === 'table_widget' && m.tablePayload ? (
                        <div className="flow-msg-table-wrap my-3">
                          <RuminationTableWidget
                            payload={m.tablePayload}
                            onConfirm={(rows) =>
                              handleTableConfirm(m.id, m.tablePayload!, rows)
                            }
                            disabled={sending}
                          />
                        </div>
                      ) : m.type === 'dimension_conclusion' && m.conclusionData ? (
                        <div className="flow-msg-conclusion-wrap">
                          <DimensionConclusionCard
                            phase={phaseClass}
                            data={m.conclusionData}
                            isCompleted={isSelectedCompleted || !!m.conclusionConfirmed}
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
                          thinkContent={m.thinkContent}
                          thinkStreaming={m.thinkStreaming}
                          thinkChunkContent={m.thinkChunkContent}
                          thinkPlaceholders={[
                            t('explore.chat.thinkInProgress1'),
                            t('explore.chat.thinkInProgress2'),
                            t('explore.chat.thinkInProgress3'),
                            t('explore.chat.thinkInProgress4'),
                            t('explore.chat.thinkInProgress5'),
                            t('explore.chat.thinkInProgress6'),
                          ]}
                          thinkLabel={t('explore.chat.thinkProcess')}
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
                {conclusionLoading && (
                  <div className="flow-msg-conclusion-wrap my-3">
                    <div className="rounded-xl border border-[var(--flow-border)] bg-[var(--flow-card-bg)] p-4 flex items-center gap-3 text-[var(--flow-text-muted)] text-sm animate-pulse">
                      <div className="w-5 h-5 border-2 border-current border-t-transparent rounded-full animate-spin" />
                      <span>{t('explore.chat.conclusionLoading')}</span>
                    </div>
                  </div>
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

          {/* 对话输入框：固定在最底部 */}
          <div className="flex-shrink-0 w-full px-6 pb-5 pt-3 bg-bd-bg/95 backdrop-blur-sm border-t border-black/[0.05]">
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
                        ? t('explore.chat.placeholderReadOnly')
                        : hasCollapsedConclusion
                          ? t('explore.chat.placeholderRefine')
                          : t('explore.chat.placeholder')
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
                      disabled={((!sending && !input.trim()) || isReadOnly) as boolean}
                      className={`flow-send-btn ${sending ? 'is-stop' : ''}`}
                    >
                      {sending ? <Square size={16} strokeWidth={0} fill="white" /> : <ArrowUp size={16} strokeWidth={2.2} />}
                    </button>
                  </div>
                </div>
              </form>
            </div>
            <div className="pt-2">
              <p className="text-xs text-neutral-500">{t('explore.chat.autoSave')}</p>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
