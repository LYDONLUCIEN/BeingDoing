/**
 * Rumination v4 Zustand store（2026-08-06 版，ADR-0015）
 *
 * 后端为单一数据源,本 store 是后端 state 的镜像(乐观更新 + 失败回滚)。
 * 变更:chips/fallback 删除;结论卡用户手填;平衡点判定走独立 SSE(confirm/analysis-stream)。
 */

import { create } from 'zustand';
import {
  BalanceAnalysis,
  BalanceAnalysisEvent,
  ComboChatEvent,
  ComboMeta,
  ComboSession,
  ConclusionCard,
  MainSection,
  RuminationV4State,
  SseStreamHandle,
  fetchComboDetail,
  fetchCombos,
  fetchV4State,
  createAndStart as apiCreateAndStart,
  startDiscussion as apiStartDiscussion,
  deleteCombo as apiDeleteCombo,
  patchConclusionCard as apiPatchCard,
  setComboStatus as apiSetStatus,
  setActiveCombo as apiSetActive,
  updateFinalSelection as apiUpdateFinal,
  submitFinalSelection as apiSubmitFinal,
  streamComboChat,
  streamConfirmConclusion,
  streamAnalysis,
} from '@/lib/explore/ruminationV4Api';

interface RuminationV4Store {
  // ── 状态 ────────────────────────────────────────────────
  loading: boolean;
  error: string | null;
  state: RuminationV4State | null;
  /** 各 combo 的 messages 缓存(combo_id -> ComboSession 完整对象) */
  comboCache: Record<string, ComboSession>;
  /** 当前激活 combo 的流式回复(对话面板用) */
  streamingText: string;
  isStreaming: boolean;
  /** 思考流式中(对话面板思考占位动画用,对齐前四 phase) */
  thinkStreaming: boolean;
  /** 思考过程实时片段(单行预览) */
  thinkChunkContent: string | undefined;
  activationCode: string | null;

  // ── 动作 ────────────────────────────────────────────────
  init: (activationCode: string) => Promise<void>;
  refreshCombos: () => Promise<void>;
  loadCombo: (comboId: string) => Promise<void>;
  /** 原子:创建 combo + 唤起引导语。成功返回 combo_id,失败返回 null 并设 error */
  createAndStart: (passion: string, strengths: string[]) => Promise<string | null>;
  removeCombo: (comboId: string) => Promise<void>;
  switchCombo: (comboId: string) => Promise<void>;
  beginDiscussion: (comboId: string) => Promise<void>;
  sendChat: (
    comboId: string,
    message: string,
    onChunk?: (full: string) => void,
    token?: string
  ) => Promise<void>;
  abortChat: () => void;
  /** 用户手填/修改结论卡 hypothesis(后端返回最新 combo,可能已退回 discussing) */
  patchCard: (comboId: string, hypothesis: string) => Promise<boolean>;
  /** 确认结论卡(含平衡点判定,失败重试也走这里);hypothesis 有变更时先 PATCH */
  confirmCard: (comboId: string, hypothesis?: string, token?: string) => Promise<void>;
  /** 刷新/重进后发现 analyzing → 补拉判定结果 */
  attachAnalysis: (comboId: string, token?: string) => Promise<void>;
  /** 完成并继续门槛:存在已确认但判定未完成的卡 */
  hasPendingAnalysis: () => boolean;
  setStatus: (comboId: string, status: ComboSession['status']) => Promise<void>;
  selectFinal: (comboIds: string[]) => Promise<void>;
  submitFinal: () => Promise<void>;
  clearError: () => void;
}

let chatHandle: SseStreamHandle<ComboChatEvent> | null = null;
const analysisHandles: Record<string, SseStreamHandle<BalanceAnalysisEvent>> = {};

export const useRuminationV4Store = create<RuminationV4Store>((set, get) => {
  /** 同步更新 comboCache 与 state.combo_sessions 中的同一 combo */
  const updateCombo = (comboId: string, updater: (c: ComboSession) => ComboSession) => {
    set((s) => {
      const cache = s.comboCache[comboId];
      return {
        comboCache: cache ? { ...s.comboCache, [comboId]: updater(cache) } : s.comboCache,
        state: s.state
          ? {
              ...s.state,
              combo_sessions: s.state.combo_sessions.map((c) =>
                c.combo_id === comboId ? updater(c) : c
              ),
            }
          : s.state,
      };
    });
  };

  /** 应用判定 SSE 事件到 combo(confirm 与 attach 共用) */
  const applyAnalysisEvent = (comboId: string, evt: BalanceAnalysisEvent) => {
    if (evt.analysis_status === 'analyzing') {
      // 后端 confirm 时已置 concluded+analyzing 并落盘,前端须同步 concluded,
      // 否则判定进行期间 status 仍是 discussing,终选弹窗的 pending 检测
      // (要求 status==='concluded')会漏检,不显示「正在检测结论…」浮层
      updateCombo(comboId, (c) => ({
        ...c,
        status: 'concluded',
        user_skipped: false,
        balance_analysis: {
          status: 'analyzing',
          balance_found: null,
          balance_fail_reason: null,
          started_at: c.balance_analysis?.started_at || new Date().toISOString(),
          finished_at: null,
          error: null,
        },
      }));
    }
    if (evt.analysis_done) {
      const { balance_found, balance_fail_reason } = evt.analysis_done;
      updateCombo(comboId, (c) => ({
        ...c,
        status: 'concluded',
        user_skipped: false,
        balance_analysis: {
          status: 'done',
          balance_found,
          balance_fail_reason,
          started_at: c.balance_analysis?.started_at || new Date().toISOString(),
          finished_at: new Date().toISOString(),
          error: null,
        },
        conclusion_card: c.conclusion_card
          ? { ...c.conclusion_card, balance_found, balance_fail_reason }
          : c.conclusion_card,
      }));
    }
    if (evt.analysis_failed) {
      updateCombo(comboId, (c) => ({
        ...c,
        balance_analysis: {
          status: 'failed',
          balance_found: null,
          balance_fail_reason: null,
          started_at: c.balance_analysis?.started_at || new Date().toISOString(),
          finished_at: new Date().toISOString(),
          error: evt.analysis_failed?.error || '判定失败',
        },
      }));
    }
    if (evt.analysis_status === 'none') {
      updateCombo(comboId, (c) => ({ ...c, balance_analysis: null }));
    }
    if (evt.error) {
      set({ error: evt.error });
    }
  };

  /** 判定 SSE 订阅(confirm / attach 共用);同一 combo 重复调用时先中断旧流 */
  const runAnalysisStream = (
    comboId: string,
    handle: SseStreamHandle<BalanceAnalysisEvent>
  ) => {
    analysisHandles[comboId]?.abort();
    analysisHandles[comboId] = handle;
    handle.subscribe(async (evt) => {
      applyAnalysisEvent(comboId, evt);
    });
    return handle.done.then(() => {
      delete analysisHandles[comboId];
    });
  };

  return {
    loading: false,
    error: null,
    state: null,
    comboCache: {},
    streamingText: '',
    isStreaming: false,
    thinkStreaming: false,
    thinkChunkContent: undefined,
    activationCode: null,

    init: async (activationCode) => {
      set({ loading: true, error: null, activationCode });
      try {
        const resp = await fetchV4State(activationCode);
        set({ state: resp.data.state, loading: false });
        // 刷新/重进自愈:有 analyzing 的 combo → 补拉判定结果
        for (const c of resp.data.state.combo_sessions || []) {
          if (c.balance_analysis?.status === 'analyzing') {
            void get().attachAnalysis(c.combo_id);
          }
        }
      } catch (e: any) {
        set({ error: e?.message || '加载失败', loading: false });
      }
    },

    refreshCombos: async () => {
      const ac = get().activationCode;
      if (!ac) return;
      try {
        const resp = await fetchCombos(ac);
        const { combos, active_combo_id } = resp.data;
        set((s) => ({
          state: s.state
            ? {
                ...s.state,
                combo_sessions: s.state.combo_sessions.map((c) => {
                  const meta = combos.find((m) => m.combo_id === c.combo_id);
                  return meta ? { ...c, ...meta } : c;
                }),
                active_combo_id,
              }
            : s.state,
        }));
      } catch (e: any) {
        set({ error: e?.message || '刷新失败' });
      }
    },

    loadCombo: async (comboId) => {
      const ac = get().activationCode;
      if (!ac) return;
      if (get().comboCache[comboId]) {
        // 缓存命中也要检查 analyzing 补拉(例如从其他 combo 切回)
        const cached = get().comboCache[comboId];
        if (cached.balance_analysis?.status === 'analyzing' && !analysisHandles[comboId]) {
          void get().attachAnalysis(comboId);
        }
        return;
      }
      try {
        const resp = await fetchComboDetail(ac, comboId);
        set((s) => ({ comboCache: { ...s.comboCache, [comboId]: resp.data.combo } }));
        if (resp.data.combo.balance_analysis?.status === 'analyzing') {
          void get().attachAnalysis(comboId);
        }
      } catch (e: any) {
        set({ error: e?.message || '加载组合失败' });
      }
    },

    createAndStart: async (passion, strengths) => {
      const ac = get().activationCode;
      if (!ac) {
        set({ error: '激活码未就绪，请刷新页面后重试' });
        return null;
      }
      set({ error: null });
      try {
        const resp = await apiCreateAndStart(ac, passion, strengths);
        const payload = resp?.data;
        const combo = payload?.combo;
        const opening = payload?.opening;
        if (!combo?.combo_id) {
          set({ error: '创建组合失败：后端未返回组合数据' });
          return null;
        }
        // 兜底：确保开场消息在 messages 里，右侧可立刻解锁对话
        const withOpening: ComboSession = {
          ...combo,
          messages:
            combo.messages?.length
              ? combo.messages
              : opening
                ? [opening]
                : combo.messages || [],
        };
        set((s) => ({
          state: s.state
            ? {
                ...s.state,
                combo_sessions: [...s.state.combo_sessions, withOpening],
                active_combo_id: withOpening.combo_id,
                main_section: 'combo_session',
              }
            : s.state,
          comboCache: { ...s.comboCache, [withOpening.combo_id]: withOpening },
          error: null,
        }));
        return withOpening.combo_id;
      } catch (e: any) {
        const detail =
          e?.response?.data?.detail ||
          e?.response?.data?.message ||
          e?.message ||
          '创建并开始失败';
        set({ error: typeof detail === 'string' ? detail : JSON.stringify(detail) });
        return null;
      }
    },

    removeCombo: async (comboId) => {
      const ac = get().activationCode;
      if (!ac) return;
      try {
        const resp = await apiDeleteCombo(ac, comboId);
        set((s) => {
          const cache = { ...s.comboCache };
          delete cache[comboId];
          const nextMainSection: MainSection = resp.data.active_combo_id ? 'combo_session' : 'matrix';
          const remainingCombos: ComboSession[] = (s.state?.combo_sessions || []).filter(
            (c) => c.combo_id !== comboId
          );
          return {
            comboCache: cache,
            state: s.state
              ? {
                  ...s.state,
                  combo_sessions: remainingCombos,
                  active_combo_id: resp.data.active_combo_id,
                  main_section: nextMainSection,
                  final_selection: {
                    ...s.state.final_selection,
                    selected_combo_ids: s.state.final_selection.selected_combo_ids.filter((x) => x !== comboId),
                  },
                }
              : s.state,
          };
        });
      } catch (e: any) {
        set({ error: e?.message || '删除失败' });
      }
    },

    switchCombo: async (comboId) => {
      const ac = get().activationCode;
      if (!ac) return;
      try {
        await apiSetActive(ac, comboId);
        set((s) => ({
          state: s.state ? { ...s.state, active_combo_id: comboId, main_section: 'combo_session' } : s.state,
        }));
        await get().loadCombo(comboId);
      } catch (e: any) {
        set({ error: e?.message || '切换失败' });
      }
    },

    beginDiscussion: async (comboId) => {
      const ac = get().activationCode;
      if (!ac) return;
      try {
        const resp = await apiStartDiscussion(ac, comboId);
        const opening = resp.data.opening;
        updateCombo(comboId, (c) => ({ ...c, messages: [...c.messages, opening] }));
      } catch (e: any) {
        set({ error: e?.message || '开始讨论失败' });
      }
    },

    sendChat: async (comboId, message, onChunk, token) => {
      const ac = get().activationCode;
      if (!ac) return;
      // 分析中锁输入(双保险,后端亦拦 409)
      const combo = get().comboCache[comboId] ||
        get().state?.combo_sessions.find((c) => c.combo_id === comboId);
      if (combo?.balance_analysis?.status === 'analyzing') {
        set({ error: '正在分析中，请稍后再聊' });
        return;
      }
      set({
        isStreaming: true,
        streamingText: '',
        thinkStreaming: false,
        thinkChunkContent: undefined,
        error: null,
      });
      // 先把用户消息加入缓存(乐观);新对话作废旧判定(聊即作废,与后端一致)
      const userMsg = { role: 'user' as const, content: message, ts: new Date().toISOString() };
      updateCombo(comboId, (c) => ({
        ...c,
        messages: [...c.messages, userMsg],
        balance_analysis:
          c.balance_analysis && c.balance_analysis.status !== 'analyzing'
            ? null
            : c.balance_analysis,
        conclusion_card:
          c.conclusion_card && c.balance_analysis
            ? { ...c.conclusion_card, balance_found: null, balance_fail_reason: null }
            : c.conclusion_card,
      }));

      const handle = streamComboChat(ac, comboId, message, token);
      chatHandle = handle;
      let full = '';
      handle.subscribe(async (evt: ComboChatEvent) => {
        // 思考事件:对齐前四 phase 的思考占位动画(后端已透传 think_*)
        if (evt.think_start) {
          set({ thinkStreaming: true, thinkChunkContent: '' });
        }
        if (evt.think_chunk) {
          const chunk = typeof evt.think_chunk === 'string' ? evt.think_chunk : '';
          if (chunk) set({ thinkChunkContent: chunk });
        }
        if (evt.think_end != null) {
          set({ thinkStreaming: false, thinkChunkContent: undefined });
        }
        if (evt.chunk) {
          full += evt.chunk;
          set({ streamingText: full });
          onChunk?.(full);
        }
        if (evt.done) {
          // 空回复不追加,避免空气泡(后端已有兜底话术,这里是双保险)
          if (!full.trim()) {
            set({ isStreaming: false, streamingText: '', thinkStreaming: false, thinkChunkContent: undefined });
            return;
          }
          const assistantMsg = { role: 'assistant' as const, content: full, ts: new Date().toISOString() };
          updateCombo(comboId, (c) => ({ ...c, messages: [...c.messages, assistantMsg] }));
          set({ isStreaming: false, streamingText: '', thinkStreaming: false, thinkChunkContent: undefined });
        }
        if (evt.error) {
          set({
            error: evt.error,
            isStreaming: false,
            streamingText: '',
            thinkStreaming: false,
            thinkChunkContent: undefined,
          });
        }
      });
      await handle.done;
      chatHandle = null;
    },

    abortChat: () => {
      chatHandle?.abort();
      chatHandle = null;
      set({ isStreaming: false, streamingText: '', thinkStreaming: false, thinkChunkContent: undefined });
    },

    patchCard: async (comboId, hypothesis) => {
      const ac = get().activationCode;
      if (!ac) return false;
      try {
        const resp = await apiPatchCard(ac, comboId, hypothesis);
        const combo = resp.data.combo;
        updateCombo(comboId, (c) => ({
          ...c,
          conclusion_card: resp.data.conclusion_card,
          ...(combo ? { status: combo.status, balance_analysis: combo.balance_analysis, user_skipped: combo.user_skipped } : {}),
        }));
        return true;
      } catch (e: any) {
        const detail = e?.response?.data?.detail || e?.message || '保存失败';
        set({ error: typeof detail === 'string' ? detail : JSON.stringify(detail) });
        return false;
      }
    },

    confirmCard: async (comboId, hypothesis, token) => {
      const ac = get().activationCode;
      if (!ac) return;
      set({ error: null });
      // 卡文本有变更 → 先 PATCH(确认以最新文本为准)
      if (typeof hypothesis === 'string') {
        const ok = await get().patchCard(comboId, hypothesis);
        if (!ok) return;
      }
      const handle = streamConfirmConclusion(ac, comboId, token);
      await runAnalysisStream(comboId, handle);
    },

    attachAnalysis: async (comboId, token) => {
      const ac = get().activationCode;
      if (!ac) return;
      if (analysisHandles[comboId]) return; // 已在补拉
      const handle = streamAnalysis(ac, comboId, token);
      await runAnalysisStream(comboId, handle);
    },

    hasPendingAnalysis: () => {
      const s = get().state;
      if (!s) return false;
      return (s.combo_sessions || []).some(
        (c) =>
          c.status === 'concluded' &&
          !c.user_skipped &&
          c.balance_analysis?.status !== 'done'
      );
    },

    setStatus: async (comboId, status) => {
      const ac = get().activationCode;
      if (!ac) return;
      try {
        const resp = await apiSetStatus(ac, comboId, status);
        const combo = resp.data?.combo;
        updateCombo(comboId, (c) => ({
          ...c,
          status,
          ...(combo
            ? {
                user_skipped: combo.user_skipped,
                balance_analysis: combo.balance_analysis,
                conclusion_card: combo.conclusion_card ?? c.conclusion_card,
              }
            : {}),
        }));
      } catch (e: any) {
        const detail = e?.response?.data?.detail || e?.message || '状态更新失败';
        set({ error: typeof detail === 'string' ? detail : JSON.stringify(detail) });
      }
    },

    selectFinal: async (comboIds) => {
      const ac = get().activationCode;
      if (!ac) return;
      try {
        const resp = await apiUpdateFinal(ac, comboIds);
        set((s) => ({
          state: s.state ? { ...s.state, final_selection: resp.data.final_selection, main_section: 'final_selection' } : s.state,
        }));
      } catch (e: any) {
        const detail = e?.response?.data?.detail || e?.message || '选择失败';
        set({ error: typeof detail === 'string' ? detail : JSON.stringify(detail) });
        throw e; // 让调用方(终选弹窗)感知门槛拦截
      }
    },

    submitFinal: async () => {
      const ac = get().activationCode;
      if (!ac) return;
      try {
        const resp = await apiSubmitFinal(ac);
        set((s) => ({
          state: s.state
            ? { ...s.state, final_selection: resp.data.final_selection, main_section: resp.data.main_section }
            : s.state,
        }));
      } catch (e: any) {
        const detail = e?.response?.data?.detail || e?.message || '提交失败';
        set({ error: typeof detail === 'string' ? detail : JSON.stringify(detail) });
        throw e;
      }
    },

    clearError: () => set({ error: null }),
  };
});
