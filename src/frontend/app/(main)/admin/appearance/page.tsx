'use client';

/**
 * Admin · Chat 外观全局默认配置（2026-09-23 拍板：配置入口从 chat 页齿轮弹层迁入 admin，
 * 全局生效、所有用户可见同一套默认，用户侧无修改入口）。
 *
 * 数据流：后端 data/admin_runtime_config.json 的 chat_appearance 键
 * （GET/PUT /api/v1/admin/chat-appearance）；保存后所有用户进入 chat/沉淀页时经
 * useChatAppearanceAttrs 的全局同步覆盖本地 localStorage。
 * 复用 .ol-chat-appearance-* 样式（openlife-chat-appearance.css）与 RECOMMENDED 默认值。
 */

import { useEffect, useState, type ReactNode } from 'react';
import { Palette, RotateCcw, Save } from 'lucide-react';
import { useChatAppearanceStore } from '@/stores/chatAppearanceStore';
import {
  fetchAdminChatAppearance,
  putAdminChatAppearance,
  type ChatAppearanceConfig,
} from '@/lib/api/chatAppearance';

function Option({
  pressed,
  onClick,
  children,
}: {
  pressed: boolean;
  onClick: () => void;
  children: ReactNode;
}) {
  return (
    <button type="button" className="ol-chat-appearance-option" aria-pressed={pressed} onClick={onClick}>
      {children}
    </button>
  );
}

function Row({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="ol-chat-appearance-row">
      <span className="ol-chat-appearance-label">{label}</span>
      <div className="ol-chat-appearance-options">{children}</div>
    </div>
  );
}

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="ol-chat-appearance-section">
      <h3 className="ol-chat-appearance-section-title">{title}</h3>
      {children}
    </section>
  );
}

export default function AdminAppearancePage() {
  const s = useChatAppearanceStore();
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchAdminChatAppearance()
      .then((cfg) => {
        useChatAppearanceStore.getState().applyGlobalConfig(cfg as Record<string, unknown>);
      })
      .catch((e: any) => setError(e?.message || '加载全局外观配置失败'));
  }, []);

  const currentConfig: ChatAppearanceConfig = {
    density: s.density,
    newChatStyle: s.newChatStyle,
    background: s.background,
    placement: s.placement,
    strength: s.strength,
    motionPaused: s.motionPaused,
    aiBubble: s.aiBubble,
    userBubble: s.userBubble,
    actionStyle: s.actionStyle,
    ruminationLayout: s.ruminationLayout,
    ruminationSkin: s.ruminationSkin,
    palette: s.palette,
    matrixStyle: s.matrixStyle,
    matrixPalette: s.matrixPalette,
    conclusionTone: s.conclusionTone,
    conclusionTags: s.conclusionTags,
  };

  const handleSave = async () => {
    setSaving(true);
    setMessage(null);
    setError(null);
    try {
      await putAdminChatAppearance(currentConfig);
      setMessage('已保存，全局生效（用户下次进入对话/沉淀页即同步）');
    } catch (e: any) {
      setError(e?.response?.data?.detail || e?.message || '保存失败');
    } finally {
      setSaving(false);
    }
  };

  const handleReset = () => {
    s.resetToRecommended();
    setMessage('已恢复为推荐组合（尚未保存，确认后点「保存全局配置」）');
  };

  return (
    <div className="space-y-6">
      <header className="flex items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          <span className="grid h-10 w-10 place-items-center rounded-xl bg-[#f1edfb] text-[#6f52c7]">
            <Palette size={20} strokeWidth={2} />
          </span>
          <div>
            <h1 className="text-xl font-semibold text-bd-fg">Chat 外观全局配置</h1>
            <p className="mt-0.5 text-sm text-neutral-500">
              对所有用户的对话 / 沉淀页生效；用户侧已无修改入口（2026-09-23 拍板）
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={handleReset}
            className="inline-flex items-center gap-1.5 rounded-full border border-[rgba(109,121,176,0.2)] bg-white px-4 py-2 text-sm font-semibold text-[#465366] transition-colors hover:bg-[#f6f8fb]"
          >
            <RotateCcw size={14} strokeWidth={2.2} /> 恢复推荐
          </button>
          <button
            type="button"
            onClick={handleSave}
            disabled={saving}
            className="bd-btn-black inline-flex items-center gap-1.5 rounded-full px-4 py-2 text-sm font-semibold text-white disabled:opacity-50"
          >
            <Save size={14} strokeWidth={2.2} /> {saving ? '保存中…' : '保存全局配置'}
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
        <Section title="聊天背景">
          <Row label="背景模式">
            {(['white', 'tint', 'flow', 'illustration'] as const).map((v) => (
              <Option key={v} pressed={s.background === v} onClick={() => s.setBackground(v)}>
                {v}
              </Option>
            ))}
          </Row>
          <Row label="贴图位置">
            {(['both', 'sidebar', 'edge', 'off'] as const).map((v) => (
              <Option key={v} pressed={s.placement === v} onClick={() => s.setPlacement(v)}>
                {v}
              </Option>
            ))}
          </Row>
          <Row label={`晕染浓度（${s.strength}）`}>
            <span className="ol-chat-appearance-range">
              <input
                type="range"
                min={0}
                max={50}
                value={s.strength}
                onChange={(e) => s.setStrength(Number(e.target.value))}
                aria-label="晕染浓度"
              />
            </span>
          </Row>
          <Row label="背景动效">
            <Option pressed={!s.motionPaused} onClick={() => s.setMotionPaused(false)}>
              流动
            </Option>
            <Option pressed={s.motionPaused} onClick={() => s.setMotionPaused(true)}>
              暂停
            </Option>
          </Row>
        </Section>

        <Section title="气泡与按钮">
          <Row label="AI 气泡">
            {(['ink', 'soft', 'theme', 'white'] as const).map((v) => (
              <Option key={v} pressed={s.aiBubble === v} onClick={() => s.setAiBubble(v)}>
                {v}
              </Option>
            ))}
          </Row>
          <Row label="用户气泡">
            {(['paper', 'soft', 'theme', 'white'] as const).map((v) => (
              <Option
                key={v}
                pressed={(v === 'paper' ? 'white' : v) === s.userBubble}
                onClick={() => s.setUserBubble(v === 'paper' ? 'white' : v)}
              >
                {v}
              </Option>
            ))}
          </Row>
          <Row label="主动作按钮">
            <Option pressed={s.actionStyle === 'ink'} onClick={() => s.setActionStyle('ink')}>
              深墨
            </Option>
            <Option pressed={s.actionStyle === 'theme'} onClick={() => s.setActionStyle('theme')}>
              主题色
            </Option>
          </Row>
        </Section>

        <Section title="沉淀工作台">
          <Row label="布局">
            {(['guided', 'classic', 'studio'] as const).map((v) => (
              <Option key={v} pressed={s.ruminationLayout === v} onClick={() => s.setRuminationLayout(v)}>
                {v}
              </Option>
            ))}
          </Row>
          <Row label="层级皮肤">
            {(['mist', 'folio', 'modules', 'editorial'] as const).map((v) => (
              <Option key={v} pressed={s.ruminationSkin === v} onClick={() => s.setRuminationSkin(v)}>
                {v}
              </Option>
            ))}
          </Row>
          <Row label="配色">
            {(['lavender', 'sage', 'slate'] as const).map((v) => (
              <Option key={v} pressed={s.palette === v} onClick={() => s.setPalette(v)}>
                {v}
              </Option>
            ))}
          </Row>
          <Row label="选择矩阵样式">
            {(['soft', 'outline', 'solid'] as const).map((v) => (
              <Option key={v} pressed={s.matrixStyle === v} onClick={() => s.setMatrixStyle(v)}>
                {v}
              </Option>
            ))}
          </Row>
          <Row label="选择矩阵配色">
            {(['duo', 'violet', 'multi'] as const).map((v) => (
              <Option key={v} pressed={s.matrixPalette === v} onClick={() => s.setMatrixPalette(v)}>
                {v}
              </Option>
            ))}
          </Row>
        </Section>

        <Section title="结论卡">
          <Row label="质感">
            {(['theme-mist', 'theme-paper', 'theme-gradient', 'theme-outline', 'theme-solid'] as const).map(
              (v) => (
                <Option key={v} pressed={s.conclusionTone === v} onClick={() => s.setConclusionTone(v)}>
                  {v.replace('theme-', '')}
                </Option>
              )
            )}
          </Row>
          <Row label="标签样式">
            {(['soft', 'outline', 'editorial'] as const).map((v) => (
              <Option key={v} pressed={s.conclusionTags === v} onClick={() => s.setConclusionTags(v)}>
                {v}
              </Option>
            ))}
          </Row>
        </Section>

        <Section title="对话排版">
          <Row label="气泡间距">
            <Option pressed={s.density === 'roomy'} onClick={() => s.setDensity('roomy')}>
              宽松
            </Option>
            <Option pressed={s.density === 'compact'} onClick={() => s.setDensity('compact')}>
              紧凑
            </Option>
          </Row>
          <Row label="新建对话按钮">
            <Option pressed={s.newChatStyle === 'solid'} onClick={() => s.setNewChatStyle('solid')}>
              深墨实心
            </Option>
            <Option pressed={s.newChatStyle === 'dashed'} onClick={() => s.setNewChatStyle('dashed')}>
              虚线浅底
            </Option>
          </Row>
        </Section>
      </div>
    </div>
  );
}
