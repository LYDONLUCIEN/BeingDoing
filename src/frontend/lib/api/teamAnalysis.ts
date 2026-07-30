/**
 * 团队分析 + 报告授权 API（P-E，ADR-0010）
 *
 * 团队分析：
 * - GET  /team-analysis/candidates   候选报告（自己码的 + 购买交付且已授权的）
 * - POST /team-analysis              创建分析（后台 LLM 生成）
 * - GET  /team-analysis              我的分析列表
 * - GET  /team-analysis/{id}         详情（含结果 markdown）
 *
 * 报告授权（simple-auth）：
 * - GET  /simple-auth/codes/{code}/report-authorize   授权状态
 * - POST /simple-auth/codes/{code}/report-authorize   一键授权/撤销（仅激活人）
 * - GET  /simple-auth/my-purchased-codes              所属人视角（我购买的码）
 */

import { apiClient } from './client';

// ─── 类型 ────────────────────────────────────────────────────

export interface TeamCandidate {
  activation_code: string;
  role: 'self' | 'purchased';
  owner_label: string;
  activated?: boolean;
  has_report: boolean;
  report_id: string | null;
  report_authorized: boolean;
  selectable: boolean;
}

export interface TeamAnalysisItem {
  id: string;
  title: string;
  code_list: string[];
  status: 'generating' | 'done' | 'failed';
  error: string | null;
  created_at: string | null;
  result_markdown?: string | null;
}

export interface PurchasedCodeItem {
  code: string;
  code_type: 'trial' | 'full';
  package_type: 'quarterly' | 'annual' | null;
  status: string;
  expires_at: string | null;
  created_at: string | null;
  activated: boolean;
  activated_by: string | null;
  activated_by_self: boolean;
  has_report: boolean;
  report_authorized: boolean;
  /** 报告审核状态：not_started / pending_review / approved；无报告或旧数据为 null */
  report_status: string | null;
}

export interface ReportAuthorizeState {
  code: string;
  authorized: boolean;
  is_activator: boolean;
  purchaser_email: string | null;
}

interface ListResponse<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
}

// ─── 团队分析 ────────────────────────────────────────────────

export async function fetchTeamCandidates(): Promise<TeamCandidate[]> {
  const res = await apiClient.get<{ items: TeamCandidate[] }>('/team-analysis/candidates');
  return res.data?.items ?? [];
}

export async function createTeamAnalysis(payload: {
  code_list: string[];
  title?: string;
}): Promise<TeamAnalysisItem> {
  const res = await apiClient.post<{ analysis: TeamAnalysisItem }>('/team-analysis', payload);
  return res.data.analysis;
}

export async function fetchTeamAnalyses(
  page = 1,
  pageSize = 20
): Promise<ListResponse<TeamAnalysisItem>> {
  const res = await apiClient.get<ListResponse<TeamAnalysisItem>>('/team-analysis', {
    params: { page, page_size: pageSize },
  });
  return (res.data ?? { items: [], total: 0, page: 1, page_size: pageSize }) as ListResponse<TeamAnalysisItem>;
}

export async function fetchTeamAnalysis(id: string): Promise<TeamAnalysisItem> {
  const res = await apiClient.get<{ analysis: TeamAnalysisItem }>(`/team-analysis/${id}`);
  return res.data.analysis;
}

// ─── 报告授权 ────────────────────────────────────────────────

export async function fetchReportAuthorize(code: string): Promise<ReportAuthorizeState> {
  const res = await apiClient.get<ReportAuthorizeState>(
    `/simple-auth/codes/${encodeURIComponent(code)}/report-authorize`
  );
  return res.data;
}

export async function setReportAuthorize(
  code: string,
  authorized: boolean
): Promise<{ code: string; authorized: boolean }> {
  const res = await apiClient.post<{ code: string; authorized: boolean }>(
    `/simple-auth/codes/${encodeURIComponent(code)}/report-authorize`,
    { authorized }
  );
  return res.data;
}

export async function fetchMyPurchasedCodes(): Promise<PurchasedCodeItem[]> {
  const res = await apiClient.get<{ items: PurchasedCodeItem[] }>('/simple-auth/my-purchased-codes');
  return res.data?.items ?? [];
}
