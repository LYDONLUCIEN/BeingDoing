'use client';

import { useEffect } from 'react';
import type { CSSProperties } from 'react';
import { useChatAppearanceStore } from '@/stores/chatAppearanceStore';
import { fetchGlobalChatAppearance } from '@/lib/api/chatAppearance';

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

/** 全局外观配置是否已同步过（会话级一次；admin 配置覆盖 localStorage，用户侧无修改入口） */
let globalAppearanceSynced = false;

export function useChatAppearanceAttrs(): {
  dataAttrs: Record<string, string>;
  style: CSSProperties;
} {
  const s = useChatAppearanceStore();

  useEffect(() => {
    if (globalAppearanceSynced) return;
    globalAppearanceSynced = true;
    fetchGlobalChatAppearance()
      .then((cfg) => {
        useChatAppearanceStore.getState().applyGlobalConfig(cfg as Record<string, unknown>);
      })
      .catch(() => {
        /* 公开接口失败（离线/后端未起）静默回落本地默认 */
      });
  }, []);

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
