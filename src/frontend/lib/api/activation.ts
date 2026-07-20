/**
 * 激活码体系 API 封装（P-A：试用码 + 我的激活码）
 *
 * 后端契约：
 * - GET /simple-auth/my-codes → data.items：当前用户名下全部激活码（试用码注册即送自动绑定）
 * - GET /simple-auth/journeys → 每个 journey item 附 activation_code / code_type / expires_at
 */
import { apiClient } from '@/lib/api/client';

// ─── 类型定义 ─────────────────────────────────────────────

export type CodeType = 'trial' | 'full';

/** 激活码来源：trial_gift 试用赠送 / purchase 购买 / admin 管理员发放 */
export type CodeSource = 'trial_gift' | 'purchase' | 'admin' | (string & {});

export interface MyCodeItem {
  code: string;
  code_type: CodeType;
  /** active / expired / revoked（其余取值按原文展示） */
  status: string;
  /** 试用码为 null（不过期）；完整码为 ISO 时间 */
  expires_at?: string | null;
  created_at?: string | null;
  source?: CodeSource | null;
  session_id?: string | null;
  has_report?: boolean;
}

// ─── 我的激活码 ──────────────────────────────────────────

/** 当前用户名下的激活码列表 */
export async function listMyCodes(): Promise<MyCodeItem[]> {
  const res = await apiClient.get('/simple-auth/my-codes');
  const data = (res.data ?? {}) as { items?: MyCodeItem[] };
  return data.items ?? [];
}
