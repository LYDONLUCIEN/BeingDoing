import { create } from 'zustand';
import { persist, createJSONStorage } from 'zustand/middleware';

/**
 * Chat 外观配置（A/B 对比期，用户可见的外观弹层）：
 * - density：气泡间距。compact=HTML 紧凑（28px 体系）/ roomy=现有宽松
 * - sidebarArt：侧栏底部是否带植物贴纸（HTML 带图）
 * - newChatStyle：新建对话按钮。dashed=HTML 虚线浅底 / solid=现有深墨实心
 * 先矩阵自由组合供决策，定稿后删除落选分支。
 */
export type ChatDensity = 'compact' | 'roomy';
export type NewChatButtonStyle = 'dashed' | 'solid';

interface ChatAppearanceState {
  density: ChatDensity;
  sidebarArt: boolean;
  newChatStyle: NewChatButtonStyle;
  setDensity: (v: ChatDensity) => void;
  setSidebarArt: (v: boolean) => void;
  setNewChatStyle: (v: NewChatButtonStyle) => void;
}

export const useChatAppearanceStore = create<ChatAppearanceState>()(
  persist(
    (set) => ({
      // 默认沿用现状（宽松间距 / 不带图 / 深墨实心），便于与 HTML 方向对比
      density: 'roomy',
      sidebarArt: false,
      newChatStyle: 'solid',
      setDensity: (density) => set({ density }),
      setSidebarArt: (sidebarArt) => set({ sidebarArt }),
      setNewChatStyle: (newChatStyle) => set({ newChatStyle }),
    }),
    {
      name: 'openlife-chat-appearance',
      storage: typeof window !== 'undefined' ? createJSONStorage(() => localStorage) : undefined,
    }
  )
);
