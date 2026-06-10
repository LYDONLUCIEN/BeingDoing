'use client';

import { useCallback, useEffect, useState } from 'react';
import {
  fetchAdminSavepoints,
  loadAdminSavepoint,
  type AdminSavepointItem,
} from '@/lib/api/admin';

export function buildExploreChatUrl(phase: string, activationCode: string, threadId: string): string {
  return (
    `/explore/chat/${encodeURIComponent(phase)}` +
    `?code=${encodeURIComponent(activationCode)}` +
    `&thread_id=${encodeURIComponent(threadId)}`
  );
}

/** 与 sandboxes 页一致的 Load → 跳转 explore chat 流程。 */
export async function loadSavepointAndNavigate(sp: AdminSavepointItem): Promise<{
  phase: string;
  thread_id: string;
  activation_code: string;
}> {
  const ret = await loadAdminSavepoint({
    activation_code: sp.source_activation_code,
    savepoint_id: sp.savepoint_id,
  });
  window.location.href = buildExploreChatUrl(ret.phase, ret.activation_code, ret.thread_id);
  return ret;
}

export function useAdminSavepoints(autoLoad = true) {
  const [savepoints, setSavepoints] = useState<AdminSavepointItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const reload = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetchAdminSavepoints();
      setSavepoints(res.items ?? []);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : '加载 Savepoint 失败');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (autoLoad) void reload();
  }, [autoLoad, reload]);

  const loadSavepoint = useCallback(async (sp: AdminSavepointItem) => {
    return loadSavepointAndNavigate(sp);
  }, []);

  return { savepoints, loading, error, reload, loadSavepoint };
}
