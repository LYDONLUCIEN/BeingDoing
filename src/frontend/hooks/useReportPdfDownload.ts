'use client';

/**
 * 报告 PDF 下载 Hook —— 异步生成 + 轮询 + 下载。
 * 用户页面和 Admin 页面共用。
 */

import { useRef, useState, useCallback } from 'react';
import {
  triggerReportPdf,
  pollReportPdfStatus,
  downloadReportPdfFile,
  extractBlobError,
  type PdfGenStatus,
} from '@/lib/api/report';

interface UseReportPdfOptions {
  /** 用户端需传激活码（admin 不需要） */
  activationCode?: string;
}

interface UseReportPdfReturn {
  /** 当前 report_id 的下载状态 */
  status: PdfGenStatus | 'idle';
  /** 错误信息 */
  error: string | null;
  /** 正在处理的 report_id */
  activeReportId: string | null;
  /** 触发下载流程 */
  download: (reportId: string) => Promise<void>;
}

const POLL_INTERVAL_MS = 2000;
const POLL_MAX_ATTEMPTS = 60; // 最多轮询 2 分钟

export function useReportPdfDownload(options?: UseReportPdfOptions): UseReportPdfReturn {
  const [status, setStatus] = useState<PdfGenStatus | 'idle'>('idle');
  const [error, setError] = useState<string | null>(null);
  const [activeReportId, setActiveReportId] = useState<string | null>(null);
  const pollingRef = useRef(false);

  const download = useCallback(
    async (reportId: string) => {
      if (pollingRef.current) return;

      setError(null);
      setActiveReportId(reportId);

      try {
        // 1. 触发生成
        setStatus('generating');
        const triggerStatus = await triggerReportPdf(reportId, {
          activationCode: options?.activationCode,
        });

        // 如果缓存命中，直接下载
        if (triggerStatus === 'ready') {
          setStatus('ready');
          await downloadReportPdfFile(reportId, {
            activationCode: options?.activationCode,
          });
          setStatus('idle');
          setActiveReportId(null);
          return;
        }

        // 2. 轮询状态
        pollingRef.current = true;
        for (let i = 0; i < POLL_MAX_ATTEMPTS; i++) {
          await new Promise((resolve) => setTimeout(resolve, POLL_INTERVAL_MS));

          const { status: pollStatus, error: pollError } = await pollReportPdfStatus(
            reportId,
            { activationCode: options?.activationCode },
          );

          if (pollStatus === 'ready') {
            setStatus('ready');
            await downloadReportPdfFile(reportId, {
              activationCode: options?.activationCode,
            });
            setStatus('idle');
            setActiveReportId(null);
            pollingRef.current = false;
            return;
          }

          if (pollStatus === 'error') {
            setStatus('error');
            setError(pollError || '报告生成失败');
            pollingRef.current = false;
            return;
          }

          // 继续轮询 (generating / none)
          setStatus('generating');
        }

        // 超时
        setStatus('error');
        setError('报告生成超时，请稍后重试');
        pollingRef.current = false;
      } catch (e: any) {
        setStatus('error');
        setError(await extractBlobError(e));
        pollingRef.current = false;
      }
    },
    [options?.activationCode],
  );

  return { status, error, activeReportId, download };
}
