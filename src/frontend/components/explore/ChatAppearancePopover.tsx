'use client';

import { useEffect, useRef, useState } from 'react';
import { Settings2 } from 'lucide-react';
import { useChatAppearanceStore } from '@/stores/chatAppearanceStore';

/**
 * Chat 外观设置弹层（对齐 HTML #appearance-popover）：
 * 齿轮按钮 → 小浮层，三组独立开关（气泡间距 / 侧栏装饰 / 新建对话样式），
 * 选择持久化到 localStorage（openlife-chat-appearance）。
 */
export default function ChatAppearancePopover() {
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);
  const { density, sidebarArt, newChatStyle, setDensity, setSidebarArt, setNewChatStyle } =
    useChatAppearanceStore();

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
        aria-label="外观设置"
        title="外观设置"
      >
        <Settings2 size={16} strokeWidth={2} aria-hidden />
      </button>

      {open && (
        <div className="ol-chat-appearance-panel" role="dialog" aria-label="外观设置">
          <p className="ol-chat-appearance-title">外观设置</p>

          <div className="ol-chat-appearance-group">
            <span className="ol-chat-appearance-label">气泡间距</span>
            <div className="ol-chat-appearance-seg" role="group" aria-label="气泡间距">
              <button
                type="button"
                aria-pressed={density === 'compact'}
                onClick={() => setDensity('compact')}
              >
                紧凑
              </button>
              <button
                type="button"
                aria-pressed={density === 'roomy'}
                onClick={() => setDensity('roomy')}
              >
                宽松
              </button>
            </div>
          </div>

          <div className="ol-chat-appearance-group">
            <span className="ol-chat-appearance-label">侧栏装饰</span>
            <div className="ol-chat-appearance-seg" role="group" aria-label="侧栏装饰">
              <button
                type="button"
                aria-pressed={sidebarArt}
                onClick={() => setSidebarArt(true)}
              >
                带植物图
              </button>
              <button
                type="button"
                aria-pressed={!sidebarArt}
                onClick={() => setSidebarArt(false)}
              >
                不带图
              </button>
            </div>
          </div>

          <div className="ol-chat-appearance-group">
            <span className="ol-chat-appearance-label">新建对话按钮</span>
            <div className="ol-chat-appearance-seg" role="group" aria-label="新建对话按钮样式">
              <button
                type="button"
                aria-pressed={newChatStyle === 'dashed'}
                onClick={() => setNewChatStyle('dashed')}
              >
                虚线浅底
              </button>
              <button
                type="button"
                aria-pressed={newChatStyle === 'solid'}
                onClick={() => setNewChatStyle('solid')}
              >
                深墨实心
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
