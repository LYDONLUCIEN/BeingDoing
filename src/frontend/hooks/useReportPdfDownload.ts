'use client';

/**
 * 报告 PDF 下载 Hook —— 异步生成 + 轮询 + 下载。
 * 用户页面和 Admin 页面共用。
 *
 * 两套用法：
 * - download()：旧行为，生成+轮询完成后自动触发浏览器下载（Admin 页面用）。
 * - check()/prepare()/saveNow()：用户报告页用。
 *   生成完成后【不自动下载】，由用户在手势内点击「下载」按钮（saveNow），
 *   避免 Chrome 将脱离用户手势的异步 blob 下载判定为「自动下载」而弹权限提示。
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
  /** 触发下载流程（生成+轮询+自动下载，Admin 用） */
  download: (reportId: string) => Promise<void>;
  /** 只查询当前状态（不触发生成）：none=未生成 / generating=生成中 / ready=可下载 */
  check: (reportId: string) => Promise<PdfGenStatus>;
  /** 生成+轮询，完成后停在 ready 状态，不自动下载（用户报告页用） */
  prepare: (reportId: string, opts?: { force?: boolean }) => Promise<void>;
  /** 用户手势内直接下载已生成的 PDF（命中缓存，不重新生成） */
  saveNow: (reportId: string) => Promise<void>;
}

const POLL_INTERVAL_MS = 2000;
const POLL_MAX_ATTEMPTS = 150; // 最多轮询 5 分钟（LLM 全量撰写报告可能超过 2 分钟）

export function useReportPdfDownload(options?: UseReportPdfOptions): UseReportPdfReturn {
  const [status, setStatus] = useState<PdfGenStatus | 'idle'>('idle');
  const [error, setError] = useState<string | null>(null);
  const [activeReportId, setActiveReportId] = useState<string | null>(null);
  const pollingRef = useRef(false);

  /** 轮询直到 ready/error/超时。返回最终状态。 */
  const pollUntilDone = useCallback(
    async (reportId: string): Promise<PdfGenStatus> => {
      pollingRef.current = true;
      try {
        for (let i = 0; i < POLL_MAX_ATTEMPTS; i++) {
          await new Promise((resolve) => setTimeout(resolve, POLL_INTERVAL_MS));

          const { status: pollStatus, error: pollError } = await pollReportPdfStatus(
            reportId,
            { activationCode: options?.activationCode },
          );

          if (pollStatus === 'ready') return 'ready';
          if (pollStatus === 'error') {
            setError(pollError || '报告生成失败');
            return 'error';
          }
        }
        // 超时：后台任务仍在运行，不视为失败，提示用户稍后直接下载
        setError('生成时间较长，后台仍在继续；稍后点击「下载 PDF 报告」即可，不会重新生成');
        return 'none';
      } finally {
        pollingRef.current = false;
      }
    },
    [options?.activationCode],
  );

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
        const final = await pollUntilDone(reportId);
        if (final === 'ready') {
          setStatus('ready');
          await downloadReportPdfFile(reportId, {
            activationCode: options?.activationCode,
          });
          setStatus('idle');
          setActiveReportId(null);
        } else {
          setStatus(final === 'error' ? 'error' : 'idle');
        }
      } catch (e: any) {
        setStatus('error');
        setError(await extractBlobError(e));
      }
    },
    [options?.activationCode, pollUntilDone],
  );

  const check = useCallback(
    async (reportId: string): Promise<PdfGenStatus> => {
      try {
        const { status: s } = await pollReportPdfStatus(reportId, {
          activationCode: options?.activationCode,
        });
        setActiveReportId(reportId);
        setStatus(s);
        return s;
      } catch {
        // 查询失败不阻断页面，保持现状
        return status === 'idle' ? 'none' : (status as PdfGenStatus);
      }
    },
    [options?.activationCode, status],
  );

  const prepare = useCallback(
    async (reportId: string, opts?: { force?: boolean }) => {
      if (pollingRef.current) return;

      setError(null);
      setActiveReportId(reportId);

      try {
        setStatus('generating');
        const triggerStatus = await triggerReportPdf(reportId, {
          activationCode: options?.activationCode,
          force: opts?.force,
        });

        if (triggerStatus === 'ready') {
          // 缓存命中：不自动下载，等用户点击「下载」按钮
          setStatus('ready');
          return;
        }

        const final = await pollUntilDone(reportId);
        setStatus(final === 'ready' ? 'ready' : final === 'error' ? 'error' : 'idle');
      } catch (e: any) {
        setStatus('error');
        setError(await extractBlobError(e));
      }
    },
    [options?.activationCode, pollUntilDone],
  );

  const saveNow = useCallback(
    async (reportId: string) => {
      setError(null);
      try {
        await downloadReportPdfFile(reportId, {
          activationCode: options?.activationCode,
        });
      } catch (e: any) {
        const msg = await extractBlobError(e);
        // 409：缓存尚未就绪（例如上次超时后后台还没写完），提示并刷新状态
        setError(msg.includes('尚未生成') || msg.includes('已失效')
          ? '报告还在生成中，请稍后再点击下载'
          : msg);
        await check(reportId);
      }
    },
    [options?.activationCode, check],
  );

  return { status, error, activeReportId, download, check, prepare, saveNow };
}
