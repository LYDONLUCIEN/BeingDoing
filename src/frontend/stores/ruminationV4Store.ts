/**
 * Rumination v4 Zustand store
 *
 * 后端为单一数据源,本 store 是后端 state 的镜像(乐观更新 + 失败回滚)。
 * 见 wiki/开发文档/0707-tag1.6.0.md 第九节"状态管理"
 */

import { create } from 'zustand';
import {
  ComboChatEvent,
  ComboChatHandle,
  ComboMeta,
  ComboSession,
  ConclusionCard,
  MainSection,
  RuminationV4State,
  fetchComboDetail,
  fetchCombos,
  fetchV4State,
  createCombo as apiCreateCombo,
  startDiscussion as apiStartDiscussion,
  deleteCombo as apiDeleteCombo,
  patchConclusionCard as apiPatchCard,
  setComboStatus as apiSetStatus,
  setActiveCombo as apiSetActive,
  updateFinalSelection as apiUpdateFinal,
  submitFinalSelection as apiSubmitFinal,
  streamComboChat,
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
  /** 最近一次兜底触发标志 */
  fallbackActive: boolean;
  activationCode: string | null;

  // ── 动作 ────────────────────────────────────────────────
  init: (activationCode: string) => Promise<void>;
  refreshCombos: () => Promise<void>;
  loadCombo: (comboId: string) => Promise<void>;
  createCombo: (passion: string, strengths: string[]) => Promise<string | null>;
  removeCombo: (comboId: string) => Promise<void>;
  switchCombo: (comboId: string) => Promise<void>;
  beginDiscussion: (comboId: string) => Promise<void>;
  sendChat: (
    comboId: string,
    message: string,
    onChunk?: (full: string) => void,
    onCard?: (card: ConclusionCard) => void,
    token?: string
  ) => Promise<void>;
  abortChat: () => void;
  patchCard: (comboId: string, fields: Partial<ConclusionCard>) => Promise<void>;
  setStatus: (comboId: string, status: ComboSession['status']) => Promise<void>;
  selectFinal: (comboIds: string[]) => Promise<void>;
  submitFinal: () => Promise<void>;
  clearError: () => void;
}

let chatHandle: ComboChatHandle | null = null;

export const useRuminationV4Store = create<RuminationV4Store>((set, get) => ({
  loading: false,
  error: null,
  state: null,
  comboCache: {},
  streamingText: '',
  isStreaming: false,
  fallbackActive: false,
  activationCode: null,

  init: async (activationCode) => {
    set({ loading: true, error: null, activationCode });
    try {
      const resp = await fetchV4State(activationCode);
      set({ state: resp.data.state, loading: false });
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
          ? { ...s.state, combo_sessions: s.state.combo_sessions.map((c) => {
              const meta = combos.find((m) => m.combo_id === c.combo_id);
              return meta ? { ...c, ...meta } : c;
            }), active_combo_id }
          : s.state,
      }));
    } catch (e: any) {
      set({ error: e?.message || '刷新失败' });
    }
  },

  loadCombo: async (comboId) => {
    const ac = get().activationCode;
    if (!ac) return;
    if (get().comboCache[comboId]) return; // 内存缓存命中
    try {
      const resp = await fetchComboDetail(ac, comboId);
      set((s) => ({ comboCache: { ...s.comboCache, [comboId]: resp.data.combo } }));
    } catch (e: any) {
      set({ error: e?.message || '加载组合失败' });
    }
  },

  createCombo: async (passion, strengths) => {
    const ac = get().activationCode;
    if (!ac) return null;
    try {
      const resp = await apiCreateCombo(ac, passion, strengths);
      const combo = resp.data.combo;
      set((s) => ({
        state: s.state
          ? {
              ...s.state,
              combo_sessions: [...s.state.combo_sessions, combo],
              active_combo_id: combo.combo_id,
              main_section: 'combo_session',
            }
          : s.state,
        comboCache: { ...s.comboCache, [combo.combo_id]: combo },
      }));
      return combo.combo_id;
    } catch (e: any) {
      set({ error: e?.message || '创建组合失败' });
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
        // 保留原 combo_session 的完整数据,只移除被删的那个
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
      set((s) => {
        const cache = s.comboCache[comboId];
        if (!cache) return {};
        const updated = { ...cache, messages: [...cache.messages, opening] };
        return {
          comboCache: { ...s.comboCache, [comboId]: updated },
          state: s.state
            ? {
                ...s.state,
                combo_sessions: s.state.combo_sessions.map((c) =>
                  c.combo_id === comboId ? { ...c, messages: [...c.messages, opening] } : c
                ),
              }
            : s.state,
        };
      });
    } catch (e: any) {
      set({ error: e?.message || '开始讨论失败' });
    }
  },

  sendChat: async (comboId, message, onChunk, onCard, token) => {
    const ac = get().activationCode;
    if (!ac) return;
    set({ isStreaming: true, streamingText: '', fallbackActive: false, error: null });
    // 先把用户消息加入缓存(乐观)
    const userMsg = { role: 'user' as const, content: message, ts: new Date().toISOString() };
    set((s) => {
      const cache = s.comboCache[comboId];
      if (!cache) return {};
      const updated = { ...cache, messages: [...cache.messages, userMsg] };
      return {
        comboCache: { ...s.comboCache, [comboId]: updated },
        state: s.state
          ? {
              ...s.state,
              combo_sessions: s.state.combo_sessions.map((c) =>
                c.combo_id === comboId ? { ...c, messages: [...c.messages, userMsg] } : c
              ),
            }
          : s.state,
      };
    });

    const handle = streamComboChat(ac, comboId, message, token);
    chatHandle = handle;
    let full = '';
    handle.subscribe(async (evt: ComboChatEvent) => {
      if (evt.chunk) {
        full += evt.chunk;
        set({ streamingText: full });
        onChunk?.(full);
      }
      if (evt.fallback) {
        set({ fallbackActive: true });
      }
      if (evt.conclusion_card) {
        onCard?.(evt.conclusion_card);
        // 写入 cache + state
        set((s) => {
          const cache = s.comboCache[comboId];
          if (!cache) return {};
          const updated: ComboSession = {
            ...cache,
            conclusion_card: evt.conclusion_card!,
            status: 'concluded',
            fields_collected: { ...cache.fields_collected, ...evt.conclusion_card! },
          };
          return {
            comboCache: { ...s.comboCache, [comboId]: updated },
            state: s.state
              ? {
                  ...s.state,
                  combo_sessions: s.state.combo_sessions.map((c) =>
                    c.combo_id === comboId ? { ...c, conclusion_card: evt.conclusion_card!, status: 'concluded' } : c
                  ),
                }
              : s.state,
          };
        });
      }
      if (evt.tool_errors) {
        // 仅调试用,可忽略
      }
      if (evt.done) {
        // 把 assistant 的完整可见回复加入消息
        const assistantMsg = { role: 'assistant' as const, content: full, ts: new Date().toISOString() };
        set((s) => {
          const cache = s.comboCache[comboId];
          if (!cache) return {};
          const updated = { ...cache, messages: [...cache.messages, assistantMsg] };
          return {
            comboCache: { ...s.comboCache, [comboId]: updated },
            isStreaming: false,
            streamingText: '',
            state: s.state
              ? {
                  ...s.state,
                  combo_sessions: s.state.combo_sessions.map((c) =>
                    c.combo_id === comboId ? { ...c, messages: [...c.messages, assistantMsg] } : c
                  ),
                }
              : s.state,
          };
        });
      }
      if (evt.error) {
        set({ error: evt.error, isStreaming: false, streamingText: '' });
      }
    });
    await handle.done;
    chatHandle = null;
  },

  abortChat: () => {
    chatHandle?.abort();
    chatHandle = null;
    set({ isStreaming: false, streamingText: '' });
  },

  patchCard: async (comboId, fields) => {
    const ac = get().activationCode;
    if (!ac) return;
    try {
      const resp = await apiPatchCard(ac, comboId, fields);
      const card = resp.data.conclusion_card;
      set((s) => {
        const cache = s.comboCache[comboId];
        if (!cache) return {};
        const updated = { ...cache, conclusion_card: card, status: 'concluded' as const };
        return {
          comboCache: { ...s.comboCache, [comboId]: updated },
          state: s.state
            ? {
                ...s.state,
                combo_sessions: s.state.combo_sessions.map((c) =>
                  c.combo_id === comboId ? { ...c, conclusion_card: card, status: 'concluded' } : c
                ),
              }
            : s.state,
        };
      });
    } catch (e: any) {
      set({ error: e?.message || '保存失败' });
    }
  },

  setStatus: async (comboId, status) => {
    const ac = get().activationCode;
    if (!ac) return;
    try {
      await apiSetStatus(ac, comboId, status);
      set((s) => {
        const cache = s.comboCache[comboId];
        return {
          comboCache: cache
            ? { ...s.comboCache, [comboId]: { ...cache, status } }
            : s.comboCache,
          state: s.state
            ? {
                ...s.state,
                combo_sessions: s.state.combo_sessions.map((c) =>
                  c.combo_id === comboId ? { ...c, status } : c
                ),
              }
            : s.state,
        };
      });
    } catch (e: any) {
      set({ error: e?.message || '状态更新失败' });
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
      set({ error: e?.message || '选择失败' });
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
      set({ error: e?.message || '提交失败' });
    }
  },

  clearError: () => set({ error: null }),
}));
