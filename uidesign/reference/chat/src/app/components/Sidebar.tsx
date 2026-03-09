import { useState } from 'react';

interface Session {
  id: string;
  title: { en: string; zh: string };
  date: string;
  status: 'completed' | 'in-progress';
}

interface SidebarProps {
  onNewChat: () => void;
  onSelectSession: (sessionId: string) => void;
  currentSessionId: string;
  language: 'en' | 'zh';
  sessions?: Session[];
}

const defaultSessions: Session[] = [
  {
    id: 'current',
    title: {
      en: 'Clarify Your Values: Identify Your 5 Non-Negotiable Principles',
      zh: '明确你的价值观：确定你的5个不可妥协的原则'
    },
    date: 'Today, 2:30 PM',
    status: 'in-progress'
  },
  {
    id: 'session-2',
    title: {
      en: 'Discover Your Natural Talents',
      zh: '发现你的天赋'
    },
    date: 'March 5, 2026',
    status: 'completed'
  },
  {
    id: 'session-3',
    title: {
      en: 'Exploring Career Passions',
      zh: '探索职业热情'
    },
    date: 'March 3, 2026',
    status: 'in-progress'
  },
  {
    id: 'session-4',
    title: {
      en: 'Define Your Career North Star',
      zh: '定义你的职业北极星'
    },
    date: 'March 1, 2026',
    status: 'completed'
  }
];

export function Sidebar({ onNewChat, onSelectSession, currentSessionId, language, sessions = defaultSessions }: SidebarProps) {
  const [isHistoryOpen, setIsHistoryOpen] = useState(true);

  const text = {
    en: {
      appName: 'Careering',
      newChat: '+ New Chat',
      chatHistory: 'Chat History',
      inProgress: 'In Progress',
      completed: 'Completed',
    },
    zh: {
      appName: 'Careering',
      newChat: '+ 新对话',
      chatHistory: '对话历史',
      inProgress: '进行中',
      completed: '已完成',
    },
  };

  const t = text[language];

  return (
    <div 
      className="w-80 h-full border-r flex flex-col"
      style={{ 
        background: 'rgba(255, 255, 255, 0.6)',
        backdropFilter: 'blur(24px)',
        WebkitBackdropFilter: 'blur(24px)',
        borderColor: 'rgba(255, 255, 255, 0.9)',
      }}
    >
      {/* Header */}
      <div className="p-6 border-b" style={{ borderColor: 'rgba(0, 0, 0, 0.05)' }}>
        <div className="flex items-center gap-3 mb-6">
          <div className="w-10 h-10 rounded-full bg-gradient-to-br from-[#4A90E2] to-[#50E3C2] flex items-center justify-center text-white">
            ✨
          </div>
          <div>
            <h2 className="font-medium" style={{ fontFamily: 'var(--font-cn)', color: 'var(--text-main)' }}>
              {t.appName}
            </h2>
          </div>
        </div>
        
        <button 
          onClick={onNewChat}
          className="w-full px-6 py-3 rounded-full text-white transition-all duration-400 hover:scale-[0.96] hover:translate-y-0.5"
          style={{
            background: 'var(--text-main)',
            boxShadow: '0 20px 40px -10px rgba(0,0,0,0.2)',
            fontFamily: 'var(--font-cn)'
          }}
        >
          {t.newChat}
        </button>
      </div>

      {/* History Section */}
      <div className="flex-1 overflow-y-auto">
        <div className="p-4">
          <button
            onClick={() => setIsHistoryOpen(!isHistoryOpen)}
            className="w-full flex items-center justify-between px-3 py-2 rounded-lg transition-colors hover:bg-black/5"
          >
            <span className="text-sm" style={{ fontFamily: 'var(--font-cn)', color: 'var(--text-light)' }}>
              {t.chatHistory}
            </span>
            <span className="text-xs" style={{ transform: isHistoryOpen ? 'rotate(180deg)' : 'rotate(0deg)', transition: 'transform 0.3s' }}>
              ▼
            </span>
          </button>

          {isHistoryOpen && (
            <div className="mt-2 space-y-2">
              {sessions.map((session) => (
                <button
                  key={session.id}
                  onClick={() => onSelectSession(session.id)}
                  className={`w-full text-left px-4 py-3 rounded-xl transition-all duration-300 ${
                    currentSessionId === session.id 
                      ? 'bg-white/80 shadow-lg scale-[1.02]' 
                      : 'bg-white/30 hover:bg-white/50'
                  }`}
                  style={{
                    border: currentSessionId === session.id ? '1px solid rgba(0, 0, 0, 0.08)' : '1px solid transparent'
                  }}
                >
                  <div className="flex items-start gap-2 mb-2">
                    <div className={`mt-1 w-2 h-2 rounded-full ${
                      session.status === 'in-progress' ? 'bg-[#F5A623]' : 'bg-[#50E3C2]'
                    }`} />
                    <div className="flex-1 min-w-0">
                      <p className="text-sm line-clamp-2 mb-1" style={{ fontFamily: 'var(--font-cn)', color: 'var(--text-main)' }}>
                        {session.title[language]}
                      </p>
                      <p className="text-xs" style={{ fontFamily: 'var(--font-en)', color: 'var(--text-light)' }}>
                        {session.date}
                      </p>
                    </div>
                  </div>
                  <div className="flex items-center gap-1">
                    <span className="text-xs px-2 py-0.5 rounded-full" style={{
                      background: session.status === 'in-progress' ? 'rgba(245, 166, 35, 0.1)' : 'rgba(80, 227, 194, 0.1)',
                      color: session.status === 'in-progress' ? '#F5A623' : '#50E3C2',
                      fontFamily: 'var(--font-en)'
                    }}>
                      {session.status === 'in-progress' ? t.inProgress : t.completed}
                    </span>
                  </div>
                </button>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}