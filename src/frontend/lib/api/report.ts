/**
 * 报告 PDF 下载相关 API（异步生成 + 轮询 + 下载）。
 *
 * 后端端点：
 * - GET  /export/my-report-id              用户端通过激活码获取 report_id
 * - POST /export/report-pdf/{id}           触发生成，返回 generating/ready
 * - GET  /export/report-pdf-status/{id}    轮询生成状态
 * - GET  /export/report-pdf-download/{id}  下载已完成的 PDF
 */

import { apiClient } from './client';

export type PdfGenStatus = 'generating' | 'ready' | 'error' | 'none';

function pickFilenameFromHeaders(headers: any, fallback: string): string {
  const disposition: string = headers?.['content-disposition'] || '';
  const match = /filename\*?=(?:UTF-8'')?"?([^";]+)"?/i.exec(disposition);
  const raw = match?.[1];
  if (!raw) return fallback;
  // 后端按 RFC 5987 返回 filename*=UTF-8''<percent-encoded>，需解码还原中文文件名
  try {
    return decodeURIComponent(raw);
  } catch {
    return raw;
  }
}

function triggerBlobDownload(blob: Blob, filename: string): void {
  const url = window.URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  // 延长回收时间：100ms 在部分浏览器/大文件下会导致下载中断
  setTimeout(() => window.URL.revokeObjectURL(url), 10_000);
}

/**
 * 用户端：通过激活码获取自己的 report_id。
 */
export async function getMyReportId(activationCode: string): Promise<string | null> {
  const res = await apiClient.raw.get('/export/my-report-id', {
    params: { activation_code: activationCode },
  });
  return (res.data as any)?.report_id ?? null;
}

export type ReportReviewStatus = 'not_started' | 'pending_review' | 'approved';

/** 复核状态（进行中）：pending=待处理 / regenerating=重新生成中 / pending_confirm=待 admin 确认 */
export type RecheckStatus = 'pending' | 'regenerating' | 'pending_confirm';

export interface MyReportInfo {
  report_id: string | null;
  /** 审核状态；存量报告无该字段，视为 approved（祖父豁免）；not_started = 五阶段未完成或尚未进入报告页 */
  review_status: ReportReviewStatus | null;
  /** 审核截止时间（ISO 字符串），仅 pending_review 时可能返回 */
  review_deadline: string | null;
  /** 复核进行中状态；null = 无进行中复核 */
  recheck_status: RecheckStatus | null;
}

/**
 * 用户端：通过激活码获取报告信息（含审核状态）。
 * 契约：审核中时返回 review_status="pending_review" + review_deadline（不含报告内容）；
 * 已批准时 review_status="approved" + 原报告内容。
 */
export async function getMyReportInfo(activationCode: string): Promise<MyReportInfo> {
  const res = await apiClient.raw.get('/export/my-report-id', {
    params: { activation_code: activationCode },
  });
  const body = res.data as any;
  const data = body?.data ?? body;
  return {
    report_id: data?.report_id ?? null,
    review_status: data?.review_status ?? null,
    review_deadline: data?.review_deadline ?? null,
    recheck_status: data?.recheck_status ?? null,
  };
}

export interface MyReportListItem {
  report_id: string;
  activation_code: string;
  review_status: ReportReviewStatus;
  review_deadline: string | null;
  created_at: string | null;
  code_type: string | null;
}

/**
 * 用户端：我的报告列表（只读）。
 * 契约：GET /export/my-reports → { items: [...] }（裸 JSON）。
 * review_status 三态（后端已做存量豁免）：not_started / pending_review / approved。
 */
export async function getMyReports(): Promise<MyReportListItem[]> {
  const res = await apiClient.raw.get('/export/my-reports');
  const body = res.data as any;
  const data = body?.data ?? body;
  return (data?.items ?? []) as MyReportListItem[];
}

/**
 * 触发 PDF 报告生成。
 * 返回 status: 'generating' | 'ready'
 */
export async function triggerReportPdf(
  reportId: string,
  options?: {
    activationCode?: string;
    force?: boolean;
  },
): Promise<PdfGenStatus> {
  const params: Record<string, any> = {};
  if (options?.activationCode) params.activation_code = options.activationCode;
  if (options?.force) params.force = 'true';

  const res = await apiClient.raw.post(
    `/export/report-pdf/${encodeURIComponent(reportId)}`,
    undefined,
    { params },
  );
  return (res.data as any)?.status ?? 'generating';
}

/**
 * 轮询报告生成状态。
 */
export async function pollReportPdfStatus(
  reportId: string,
  options?: { activationCode?: string },
): Promise<{ status: PdfGenStatus; error?: string }> {
  const params: Record<string, any> = {};
  if (options?.activationCode) params.activation_code = options.activationCode;

  const res = await apiClient.raw.get(
    `/export/report-pdf-status/${encodeURIComponent(reportId)}`,
    { params },
  );
  const data = res.data as any;
  return {
    status: data?.status ?? 'none',
    error: data?.error,
  };
}

/**
 * 下载已生成的 PDF 报告。
 */
export async function downloadReportPdfFile(
  reportId: string,
  options?: { activationCode?: string },
): Promise<void> {
  const params: Record<string, any> = {};
  if (options?.activationCode) params.activation_code = options.activationCode;

  const res = await apiClient.raw.get(
    `/export/report-pdf-download/${encodeURIComponent(reportId)}`,
    { params, responseType: 'blob' },
  );

  const blob = res.data as Blob;
  const filename = pickFilenameFromHeaders(res.headers, `寻路OpenLife职业探索报告.pdf`);
  triggerBlobDownload(blob, filename);
}

/**
 * 从 Blob 错误响应中提取错误信息。
 */
export async function extractBlobError(e: any): Promise<string> {
  if (e?.response?.data instanceof Blob) {
    try {
      const text = await e.response.data.text();
      const parsed = JSON.parse(text);
      return parsed?.detail || parsed?.message || '操作失败';
    } catch {
      return '操作失败';
    }
  }
  return e?.response?.data?.detail || e?.message || '操作失败';
}

// ---------- 报告复核（2026-08-18）----------

export type RecheckCategory = 'content_issue' | 'download_issue';

export interface RecheckSubmitResult {
  /** recheck = 已建复核单（内容问题）；feedback = 已转故障反馈（下载问题） */
  path: 'recheck' | 'feedback';
}

/**
 * 提交报告复核申请。
 * content_issue → 建复核单 + 双写 Feedback 工单（每报告每天限 1 次，有进行中复核时 409）；
 * download_issue → 仅进 Feedback 通道（与「反馈 bug」同流程同结果）。
 */
export async function submitReportRecheck(
  reportId: string,
  options: {
    activationCode: string;
    category: RecheckCategory;
    description?: string;
  },
): Promise<RecheckSubmitResult> {
  const res = await apiClient.raw.post(
    `/export/report-recheck/${encodeURIComponent(reportId)}`,
    { category: options.category, description: options.description ?? '' },
    { params: { activation_code: options.activationCode } },
  );
  return { path: (res.data as any)?.path ?? 'feedback' };
}
