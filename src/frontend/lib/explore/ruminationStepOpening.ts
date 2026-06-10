/**
 * 沉淀筛选：整表确认进入下一子步后，右侧引导语（固定模拟流式 / LLM 真流式）。
 */

import { apiClient } from '@/lib/api/client';
import { authApi } from '@/lib/api/auth';
import { useAuthStore } from '@/stores/authStore';

export async function simulateFixedRuminationOpening(
  fullText: string,
  signal: AbortSignal,
  onContent: (accumulated: string) => void,
  /** 首字前等待毫秒，让"思考中"气泡先展示 */
  initialDelayMs = 600,
): Promise<void> {
  if (signal.aborted) return;
  await new Promise((r) => window.setTimeout(r, initialDelayMs));
  const step = 2;
  const delayMs = 22;
  let acc = '';
  for (let i = 0; i < fullText.length; i += step) {
    if (signal.aborted) return;
    acc += fullText.slice(i, i + step);
    onContent(acc);
    await new Promise((r) => window.setTimeout(r, delayMs));
  }
}

export type RuminationOpeningStreamHandlers = {
  onChunk: (delta: string) => void;
  onThinkStart?: () => void;
  onThinkChunk?: (chunk: string) => void;
  onThinkEnd?: () => void;
  onDone: (fullResponse: string) => void;
  onError: (message: string) => void;
};

/**
 * 与 /message/stream 相同 data: JSON 行协议（chunk / think_* / done / error）。
 */
export async function streamRuminationStepOpening(
  activationCode: string,
  filterStep: number,
  threadId: string,
  signal: AbortSignal,
  handlers: RuminationOpeningStreamHandlers,
  streamAuthExpiredMessage: string
): Promise<void> {
  const apiBase = (process.env.NEXT_PUBLIC_API_URL || '').trim();
  const streamUrl = `${apiBase ? apiBase.replace(/\/+$/, '') : ''}/api/v1/simple-chat/rumination-step-opening-stream`;

  const doFetch = async (accessToken: string | null) =>
    fetch(streamUrl, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...(accessToken ? { Authorization: `Bearer ${accessToken}` } : {}),
      },
      body: JSON.stringify({
        activation_code: activationCode,
        filter_step: filterStep,
        thread_id: threadId || '',
      }),
      signal,
    });

  let token = typeof window !== 'undefined' ? localStorage.getItem('token') : null;
  let res = await doFetch(token);
  if (res.status === 401) {
    try {
      const refreshed = await authApi.refresh();
      const nextToken = refreshed?.data?.token || null;
      if (nextToken) {
        apiClient.setToken(nextToken);
        useAuthStore.getState().setTokens(nextToken);
        token = nextToken;
        res = await doFetch(nextToken);
      }
    } catch {
      /* handled below */
    }
  }

  if (!res.ok) {
    if (res.status === 401) {
      handlers.onError(streamAuthExpiredMessage);
      return;
    }
    let detail = '';
    try {
      const errPayload = await res.json();
      detail = errPayload?.detail || errPayload?.message || '';
    } catch {
      /* ignore */
    }
    handlers.onError(detail || `请求失败（${res.status}）`);
    return;
  }

  if (!res.body) {
    handlers.onError('流式接口返回为空');
    return;
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  let fullReply = '';

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split('\n');
    buffer = lines.pop() || '';
    for (const line of lines) {
      if (!line.startsWith('data: ')) continue;
      try {
        const payload = JSON.parse(line.slice(6)) as Record<string, unknown>;
        if (payload.error) {
          handlers.onError(String(payload.error));
          await reader.cancel();
          return;
        }
        if (payload.think_start) handlers.onThinkStart?.();
        if (payload.think_chunk && typeof payload.think_chunk === 'string') {
          const tc = payload.think_chunk;
          if (tc) handlers.onThinkChunk?.(tc);
        }
        if (payload.think_end != null) handlers.onThinkEnd?.();
        if (payload.chunk && typeof payload.chunk === 'string') {
          const ch = payload.chunk;
          fullReply += ch;
          handlers.onChunk(ch);
        }
        if (payload.done && payload.response != null) {
          fullReply = String(payload.response);
          handlers.onDone(fullReply);
          return;
        }
      } catch {
        /* ignore malformed line */
      }
    }
  }
  handlers.onDone(fullReply);
}
