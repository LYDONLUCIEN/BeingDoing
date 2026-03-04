'use client';

import { useState, useRef, useEffect } from 'react';
import { ArrowUp, Square } from 'lucide-react';

interface FlowChatInputProps {
  onSubmit: (content: string) => void;
  streaming?: boolean;
  onStopStream?: () => void;
  placeholder?: string;
  externalText?: string;
  onExternalTextConsumed?: () => void;
}

/**
 * 完全复刻 llmchat.html 的输入框：圆角白底、内嵌圆形发送/停止、呼吸灯
 */
export default function FlowChatInput({
  onSubmit,
  streaming = false,
  onStopStream,
  placeholder = '说说你的想法...',
  externalText,
  onExternalTextConsumed,
}: FlowChatInputProps) {
  const [text, setText] = useState('');
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    if (externalText) {
      setText(externalText);
      onExternalTextConsumed?.();
    }
  }, [externalText]);

  useEffect(() => {
    const ta = textareaRef.current;
    if (!ta) return;
    ta.style.height = 'auto';
    ta.style.height = Math.min(ta.scrollHeight, 150) + 'px';
  }, [text]);

  const handleSubmit = (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    const trimmed = text.trim();
    if (!trimmed || streaming) return;
    onSubmit(trimmed);
    setText('');
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
    }
  };

  const onKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  };

  const handleSendOrStop = () => {
    if (streaming && onStopStream) {
      onStopStream();
    } else {
      handleSubmit();
    }
  };

  return (
    <form onSubmit={handleSubmit} className="flow-input-area">
      <div className="flow-input-box">
        <textarea
          ref={textareaRef}
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={onKeyDown}
          placeholder={placeholder}
          rows={1}
          disabled={streaming}
          className="flow-input-field"
        />
        <div className="flow-send-btn-wrap">
          {streaming && <div className="flow-send-glow" aria-hidden />}
          <button
            type="button"
            onClick={handleSendOrStop}
            className={`flow-send-btn ${streaming ? 'is-stop' : ''}`}
            disabled={!streaming && !text.trim()}
            title={streaming ? '停止' : '发送'}
          >
            {streaming ? (
              <Square size={16} strokeWidth={0} fill="white" />
            ) : (
              <ArrowUp size={16} strokeWidth={2.2} />
            )}
          </button>
        </div>
      </div>
    </form>
  );
}
