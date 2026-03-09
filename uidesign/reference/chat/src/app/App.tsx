import { useState, useRef, useEffect } from 'react';
import { AnimatedBackground } from './components/BackgroundLayer';
import { ChatMessage } from './components/ChatMessage';
import { Sidebar } from './components/Sidebar';
import { ChatInput } from './components/ChatInput';
import { TopMenu } from './components/TopMenu';

interface Message {
  id: string;
  role: 'ai' | 'user';
  content: {
    en: string;
    zh: string;
  };
  timestamp: string;
}

interface SessionData {
  id: string;
  status: 'in-progress' | 'completed';
  title: {
    en: string;
    zh: string;
  };
}

const sessionsData: Record<string, SessionData> = {
  'current': {
    id: 'current',
    status: 'in-progress',
    title: {
      en: 'Clarify Your Values: Identify Your 5 Non-Negotiable Principles',
      zh: '澄清你的价值观：确定你的5个不可妥协的原则'
    }
  },
  'session-2': {
    id: 'session-2',
    status: 'completed',
    title: {
      en: 'Discover Your Talents: Uncover Your Natural Strengths',
      zh: '发现你的天赋：揭示你的天生优势'
    }
  },
  'session-3': {
    id: 'session-3',
    status: 'completed',
    title: {
      en: 'Explore Your Passions: What Truly Excites You',
      zh: '探索你的热情：什么真正让你兴奋'
    }
  },
  'session-4': {
    id: 'session-4',
    status: 'in-progress',
    title: {
      en: 'Define Your Goals: Create Your Career Roadmap',
      zh: '定义你的目标：创建你的职业路线图'
    }
  }
};

export default function App() {
  const [language, setLanguage] = useState<'en' | 'zh'>('en');
  const [currentSessionId, setCurrentSessionId] = useState('current');
  const [currentSession, setCurrentSession] = useState<SessionData>(sessionsData['current']);
  const [aiSuggestsCompletion, setAiSuggestsCompletion] = useState(false);
  const [messages, setMessages] = useState<Message[]>([
    {
      id: '1',
      role: 'ai',
      content: {
        en: "Hello! I'm your AI Career Advisor. Today, we're going to explore the values that matter most to you in your career. Let's identify your 5 non-negotiable principles - the core values that will guide your professional journey. To get started, think about a time in your life when you felt truly fulfilled. What made that moment special?",
        zh: "你好！我是你的AI职业顾问。今天，我们将探索在你的职业生涯中最重要的价值观。让我们确定你的5个不可妥协的原则 - 这些核心价值观将指引你的职业之旅。首先，想一想你生活中感到真正满足的时刻。是什么让那一刻如此特别？"
      },
      timestamp: '2:30 PM'
    }
  ]);
  const [isCompleteDialogOpen, setIsCompleteDialogOpen] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const text = {
    en: {
      sessionTopic: 'Session Topic',
      completeAndContinue: 'Complete & Continue',
      completeDialogTitle: 'Complete This Session?',
      completeDialogMessage: 'Are you ready to mark this session as complete and move on to the next topic in your career exploration journey?',
      resumeSession: 'Resume Session',
      complete: 'Complete',
      cannotComplete: 'Complete this session first',
      aiSuggestsComplete: 'Great work! I believe we\'ve covered all the key aspects of this session.',
      confirmCompletion: 'Confirm Session Completion',
      sessionCompleted: 'This session has been completed',
    },
    zh: {
      sessionTopic: '会话主题',
      completeAndContinue: '完成并继续',
      completeDialogTitle: '完成此会话？',
      completeDialogMessage: '您准备好将此会话标记为已完成并继续探索职业生涯的下一个主题吗？',
      resumeSession: '继续会话',
      complete: '完成',
      cannotComplete: '请先完成此会话',
      aiSuggestsComplete: '做得很好！我相信我们已经涵盖了本次会话的所有关键方面。',
      confirmCompletion: '确认会话完成',
      sessionCompleted: '此会话已完成',
    },
  };

  const t = text[language];

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  const handleSendMessage = (content: string) => {
    const userMessage: Message = {
      id: Date.now().toString(),
      role: 'user',
      content: {
        en: content,
        zh: content
      },
      timestamp: new Date().toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit' })
    };

    setMessages(prev => [...prev, userMessage]);

    // Count user messages to determine if session should be completed
    const userMessageCount = messages.filter(m => m.role === 'user').length + 1;

    // Simulate AI response
    setTimeout(() => {
      let aiResponseContent;
      
      // After 3 user messages, AI suggests completion
      if (userMessageCount >= 3 && !aiSuggestsCompletion && currentSession.status === 'in-progress') {
        aiResponseContent = {
          en: "Excellent reflection! Based on our conversation, I can see you've identified some powerful core values. We've explored your fulfillment moments, the aspects that resonate with you, and the principles that guide your decisions. I believe we've covered all the key aspects of this session. You're ready to move forward!",
          zh: "非常好的反思！根据我们的对话，我可以看出你已经确定了一些强大的核心价值观。我们探讨了让你感到满足的时刻、与你产生共鸣的方面，以及指导你决策的原则。我相信我们已经涵盖了本次会话的所有关键方面。你已经准备好继续前进了！"
        };
        setAiSuggestsCompletion(true);
      } else {
        aiResponseContent = {
          en: "That's a wonderful insight! Understanding what made you feel fulfilled helps us identify your core values. Can you tell me what specific aspects of that experience resonated with you the most? Was it the sense of accomplishment, the impact on others, the creative expression, or something else?",
          zh: "这是一个很好的见解！了解是什么让你感到满足有助于我们确定你的核心价值观。你能告诉我那次经历中哪些具体方面最能引起你的共鸣吗？是成就感、对他人的影响、创造性表达，还是其他什么？"
        };
      }

      const aiMessage: Message = {
        id: (Date.now() + 1).toString(),
        role: 'ai',
        content: aiResponseContent,
        timestamp: new Date().toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit' })
      };
      setMessages(prev => [...prev, aiMessage]);
    }, 1000);
  };

  const handleConfirmCompletion = () => {
    setCurrentSession(prev => ({ ...prev, status: 'completed' }));
    setAiSuggestsCompletion(false);
    // In a real app, this would update the session in the database
  };

  const handleNewChat = () => {
    const newSessionId = 'new-' + Date.now();
    const newSession: SessionData = {
      id: newSessionId,
      status: 'in-progress',
      title: {
        en: 'New Conversation',
        zh: '新对话'
      }
    };
    setCurrentSessionId(newSessionId);
    setCurrentSession(newSession);
    setAiSuggestsCompletion(false);
    setMessages([
      {
        id: '1',
        role: 'ai',
        content: {
          en: "Hello! I'm your AI Career Advisor. What would you like to explore today? I can help you with understanding your values, discovering your talents, exploring your passions, or defining your career goals.",
          zh: "你好！我是你的AI职业顾问。今天你想探索什么？我可以帮助你了解你的价值观、发现你的天赋、探索你的热情或定义你的职业目标。"
        },
        timestamp: new Date().toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit' })
      }
    ]);
  };

  const handleSelectSession = (sessionId: string) => {
    setCurrentSessionId(sessionId);
    const session = sessionsData[sessionId];
    if (session) {
      setCurrentSession(session);
      setAiSuggestsCompletion(false);
    }
    // In a real app, this would load the session's messages from a database
    if (sessionId === 'current') {
      setMessages([
        {
          id: '1',
          role: 'ai',
          content: {
            en: "Hello! I'm your AI Career Advisor. Today, we're going to explore the values that matter most to you in your career. Let's identify your 5 non-negotiable principles - the core values that will guide your professional journey. To get started, think about a time in your life when you felt truly fulfilled. What made that moment special?",
            zh: "你好！我是你的AI职业顾问。今天，我们将探索在你的职业生涯中最重要的价值观。让我们确定你的5个不可妥协的原则 - 这些核心价值观将指引你的职业之旅。首先，想一想你生活中感到真正满足的时刻。是什么让那一刻如此特别？"
          },
          timestamp: '2:30 PM'
        }
      ]);
    } else {
      setMessages([
        {
          id: '1',
          role: 'ai',
          content: {
            en: "Resuming your previous session. Let's continue exploring your career path together!",
            zh: "恢复您之前的会话。让我们继续一起探索您的职业道路！"
          },
          timestamp: new Date().toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit' })
        }
      ]);
    }
  };

  const handleCompleteAndContinue = () => {
    if (currentSession.status === 'completed') {
      alert(language === 'en' 
        ? 'Moving to the next session in your career exploration journey!' 
        : '进入职业探索之旅的下一个会话！'
      );
    }
  };

  const isSessionInProgress = currentSession.status === 'in-progress';

  // Build sessions list with current session status
  const sessionsList = Object.entries(sessionsData).map(([id, session]) => {
    const sessionData = id === currentSessionId ? currentSession : session;
    return {
      id: sessionData.id,
      title: sessionData.title,
      date: id === 'current' ? 'Today, 2:30 PM' : 
            id === 'session-2' ? 'March 5, 2026' :
            id === 'session-3' ? 'March 3, 2026' : 'March 1, 2026',
      status: sessionData.status
    };
  });

  return (
    <div className="h-screen flex flex-col" style={{ background: '#faf9f8' }}>
      {/* Top Menu */}
      <TopMenu language={language} onLanguageChange={setLanguage} />

      {/* Animated Background */}
      <AnimatedBackground />

      {/* Main Content - with top padding for fixed menu */}
      <div className="flex-1 flex relative mt-[72px]" style={{ zIndex: 10 }}>
        {/* Sidebar */}
        <Sidebar 
          onNewChat={handleNewChat}
          onSelectSession={handleSelectSession}
          currentSessionId={currentSessionId}
          language={language}
          sessions={sessionsList}
        />

        {/* Chat Area */}
        <div className="flex-1 flex flex-col">
          {/* Header */}
          <div 
            className="px-8 py-6 border-b"
            style={{ 
              background: 'rgba(255, 255, 255, 0.7)',
              backdropFilter: 'blur(20px)',
              WebkitBackdropFilter: 'blur(20px)',
              borderColor: 'rgba(0, 0, 0, 0.08)'
            }}
          >
            <div className="max-w-4xl mx-auto">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-xs mb-2" style={{ 
                    fontFamily: 'var(--font-en)', 
                    color: 'var(--text-light)',
                    letterSpacing: '0.3em',
                    textTransform: 'uppercase'
                  }}>
                    {t.sessionTopic}
                  </p>
                  <h1 className="text-2xl" style={{ 
                    fontFamily: 'var(--font-cn)', 
                    color: 'var(--text-main)',
                    fontWeight: 600
                  }}>
                    {currentSession.title[language]}
                  </h1>
                </div>
                <button
                  onClick={handleCompleteAndContinue}
                  disabled={isSessionInProgress}
                  title={isSessionInProgress ? t.cannotComplete : ''}
                  className={`px-6 py-3 rounded-full text-white transition-all duration-400 ${
                    isSessionInProgress
                      ? 'opacity-40 cursor-not-allowed' 
                      : 'hover:scale-[0.96] hover:translate-y-0.5'
                  }`}
                  style={{
                    background: isSessionInProgress
                      ? '#ccc' 
                      : 'linear-gradient(135deg, #4A90E2 0%, #50E3C2 100%)',
                    boxShadow: isSessionInProgress
                      ? 'none' 
                      : '0 20px 40px -10px rgba(74, 144, 226, 0.3)',
                    fontFamily: 'var(--font-cn)'
                  }}
                >
                  {t.completeAndContinue}
                </button>
              </div>
            </div>
          </div>

          {/* Messages Area */}
          <div className="flex-1 overflow-y-auto px-8 py-6">
            <div className="max-w-4xl mx-auto">
              {messages.map((message) => (
                <ChatMessage
                  key={message.id}
                  role={message.role}
                  content={message.content[language]}
                  timestamp={message.timestamp}
                  language={language}
                />
              ))}
              
              {/* AI Suggests Completion Button */}
              {aiSuggestsCompletion && currentSession.status === 'in-progress' && (
                <div className="flex justify-center mt-8 mb-4">
                  <button
                    onClick={handleConfirmCompletion}
                    className="px-8 py-4 rounded-full text-white transition-all duration-400 hover:scale-[0.98] hover:translate-y-0.5"
                    style={{
                      background: 'linear-gradient(135deg, #4A90E2 0%, #50E3C2 100%)',
                      boxShadow: '0 20px 40px -10px rgba(74, 144, 226, 0.4)',
                      fontFamily: 'var(--font-cn)',
                      fontSize: '16px',
                      fontWeight: 500
                    }}
                  >
                    ✓ {t.confirmCompletion}
                  </button>
                </div>
              )}

              {/* Session Completed Notice */}
              {currentSession.status === 'completed' && (
                <div className="flex justify-center mt-8 mb-4">
                  <div 
                    className="px-6 py-3 rounded-full"
                    style={{
                      background: 'rgba(80, 227, 194, 0.15)',
                      color: '#50E3C2',
                      fontFamily: 'var(--font-cn)',
                      fontSize: '14px',
                      border: '1px solid rgba(80, 227, 194, 0.3)'
                    }}
                  >
                    ✓ {t.sessionCompleted}
                  </div>
                </div>
              )}
              
              <div ref={messagesEndRef} />
            </div>
          </div>

          {/* Input Area */}
          <ChatInput 
            onSend={handleSendMessage} 
            language={language}
            disabled={currentSession.status === 'completed'}
          />
        </div>
      </div>
    </div>
  );
}
