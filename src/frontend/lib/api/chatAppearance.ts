/**
 * Chat 外观全局默认配置 API（2026-09-23 拍板：配置入口迁 admin，全局生效，用户不可自行修改）。
 *
 * - fetchGlobalChatAppearance：公开读（chat 页加载时同步进 chatAppearanceStore，覆盖 localStorage）
 * - fetchAdminChatAppearance / putAdminChatAppearance：admin 空间读写
 */

import { apiClient } from '@/lib/api/client';

/** 与后端 FIELD_ENUMS 白名单对齐的可配置字段 */
export interface ChatAppearanceConfig {
  density?: 'compact' | 'roomy';
  newChatStyle?: 'dashed' | 'solid';
  background?: 'white' | 'tint' | 'flow' | 'illustration';
  placement?: 'both' | 'sidebar' | 'edge' | 'off';
  strength?: number;
  motionPaused?: boolean;
  aiBubble?: 'ink' | 'soft' | 'theme' | 'white';
  userBubble?: 'ink' | 'soft' | 'theme' | 'white';
  actionStyle?: 'ink' | 'theme';
  ruminationLayout?: 'classic' | 'studio' | 'guided';
  ruminationSkin?: 'folio' | 'modules' | 'editorial' | 'mist';
  palette?: 'lavender' | 'sage' | 'slate';
  matrixStyle?: 'soft' | 'outline' | 'solid';
  matrixPalette?: 'duo' | 'violet' | 'multi';
  conclusionTone?:
    | 'theme-mist'
    | 'theme-paper'
    | 'theme-gradient'
    | 'theme-outline'
    | 'theme-solid';
  conclusionTags?: 'soft' | 'outline' | 'editorial';
}

function unwrap(res: unknown): ChatAppearanceConfig {
  const data = (res as any)?.data ?? res;
  return data && typeof data === 'object' ? (data as ChatAppearanceConfig) : {};
}

/** 公开读：全局外观默认值（未配置返回空对象，调用方回落内置默认） */
export async function fetchGlobalChatAppearance(): Promise<ChatAppearanceConfig> {
  const res = await apiClient.get('/chat-appearance');
  return unwrap(res);
}

/** admin 读：当前全局配置 */
export async function fetchAdminChatAppearance(): Promise<ChatAppearanceConfig> {
  const res = await apiClient.get('/admin/chat-appearance');
  return unwrap(res);
}

/** admin 写：整体保存（后端白名单校验，非法值 400） */
export async function putAdminChatAppearance(config: ChatAppearanceConfig): Promise<void> {
  await apiClient.put('/admin/chat-appearance', { config });
}

/** admin 恢复默认：一键写回出厂默认（后端 DEFAULT_CHAT_APPEARANCE）并生效 */
export async function resetAdminChatAppearance(): Promise<ChatAppearanceConfig> {
  const res = await apiClient.post('/admin/chat-appearance/reset');
  return unwrap(res);
}
