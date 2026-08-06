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
  /** active / inactive（已购买未开始探索，有效期首次起算）/ expired / revoked（其余取值按原文展示） */
  status: string;
  /** 试用码为 null（不过期）；完整码为 ISO 时间 */
  expires_at?: string | null;
  created_at?: string | null;
  source?: CodeSource | null;
  session_id?: string | null;
  /** approved 才算 true（审核中不算） */
  has_report?: boolean;
  /** 报告审核状态：not_started / pending_review / approved；无报告或旧数据为 null */
  report_status?: string | null;
}

// ─── 我的激活码 ──────────────────────────────────────────

/** 当前用户名下的激活码列表 */
export async function listMyCodes(): Promise<MyCodeItem[]> {
  const res = await apiClient.get('/simple-auth/my-codes');
  const data = (res.data ?? {}) as { items?: MyCodeItem[] };
  return data.items ?? [];
}

// ─── 消耗升级（ADR-0014）─────────────────────────────────

/** 我购买的未绑定完整码（可消耗升级 / 转赠 / 自激活） */
export interface UnboundCodeItem {
  code: string;
  package_type?: 'quarterly' | 'annual' | null;
  created_at?: string | null;
  source_order_id?: string | null;
}

export interface UpgradeContext {
  has_started_trial: boolean;
  trial_code: string | null;
  unbound_codes: UnboundCodeItem[];
  /** 支付结果页升级弹窗「不再提醒」 */
  dont_remind: boolean;
}

export interface ApplyToTrialResult {
  trial_code: string;
  consumed_code: string;
  package_type: string;
  code_type: string;
}

/** 升级试用码弹窗上下文 */
export async function getUpgradeContext(): Promise<UpgradeContext> {
  const res = await apiClient.get('/simple-auth/upgrade-context');
  return (res.data ?? {}) as UpgradeContext;
}

/** 消耗升级：作废一个未绑定完整码，把当前用户的试用码原地升级为完整码 */
export async function applyToTrial(code: string): Promise<ApplyToTrialResult> {
  const res = await apiClient.post('/simple-auth/codes/apply-to-trial', { code });
  return (res.data ?? {}) as ApplyToTrialResult;
}

// ─── 用户偏好 ────────────────────────────────────────────

/** 读当前用户偏好（如 upgrade_modal_dont_remind） */
export async function getPreferences(): Promise<Record<string, unknown>> {
  const res = await apiClient.get('/simple-auth/preferences');
  const data = (res.data ?? {}) as { preferences?: Record<string, unknown> };
  return data.preferences ?? {};
}

/** 更新当前用户偏好（白名单 key 合入） */
export async function patchPreferences(prefs: {
  upgrade_modal_dont_remind?: boolean;
}): Promise<Record<string, unknown>> {
  const res = await apiClient.patch('/simple-auth/preferences', prefs);
  const data = (res.data ?? {}) as { preferences?: Record<string, unknown> };
  return data.preferences ?? {};
}
