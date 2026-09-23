/**
 * LLM 场景分流配置 API（2026-09-23 拍板：admin 可配置 chat/rumination/report
 * 三场景的 flash|pro 档位与 thinking 开关，全局生效）。
 *
 * 档位固定映射：flash→deepseek-v4-flash，pro→deepseek-v4-pro（后端 scene_config.py）。
 * 存储与消费均在后端（data/admin_runtime_config.json），前端仅 admin 页读写。
 */

import { apiClient } from '@/lib/api/client';

export type LlmScene = 'chat' | 'rumination' | 'report';
export type LlmTier = 'flash' | 'pro';

export interface LlmSceneItem {
  tier: LlmTier;
  thinking: boolean;
}

export type LlmSceneConfig = Record<LlmScene, LlmSceneItem>;

/** 档位 → 具体模型名（与后端 TIER_MODELS 对齐，仅用于页面展示） */
export const TIER_MODEL_NAMES: Record<LlmTier, string> = {
  flash: 'deepseek-v4-flash',
  pro: 'deepseek-v4-pro',
};

function unwrap(res: unknown): LlmSceneConfig {
  const data = (res as any)?.data ?? res;
  return data && typeof data === 'object' ? (data as LlmSceneConfig) : ({} as LlmSceneConfig);
}

/** admin 读：当前场景配置（后端始终返回合并默认后的完整三场景） */
export async function fetchAdminLlmScene(): Promise<LlmSceneConfig> {
  const res = await apiClient.get('/admin/llm-scene');
  return unwrap(res);
}

/** admin 写：整体保存（后端校验 tier/thinking，非法值 400），立即生效 */
export async function putAdminLlmScene(config: LlmSceneConfig): Promise<LlmSceneConfig> {
  const res = await apiClient.put('/admin/llm-scene', { config });
  return unwrap(res);
}

/** admin 恢复默认：一键写回出厂默认并生效，返回默认配置 */
export async function resetAdminLlmScene(): Promise<LlmSceneConfig> {
  const res = await apiClient.post('/admin/llm-scene/reset');
  return unwrap(res);
}
