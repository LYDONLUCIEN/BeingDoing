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
  return match?.[1] || fallback;
}

function triggerBlobDownload(blob: Blob, filename: string): void {
  const url = window.URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  setTimeout(() => window.URL.revokeObjectURL(url), 100);
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

export type ReportReviewStatus = 'pending_review' | 'approved';

export interface MyReportInfo {
  report_id: string | null;
  /** 审核状态；存量报告无该字段，视为 approved（祖父豁免） */
  review_status: ReportReviewStatus | null;
  /** 审核截止时间（ISO 字符串），仅 pending_review 时可能返回 */
  review_deadline: string | null;
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
  };
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
  return { status: data?.status ?? 'none', error: data?.error };
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
  const filename = pickFilenameFromHeaders(res.headers, `寻路报告_${reportId}.pdf`);
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
