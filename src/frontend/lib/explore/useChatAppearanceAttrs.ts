'use client';

import type { CSSProperties } from 'react';
import { useChatAppearanceStore } from '@/stores/chatAppearanceStore';

/**
 * 把 chat 外观 store 折算成挂在页面根节点上的 data-* 属性与 CSS 变量，
 * 供 styles/components/openlife-chat-appearance.css 的 `.flow-light[data-xxx]` 规则消费。
 *
 * 挂载点：
 * - app/(main)/explore/chat/[phase]/page.tsx 根 div（前四阶段 .careering-matte / v3 沉淀）
 * - components/explore/ruminationV4/RuminationV4Page.tsx 根 div（.rumination-v4-root）
 *
 * zustand persist 客户端水合后自动重渲染，与现有 chatAppearance 用法同一模式。
 */
export function useChatAppearanceAttrs(): {
  dataAttrs: Record<string, string>;
  style: CSSProperties;
} {
  const s = useChatAppearanceStore();

  const dataAttrs: Record<string, string> = {
    // 对话排版（A/B 保留项）
    'data-chat-density': s.density,
    'data-chat-newbtn': s.newChatStyle,
    // 聊天背景（sidebarArt 已由 placement 接管，不再输出 data-chat-sidebar-art）
    'data-background': s.background,
    'data-placement': s.placement,
    'data-motion': s.motionPaused ? 'off' : 'on',
    // 气泡与按钮
    'data-ai-bubble': s.aiBubble,
    'data-user-bubble': s.userBubble,
    'data-action-style': s.actionStyle,
    // 沉淀（v4）
    'data-rumination-layout': s.ruminationLayout,
    'data-rumination-skin': s.ruminationSkin,
    'data-palette': s.palette,
    'data-matrix-style': s.matrixStyle,
    'data-matrix-palette': s.matrixPalette,
    // 结论卡
    'data-conclusion-tone': s.conclusionTone,
    'data-conclusion-tags': s.conclusionTags,
  };

  const style = {
    '--chat-wash-opacity': String(s.strength / 100),
  } as CSSProperties;

  return { dataAttrs, style };
}
