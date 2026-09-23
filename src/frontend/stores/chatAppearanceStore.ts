import { create } from 'zustand';
import { persist, createJSONStorage } from 'zustand/middleware';

/**
 * Chat 页外观配置（复刻 wiki/开发文档/0919/openlife-journey (21).html #appearance-popover）。
 *
 * 维度总览（默认值 = HTML RECOMMENDED_APPEARANCE）：
 * - 聊天背景：background（white/tint/flow/illustration）+ placement（贴图位置）
 *   + strength（晕染浓度 0-50 → --chat-wash-opacity）+ motionPaused（动效暂停）
 * - 气泡与按钮：aiBubble / userBubble（ink/soft/theme/white）+ actionStyle（ink/theme）
 * - 沉淀（v4）：ruminationLayout / ruminationSkin / palette / matrixStyle / matrixPalette
 * - 结论卡：conclusionTone / conclusionTags
 * - 对话排版（A/B 对比期保留）：density / newChatStyle
 * - sidebarArt：旧字段保留仅供 migrate（v0 → v1 折算成 placement），面板不再展示。
 *
 * 消费方式：lib/explore/useChatAppearanceAttrs.ts 把全部字段输出为 chat 根节点
 * data-* 属性 + --chat-wash-opacity 内联变量，样式规则见
 * styles/components/openlife-chat-appearance.css（.flow-light[data-xxx] 作用域）。
 */
export type ChatDensity = 'compact' | 'roomy';
export type NewChatButtonStyle = 'dashed' | 'solid';
export type ChatBackground = 'white' | 'tint' | 'flow' | 'illustration';
export type ChatStickerPlacement = 'both' | 'sidebar' | 'edge' | 'off';
export type ChatBubbleStyle = 'ink' | 'soft' | 'theme' | 'white';
export type ChatActionStyle = 'ink' | 'theme';
export type RuminationLayout = 'classic' | 'studio' | 'guided';
export type RuminationSkin = 'folio' | 'modules' | 'editorial' | 'mist';
export type RuminationPalette = 'lavender' | 'sage' | 'slate';
export type MatrixStyle = 'soft' | 'outline' | 'solid';
export type MatrixPalette = 'duo' | 'violet' | 'multi';
export type ConclusionTone =
  | 'theme-mist'
  | 'theme-paper'
  | 'theme-gradient'
  | 'theme-outline'
  | 'theme-solid';
export type ConclusionTagsStyle = 'soft' | 'outline' | 'editorial';

/** HTML RECOMMENDED_APPEARANCE 推荐组合（resetToRecommended 只重置这 14 个字段） */
export const RECOMMENDED_CHAT_APPEARANCE = {
  background: 'flow',
  placement: 'both',
  strength: 22,
  motionPaused: false,
  aiBubble: 'ink',
  userBubble: 'white',
  actionStyle: 'ink',
  ruminationLayout: 'guided',
  ruminationSkin: 'mist',
  palette: 'lavender',
  matrixStyle: 'soft',
  matrixPalette: 'duo',
  conclusionTone: 'theme-mist',
  conclusionTags: 'soft',
} as const satisfies {
  background: ChatBackground;
  placement: ChatStickerPlacement;
  strength: number;
  motionPaused: boolean;
  aiBubble: ChatBubbleStyle;
  userBubble: ChatBubbleStyle;
  actionStyle: ChatActionStyle;
  ruminationLayout: RuminationLayout;
  ruminationSkin: RuminationSkin;
  palette: RuminationPalette;
  matrixStyle: MatrixStyle;
  matrixPalette: MatrixPalette;
  conclusionTone: ConclusionTone;
  conclusionTags: ConclusionTagsStyle;
};

interface ChatAppearanceState {
  density: ChatDensity;
  /** @deprecated 仅供 v0 存档 migrate 折算 placement；面板不再展示 */
  sidebarArt: boolean;
  newChatStyle: NewChatButtonStyle;
  background: ChatBackground;
  placement: ChatStickerPlacement;
  /** 晕染浓度 0-50（→ --chat-wash-opacity = strength/100） */
  strength: number;
  motionPaused: boolean;
  aiBubble: ChatBubbleStyle;
  userBubble: ChatBubbleStyle;
  actionStyle: ChatActionStyle;
  ruminationLayout: RuminationLayout;
  ruminationSkin: RuminationSkin;
  palette: RuminationPalette;
  matrixStyle: MatrixStyle;
  matrixPalette: MatrixPalette;
  conclusionTone: ConclusionTone;
  conclusionTags: ConclusionTagsStyle;
  setDensity: (v: ChatDensity) => void;
  setSidebarArt: (v: boolean) => void;
  setNewChatStyle: (v: NewChatButtonStyle) => void;
  setBackground: (v: ChatBackground) => void;
  setPlacement: (v: ChatStickerPlacement) => void;
  setStrength: (v: number) => void;
  setMotionPaused: (v: boolean) => void;
  setAiBubble: (v: ChatBubbleStyle) => void;
  setUserBubble: (v: ChatBubbleStyle) => void;
  setActionStyle: (v: ChatActionStyle) => void;
  setRuminationLayout: (v: RuminationLayout) => void;
  setRuminationSkin: (v: RuminationSkin) => void;
  setPalette: (v: RuminationPalette) => void;
  setMatrixStyle: (v: MatrixStyle) => void;
  setMatrixPalette: (v: MatrixPalette) => void;
  setConclusionTone: (v: ConclusionTone) => void;
  setConclusionTags: (v: ConclusionTagsStyle) => void;
  /** 重置 14 个新字段为推荐组合；不动 density / newChatStyle / sidebarArt */
  resetToRecommended: () => void;
  /** 应用 admin 下发的全局默认配置（0923：用户侧无修改入口，全局配置覆盖本地持久化）；
      只接受白名单字段，非法/缺省字段保持现状 */
  applyGlobalConfig: (cfg: Record<string, unknown>) => void;
}

/** applyGlobalConfig 接受的字段白名单（与后端 chat_appearance FIELD_ENUMS 对齐） */
const GLOBAL_CONFIG_FIELDS = [
  'density',
  'newChatStyle',
  'background',
  'placement',
  'strength',
  'motionPaused',
  'aiBubble',
  'userBubble',
  'actionStyle',
  'ruminationLayout',
  'ruminationSkin',
  'palette',
  'matrixStyle',
  'matrixPalette',
  'conclusionTone',
  'conclusionTags',
] as const;

export const useChatAppearanceStore = create<ChatAppearanceState>()(
  persist(
    (set) => ({
      // 对话排版默认沿用现状（宽松间距 / 深墨实心）；其余字段为 HTML 推荐组合
      density: 'roomy',
      sidebarArt: false,
      newChatStyle: 'solid',
      ...RECOMMENDED_CHAT_APPEARANCE,
      setDensity: (density) => set({ density }),
      setSidebarArt: (sidebarArt) => set({ sidebarArt }),
      setNewChatStyle: (newChatStyle) => set({ newChatStyle }),
      setBackground: (background) => set({ background }),
      setPlacement: (placement) => set({ placement }),
      setStrength: (strength) =>
        set({ strength: Math.max(0, Math.min(50, Math.round(strength))) }),
      setMotionPaused: (motionPaused) => set({ motionPaused }),
      setAiBubble: (aiBubble) => set({ aiBubble }),
      setUserBubble: (userBubble) => set({ userBubble }),
      setActionStyle: (actionStyle) => set({ actionStyle }),
      setRuminationLayout: (ruminationLayout) => set({ ruminationLayout }),
      setRuminationSkin: (ruminationSkin) => set({ ruminationSkin }),
      setPalette: (palette) => set({ palette }),
      setMatrixStyle: (matrixStyle) => set({ matrixStyle }),
      setMatrixPalette: (matrixPalette) => set({ matrixPalette }),
      setConclusionTone: (conclusionTone) => set({ conclusionTone }),
      setConclusionTags: (conclusionTags) => set({ conclusionTags }),
      resetToRecommended: () => set({ ...RECOMMENDED_CHAT_APPEARANCE }),
      applyGlobalConfig: (cfg) => {
        const patch: Record<string, unknown> = {};
        for (const key of GLOBAL_CONFIG_FIELDS) {
          const val = cfg?.[key];
          if (val !== undefined && val !== null) patch[key] = val;
        }
        if (Object.keys(patch).length > 0) {
          set(patch as unknown as Partial<ChatAppearanceState>);
        }
      },
    }),
    {
      name: 'openlife-chat-appearance',
      version: 3,
      storage: typeof window !== 'undefined' ? createJSONStorage(() => localStorage) : undefined,
      migrate: (persisted, version) => {
        if (!persisted || typeof persisted !== 'object') return persisted;
        // v0（三开关时代）→ v1：保留 density/newChatStyle；
        // sidebarArt=true→placement=both，false→placement=edge；新字段由默认浅合并补齐
        let next: Record<string, unknown> = { ...(persisted as Record<string, unknown>) };
        if (version < 1) {
          const old = persisted as {
            density?: unknown;
            newChatStyle?: unknown;
            sidebarArt?: unknown;
          };
          next = {
            density: old.density === 'compact' ? 'compact' : 'roomy',
            newChatStyle: old.newChatStyle === 'dashed' ? 'dashed' : 'solid',
            sidebarArt: old.sidebarArt === true,
            placement: old.sidebarArt === true ? 'both' : 'edge',
          };
        }
        // v1 → v2（2026-09-22 拷问拍板）：沉淀页 guided 三栏（HTML 唯一视觉准绳）设为默认；
        // 存量 'classic' 为旧默认值（无法与显式选择区分），一并升级，可在外观面板切回
        if (version < 2) {
          if (!next.ruminationLayout || next.ruminationLayout === 'classic') {
            next.ruminationLayout = 'guided';
          }
        }
        // v2 → v3（2026-09-23 拍板）：新建对话/新建组系统一实心深墨；
        // 存量 dashed 一并升级 solid，外观面板开关保留可切回
        if (version < 3 && next.newChatStyle === 'dashed') {
          next.newChatStyle = 'solid';
        }
        return next;
      },
    }
  )
);
