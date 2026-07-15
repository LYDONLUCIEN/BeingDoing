/**
 * 报告 PDF 下载相关 API。
 *
 * 后端端点：
 * - GET  /export/my-report-id        用户端通过激活码获取 report_id
 * - POST /export/report-pdf/{id}     生成并下载 PDF
 */

import { apiClient } from './client';

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

/**
 * 下载报告 PDF（通用，admin 和用户共用）。
 *
 * @param reportId  报告 ID
 * @param options   可选参数
 *   - activationCode: 用户端必须传入（权限校验），admin 端可不传
 *   - force: 是否强制重新生成（跳过缓存）
 */
export async function downloadReportPdf(
  reportId: string,
  options?: {
    activationCode?: string;
    force?: boolean;
  },
): Promise<void> {
  const params: Record<string, any> = {};
  if (options?.activationCode) {
    params.activation_code = options.activationCode;
  }
  if (options?.force) {
    params.force = 'true';
  }

  const res = await apiClient.raw.post(
    `/export/report-pdf/${encodeURIComponent(reportId)}`,
    undefined, // POST 无 body
    {
      params,
      responseType: 'blob',
    },
  );

  const blob = res.data as Blob;
  const filename = pickFilenameFromHeaders(res.headers, `寻路报告_${reportId}.pdf`);
  triggerBlobDownload(blob, filename);
}
