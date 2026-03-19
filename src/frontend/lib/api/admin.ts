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
  return res.data ?? {};
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

