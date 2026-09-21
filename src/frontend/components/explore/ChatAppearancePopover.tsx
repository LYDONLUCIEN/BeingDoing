'use client';

import { useEffect, useRef, useState, type ReactNode } from 'react';
import { Settings2 } from 'lucide-react';
import { useChatAppearanceStore } from '@/stores/chatAppearanceStore';

/**
 * Chat 外观设置弹层（复刻 HTML #appearance-popover 全维度）：
 * 齿轮按钮 → 下弹浮层，分组覆盖 聊天背景 / 气泡与按钮 / 沉淀 / 结论卡 / 对话排版，
 * 选择持久化到 localStorage（openlife-chat-appearance，v1），
 * 经 useChatAppearanceAttrs 输出为根节点 data-* 属性，CSS 即时生效。
 */

function SwatchOption({
  pressed,
  onClick,
  swatch,
  children,
}: {
  pressed: boolean;
  onClick: () => void;
  /** ol-swatch-* 色块类名；不传则纯文字按钮 */
  swatch?: string;
  children: ReactNode;
}) {
  return (
    <button
      type="button"
      className="ol-chat-appearance-option"
      aria-pressed={pressed}
      onClick={onClick}
    >
      {swatch && <i className={`ol-swatch ${swatch}`} aria-hidden />}
      {children}
    </button>
  );
}

/** 分段小按钮组（贴图位置 / 动效 / 排版等非色块选项） */
function SegOption({
  pressed,
  onClick,
  children,
}: {
  pressed: boolean;
  onClick: () => void;
  children: ReactNode;
}) {
  return (
    <button
      type="button"
      className="ol-chat-appearance-option"
      aria-pressed={pressed}
      onClick={onClick}
    >
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

export default function ChatAppearancePopover({
  hideSidebarOptions = false,
}: {
  /** rumination 等无会话侧栏页面：隐藏「对话排版」组（气泡间距 / 新建对话按钮） */
  hideSidebarOptions?: boolean;
}) {
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);
  const s = useChatAppearanceStore();

  // 点击外部 / Esc 关闭
  useEffect(() => {
    if (!open) return;
    const onPointerDown = (e: PointerEvent) => {
      if (rootRef.current && !rootRef.current.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setOpen(false);
    };
    document.addEventListener('pointerdown', onPointerDown);
    window.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('pointerdown', onPointerDown);
      window.removeEventListener('keydown', onKey);
    };
  }, [open]);

  return (
    <div className="ol-chat-appearance" ref={rootRef}>
      <button
        type="button"
        className="ol-chat-appearance-toggle"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        aria-label="页面设置"
        title="页面设置"
      >
        <Settings2 size={16} strokeWidth={2} aria-hidden />
      </button>

      {open && (
        <div className="ol-chat-appearance-panel" role="dialog" aria-label="页面设置">
          <p className="ol-chat-appearance-title">页面设置</p>
          <p className="ol-chat-appearance-subtitle">选项保存在此浏览器，即时生效</p>

          {/* ── 聊天背景 ── */}
          <section className="ol-chat-appearance-section">
            <p className="ol-chat-appearance-section-title">聊天背景</p>
            <Row label="背景样式">
              <SwatchOption pressed={s.background === 'white'} onClick={() => s.setBackground('white')} swatch="ol-swatch-bg-white">
                纯白
              </SwatchOption>
              <SwatchOption pressed={s.background === 'tint'} onClick={() => s.setBackground('tint')} swatch="ol-swatch-bg-tint">
                主题浅色
              </SwatchOption>
              <SwatchOption pressed={s.background === 'flow'} onClick={() => s.setBackground('flow')} swatch="ol-swatch-bg-flow">
                流动晕染
              </SwatchOption>
              <SwatchOption pressed={s.background === 'illustration'} onClick={() => s.setBackground('illustration')} swatch="ol-swatch-bg-illustration">
                插画点缀
              </SwatchOption>
            </Row>
            <Row label="贴图位置">
              <SegOption pressed={s.placement === 'both'} onClick={() => s.setPlacement('both')}>侧栏＋边缘</SegOption>
              <SegOption pressed={s.placement === 'sidebar'} onClick={() => s.setPlacement('sidebar')}>仅侧栏</SegOption>
              <SegOption pressed={s.placement === 'edge'} onClick={() => s.setPlacement('edge')}>仅边缘</SegOption>
              <SegOption pressed={s.placement === 'off'} onClick={() => s.setPlacement('off')}>隐藏</SegOption>
            </Row>
            <div className="ol-chat-appearance-row">
              <span className="ol-chat-appearance-label">晕染浓度</span>
              <div className="ol-chat-appearance-range">
                <input
                  type="range"
                  min={0}
                  max={50}
                  step={1}
                  value={s.strength}
                  onChange={(e) => s.setStrength(Number(e.target.value))}
                  aria-label="背景晕染浓度"
                />
                <span className="ol-chat-appearance-range-value">{s.strength}</span>
              </div>
            </div>
            <Row label="动效">
              <SegOption pressed={!s.motionPaused} onClick={() => s.setMotionPaused(false)}>播放</SegOption>
              <SegOption pressed={s.motionPaused} onClick={() => s.setMotionPaused(true)}>暂停</SegOption>
            </Row>
          </section>

          {/* ── 气泡与按钮 ── */}
          <section className="ol-chat-appearance-section">
            <p className="ol-chat-appearance-section-title">气泡与按钮</p>
            <Row label="AI 回复气泡">
              <SwatchOption pressed={s.aiBubble === 'ink'} onClick={() => s.setAiBubble('ink')} swatch="ol-swatch-ink">深墨</SwatchOption>
              <SwatchOption pressed={s.aiBubble === 'soft'} onClick={() => s.setAiBubble('soft')} swatch="ol-swatch-soft">浅主题</SwatchOption>
              <SwatchOption pressed={s.aiBubble === 'theme'} onClick={() => s.setAiBubble('theme')} swatch="ol-swatch-theme">主题实色</SwatchOption>
              <SwatchOption pressed={s.aiBubble === 'white'} onClick={() => s.setAiBubble('white')} swatch="ol-swatch-white">纸白</SwatchOption>
            </Row>
            <Row label="我的消息气泡">
              <SwatchOption pressed={s.userBubble === 'soft'} onClick={() => s.setUserBubble('soft')} swatch="ol-swatch-soft">浅主题</SwatchOption>
              <SwatchOption pressed={s.userBubble === 'theme'} onClick={() => s.setUserBubble('theme')} swatch="ol-swatch-theme">主题实色</SwatchOption>
              <SwatchOption pressed={s.userBubble === 'ink'} onClick={() => s.setUserBubble('ink')} swatch="ol-swatch-ink">深墨</SwatchOption>
              <SwatchOption pressed={s.userBubble === 'white'} onClick={() => s.setUserBubble('white')} swatch="ol-swatch-white">纸白</SwatchOption>
            </Row>
            <Row label="发送与主要按钮">
              <SwatchOption pressed={s.actionStyle === 'ink'} onClick={() => s.setActionStyle('ink')} swatch="ol-swatch-ink">深墨</SwatchOption>
              <SwatchOption pressed={s.actionStyle === 'theme'} onClick={() => s.setActionStyle('theme')} swatch="ol-swatch-theme">主题实色</SwatchOption>
            </Row>
          </section>

          {/* ── 沉淀（v4 工作台） ── */}
          <section className="ol-chat-appearance-section">
            <p className="ol-chat-appearance-section-title">沉淀</p>
            <Row label="页面布局">
              <SegOption pressed={s.ruminationLayout === 'classic'} onClick={() => s.setRuminationLayout('classic')}>对话分栏</SegOption>
              <SegOption pressed={s.ruminationLayout === 'studio'} onClick={() => s.setRuminationLayout('studio')}>横向工作台</SegOption>
              <SegOption pressed={s.ruminationLayout === 'guided'} onClick={() => s.setRuminationLayout('guided')}>组合解锁</SegOption>
            </Row>
            <Row label="界面层级">
              <SegOption pressed={s.ruminationSkin === 'folio'} onClick={() => s.setRuminationSkin('folio')}>静谧双页</SegOption>
              <SegOption pressed={s.ruminationSkin === 'modules'} onClick={() => s.setRuminationSkin('modules')}>模块编辑</SegOption>
              <SegOption pressed={s.ruminationSkin === 'editorial'} onClick={() => s.setRuminationSkin('editorial')}>编辑长卷</SegOption>
              <SegOption pressed={s.ruminationSkin === 'mist'} onClick={() => s.setRuminationSkin('mist')}>柔雾玻璃</SegOption>
            </Row>
            <Row label="氛围方案">
              <SwatchOption pressed={s.palette === 'lavender'} onClick={() => s.setPalette('lavender')} swatch="ol-swatch-palette-lavender">四色交融</SwatchOption>
              <SwatchOption pressed={s.palette === 'sage'} onClick={() => s.setPalette('sage')} swatch="ol-swatch-palette-sage">蓝绿呼吸</SwatchOption>
              <SwatchOption pressed={s.palette === 'slate'} onClick={() => s.setPalette('slate')} swatch="ol-swatch-palette-slate">暖色微光</SwatchOption>
            </Row>
            <Row label="选择矩阵样式">
              <SwatchOption pressed={s.matrixStyle === 'soft'} onClick={() => s.setMatrixStyle('soft')} swatch="ol-swatch-matrix-soft">柔和填充</SwatchOption>
              <SwatchOption pressed={s.matrixStyle === 'outline'} onClick={() => s.setMatrixStyle('outline')} swatch="ol-swatch-matrix-outline">空心描边</SwatchOption>
              <SwatchOption pressed={s.matrixStyle === 'solid'} onClick={() => s.setMatrixStyle('solid')} swatch="ol-swatch-matrix-solid">实心高亮</SwatchOption>
            </Row>
            <Row label="选择矩阵配色">
              <SwatchOption pressed={s.matrixPalette === 'duo'} onClick={() => s.setMatrixPalette('duo')} swatch="ol-swatch-matrix-duo">热爱橙 × 优势绿</SwatchOption>
              <SwatchOption pressed={s.matrixPalette === 'violet'} onClick={() => s.setMatrixPalette('violet')} swatch="ol-swatch-matrix-violet">统一紫</SwatchOption>
              <SwatchOption pressed={s.matrixPalette === 'multi'} onClick={() => s.setMatrixPalette('multi')} swatch="ol-swatch-matrix-multi">多色区分</SwatchOption>
            </Row>
          </section>

          {/* ── 结论卡（前四阶段） ── */}
          <section className="ol-chat-appearance-section">
            <p className="ol-chat-appearance-section-title">结论卡</p>
            <Row label="结论卡配色">
              <SwatchOption pressed={s.conclusionTone === 'theme-mist'} onClick={() => s.setConclusionTone('theme-mist')} swatch="ol-swatch-tone-mist">主题中调</SwatchOption>
              <SwatchOption pressed={s.conclusionTone === 'theme-paper'} onClick={() => s.setConclusionTone('theme-paper')} swatch="ol-swatch-tone-paper">主题纸感</SwatchOption>
              <SwatchOption pressed={s.conclusionTone === 'theme-gradient'} onClick={() => s.setConclusionTone('theme-gradient')} swatch="ol-swatch-tone-gradient">主题渐层</SwatchOption>
              <SwatchOption pressed={s.conclusionTone === 'theme-outline'} onClick={() => s.setConclusionTone('theme-outline')} swatch="ol-swatch-tone-outline">主题描边</SwatchOption>
              <SwatchOption pressed={s.conclusionTone === 'theme-solid'} onClick={() => s.setConclusionTone('theme-solid')} swatch="ol-swatch-tone-solid">主题实色</SwatchOption>
            </Row>
            <Row label="结论标签样式">
              <SegOption pressed={s.conclusionTags === 'soft'} onClick={() => s.setConclusionTags('soft')}>柔和胶囊</SegOption>
              <SegOption pressed={s.conclusionTags === 'outline'} onClick={() => s.setConclusionTags('outline')}>清晰描边</SegOption>
              <SegOption pressed={s.conclusionTags === 'editorial'} onClick={() => s.setConclusionTags('editorial')}>报告短线</SegOption>
            </Row>
          </section>

          {/* ── 对话排版（无会话侧栏的页面隐藏） ── */}
          {!hideSidebarOptions && (
            <section className="ol-chat-appearance-section">
              <p className="ol-chat-appearance-section-title">对话排版</p>
              <Row label="气泡间距">
                <SegOption pressed={s.density === 'compact'} onClick={() => s.setDensity('compact')}>紧凑</SegOption>
                <SegOption pressed={s.density === 'roomy'} onClick={() => s.setDensity('roomy')}>宽松</SegOption>
              </Row>
              <Row label="新建对话按钮">
                <SegOption pressed={s.newChatStyle === 'dashed'} onClick={() => s.setNewChatStyle('dashed')}>虚线浅底</SegOption>
                <SegOption pressed={s.newChatStyle === 'solid'} onClick={() => s.setNewChatStyle('solid')}>深墨实心</SegOption>
              </Row>
            </section>
          )}

          <footer className="ol-chat-appearance-foot">
            <button type="button" onClick={() => s.resetToRecommended()}>
              恢复推荐组合
            </button>
          </footer>
        </div>
      )}
    </div>
  );
}
