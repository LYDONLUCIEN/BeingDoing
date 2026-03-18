'use client';

import { useEffect, useState } from 'react';

interface BasicSettings {
  APP_ENV?: string;
  ARCHITECTURE_MODE?: string;
  LLM_PROVIDER?: string;
  LLM_MODEL?: string;
}

export default function AdminSystemPage() {
  const [settings] = useState<BasicSettings | null>(null);

  useEffect(() => {
    // 预留：后续可在这里调用一个只读的 /api/v1/admin/system-settings 接口
  }, []);

  return (
    <div className="max-w-5xl mx-auto space-y-6">
      <header>
        <h1 className="text-xl font-semibold mb-2" style={{ color: 'var(--bd-fg)' }}>
          系统设置（只读）
        </h1>
        <p className="text-sm" style={{ color: 'var(--bd-fg-muted)' }}>
          展示当前后端运行环境的只读信息（环境类型 / 架构模式 / 模型配置），避免在 Admin 控制台直接进行高风险写操作。
        </p>
      </header>

      <section className="rounded-2xl bg-bd-card border border-bd-border px-6 py-5 shadow-sm space-y-3">
        <p className="text-xs text-bd-subtle">
          占位说明：后续可通过一个只读接口返回 <code className="px-1 py-0.5 rounded bg-bd-overlay-md">APP_ENV</code>、
          <code className="px-1 py-0.5 rounded bg-bd-overlay-md">ARCHITECTURE_MODE</code>、
          <code className="px-1 py-0.5 rounded bg-bd-overlay-md">LLM_PROVIDER</code> 等信息，在此处展示。
        </p>

        {!settings && (
          <p className="text-xs text-bd-subtle">
            当前暂未从后端加载系统配置，这是一个 UI 占位骨架，后续可以在这里挂接真实的数据接口。
          </p>
        )}
      </section>
    </div>
  );
}

