import { useState, KeyboardEvent } from 'react';

interface ChatInputProps {
  onSend: (message: string) => void;
  disabled?: boolean;
  language: 'en' | 'zh';
}

export function ChatInput({ onSend, disabled = false, language }: ChatInputProps) {
  const [message, setMessage] = useState('');

  const text = {
    en: {
      placeholder: 'Type your response here...',
      send: 'Send',
    },
    zh: {
      placeholder: '在此输入您的回复...',
      send: '发送',
    },
  };

  const t = text[language];

  const handleSend = () => {
    if (message.trim() && !disabled) {
      onSend(message.trim());
      setMessage('');
    }
  };

  const handleKeyPress = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  return (
    <div 
      className="px-6 py-4 border-t"
      style={{ 
        background: 'rgba(255, 255, 255, 0.85)',
        backdropFilter: 'blur(20px)',
        WebkitBackdropFilter: 'blur(20px)',
        borderColor: 'rgba(0, 0, 0, 0.08)'
      }}
    >
      <div className="max-w-4xl mx-auto">
        <div className="flex items-end gap-3">
          <div className="flex-1 relative">
            <textarea
              value={message}
              onChange={(e) => setMessage(e.target.value)}
              onKeyPress={handleKeyPress}
              disabled={disabled}
              placeholder={t.placeholder}
              className="w-full px-6 py-4 rounded-3xl resize-none overflow-hidden border transition-all duration-300 focus:outline-none focus:shadow-lg disabled:cursor-not-allowed"
              style={{
                fontFamily: 'var(--font-cn)',
                background: disabled ? 'rgba(240, 240, 240, 0.9)' : 'rgba(255, 255, 255, 0.9)',
                borderColor: 'rgba(0, 0, 0, 0.08)',
                color: disabled ? '#999' : 'var(--text-main)',
                minHeight: '56px',
                maxHeight: '150px',
                opacity: disabled ? 0.6 : 1
              }}
              rows={1}
            />
          </div>
          <button
            onClick={handleSend}
            disabled={!message.trim() || disabled}
            className="px-8 py-4 rounded-full text-white transition-all duration-400 disabled:opacity-50 disabled:cursor-not-allowed hover:scale-[0.96] hover:translate-y-0.5"
            style={{
              background: message.trim() && !disabled ? 'var(--text-main)' : '#ccc',
              boxShadow: message.trim() && !disabled ? '0 20px 40px -10px rgba(0,0,0,0.2)' : 'none',
              fontFamily: 'var(--font-cn)'
            }}
          >
            {t.send}
          </button>
        </div>
      </div>
    </div>
  );
}