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
  resetAdminChatAppearance,
  type ChatAppearanceConfig,
} from '@/lib/api/chatAppearance';

function Option({
  pressed,
  onClick,
  swatch,
  children,
}: {
  pressed: boolean;
  onClick: () => void;
  /** ol-swatch-* 色块类名（openlife-chat-appearance.css）；不传则纯文字按钮 */
  swatch?: string;
  children: ReactNode;
}) {
  return (
    <button type="button" className="ol-chat-appearance-option" aria-pressed={pressed} onClick={onClick}>
      {swatch && <i className={`ol-swatch ${swatch}`} aria-hidden />}
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

  const handleReset = async () => {
    setMessage(null);
    setError(null);
    try {
      // 一键恢复默认：后端写入出厂默认（DEFAULT_CHAT_APPEARANCE）并生效，
      // 返回值直接应用进 store（用户下次进入对话/沉淀页即同步）
      const defaults = await resetAdminChatAppearance();
      useChatAppearanceStore.getState().applyGlobalConfig(defaults as Record<string, unknown>);
      setMessage('已恢复默认并保存生效（用户下次进入对话/沉淀页即同步）');
    } catch (e: any) {
      setError(e?.response?.data?.detail || e?.message || '恢复默认失败');
    }
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
            <RotateCcw size={14} strokeWidth={2.2} /> 恢复默认
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
          <Row label="背景样式">
            <Option pressed={s.background === 'white'} onClick={() => s.setBackground('white')} swatch="ol-swatch-bg-white">
              纯白
            </Option>
            <Option pressed={s.background === 'tint'} onClick={() => s.setBackground('tint')} swatch="ol-swatch-bg-tint">
              主题浅色
            </Option>
            <Option pressed={s.background === 'flow'} onClick={() => s.setBackground('flow')} swatch="ol-swatch-bg-flow">
              流动晕染
            </Option>
            <Option
              pressed={s.background === 'illustration'}
              onClick={() => s.setBackground('illustration')}
              swatch="ol-swatch-bg-illustration"
            >
              插画点缀
            </Option>
          </Row>
          <Row label="贴图位置">
            <Option pressed={s.placement === 'both'} onClick={() => s.setPlacement('both')}>
              侧栏＋边缘
            </Option>
            <Option pressed={s.placement === 'sidebar'} onClick={() => s.setPlacement('sidebar')}>
              仅侧栏
            </Option>
            <Option pressed={s.placement === 'edge'} onClick={() => s.setPlacement('edge')}>
              仅边缘
            </Option>
            <Option pressed={s.placement === 'off'} onClick={() => s.setPlacement('off')}>
              隐藏
            </Option>
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
          <Row label="AI 回复气泡">
            <Option pressed={s.aiBubble === 'ink'} onClick={() => s.setAiBubble('ink')} swatch="ol-swatch-ink">
              深墨
            </Option>
            <Option pressed={s.aiBubble === 'soft'} onClick={() => s.setAiBubble('soft')} swatch="ol-swatch-soft">
              浅主题
            </Option>
            <Option pressed={s.aiBubble === 'theme'} onClick={() => s.setAiBubble('theme')} swatch="ol-swatch-theme">
              主题实色
            </Option>
            <Option pressed={s.aiBubble === 'white'} onClick={() => s.setAiBubble('white')} swatch="ol-swatch-white">
              纸白
            </Option>
          </Row>
          <Row label="我的消息气泡">
            <Option pressed={s.userBubble === 'soft'} onClick={() => s.setUserBubble('soft')} swatch="ol-swatch-soft">
              浅主题
            </Option>
            <Option pressed={s.userBubble === 'theme'} onClick={() => s.setUserBubble('theme')} swatch="ol-swatch-theme">
              主题实色
            </Option>
            <Option pressed={s.userBubble === 'ink'} onClick={() => s.setUserBubble('ink')} swatch="ol-swatch-ink">
              深墨
            </Option>
            <Option pressed={s.userBubble === 'white'} onClick={() => s.setUserBubble('white')} swatch="ol-swatch-white">
              纸白
            </Option>
          </Row>
          <Row label="发送与主要按钮">
            <Option pressed={s.actionStyle === 'ink'} onClick={() => s.setActionStyle('ink')} swatch="ol-swatch-ink">
              深墨
            </Option>
            <Option
              pressed={s.actionStyle === 'theme'}
              onClick={() => s.setActionStyle('theme')}
              swatch="ol-swatch-theme"
            >
              主题实色
            </Option>
          </Row>
        </Section>

        <Section title="沉淀工作台">
          <Row label="页面布局">
            <Option
              pressed={s.ruminationLayout === 'guided'}
              onClick={() => s.setRuminationLayout('guided')}
            >
              组合解锁
            </Option>
            <Option
              pressed={s.ruminationLayout === 'classic'}
              onClick={() => s.setRuminationLayout('classic')}
            >
              对话分栏
            </Option>
            <Option
              pressed={s.ruminationLayout === 'studio'}
              onClick={() => s.setRuminationLayout('studio')}
            >
              横向工作台
            </Option>
          </Row>
          <Row label="界面层级">
            <Option pressed={s.ruminationSkin === 'mist'} onClick={() => s.setRuminationSkin('mist')}>
              柔雾玻璃
            </Option>
            <Option pressed={s.ruminationSkin === 'folio'} onClick={() => s.setRuminationSkin('folio')}>
              静谧双页
            </Option>
            <Option
              pressed={s.ruminationSkin === 'modules'}
              onClick={() => s.setRuminationSkin('modules')}
            >
              模块编辑
            </Option>
            <Option
              pressed={s.ruminationSkin === 'editorial'}
              onClick={() => s.setRuminationSkin('editorial')}
            >
              编辑长卷
            </Option>
          </Row>
          <Row label="氛围方案">
            <Option
              pressed={s.palette === 'lavender'}
              onClick={() => s.setPalette('lavender')}
              swatch="ol-swatch-palette-lavender"
            >
              四色交融
            </Option>
            <Option
              pressed={s.palette === 'sage'}
              onClick={() => s.setPalette('sage')}
              swatch="ol-swatch-palette-sage"
            >
              蓝绿呼吸
            </Option>
            <Option
              pressed={s.palette === 'slate'}
              onClick={() => s.setPalette('slate')}
              swatch="ol-swatch-palette-slate"
            >
              暖色微光
            </Option>
          </Row>
          <Row label="选择矩阵样式">
            <Option
              pressed={s.matrixStyle === 'soft'}
              onClick={() => s.setMatrixStyle('soft')}
              swatch="ol-swatch-matrix-soft"
            >
              柔和填充
            </Option>
            <Option
              pressed={s.matrixStyle === 'outline'}
              onClick={() => s.setMatrixStyle('outline')}
              swatch="ol-swatch-matrix-outline"
            >
              空心描边
            </Option>
            <Option
              pressed={s.matrixStyle === 'solid'}
              onClick={() => s.setMatrixStyle('solid')}
              swatch="ol-swatch-matrix-solid"
            >
              实心高亮
            </Option>
          </Row>
          <Row label="选择矩阵配色">
            <Option
              pressed={s.matrixPalette === 'duo'}
              onClick={() => s.setMatrixPalette('duo')}
              swatch="ol-swatch-matrix-duo"
            >
              珊瑚 × 雾蓝
            </Option>
            <Option
              pressed={s.matrixPalette === 'violet'}
              onClick={() => s.setMatrixPalette('violet')}
              swatch="ol-swatch-matrix-violet"
            >
              统一紫
            </Option>
            <Option
              pressed={s.matrixPalette === 'multi'}
              onClick={() => s.setMatrixPalette('multi')}
              swatch="ol-swatch-matrix-multi"
            >
              多色区分
            </Option>
          </Row>
        </Section>

        <Section title="结论卡">
          <Row label="结论卡配色">
            <Option
              pressed={s.conclusionTone === 'theme-mist'}
              onClick={() => s.setConclusionTone('theme-mist')}
              swatch="ol-swatch-tone-mist"
            >
              主题中调
            </Option>
            <Option
              pressed={s.conclusionTone === 'theme-paper'}
              onClick={() => s.setConclusionTone('theme-paper')}
              swatch="ol-swatch-tone-paper"
            >
              主题纸感
            </Option>
            <Option
              pressed={s.conclusionTone === 'theme-gradient'}
              onClick={() => s.setConclusionTone('theme-gradient')}
              swatch="ol-swatch-tone-gradient"
            >
              主题渐层
            </Option>
            <Option
              pressed={s.conclusionTone === 'theme-outline'}
              onClick={() => s.setConclusionTone('theme-outline')}
              swatch="ol-swatch-tone-outline"
            >
              主题描边
            </Option>
            <Option
              pressed={s.conclusionTone === 'theme-solid'}
              onClick={() => s.setConclusionTone('theme-solid')}
              swatch="ol-swatch-tone-solid"
            >
              主题实色
            </Option>
          </Row>
          <Row label="结论标签样式">
            <Option pressed={s.conclusionTags === 'soft'} onClick={() => s.setConclusionTags('soft')}>
              柔和胶囊
            </Option>
            <Option pressed={s.conclusionTags === 'outline'} onClick={() => s.setConclusionTags('outline')}>
              清晰描边
            </Option>
            <Option
              pressed={s.conclusionTags === 'editorial'}
              onClick={() => s.setConclusionTags('editorial')}
            >
              报告短线
            </Option>
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
