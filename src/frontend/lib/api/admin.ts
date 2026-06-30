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

/**
 * 从 axios 响应头 Content-Disposition 取文件名，兜底返回 fallback。
 */
function pickFilenameFromHeaders(headers: any, fallback: string): string {
  const disposition: string = headers?.['content-disposition'] || '';
  const match = /filename\*?=(?:UTF-8'')?"?([^";]+)"?/i.exec(disposition);
  return match?.[1] || fallback;
}

/**
 * 用 Blob 触发浏览器下载（内部工具）。
 */
function triggerBlobDownload(blob: Blob, filename: string): void {
  const url = window.URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  // 延迟回收 object URL，给浏览器足够时间发起下载（慢网络下 0ms 可能过早 revoke）
  setTimeout(() => window.URL.revokeObjectURL(url), 100);
}

/**
 * 批量导出报告对话记录（zip）。
 * 后端返回 application/zip blob，前端触发浏览器下载。
 * 单次最多 50 个 report。
 *
 * 注：用底层 axios 实例请求，因为 apiClient.post 包装方法会解包 response.data，
 * 而 blob 下载需要完整的 AxiosResponse（取 data: Blob 与 headers）。
 */
export async function exportReportsBatch(
  reportIds: string[],
  format: 'md' | 'txt',
): Promise<void> {
  const res = await apiClient.raw.post(
    '/admin/reports/export/batch',
    {
      report_ids: reportIds,
      format,
    },
    {
      responseType: 'blob',
    },
  );
  const blob = res.data as Blob;
  const filename = pickFilenameFromHeaders(res.headers, 'reports_batch_export.zip');
  triggerBlobDownload(blob, filename);
}

/**
 * 下载单个 report 的完整明细（zip，带认证 token）。
 *
 * zip 内含：raw/*.json（各 phase 完整对话源文件）、report_{id}.md（纯净对话）、
 * stats.json（字数/用时/token 统计）。
 *
 * 不用 <a href> 直接跳转，因为浏览器跳转无法附加 Authorization header，
 * 后端会返回 401。改为用 axios 拉 blob 再触发下载。
 */
export async function downloadReportJson(reportId: string): Promise<void> {
  const res = await apiClient.raw.get(
    `/admin/reports/${encodeURIComponent(reportId)}/download`,
    {
      responseType: 'blob',
    },
  );
  const blob = res.data as Blob;
  const filename = pickFilenameFromHeaders(
    res.headers,
    `report_${reportId}.zip`,
  );
  triggerBlobDownload(blob, filename);
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

export interface AdminSavepointItem {
  savepoint_id: string;
  display_name: string;
  created_at: string;
  created_by_user_id?: string;
  source_activation_code: string;
  source_report_id: string;
  phase: string;
  thread_id: string;
  rewind_mode: 'global_rewind';
  fixture_path: string;
  meta_path: string;
  expected_hint?: string;
  replay_command?: string;
  last_replay_status?: 'passed' | 'failed' | null;
  last_replay_at?: string | null;
  last_replay_summary?: string | null;
}

export async function fetchAdminSavepoints(): Promise<{ items: AdminSavepointItem[]; total: number }> {
  const res = await apiClient.get('/admin/savepoints');
  return (res.data ?? { items: [], total: 0 }) as { items: AdminSavepointItem[]; total: number };
}

export async function createAdminSavepoint(payload: {
  activation_code: string;
  phase: string;
  thread_id: string;
  target_message_index: number;
  display_name: string;
  expected_hint?: string;
  expected_keywords?: string[];
}): Promise<any> {
  const res = await apiClient.post('/admin/savepoints/create', payload);
  return res.data ?? {};
}

export async function loadAdminSavepoint(payload: {
  activation_code: string;
  savepoint_id: string;
}): Promise<{ loaded: boolean; savepoint_id: string; activation_code: string; phase: string; thread_id: string }> {
  const res = await apiClient.post('/admin/savepoints/load', payload);
  return (res.data ?? {}) as {
    loaded: boolean;
    savepoint_id: string;
    activation_code: string;
    phase: string;
    thread_id: string;
  };
}

export async function deleteAdminSavepoint(payload: { savepoint_id: string }): Promise<{ deleted: boolean; savepoint_id: string }> {
  const res = await apiClient.delete('/admin/savepoints', { data: payload });
  return (res.data ?? {}) as { deleted: boolean; savepoint_id: string };
}

export async function exportAdminSavepoint(payload: { savepoint_id: string }): Promise<{
  savepoint_id: string;
  exported_at?: string;
  fixture_dir: string;
  fixture_report_dir: string;
  cases_file: string;
  scenario_file: string;
  playwright_scenario_file?: string;
  playwright_command?: string;
  replay_command: string;
}> {
  const res = await apiClient.post('/admin/savepoints/export', payload);
  return (res.data ?? {}) as {
    savepoint_id: string;
    exported_at?: string;
    fixture_dir: string;
    fixture_report_dir: string;
    cases_file: string;
    scenario_file: string;
    playwright_scenario_file?: string;
    playwright_command?: string;
    replay_command: string;
  };
}

export interface AdminGeneratedScenarioItem {
  savepoint_id: string;
  display_name: string;
  exported_at: string;
  phase: string;
  thread_id: string;
  source_activation_code: string;
  scenario_file: string;
  playwright_scenario_file?: string;
  playwright_command?: string;
  replay_command?: string;
  fixture_report_dir?: string;
  last_run_at?: string;
  last_run_status?: 'passed' | 'failed';
  last_run_engine?: 'auto' | 'replay' | 'playwright' | string;
  last_run_exit_code?: number;
  last_run_report_file?: string | null;
  last_run_summary?: string;
  last_run_stdout_tail?: string;
  last_run_stderr_tail?: string;
  last_run_code?: string;
  last_run_attempts?: number;
  last_run_log_file?: string;
}

export async function fetchAdminGeneratedScenarios(limit = 200): Promise<{
  items: AdminGeneratedScenarioItem[];
  total: number;
}> {
  const res = await apiClient.get('/admin/savepoints/generated-scenarios', { params: { limit } });
  return (res.data ?? { items: [], total: 0 }) as {
    items: AdminGeneratedScenarioItem[];
    total: number;
  };
}

export async function runAdminGeneratedScenario(payload: {
  savepoint_id: string;
  engine?: 'auto' | 'replay' | 'playwright';
  dry_run?: boolean;
  timeout_sec?: number;
}): Promise<{
  savepoint_id: string;
  engine: string;
  dry_run: boolean;
  command: string;
  exit_code: number;
  status: 'passed' | 'failed';
  summary: string;
  report_file?: string | null;
  stdout_tail?: string;
  stderr_tail?: string;
  last_run_at: string;
  run_code?: string;
  attempts?: number;
  log_file?: string;
}> {
  const res = await apiClient.post('/admin/savepoints/generated-scenarios/run', payload);
  return (res.data ?? {}) as {
    savepoint_id: string;
    engine: string;
    dry_run: boolean;
    command: string;
    exit_code: number;
    status: 'passed' | 'failed';
    summary: string;
    report_file?: string | null;
    stdout_tail?: string;
    stderr_tail?: string;
    last_run_at: string;
    run_code?: string;
    attempts?: number;
    log_file?: string;
  };
}

export async function runAdminGeneratedScenarioBatch(payload: {
  savepoint_ids?: string[];
  only_failed?: boolean;
  engine?: 'auto' | 'replay' | 'playwright';
  timeout_sec?: number;
  max_retries?: number;
}): Promise<{
  total: number;
  passed: number;
  failed: number;
  items: Array<{
    savepoint_id: string;
    status: 'passed' | 'failed';
    exit_code: number;
    summary: string;
    report_file?: string | null;
  }>;
  message?: string;
}> {
  const res = await apiClient.post('/admin/savepoints/generated-scenarios/run-batch', payload);
  return (res.data ?? {}) as {
    total: number;
    passed: number;
    failed: number;
    items: Array<{
      savepoint_id: string;
      status: 'passed' | 'failed';
      exit_code: number;
      summary: string;
      report_file?: string | null;
    }>;
    message?: string;
  };
}

export async function startAdminGeneratedScenarioBatchJob(payload: {
  savepoint_ids?: string[];
  only_failed?: boolean;
  engine?: 'auto' | 'replay' | 'playwright';
  timeout_sec?: number;
  max_retries?: number;
}): Promise<{
  job_id: string;
  status: 'running' | 'completed';
  total: number;
  processed: number;
  passed: number;
  failed: number;
}> {
  const res = await apiClient.post('/admin/savepoints/generated-scenarios/run-batch-async', payload);
  return (res.data ?? {}) as {
    job_id: string;
    status: 'running' | 'completed';
    total: number;
    processed: number;
    passed: number;
    failed: number;
  };
}

export async function fetchAdminGeneratedScenarioBatchJob(jobId: string): Promise<{
  job_id: string;
  status: 'running' | 'completed' | 'cancelled' | 'interrupted';
  total: number;
  processed: number;
  passed: number;
  failed: number;
  cancel_requested?: boolean;
  items?: Array<{
    savepoint_id: string;
    status: 'passed' | 'failed';
    exit_code: number;
    summary: string;
    report_file?: string | null;
    log_file?: string | null;
    run_code?: string;
  }>;
}> {
  const res = await apiClient.get(`/admin/savepoints/generated-scenarios/run-batch-async/${encodeURIComponent(jobId)}`);
  return (res.data ?? {}) as {
    job_id: string;
    status: 'running' | 'completed' | 'cancelled' | 'interrupted';
    total: number;
    processed: number;
    passed: number;
    failed: number;
    cancel_requested?: boolean;
    items?: Array<{
      savepoint_id: string;
      status: 'passed' | 'failed';
      exit_code: number;
      summary: string;
      report_file?: string | null;
      log_file?: string | null;
      run_code?: string;
    }>;
  };
}

export async function cancelAdminGeneratedScenarioBatchJob(jobId: string): Promise<{
  job_id: string;
  cancel_requested: boolean;
  status: 'running' | 'completed' | 'cancelled' | 'interrupted';
}> {
  const res = await apiClient.post(`/admin/savepoints/generated-scenarios/run-batch-async/${encodeURIComponent(jobId)}/cancel`, {});
  return (res.data ?? {}) as {
    job_id: string;
    cancel_requested: boolean;
    status: 'running' | 'completed' | 'cancelled' | 'interrupted';
  };
}

export async function fetchAdminGeneratedScenarioBatchJobs(limit = 50): Promise<{
  items: Array<{
    job_id: string;
    status: 'running' | 'completed' | 'cancelled' | 'interrupted';
    created_at?: string;
    started_at?: string;
    finished_at?: string;
    engine?: string;
    max_retries?: number;
    only_failed?: boolean;
    total: number;
    processed: number;
    passed: number;
    failed: number;
    cancel_requested?: boolean;
  }>;
  total: number;
}> {
  const res = await apiClient.get('/admin/savepoints/generated-scenarios/run-batch-async-jobs', { params: { limit } });
  return (res.data ?? { items: [], total: 0 }) as {
    items: Array<{
      job_id: string;
      status: 'running' | 'completed' | 'cancelled' | 'interrupted';
      created_at?: string;
      started_at?: string;
      finished_at?: string;
      engine?: string;
      max_retries?: number;
      only_failed?: boolean;
      total: number;
      processed: number;
      passed: number;
      failed: number;
      cancel_requested?: boolean;
    }>;
    total: number;
  };
}

export async function fetchAdminGeneratedScenarioBatchJobHistory(limit = 50): Promise<{
  items: Array<{
    job_id: string;
    status: 'running' | 'completed' | 'cancelled' | 'interrupted';
    created_at?: string;
    started_at?: string;
    finished_at?: string;
    engine?: string;
    max_retries?: number;
    only_failed?: boolean;
    total: number;
    processed: number;
    passed: number;
    failed: number;
  }>;
  total: number;
}> {
  const res = await apiClient.get('/admin/savepoints/generated-scenarios/run-batch-async-history', { params: { limit } });
  return (res.data ?? { items: [], total: 0 }) as {
    items: Array<{
      job_id: string;
      status: 'running' | 'completed' | 'cancelled' | 'interrupted';
      created_at?: string;
      started_at?: string;
      finished_at?: string;
      engine?: string;
      max_retries?: number;
      only_failed?: boolean;
      total: number;
      processed: number;
      passed: number;
      failed: number;
    }>;
    total: number;
  };
}

export async function cleanupAdminGeneratedScenarioBatchJobHistory(payload?: {
  keep_latest?: number;
  older_than_days?: number;
}): Promise<{ removed: number; remaining: number }> {
  const res = await apiClient.post('/admin/savepoints/generated-scenarios/run-batch-async-history/cleanup', payload ?? {});
  return (res.data ?? { removed: 0, remaining: 0 }) as { removed: number; remaining: number };
}

export interface AdminSavepointReplayLogItem {
  at: string;
  savepoint_id: string;
  display_name?: string;
  status: 'passed' | 'failed';
  summary?: string;
  command?: string;
  source_activation_code?: string;
  phase?: string;
  thread_id?: string;
}

export async function fetchAdminSavepointReplayLogs(limit = 200): Promise<{
  items: AdminSavepointReplayLogItem[];
  total: number;
}> {
  const res = await apiClient.get('/admin/savepoints/replay-logs', { params: { limit } });
  return (res.data ?? { items: [], total: 0 }) as {
    items: AdminSavepointReplayLogItem[];
    total: number;
  };
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

export interface PromptContentSegment {
  type: 'text' | 'variable';
  content?: string;
  name?: string;
  raw?: string;
}

export interface PromptCatalogLayer {
  id: string;
  kind: 'static' | 'runtime';
  category?: string;
  label: string;
  phase_match?: string;
  active?: boolean;
  content?: string;
  segments?: PromptContentSegment[];
  nested_conditions?: Array<{
    condition: string;
    content: string;
    segments?: PromptContentSegment[];
  }>;
  inject_after?: string;
  trigger?: string;
  source_path?: string;
  collapsed_default?: boolean;
}

export interface PromptCatalogSection {
  key: string;
  label: string;
  category: string;
  source_path?: string;
  content?: string;
  segments?: PromptContentSegment[];
  layer_stack?: PromptCatalogLayer[];
  opening_mode?: string;
  items?: Array<{
    role: string;
    label?: string;
    content?: string;
    segments?: PromptContentSegment[];
    source_path?: string;
  }>;
}

export interface PromptCatalogRuminationStep {
  step: number;
  label: string;
  opening_mode: string;
  sections: PromptCatalogSection[];
}

export interface PromptCatalogPhase {
  key: string;
  label: string;
  color: string;
  sections: PromptCatalogSection[];
  rumination_steps?: PromptCatalogRuminationStep[];
}

export interface PromptCatalogSimpleChatDiff {
  canonical_source: string;
  canonical_template: string;
  override_template?: string | null;
  override_meta?: {
    profile_id?: string;
    profile_name?: string;
    version_id?: string;
  } | null;
  effective_preview: string;
  effective_phase: string;
  active_branch_content?: string;
  has_override: boolean;
}

export interface PromptCatalogData {
  locale: string;
  phases: PromptCatalogPhase[];
  variable_samples: Record<string, string>;
  runtime_injection_catalog: Array<Record<string, unknown>>;
  simple_chat_system_diff: PromptCatalogSimpleChatDiff;
  test_links: { savepoint_resume: string; fork_from_scratch: string };
}

export async function fetchPromptCatalog(params?: {
  locale?: 'zh' | 'en';
  profileId?: string;
  previewPhase?: string;
}): Promise<PromptCatalogData> {
  const res = await apiClient.get('/admin/prompt-catalog', {
    params: {
      locale: params?.locale ?? 'zh',
      profile_id: params?.profileId,
      preview_phase: params?.previewPhase ?? 'values',
    },
  });
  return (res.data ?? {}) as PromptCatalogData;
}

// ─── Admin Users ──────────────────────────────────────────────

export interface AdminUserItem {
  user_id: string;
  email?: string | null;
  username?: string | null;
  is_active: boolean;
  email_verified?: boolean;
  created_at?: string | null;
  last_login_at?: string | null;
  profile_completed: boolean;
  activation_count: number;
}

export interface AdminUserActivation {
  activation_code: string;
  session_id?: string;
  status: string;
  created_at?: string;
  expires_at?: string;
  claimed_at?: string;
  is_sandbox?: boolean;
}

export interface AdminUserDetail {
  user_id: string;
  email?: string | null;
  phone?: string | null;
  username?: string | null;
  is_active: boolean;
  created_at?: string | null;
  updated_at?: string | null;
  last_login_at?: string | null;
  profile: {
    gender?: string | null;
    age?: number | null;
    profile_completed: boolean;
    survey_data?: Record<string, any>;
  };
  activations: AdminUserActivation[];
  work_histories: Array<{
    id: string;
    company?: string | null;
    position?: string | null;
    start_date?: string | null;
    end_date?: string | null;
    evaluation?: string | null;
    skills_used?: string | null;
    projects: Array<{
      id: string;
      name: string;
      description?: string | null;
      role?: string | null;
      achievements?: string | null;
    }>;
  }>;
}

export async function fetchAdminUsers(params?: {
  page?: number;
  page_size?: number;
  q?: string;
  is_active?: boolean | null;
  profile_completed?: boolean | null;
  created_after?: string;
  created_before?: string;
}): Promise<{ items: AdminUserItem[]; total: number; page: number; page_size: number }> {
  const res = await apiClient.get('/admin/users', { params });
  return (res.data ?? { items: [], total: 0, page: 1, page_size: 50 }) as {
    items: AdminUserItem[];
    total: number;
    page: number;
    page_size: number;
  };
}

export async function fetchAdminUserDetail(userId: string): Promise<AdminUserDetail> {
  const res = await apiClient.get(`/admin/users/${encodeURIComponent(userId)}`);
  return (res.data ?? {}) as AdminUserDetail;
}

export async function patchAdminUserStatus(
  userId: string,
  isActive: boolean,
): Promise<{ user_id: string; is_active: boolean }> {
  const res = await apiClient.patch(`/admin/users/${encodeURIComponent(userId)}/status`, {
    is_active: isActive,
  });
  return (res.data ?? {}) as { user_id: string; is_active: boolean };
}

export async function adminVerifyUserEmail(
  userId: string,
): Promise<{ user_id: string; email_verified: boolean }> {
  const res = await apiClient.post(`/admin/users/${encodeURIComponent(userId)}/verify-email`);
  return (res.data?.data ?? {}) as { user_id: string; email_verified: boolean };
}

// ─── Notification Email (通知邮件群发) ─────────────────────────

export interface NotificationUserFilter {
  is_active?: boolean | null;
  profile_completed?: boolean | null;
  created_after?: string;
  /** 手动勾选模式：显式指定收件人 user_id 列表，非空时忽略其他筛选 */
  user_ids?: string[];
}

export interface NotificationRecipientStatus {
  email: string;
  user_id?: string | null;
  status: 'pending' | 'sent' | 'failed';
  error_msg?: string | null;
}

export interface NotificationTaskStatus {
  task_id: string;
  subject: string;
  body: string;
  filter: NotificationUserFilter;
  total: number;
  sent: number;
  failed: number;
  status: 'pending' | 'running' | 'completed' | 'interrupted' | 'failed';
  created_at?: string | null;
  started_at?: string | null;
  finished_at?: string | null;
  recipients: NotificationRecipientStatus[];
}

export interface NotificationTaskListItem {
  task_id: string;
  subject: string;
  total: number;
  sent: number;
  failed: number;
  status: 'pending' | 'running' | 'completed' | 'interrupted' | 'failed';
  created_at?: string | null;
  finished_at?: string | null;
}

/**
 * 创建通知邮件群发任务（后台异步发送，立即返回 task_id）。
 */
export async function sendNotificationEmail(payload: {
  subject: string;
  body: string;
  user_filter?: NotificationUserFilter;
}): Promise<{ task_id: string }> {
  const res = await apiClient.post('/admin/notifications/email', payload);
  return (res.data ?? {}) as { task_id: string };
}

/**
 * 查询单个群发任务的进度详情（含收件人明细）。
 */
export async function getNotificationStatus(taskId: string): Promise<NotificationTaskStatus> {
  const res = await apiClient.get(`/admin/notifications/email/${encodeURIComponent(taskId)}`);
  return (res.data ?? {}) as NotificationTaskStatus;
}

/**
 * 分页查询历史任务列表。
 */
export async function listNotificationTasks(params?: {
  page?: number;
  page_size?: number;
}): Promise<{ items: NotificationTaskListItem[]; total: number; page: number; page_size: number }> {
  const res = await apiClient.get('/admin/notifications/email', { params });
  return (res.data ?? { items: [], total: 0, page: 1, page_size: 20 }) as {
    items: NotificationTaskListItem[];
    total: number;
    page: number;
    page_size: number;
  };
}

// ─── 每轮平均时间统计（T3） ─────────────────────────────────────

export interface ConversationPhaseStat {
  phase_id: string;
  phase_name: string;
  session_id?: string;
  turns: number;
  avg_seconds: number;
  total_seconds: number;
  avg_minutes: number;
  total_minutes: number;
  skipped_no_ts: number;
  skipped_long_turns: number;
  total_turns_seen: number;
  message_count: number;
}

export interface ConversationStatsResult {
  total_turns: number;
  total_seconds: number;
  avg_seconds: number;
  total_minutes: number;
  avg_minutes: number;
  skipped_no_ts: number;
  skipped_long_turns: number;
  per_phase: ConversationPhaseStat[];
  report_count?: number;
  reminder_text: string;
}

/**
 * 获取用户所有对话的每轮平均时长统计。
 */
export async function getUserConversationStats(userId: string): Promise<ConversationStatsResult> {
  const res = await apiClient.get(`/admin/users/${encodeURIComponent(userId)}/conversation-stats`);
  return (res.data ?? {}) as ConversationStatsResult;
}

/**
 * 获取单个 report 的每轮平均时长统计。
 */
export async function getReportConversationStats(reportId: string): Promise<ConversationStatsResult> {
  const res = await apiClient.get(
    `/admin/reports/${encodeURIComponent(reportId)}/conversation-stats`,
  );
  return (res.data ?? {}) as ConversationStatsResult;
}

