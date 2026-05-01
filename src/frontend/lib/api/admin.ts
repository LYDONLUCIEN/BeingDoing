import { apiClient } from '@/lib/api/client';

export interface AdminActivationItem {
  activation_code: string;
  session_id: string;
  mode: string;
  created_at: string;
  expires_at: string;
  last_activity_at: string;
  status: string;
  owner_user_id?: string;
  owner_email?: string;
  claimed_at?: string;
  deleted_at?: string;
  purge_after?: string;
  source?: string;
  /** 调试沙箱 Fork */
  is_sandbox?: boolean;
  /** 与列表筛选一致：fork=沙箱，normal=正式 */
  activation_type?: 'normal' | 'fork';
  sandbox_root?: string | null;
  fork_id?: string | null;
  forked_from_code?: string | null;
  forked_at?: string | null;
  sandbox_expires_at?: string | null;
  workspace_kind?: 'fork' | 'resident' | null;
  workspace_root?: string | null;
}

export interface AdminActivationRecycleItem {
  activation_code: string;
  session_id: string;
  mode: string;
  deleted_at: string;
  purge_after: string;
  days_remaining?: number | null;
  deleted_by_user_id?: string;
  deleted_by_email?: string;
}

export async function fetchAdminActivations(params?: {
  status?: string;
  mode?: string;
  q?: string;
  /** normal | fork，不传为全部 */
  activation_type?: 'normal' | 'fork';
}): Promise<AdminActivationItem[]> {
  const res = await apiClient.get('/admin/activations', { params });
  const items = res.data?.items ?? [];
  return items as AdminActivationItem[];
}

export async function batchCreateActivations(payload: {
  ttl_days: number;
  count: number;
}) {
  const res = await apiClient.post('/admin/activations/batch-create', payload);
  return res.data ?? { count: 0, items: [] };
}

export async function batchUpdateActivationStatus(payload: {
  codes: string[];
  status: 'active' | 'expired' | 'revoked';
}) {
  const res = await apiClient.post('/admin/activations/batch-status', payload);
  return res.data ?? { changed: 0 };
}

export async function batchExtendActivations(payload: {
  codes: string[];
  extend_days: number;
}) {
  const res = await apiClient.post('/admin/activations/batch-extend', payload);
  return res.data ?? { changed: 0, skipped: 0 };
}

export async function batchDeleteActivations(payload: { codes: string[] }) {
  const res = await apiClient.post('/admin/activations/batch-delete', payload);
  return res.data ?? { changed: 0 };
}

export async function fetchActivationRecycleBin(): Promise<AdminActivationRecycleItem[]> {
  const res = await apiClient.get('/admin/activations/recycle-bin');
  const items = res.data?.items ?? [];
  return items as AdminActivationRecycleItem[];
}

export async function restoreActivationsFromRecycle(payload: { codes: string[] }) {
  const res = await apiClient.post('/admin/activations/recycle-bin/restore', payload);
  return res.data ?? { changed: 0 };
}

export async function permanentDeleteFromRecycleBin(payload: { codes: string[] }) {
  const res = await apiClient.post('/admin/activations/recycle-bin/permanent-delete', payload);
  return res.data ?? { deleted: 0 };
}

export async function syncActivationsFromDb() {
  const res = await apiClient.post('/admin/activations/sync-from-db');
  return res.data ?? { synced: 0, rows_scanned: 0 };
}

export type ActivationSyncSource =
  | 'analytics_reports'
  | 'reports_registry'
  | 'simple_activations_file';

export interface ActivationSyncPayload {
  sources?: ActivationSyncSource[];
  dry_run?: boolean;
  mode?: 'insert_only';
  default_status?: 'active' | 'expired' | 'revoked' | 'deleted';
}

export interface ActivationSyncResult {
  mode: string;
  dry_run: boolean;
  sources: ActivationSyncSource[];
  rows_scanned: number;
  rows_normalized: number;
  rows_merged: number;
  skipped_invalid: number;
  duplicates: number;
  conflicts: number;
  would_insert: number;
  synced: number;
  by_source: Record<string, { scanned: number; normalized: number; would_insert: number; inserted: number }>;
}

export async function syncActivations(payload?: ActivationSyncPayload): Promise<ActivationSyncResult> {
  const res = await apiClient.post('/admin/activations/sync-from-db', payload ?? {});
  return (res.data ?? {}) as ActivationSyncResult;
}

export interface AdminDashboardOverview {
  user_count: number;
  visit_count: number;
  report_count: number;
  today_new_activations: number;
  funnel: Array<{ step_id: string; count: number; pct: number }>;
  token_totals: { input_tokens: number; output_tokens: number; total_tokens: number };
  token_by_step: Record<string, { input_tokens: number; output_tokens: number; total_tokens: number }>;
}

export interface AdminDashboardOverviewPayload {
  generated_at: string;
  source: string;
  overview: AdminDashboardOverview;
}

export async function fetchAdminDashboardOverview(): Promise<AdminDashboardOverviewPayload> {
  const res = await apiClient.get('/admin/dashboard/overview');
  return (res.data ?? {}) as AdminDashboardOverviewPayload;
}

export async function syncAdminDashboardOverview(): Promise<AdminDashboardOverviewPayload> {
  const res = await apiClient.post('/admin/dashboard/overview/sync');
  return (res.data ?? {}) as AdminDashboardOverviewPayload;
}

export interface AdminConversationItem {
  report_id: string;
  activation_code: string;
  user_id: string;
  step_id: string;
  session_id: string;
  message_count: number;
  last_message_at?: string | null;
  updated_at?: string | null;
}

export async function fetchAdminConversations(params?: {
  q?: string;
  report_id?: string;
  activation_code?: string;
  user_id?: string;
  step_id?: string;
  session_id?: string;
  page?: number;
  page_size?: number;
}): Promise<{ items: AdminConversationItem[]; total: number; page: number; page_size: number }> {
  const res = await apiClient.get('/admin/conversations', { params });
  return (res.data ?? { items: [], total: 0, page: 1, page_size: 50 }) as {
    items: AdminConversationItem[];
    total: number;
    page: number;
    page_size: number;
  };
}

export async function fetchAdminConversationDetail(
  sessionId: string,
  params?: { report_id?: string; step_id?: string },
): Promise<any> {
  const res = await apiClient.get(`/admin/conversations/${encodeURIComponent(sessionId)}`, { params });
  return res.data ?? null;
}

export async function cloneConversation(payload: {
  source_report_id: string;
  source_phase: string;
  source_thread_id: string;
  target_activation_code: string;
  target_phase: string;
  target_thread_id?: string;
}): Promise<{ target_report_id: string; target_phase: string; target_thread_id: string }> {
  const res = await apiClient.post('/admin/conversations/clone', payload);
  return (res.data ?? {}) as { target_report_id: string; target_phase: string; target_thread_id: string };
}

export async function jumpToRumination(payload: {
  activation_code: string;
  target_section?: string;
  target_filter_step?: number;
  seed_table?: Record<string, unknown>;
}): Promise<{ progress: unknown; activation_code: string }> {
  const res = await apiClient.post('/admin/conversations/jump-to-rumination', payload);
  return (res.data ?? {}) as { progress: unknown; activation_code: string };
}

export async function getMockInfo(): Promise<{
  exists: boolean;
  record_template_path: string;
  prior_files: string[];
}> {
  const res = await apiClient.get('/admin/conversations/mock-info');
  return ((res.data as any)?.data ?? {}) as { exists: boolean; record_template_path: string; prior_files: string[] };
}

export async function initMock(): Promise<{ exists: boolean; record_template_path: string; prior_files: string[] }> {
  const res = await apiClient.post('/admin/conversations/init-mock');
  return ((res.data as any)?.data ?? {}) as any;
}

export async function applyMockToActivation(activationCode: string): Promise<{
  activation_code: string;
  report_id: string;
  applied_steps: string[];
  copied_prior: string[];
}> {
  const res = await apiClient.post('/admin/conversations/apply-mock-to-activation', {
    activation_code: activationCode,
  });
  return ((res.data as any)?.data ?? {}) as any;
}

export async function saveAsMock(payload: {
  activation_code?: string;
  report_id?: string;
}): Promise<{ report_id: string; activation_code?: string; saved_prior_phases: string[] }> {
  const res = await apiClient.post('/admin/conversations/save-as-mock', payload);
  return ((res.data as any)?.data ?? {}) as any;
}

export interface AdminReportItem {
  report_id: string;
  activation_code: string;
  user_id: string;
  status: string;
  created_at: string;
  updated_at: string;
  step_stats: Record<string, number>;
  completed_steps: number;
}

export async function fetchAdminReports(params?: {
  q?: string;
  activation_code?: string;
  user_id?: string;
}): Promise<{ items: AdminReportItem[]; total: number }> {
  const res = await apiClient.get('/admin/reports', { params });
  return (res.data ?? { items: [], total: 0 }) as { items: AdminReportItem[]; total: number };
}

export async function fetchAdminReportDetail(reportId: string): Promise<any> {
  const res = await apiClient.get(`/admin/reports/${encodeURIComponent(reportId)}`);
  return res.data ?? null;
}

export async function syncReportsFromActivations() {
  const res = await apiClient.post('/admin/reports/sync-from-activations');
  return res.data ?? { created: 0, scanned: 0 };
}

export async function fetchAdminChatRecords(params?: {
  page?: number;
  page_size?: number;
  dimension?: string;
  session_id?: string;
}) {
  const res = await apiClient.get('/admin/analytics/chat-records', { params });
  return res.data ?? { records: [], total: 0, page: 1, page_size: 50 };
}

export async function fetchAdminSessionDetail(sessionId: string) {
  const res = await apiClient.get('/admin/analytics/session-detail', { params: { session_id: sessionId } });
  return res.data ?? null;
}

export async function fetchAdminLikeDetail(sessionId: string, logIndex: number) {
  const res = await apiClient.get('/admin/analytics/like-detail', {
    params: { session_id: sessionId, log_index: logIndex },
  });
  return res.data ?? null;
}

export async function fetchAdminSystemSettings() {
  const res = await apiClient.get('/admin/system/settings');
  return (res.data?.data ?? res.data ?? {}) as Record<string, unknown>;
}

export async function patchAdminSystemSettings(payload: {
  basic_info_merge_strategy?: 'A' | 'B' | 'C';
}) {
  const res = await apiClient.patch('/admin/system/settings', payload);
  return (res.data?.data ?? res.data ?? {}) as Record<string, unknown>;
}

export interface AdminAnalyticsDashboard {
  user_count: number;
  visit_count: number;
  dialogs_by_dimension: Record<string, number>;
  user_input_total_chars: number;
  llm_input_tokens: number;
  llm_output_tokens: number;
  report_count: number;
  last_stop_by_dimension: Record<string, number>;
  like_count: number;
  like_records: Array<{
    id: number;
    session_id: string;
    log_index: number;
    content_preview?: string;
    dimension?: string;
    created_at?: string;
  }>;
}

export async function fetchAdminAnalyticsDashboard(): Promise<AdminAnalyticsDashboard> {
  const res = await apiClient.get('/admin/analytics');
  return (res.data ?? {}) as AdminAnalyticsDashboard;
}

/** Admin 调试沙箱（从正式激活码 Fork，独立目录） */
export interface AdminSandboxItem {
  activation_code: string;
  fork_id?: string | null;
  sandbox_root?: string | null;
  session_id: string;
  forked_from_code?: string | null;
  forked_at?: string | null;
  forked_by_user_id?: string | null;
  sandbox_expires_at?: string | null;
  status: string;
  expired: boolean;
  created_at?: string;
  expires_at?: string;
}

export async function fetchAdminSandboxes(): Promise<{
  items: AdminSandboxItem[];
  total: number;
  retention_days: number;
}> {
  const res = await apiClient.get<{
    items: AdminSandboxItem[];
    total: number;
    retention_days: number;
  }>('/admin/sandboxes');
  const d = res.data ?? { items: [], total: 0, retention_days: 15 };
  return d;
}

export interface AdminResidentWorkspace {
  created: boolean;
  activation_code: string;
  session_id: string;
  workspace_kind?: 'resident' | null;
  workspace_root?: string | null;
  status: string;
  expires_at?: string;
}

export async function ensureAdminWorkspace(): Promise<AdminResidentWorkspace> {
  const res = await apiClient.post('/admin/workspace/ensure', {});
  return (res.data ?? {}) as AdminResidentWorkspace;
}

export async function forkAdminSandbox(source_activation_code: string): Promise<{
  sandbox_activation_code: string;
  fork_id: string;
  sandbox_root: string;
  report_id: string;
  session_id: string;
  source_activation_code: string;
  source_report_id: string;
  sandbox_expires_at: string;
  retention_days: number;
}> {
  const res = await apiClient.post('/admin/sandboxes/fork', { source_activation_code });
  return (res.data ?? {}) as any;
}

export async function deleteAdminSandbox(activation_code: string): Promise<void> {
  await apiClient.delete('/admin/sandboxes', { params: { activation_code } });
}

export async function purgeExpiredAdminSandboxes(): Promise<{ removed: number }> {
  const res = await apiClient.post('/admin/sandboxes/purge-expired', {});
  return (res.data ?? { removed: 0 }) as { removed: number };
}

export interface PromptLabProfileSummary {
  profile_id: string;
  name: string;
  description: string;
  current_version_id?: string | null;
  version_count: number;
  updated_at?: string;
  created_at?: string;
}

export interface PromptLabVersion {
  version_id: string;
  created_at: string;
  created_by?: { user_id?: string; email?: string };
  simple_chat_system_prompt_template: string;
  extra_goal_hint?: string;
}

export interface PromptLabProfileDetail {
  profile_id: string;
  name: string;
  description: string;
  current_version_id?: string | null;
  versions: PromptLabVersion[];
  updated_at?: string;
  created_at?: string;
}

export interface PromptLabBinding {
  activation_code: string;
  profile_id: string;
  created_at?: string;
  updated_at?: string;
  updated_by?: { user_id?: string; email?: string };
}

export async function listPromptLabProfiles(): Promise<PromptLabProfileSummary[]> {
  const res = await apiClient.get('/admin/prompt-lab/profiles');
  return (res.data?.items ?? []) as PromptLabProfileSummary[];
}

export async function createPromptLabProfile(payload: {
  name: string;
  description?: string;
}): Promise<PromptLabProfileDetail> {
  const res = await apiClient.post('/admin/prompt-lab/profiles', payload);
  return (res.data ?? {}) as PromptLabProfileDetail;
}

export async function getPromptLabProfile(profileId: string): Promise<PromptLabProfileDetail> {
  const res = await apiClient.get(`/admin/prompt-lab/profiles/${encodeURIComponent(profileId)}`);
  return (res.data ?? {}) as PromptLabProfileDetail;
}

export interface PromptLabExportPayload {
  profile_id: string;
  profile_name: string;
  current_version_id: string;
  template: string;
  extra_goal_hint?: string;
  merged_for_copy: string;
  copied_from?: {
    created_at?: string;
    created_by?: { user_id?: string; email?: string };
  };
}

export async function exportPromptLabCurrent(profileId: string): Promise<PromptLabExportPayload> {
  const res = await apiClient.get(
    `/admin/prompt-lab/profiles/${encodeURIComponent(profileId)}/export-current`,
  );
  return (res.data ?? {}) as PromptLabExportPayload;
}

export async function addPromptLabProfileVersion(
  profileId: string,
  payload: {
    simple_chat_system_prompt_template: string;
    extra_goal_hint?: string;
  },
): Promise<PromptLabVersion> {
  const res = await apiClient.post(
    `/admin/prompt-lab/profiles/${encodeURIComponent(profileId)}/versions`,
    payload,
  );
  return (res.data ?? {}) as PromptLabVersion;
}

export async function activatePromptLabVersion(
  profileId: string,
  versionId: string,
): Promise<PromptLabProfileDetail> {
  const res = await apiClient.post(
    `/admin/prompt-lab/profiles/${encodeURIComponent(profileId)}/activate-version`,
    { version_id: versionId },
  );
  return (res.data ?? {}) as PromptLabProfileDetail;
}

export async function listPromptLabBindings(): Promise<PromptLabBinding[]> {
  const res = await apiClient.get('/admin/prompt-lab/bindings');
  return (res.data?.items ?? []) as PromptLabBinding[];
}

export async function bindPromptLabProfile(payload: {
  activation_code: string;
  profile_id: string;
}): Promise<{ activation_code: string; profile_id: string }> {
  const res = await apiClient.post('/admin/prompt-lab/bindings', payload);
  return (res.data ?? {}) as { activation_code: string; profile_id: string };
}

