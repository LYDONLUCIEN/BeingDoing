'use client';

import { useState, useEffect, useRef } from 'react';
import { useRouter, useParams } from 'next/navigation';
import { motion } from 'framer-motion';
import { Lock, CheckCircle2, ChevronRight } from 'lucide-react';
import { apiClient } from '@/lib/api/client';
import MessageContent from '@/components/explore/MessageContent';
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
  ring: string;
  desc: string;
  hint: string;
  unlockHint: string;
}> = {
  values: {
    color: 'text-bd-phase-values',
    bg: 'border border-bd-phase-values',
    ring: 'ring-bd-phase-values/50',
    desc: '探索你最深层的信念。什么对你最重要？哪些原则是你绝不妥协的？',
    hint: '这一步帮你发现5个核心价值观关键词。',
    unlockHint: '',
  },
  strengths: {
    color: 'text-bd-phase-strengths',
    bg: 'border border-bd-phase-strengths',
    ring: 'ring-bd-phase-strengths/50',
    desc: '探索你的天赋与禀赋。有些事你做起来不费力，却让别人惊叹。',
    hint: '这一步帮你发现10件真正擅长的事。',
    unlockHint: '完成「信念」探索后解锁',
  },
  interests: {
    color: 'text-bd-phase-interests',
    bg: 'border border-bd-phase-interests',
    ring: 'ring-bd-phase-interests/50',
    desc: '探索你的热忱。什么话题让你停不下来？什么场景让时间消失？',
    hint: '这一步帮你找到真正让你忘我的事。',
    unlockHint: '完成「禀赋」探索后解锁',
  },
  purpose: {
    color: 'text-bd-phase-purpose',
    bg: 'border border-bd-phase-purpose',
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

  const handleSend = async () => {
    if (!activationCode || !input.trim() || sending) return;
    const userMsg: SimpleMessage = {
      id: `u_${Date.now()}`,
      role: 'user',
      content: input.trim(),
    };
    const assistantId = `a_${Date.now()}`;
    setMessages((prev) => [...prev, userMsg, { id: assistantId, role: 'assistant', content: '' }]);
    setInput('');
    setChatError(null);
    setSending(true);

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

  return (
    <div className="min-h-screen bg-bd-gradient text-bd-fg flex flex-col">

      {/* Top progress bar */}
      <div className="fixed top-14 left-0 right-0 z-40 backdrop-blur" style={{ backgroundColor: 'var(--bd-nav-bg)', borderBottom: '1px solid var(--bd-border-soft)' }}>
        <div className="max-w-5xl mx-auto px-4 py-3 flex items-center gap-3 overflow-x-auto">
          {PHASES.map((p, i) => {
            const unlocked = session.unlockedPhases.includes(p.key);
            const isActive = p.key === phase;
            const meta = PHASE_META[p.key];
            return (
              <button
                key={p.key}
                type="button"
                disabled={!unlocked}
                onClick={() => unlocked && router.push(`/explore/chat/${p.key}`)}
                className={`flex items-center gap-2 px-3 py-1.5 rounded-full text-sm font-medium transition-all flex-shrink-0 ${
                  isActive
                    ? `${meta.bg} border ${meta.color}`
                    : unlocked
                    ? 'text-bd-muted hover:text-bd-fg hover:bg-bd-overlay-md'
                    : 'text-bd-ghost cursor-not-allowed'
                }`}
              >
                {unlocked && !isActive ? (
                  <CheckCircle2 size={13} className="text-bd-subtle" />
                ) : !unlocked ? (
                  <Lock size={13} />
                ) : null}
                <span className="text-xs font-mono text-current opacity-50 mr-0.5">{p.num}</span>
                {p.label}
              </button>
            );
          })}
        </div>
      </div>

      <div className="flex-1 max-w-3xl mx-auto w-full px-4 pt-28 pb-6 flex flex-col gap-4">

        {/* Phase header */}
        <motion.div
          key={phase}
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.4 }}
          className="space-y-1"
        >
          <div className="flex items-center gap-2">
            <span className="text-xs font-mono text-bd-ghost">{phaseInfo.num}</span>
            <h1 className={`text-2xl font-bold ${phaseMeta.color}`}>{phaseInfo.label}</h1>
          </div>
          <p className="text-sm text-bd-muted leading-relaxed">{phaseMeta.desc}</p>
          <p className="text-xs text-bd-subtle italic">{phaseMeta.hint}</p>
        </motion.div>

        {/* Chat area */}
        <div
          className={`flex-1 rounded-2xl border bd-chat-card ${phaseMeta.bg} flex flex-col min-h-[400px] overflow-hidden`}
          data-phase={phase}
        >
          {/* Messages */}
          <div className="flex-1 overflow-y-auto p-4 md:p-6 space-y-4">
            {initLoading ? (
              <div className="flex items-center justify-center py-12">
                <div className="flex gap-1.5">
                  {[0, 1, 2].map((i) => (
                    <motion.div
                      key={i}
                      className="w-2 h-2 rounded-full bg-bd-subtle"
                      animate={{ opacity: [0.3, 1, 0.3] }}
                      transition={{ duration: 1.2, delay: i * 0.2, repeat: Infinity }}
                    />
                  ))}
                </div>
              </div>
            ) : messages.length === 0 ? (
              <p className="text-sm text-bd-subtle text-center py-8">正在准备第一个问题…</p>
            ) : (
              messages.map((m) => (
                <div key={m.id} className={`flex ${m.role === 'user' ? 'justify-end' : 'justify-start'}`}>
                  <div
                    className={`max-w-[85%] rounded-2xl px-4 py-3 text-sm leading-relaxed ${
                      m.role === 'user'
                        ? 'bg-bd-primary text-bd-primary-fg rounded-br-md'
                        : 'bg-bd-surface-2 text-bd-fg rounded-bl-md'
                    }`}
                  >
                    {m.role === 'assistant' ? (
                      <MessageContent content={m.content} markdown className="assistant" />
                    ) : (
                      <span className="whitespace-pre-wrap">{m.content}</span>
                    )}
                  </div>
                </div>
              ))
            )}
            <div ref={messagesEndRef} />
          </div>

          {/* Input */}
          {chatError && <p className="px-4 text-xs text-bd-err">{chatError}</p>}
          <div className="border-t border-bd-border-soft p-3 flex items-end gap-2">
            <textarea
              rows={2}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder="输入你的回答…（Shift+Enter 换行，Enter 发送）"
              className="flex-1 resize-none rounded-xl border border-bd-border bg-bd-overlay px-4 py-2.5 text-sm outline-none focus:border-bd-primary transition-colors text-bd-fg"
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
              className="rounded-xl px-4 py-2.5 text-sm font-medium transition-all flex-shrink-0 text-bd-primary-fg disabled:opacity-30"
              style={{ background: 'var(--bd-primary)' }}
            >
              {sending ? (
                <motion.span animate={{ opacity: [0.5, 1, 0.5] }} transition={{ duration: 1, repeat: Infinity }}>
                  发送中
                </motion.span>
              ) : '发送'}
            </button>
          </div>
        </div>

        {/* Complete phase button */}
        <div className="flex items-center justify-between pt-2 pb-4">
          <p className="text-xs text-bd-subtle">
            对话记录自动保存。随时可以关闭页面，下次回来用同一激活码继续。
          </p>
          <button
            type="button"
            onClick={handleCompletePhase}
            className={`flex items-center gap-1.5 px-4 py-2 rounded-xl border text-sm font-medium transition-all ${phaseMeta.color} ${phaseMeta.bg} hover:brightness-110`}
          >
            完成此步，进入下一步
            <ChevronRight size={14} />
          </button>
        </div>

      </div>
    </div>
  );
}
