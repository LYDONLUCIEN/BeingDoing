'use client';

/**
 * Admin · AI 模型分流配置（2026-09-23 拍板：chat/rumination/report 三场景
 * 各自选择 flash|pro 档位与 thinking 开关，全局生效，与 Chat 外观配置同构）。
 *
 * 数据流：后端 data/admin_runtime_config.json 的 llm_scene_config 键
 * （GET/PUT/POST /api/v1/admin/llm-scene[.../reset]）；factory._scene_model 与
 * openai_provider 的 thinking 分支实时读取，保存即生效。
 * 档位固定映射：flash→deepseek-v4-flash，pro→deepseek-v4-pro（不受 .env 覆盖影响）。
 */

import { useEffect, useState } from 'react';
import { Cpu, RotateCcw, Save } from 'lucide-react';
import {
  fetchAdminLlmScene,
  putAdminLlmScene,
  resetAdminLlmScene,
  TIER_MODEL_NAMES,
  type LlmScene,
  type LlmSceneConfig,
  type LlmTier,
} from '@/lib/api/llmScene';

const SCENE_META: { key: LlmScene; title: string; desc: string }[] = [
  { key: 'chat', title: '前四轮对话', desc: '价值观 / 热情 / 天赋 / 目的四阶段的对话与结论卡' },
  { key: 'rumination', title: '沉淀对话', desc: '沉淀工作台的对话、平衡点判定与收尾语' },
  { key: 'report', title: '报告生成', desc: 'PDF 报告的 Markdown 生成与润色压缩' },
];

const TIERS: { value: LlmTier; label: string; hint: string }[] = [
  { value: 'flash', label: 'flash', hint: '快 · 省' },
  { value: 'pro', label: 'pro', hint: '强 · 慢' },
];

function Option({
  pressed,
  onClick,
  children,
}: {
  pressed: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button type="button" className="ol-chat-appearance-option" aria-pressed={pressed} onClick={onClick}>
      {children}
    </button>
  );
}

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="ol-chat-appearance-row">
      <span className="ol-chat-appearance-label">{label}</span>
      <div className="ol-chat-appearance-options">{children}</div>
    </div>
  );
}

export default function AdminLlmScenePage() {
  const [config, setConfig] = useState<LlmSceneConfig | null>(null);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchAdminLlmScene()
      .then(setConfig)
      .catch((e: any) => setError(e?.message || '加载场景配置失败'));
  }, []);

  const updateScene = (scene: LlmScene, patch: Partial<LlmSceneConfig[LlmScene]>) => {
    setConfig((prev) => (prev ? { ...prev, [scene]: { ...prev[scene], ...patch } } : prev));
  };

  const handleSave = async () => {
    if (!config) return;
    setSaving(true);
    setMessage(null);
    setError(null);
    try {
      const saved = await putAdminLlmScene(config);
      setConfig(saved);
      setMessage('已保存并全局生效（下一次对话 / 报告生成即按新配置分流）');
    } catch (e: any) {
      setError(e?.response?.data?.detail || e?.message || '保存失败');
    } finally {
      setSaving(false);
    }
  };

  const handleReset = async () => {
    setError(null);
    try {
      const defaults = await resetAdminLlmScene();
      setConfig(defaults);
      setMessage('已恢复默认并保存生效（前四轮 flash、沉淀 / 报告 pro，thinking 全开）');
    } catch (e: any) {
      setError(e?.response?.data?.detail || e?.message || '恢复默认失败');
    }
  };

  return (
    <div className="space-y-6">
      <header className="flex items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          <span className="grid h-10 w-10 place-items-center rounded-xl bg-[#f1edfb] text-[#6f52c7]">
            <Cpu size={20} strokeWidth={2} />
          </span>
          <div>
            <h1 className="text-xl font-semibold text-bd-fg">AI 模型分流配置</h1>
            <p className="mt-0.5 text-sm text-neutral-500">
              前四轮对话 / 沉淀对话 / 报告生成各自选择模型档位与思维链开关，保存即全局生效
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={handleReset}
            className="inline-flex items-center gap-1.5 rounded-full border border-[rgba(109,121,176,0.2)] bg-white px-4 py-2 text-sm font-semibold text-[#465366] transition-colors hover:bg-[#f6f8fb]"
          >
            <RotateCcw size={14} strokeWidth={2.2} /> 恢复默认
          </button>
          <button
            type="button"
            onClick={handleSave}
            disabled={saving || !config}
            className="bd-btn-black inline-flex items-center gap-1.5 rounded-full px-4 py-2 text-sm font-semibold text-white disabled:opacity-50"
          >
            <Save size={14} strokeWidth={2.2} /> {saving ? '保存中…' : '保存配置'}
          </button>
        </div>
      </header>

      {message && (
        <p className="rounded-xl bg-[#e8faf3] px-4 py-2.5 text-sm font-medium text-[#02a475]" role="status">
          {message}
        </p>
      )}
      {error && (
        <p className="rounded-xl bg-red-50 px-4 py-2.5 text-sm font-medium text-red-600" role="alert">
          {error}
        </p>
      )}

      <div className="ol-chat-appearance-panel static !max-h-none !w-full !shadow-none" style={{ position: 'static' }}>
        {SCENE_META.map(({ key, title, desc }) => {
          const item = config?.[key];
          return (
            <section key={key} className="ol-chat-appearance-section">
              <h3 className="ol-chat-appearance-section-title">
                {title}
                <span className="ml-2 text-xs font-normal text-neutral-400">{desc}</span>
              </h3>
              <Row label="模型档位">
                {TIERS.map((t) => (
                  <Option
                    key={t.value}
                    pressed={item?.tier === t.value}
                    onClick={() => updateScene(key, { tier: t.value })}
                  >
                    {t.label} · {t.hint}
                  </Option>
                ))}
                {item && (
                  <span className="ml-1 self-center text-xs text-neutral-400">
                    当前模型：{TIER_MODEL_NAMES[item.tier]}
                  </span>
                )}
              </Row>
              <Row label="思维链（thinking）">
                <Option pressed={item?.thinking === true} onClick={() => updateScene(key, { thinking: true })}>
                  开
                </Option>
                <Option pressed={item?.thinking === false} onClick={() => updateScene(key, { thinking: false })}>
                  关
                </Option>
                <span className="ml-1 self-center text-xs text-neutral-400">
                  开：模型先思考再回答（对话页展示思考过程）；关：更快、消耗更少
                </span>
              </Row>
            </section>
          );
        })}
        <p className="px-1 text-xs leading-relaxed text-neutral-400">
          说明：三场景保存后立即生效；其他内部调用（如团队分析）仍按 .env 兜底配置。
          档位与模型名固定映射（flash→deepseek-v4-flash，pro→deepseek-v4-pro）。
        </p>
      </div>
    </div>
  );
}
