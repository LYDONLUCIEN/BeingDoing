'use client';

import { useState, useRef, useEffect } from 'react';
import { ImagePlus, Mic, Square } from 'lucide-react';

interface ConversationInputProps {
  onSubmit: (content: string) => void;
  loading: boolean;
  /** 是否正在流式输出（显示终止按钮） */
  streaming?: boolean;
  onStopStream?: () => void;
  placeholder?: string;
  /** 外部设置的文本（如点击建议标签） */
  externalText?: string;
  onExternalTextConsumed?: () => void;
}

export default function ConversationInput({
  onSubmit,
  loading,
  streaming = false,
  onStopStream,
  placeholder = '把你现在的想法、回答或问题都写在这里，我们一起聊聊…',
  externalText,
  onExternalTextConsumed,
}: ConversationInputProps) {
  const [text, setText] = useState('');
  const fileInputRef = useRef<HTMLInputElement>(null);

  // 同步外部文本到内部 state
  useEffect(() => {
    if (externalText) {
      setText(externalText);
      onExternalTextConsumed?.();
    }
  }, [externalText]);

  const handleSubmit = (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    const trimmed = text.trim();
    if (!trimmed || loading || streaming) return;
    onSubmit(trimmed);
    setText('');
  };

  const onKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  };

  return (
    <form onSubmit={handleSubmit} className="flex flex-col gap-2">
      <div className="flex rounded-xl border border-white/15 bg-slate-800/50 focus-within:border-primary-400/50 focus-within:ring-2 focus-within:ring-primary-400/20 transition-all">
        <textarea
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={onKeyDown}
          placeholder={placeholder}
          rows={3}
          disabled={loading || streaming}
          className="flex-1 min-h-[80px] resize-none bg-transparent px-4 py-3 text-white placeholder-white/40 focus:outline-none rounded-xl"
        />
        <div className="flex flex-col justify-end gap-1 pr-2 pb-2">
          <button
            type="button"
            onClick={() => fileInputRef.current?.click()}
            className="p-2 rounded-lg text-white/50 hover:bg-white/10 hover:text-white/70 transition-colors"
            title="上传图片（占位）"
          >
            <ImagePlus size={20} />
          </button>
          <input
            ref={fileInputRef}
            type="file"
            accept="image/*"
            className="hidden"
            onChange={() => {}}
          />
          <button
            type="button"
            className="p-2 rounded-lg text-white/50 hover:bg-white/10 hover:text-white/70 transition-colors"
            title="语音输入（占位）"
          >
            <Mic size={20} />
          </button>
        </div>
      </div>
      <div className="flex items-center gap-2 self-end">
        {streaming && onStopStream && (
          <button
            type="button"
            onClick={onStopStream}
            className="flex items-center gap-1.5 px-4 py-2.5 rounded-lg bg-red-500/80 hover:bg-red-500 text-white font-medium transition-colors"
          >
            <Square size={14} /> 终止
          </button>
        )}
        <button
          type="submit"
          disabled={loading || streaming || !text.trim()}
          className="px-6 py-2.5 rounded-lg bg-primary-500 hover:bg-primary-400 text-white font-medium disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
        >
          {loading ? '提交中…' : '发送'}
        </button>
      </div>
    </form>
  );
}
