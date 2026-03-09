interface ChatMessageProps {
  role: 'ai' | 'user';
  content: string;
  timestamp?: string;
  language: 'en' | 'zh';
}

export function ChatMessage({ role, content, timestamp, language }: ChatMessageProps) {
  const text = {
    en: {
      aiName: 'AI Career Advisor',
      userName: 'You',
    },
    zh: {
      aiName: 'AI 职业顾问',
      userName: '你',
    },
  };

  const t = text[language];

  return (
    <div className={`flex ${role === 'user' ? 'justify-end' : 'justify-start'} mb-6`}>
      <div className={`max-w-[75%] ${role === 'ai' ? 'mr-auto' : 'ml-auto'}`}>
        <div className="flex items-center gap-2 mb-2">
          <div className={`w-8 h-8 rounded-full flex items-center justify-center text-white ${
            role === 'ai' ? 'bg-gradient-to-br from-[#4A90E2] to-[#50E3C2]' : 'bg-[#1d1d1f]'
          }`}>
            {role === 'ai' ? '✨' : '👤'}
          </div>
          <span className="text-xs" style={{ color: 'var(--text-light)', fontFamily: 'var(--font-en)' }}>
            {role === 'ai' ? t.aiName : t.userName}
          </span>
          {timestamp && (
            <span className="text-xs" style={{ color: 'var(--text-light)', fontFamily: 'var(--font-en)' }}>
              • {timestamp}
            </span>
          )}
        </div>
        <div 
          className={`px-6 py-4 rounded-3xl ${
            role === 'ai' 
              ? 'bg-white/60 backdrop-blur-2xl border border-white/90' 
              : 'bg-[#1d1d1f] text-white'
          }`}
          style={{ 
            fontFamily: 'var(--font-cn)',
            boxShadow: '0 20px 40px -10px rgba(0,0,0,0.03)'
          }}
        >
          <p className="leading-relaxed">{content}</p>
        </div>
      </div>
    </div>
  );
}