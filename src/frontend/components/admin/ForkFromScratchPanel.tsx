'use client';

import { useState } from 'react';
import { bindPromptLabProfile, forkAdminSandbox } from '@/lib/api/admin';

interface ForkFromScratchPanelProps {
  profileId?: string;
  onNotice?: (msg: string) => void;
  onError?: (msg: string) => void;
}

export function ForkFromScratchPanel({ profileId = '', onNotice, onError }: ForkFromScratchPanelProps) {
  const [sourceCode, setSourceCode] = useState('');
  const [working, setWorking] = useState(false);

  const handleFork = async () => {
    const c = sourceCode.trim().toUpperCase();
    if (!c) return;
    setWorking(true);
    try {
      const data = await forkAdminSandbox(c);
      const sandboxCode = data.sandbox_activation_code;
      if (profileId) {
        await bindPromptLabProfile({
          activation_code: sandboxCode,
          profile_id: profileId,
        });
      }
      onNotice?.(
        profileId
          ? `已 Fork 沙箱 ${sandboxCode} 并绑定当前 Profile，即将进入探索…`
          : `已 Fork 沙箱 ${sandboxCode}，即将进入探索…`,
      );
      window.location.href = `/explore/activate?code=${encodeURIComponent(sandboxCode)}`;
    } catch (e: unknown) {
      onError?.(e instanceof Error ? e.message : 'Fork 失败');
    } finally {
      setWorking(false);
    }
  };

  return (
    <section className="rounded-2xl bg-bd-card border border-bd-border p-5 space-y-3">
      <div>
        <h3 className="text-sm font-medium text-bd-fg">Fork 从头试跑</h3>
        <p className="text-xs text-bd-subtle mt-1">
          从正式激活码复制数据到 SBX 沙箱；若已选 Profile 将自动绑定到新沙箱激活码。
        </p>
      </div>
      <div className="flex flex-wrap gap-2 items-end">
        <div className="flex-1 min-w-[200px]">
          <label className="block text-xs text-bd-muted mb-1">源激活码（正式用户）</label>
          <input
            value={sourceCode}
            onChange={(e) => setSourceCode(e.target.value)}
            placeholder="例如 ABCD123456"
            disabled={working}
            className="w-full rounded-lg border border-bd-border bg-bd-overlay px-3 py-2 text-sm font-mono"
          />
        </div>
        <button
          type="button"
          disabled={working || !sourceCode.trim()}
          onClick={() => void handleFork()}
          className="px-3 py-2 rounded-lg border border-violet-300 dark:border-violet-700 text-violet-700 dark:text-violet-300 text-xs hover:bg-violet-500/10 disabled:opacity-50"
        >
          {working ? '处理中…' : 'Fork 从头试跑'}
        </button>
      </div>
    </section>
  );
}
