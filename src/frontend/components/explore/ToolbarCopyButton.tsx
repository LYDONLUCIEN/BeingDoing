'use client';

/**
 * 聊天气泡工具栏复制按钮：复制成功后在按钮上方浮出小气泡反馈（如「已复制」），1.6s 自动消失。
 * 前四阶段 chat 页用户气泡、沉淀 v4 用户气泡、FlowAiMessage AI 气泡共用。
 */

import { useEffect, useRef, useState } from 'react';
import { Copy } from 'lucide-react';
import { copyToClipboard } from '@/lib/utils/clipboard';

interface ToolbarCopyButtonProps {
  /** 待复制文本 */
  text: string;
  /** 按钮无障碍/hover 文案 */
  title: string;
  /** 复制成功反馈文案（如「已复制」） */
  feedback: string;
  /** 复制成功后的额外回调 */
  onCopied?: () => void;
}

export default function ToolbarCopyButton({ text, title, feedback, onCopied }: ToolbarCopyButtonProps) {
  const [showFeedback, setShowFeedback] = useState(false);
  const timerRef = useRef<number | null>(null);

  useEffect(
    () => () => {
      if (timerRef.current) window.clearTimeout(timerRef.current);
    },
    []
  );

  const handleCopy = () => {
    copyToClipboard(text).then((ok) => {
      if (!ok) return;
      onCopied?.();
      setShowFeedback(true);
      if (timerRef.current) window.clearTimeout(timerRef.current);
      timerRef.current = window.setTimeout(() => setShowFeedback(false), 1600);
    });
  };

  return (
    <span className="flow-toolbar-btn-wrap">
      <button type="button" className="flow-toolbar-btn" title={title} aria-label={title} onClick={handleCopy}>
        <Copy size={14} strokeWidth={1.6} />
      </button>
      {showFeedback && (
        <span className="flow-toolbar-feedback" role="status">
          {feedback}
        </span>
      )}
    </span>
  );
}
