'use client';

/**
 * 共享悬停气泡组件
 *
 * 用于长文本缩略后的悬停全文展示（如终选卡片的假设正文、优势文字、不推荐原因）。
 * 采用 portal + fixed 定位，避免被 overflow 滚动容器裁剪。
 */

import { ReactNode, useRef, useState } from 'react';
import { createPortal } from 'react-dom';

interface HoverTooltipProps {
  /** 悬停显示的完整文本；空白时不挂气泡 */
  content?: string | null;
  children: ReactNode;
  /** 触发元素额外 className */
  className?: string;
  /** 气泡最大宽度（px） */
  maxWidth?: number;
}

export default function HoverTooltip({
  content,
  children,
  className,
  maxWidth = 320,
}: HoverTooltipProps) {
  const triggerRef = useRef<HTMLSpanElement>(null);
  const [pos, setPos] = useState<{ x: number; y: number; above: boolean } | null>(null);

  const show = () => {
    if (!content?.trim() || !triggerRef.current) return;
    const r = triggerRef.current.getBoundingClientRect();
    // 上方空间足够则向上弹出，否则向下
    const above = r.top > 160;
    // 水平方向钳制在视口内
    const half = Math.min(maxWidth, window.innerWidth - 16) / 2;
    const x = Math.min(Math.max(r.left + r.width / 2, half + 8), window.innerWidth - half - 8);
    setPos({ x, y: above ? r.top : r.bottom, above });
  };

  const hide = () => setPos(null);

  return (
    <span
      ref={triggerRef}
      className={className}
      onMouseEnter={show}
      onMouseLeave={hide}
    >
      {children}
      {pos &&
        createPortal(
          <span
            role="tooltip"
            className="pointer-events-none fixed z-[300] whitespace-pre-wrap rounded-[10px] px-3 py-2 text-left text-[12px] leading-relaxed"
            style={{
              left: pos.x,
              top: pos.above ? pos.y - 8 : pos.y + 8,
              transform: pos.above ? 'translate(-50%, -100%)' : 'translate(-50%, 0)',
              maxWidth,
              background: 'rgba(255,255,255,0.99)',
              border: '1px solid #e3dfff',
              color: '#3d4a63',
              boxShadow: '0 10px 28px rgba(83,61,242,0.16)',
            }}
          >
            {content}
          </span>,
          document.body
        )}
    </span>
  );
}
