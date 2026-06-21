/**
 * useComboGuideStream
 *
 * Step3 matrix 模式下，按 comboId 拉取/复用组合引导语，并以"假流式逐字"
 * 方式把真实内容渲染到 messages 中。
 *
 * 设计要点（解决原 effect 的 race condition）：
 * 1. 每个 comboId 的生成任务由 ref Map 持有，脱离 React effect 重跑。
 *    切到别的 combo 不会 cancel 当前任务；任务跑完后无论用户停在哪，
 *    都会把真实消息写入 messages（命中已存在则跳过）。
 * 2. 同一 comboId 全局只发一次 ensureComboGuide + pollComboGuide，
 *    后端 is_in_flight + 本 Map 双重去重。
 * 3. poll 拿到完整内容后，进入 streaming 阶段：setInterval 把完整内容
 *    按字符切片逐步追加到对应 message 的 content 字段，模拟 AI 打字效果。
 *    期间 placeholder 行（thinkPlaceholders）继续轮换显示"前面还有任务"。
 *
 * 返回 isBusy 供页面层做交互门控（替代原 ruminationGuideBusy 的语义）。
 */
'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import type { ThreadMessage } from './threads';

export type ComboGuideStatus = 'idle' | 'fetching' | 'streaming' | 'done' | 'error';

interface ComboTask {
  status: ComboGuideStatus;
  /** 已生成的完整文本（streaming 阶段用作逐字追加的源） */
  fullText: string;
  /** 后端原始消息（含 hypCandidates 等字段），映射成 ThreadMessage 时用 */
  rawMessage: Record<string, unknown> | null;
  /** streaming 阶段已追加到的字符偏移 */
  streamedChars: number;
  /** streaming 定时器 */
  streamTimer: ReturnType<typeof setInterval> | null;
}

interface UseComboGuideStreamOptions {
  enabled: boolean;
  activationCode: string | null | undefined;
  threadId: string | null | undefined;
  /** 当前选中的 comboId；变化时自动触发该 combo 的生成（若尚未生成过） */
  comboId: string | null | undefined;
  /** 由页面注入：把后端原始 message 映射为 ThreadMessage（复用 mapHistoryToThreadMessages） */
  mapGuideMessage: (raw: Record<string, unknown>) => ThreadMessage | null;
  /** 由页面注入：写入/更新 messages state */
  setMessages: (updater: (prev: ThreadMessage[]) => ThreadMessage[]) => void;
  /** 由页面注入：读取当前最新 messages（用于跳过 history 已加载的 combo，避免重复发起） */
  getMessages: () => ThreadMessage[];
  /** 由页面注入：busy 状态变化回调（页面据此 OR 到既有 ruminationGuideBusy 等门控） */
  onBusyChange?: (busy: boolean) => void;
}

/** 逐字追加间隔（ms）。每 tick 推进若干字符以保持节奏自然。 */
const STREAM_TICK_MS = 28;
/** 每个 tick 推进的字符数（中文按字、英文按字符，含标点）。 */
const STREAM_CHARS_PER_TICK = 2;
/** 生成 message id 前缀 */
const PLACEHOLDER_ID_PREFIX = 'combo_guide_placeholder_';
/** 真实消息 id 前缀（避免与 history 消息 h_ 前缀冲突） */
const REAL_ID_PREFIX = 'combo_guide_real_';

function makePlaceholderId(comboId: string): string {
  return `${PLACEHOLDER_ID_PREFIX}${comboId}`;
}
function makeRealId(comboId: string): string {
  return `${REAL_ID_PREFIX}${comboId}`;
}
/** 判断 messages 里是否已存在该 combo 的 assistant 引导消息（含 history 加载与 hook 自己写入的）。 */
function messagesHaveGuide(messages: ThreadMessage[], cid: string): boolean {
  return messages.some(
    (m) => m.comboId === cid && m.role === 'assistant' && !m.comboGuidePlaceholder,
  );
}

export function useComboGuideStream({
  enabled,
  activationCode,
  threadId,
  comboId,
  mapGuideMessage,
  setMessages,
  getMessages,
  onBusyChange,
}: UseComboGuideStreamOptions) {
  /** comboId → 任务状态。组件卸载时统一清理定时器。 */
  const tasksRef = useRef<Map<string, ComboTask>>(new Map());
  /** 已发起过 ensureComboGuide 的 comboId 集合（防止 effect 重跑重复发起）。 */
  const initiatedRef = useRef<Set<string>>(new Set());
  /** 最新 props 的镜像，供异步回调读取，避免闭包陈旧。 */
  const propsRef = useRef({ activationCode, threadId, mapGuideMessage, setMessages, getMessages });
  propsRef.current = { activationCode, threadId, mapGuideMessage, setMessages, getMessages };

  /** 是否有任务处于 fetching/streaming（供页面做交互门控，替代原 ruminationGuideBusy）。 */
  const [isBusy, setIsBusy] = useState(false);
  const onBusyChangeRef = useRef(onBusyChange);
  onBusyChangeRef.current = onBusyChange;
  const recomputeBusy = useCallback(() => {
    const busy = Array.from(tasksRef.current.values()).some(
      (t) => t.status === 'fetching' || t.status === 'streaming',
    );
    setIsBusy(busy);
    onBusyChangeRef.current?.(busy);
  }, []);

  /** 清理指定 combo 任务的定时器（不动 status）。 */
  const clearTimers = useCallback((cid: string) => {
    const task = tasksRef.current.get(cid);
    if (!task) return;
    if (task.streamTimer) {
      clearInterval(task.streamTimer);
      task.streamTimer = null;
    }
  }, []);

  /** 启动逐字流式：把 task.fullText 分片追加到对应真实消息的 content。 */
  const startStreaming = useCallback(
    (cid: string) => {
      const task = tasksRef.current.get(cid);
      if (!task || !task.rawMessage) return;
      const { setMessages: sm, mapGuideMessage: mapper } = propsRef.current;

      // 首次插入"真实消息"骨架（content 从空开始，逐字追加）
      const mapped = mapper(task.rawMessage);
      if (!mapped) {
        task.status = 'error';
        clearTimers(cid);
        recomputeBusy();
        return;
      }
      const realId = makeRealId(cid);
      const initialMsg: ThreadMessage = {
        ...mapped,
        id: realId,
        content: '',
        // 流式期间保留 streaming 标记，让 FlowAiMessage 显示光标（contentMode=markdown 时
        // 由 streaming prop 驱动；thinkPlaceholders 此时不再渲染，因为 content 已存在）
        comboGuidePlaceholder: false,
      };
      sm((prev) => {
        const withoutPlaceholder = prev.filter(
          (m) => m.id !== makePlaceholderId(cid) && m.id !== realId,
        );
        return [...withoutPlaceholder, initialMsg];
      });
      task.status = 'streaming';
      task.streamedChars = 0;
      recomputeBusy();

      task.streamTimer = setInterval(() => {
        const t = tasksRef.current.get(cid);
        if (!t) return;
        t.streamedChars = Math.min(t.streamedChars + STREAM_CHARS_PER_TICK, t.fullText.length);
        const slice = t.fullText.slice(0, t.streamedChars);
        const { setMessages: sm2 } = propsRef.current;
        sm2((prev) =>
          prev.map((m) => (m.id === realId ? { ...m, content: slice } : m)),
        );
        if (t.streamedChars >= t.fullText.length) {
          if (t.streamTimer) {
            clearInterval(t.streamTimer);
            t.streamTimer = null;
          }
          t.status = 'done';
          recomputeBusy();
          // 流式结束：移除 streaming 标记（content 已完整）
          sm2((prev) =>
            prev.map((m) => (m.id === realId ? { ...m, content: t.fullText } : m)),
          );
        }
      }, STREAM_TICK_MS);
    },
    [clearTimers, recomputeBusy],
  );

  /** 发起并等待单个 combo 的引导语生成完成（poll），完成后启动流式。 */
  const ensureCombo = useCallback(
    async (cid: string) => {
      const { activationCode: ac, threadId: tid, getMessages: gm } = propsRef.current;
      if (!ac) return;
      if (initiatedRef.current.has(cid)) return;
      // history 已加载完该 combo 的引导语（或之前的会话已写入）→ 直接标 done，不重复发起
      if (messagesHaveGuide(gm(), cid)) {
        initiatedRef.current.add(cid);
        return;
      }
      initiatedRef.current.add(cid);

      let task = tasksRef.current.get(cid);
      if (!task) {
        task = {
          status: 'fetching',
          fullText: '',
          rawMessage: null,
          streamedChars: 0,
          streamTimer: null,
        };
        tasksRef.current.set(cid, task);
      } else if (task.status === 'done' || task.status === 'streaming') {
        // 已完成或正在流式：不重复发起
        initiatedRef.current.delete(cid);
        return;
      } else {
        task.status = 'fetching';
      }
      recomputeBusy();

      // 插入/确保 placeholder 存在（fetching 阶段显示静态轮换文案）
      const placeholderId = makePlaceholderId(cid);
      const { setMessages: sm } = propsRef.current;
      sm((prev) => {
        if (prev.some((m) => m.id === placeholderId)) return prev;
        return [
          ...prev,
          {
            id: placeholderId,
            role: 'assistant' as const,
            content: '',
            createdAt: Date.now(),
            comboId: cid,
            filterStep: 3,
            comboGuidePlaceholder: true,
          },
        ];
      });

      try {
        const { ruminationApi } = await import('@/lib/api/rumination');
        const res = await ruminationApi.ensureComboGuide(ac, cid, tid ?? undefined);

        // 同步路径（legacy，理论不再发生）：直接拿到 message
        const guide = res.data?.message as Record<string, unknown> | undefined | null;
        if (guide && (guide as any).role === 'assistant' && typeof (guide as any).content === 'string') {
          const t = tasksRef.current.get(cid);
          if (t) {
            t.rawMessage = guide;
            t.fullText = ((guide as any).content as string) || '';
          }
          startStreaming(cid);
          return;
        }

        // 队列路径：poll /history 直到出现
        if (res.data?.status === 'queued' || res.data?.created === false) {
          const polled = await ruminationApi.pollComboGuide(ac, cid, tid ?? undefined);
          const t = tasksRef.current.get(cid);
          if (!polled) {
            // 超时：保留 placeholder，标 error（视觉上仍显示占位文案）
            if (t) {
              t.status = 'error';
              recomputeBusy();
            }
            return;
          }
          if (t) {
            t.rawMessage = polled;
            t.fullText = (typeof (polled as any).content === 'string'
              ? ((polled as any).content as string)
              : '') || '';
          }
          startStreaming(cid);
        }
      } catch (err) {
        console.error('useComboGuideStream ensureCombo failed:', err);
        const t = tasksRef.current.get(cid);
        if (t) {
          t.status = 'error';
          recomputeBusy();
        }
      }
    },
    [startStreaming, recomputeBusy],
  );

  /** comboId 变化或 enabled 开启时触发当前 combo 的生成（若尚未生成过）。 */
  useEffect(() => {
    if (!enabled || !activationCode || !comboId) return;
    const cid = comboId;
    // 已完成/已记录任务：不重复发起
    const existing = tasksRef.current.get(cid);
    if (existing && (existing.status === 'done' || existing.status === 'streaming')) return;
    void ensureCombo(cid);
  }, [enabled, activationCode, comboId, ensureCombo]);

  /** enabled 变 false（退出 matrix 模式 / 切到 3b）时自动清理所有任务与消息。
   *  写在 hook 内部是为了避免页面层 effect/hook 顺序耦合。 */
  const prevEnabledRef = useRef(enabled);
  useEffect(() => {
    if (prevEnabledRef.current && !enabled) {
      tasksRef.current.forEach((_, cid) => clearTimers(cid));
      tasksRef.current.clear();
      initiatedRef.current.clear();
      setMessages((prev) =>
        prev.filter(
          (m) =>
            !m.comboGuidePlaceholder &&
            !(m.id && m.id.startsWith(REAL_ID_PREFIX)),
        ),
      );
      setIsBusy(false);
      onBusyChangeRef.current?.(false);
    }
    prevEnabledRef.current = enabled;
  }, [enabled, clearTimers, setMessages]);

  /** 卸载时清理所有定时器。 */
  useEffect(() => {
    const snapshot = tasksRef.current;
    return () => {
      snapshot.forEach((_, cid) => clearTimers(cid));
    };
  }, [clearTimers]);

  return {
    /**
     * 是否有任务正在 fetching/streaming。页面可用作交互门控（替代原 ruminationGuideBusy）：
     * - 为 true 时阻塞线程切换、表格提交、filter 前后导航等。
     */
    isBusy,
    /**
     * 清除某个 combo 的所有痕迹（用于"重置 matrix / 切子步"场景）。
     * 会停止定时器并把该 combo 的 placeholder/真实消息从 messages 移除。
     */
    clearCombo: useCallback(
      (cid: string) => {
        clearTimers(cid);
        tasksRef.current.delete(cid);
        initiatedRef.current.delete(cid);
        const placeholderId = makePlaceholderId(cid);
        const realId = makeRealId(cid);
        setMessages((prev) => prev.filter((m) => m.id !== placeholderId && m.id !== realId));
      },
      [clearTimers, setMessages],
    ),
    /** 清除所有 combo（用于退出 matrix 模式） */
    clearAll: useCallback(() => {
      tasksRef.current.forEach((_, cid) => clearTimers(cid));
      tasksRef.current.clear();
      initiatedRef.current.clear();
      setMessages((prev) =>
        prev.filter(
          (m) =>
            !m.comboGuidePlaceholder &&
            !(m.id && m.id.startsWith(REAL_ID_PREFIX)),
        ),
      );
    }, [clearTimers, setMessages]),
    /**
     * 停止所有 streaming/fetching 的定时器，但保留 messages 里已写入的内容。
     * 用于"用户主动输入打断引导流"：已生成的部分内容留在对话里作为上下文。
     */
    stopAll: useCallback(() => {
      tasksRef.current.forEach((task, cid) => {
        clearTimers(cid);
        // streaming 中途打断：把已流式部分作为最终 content 保留，status 标 done
        if (task.status === 'streaming') {
          task.status = 'done';
          const realId = makeRealId(cid);
          setMessages((prev) =>
            prev.map((m) =>
              m.id === realId ? { ...m, content: task.fullText.slice(0, task.streamedChars) } : m,
            ),
          );
        }
        // fetching 中途打断：移除 placeholder（用户已经发新消息，不再需要占位）
        if (task.status === 'fetching') {
          const placeholderId = makePlaceholderId(cid);
          setMessages((prev) => prev.filter((m) => m.id !== placeholderId));
          task.status = 'idle';
        }
      });
      recomputeBusy();
    }, [clearTimers, setMessages, recomputeBusy]),
  };
}
