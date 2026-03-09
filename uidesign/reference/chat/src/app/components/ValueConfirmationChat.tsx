import { useState, useRef, useEffect } from 'react';
import { AnimatedBackground } from './BackgroundLayer';
import { ChatMessage } from './ChatMessage';
import { TopMenu } from './TopMenu';

interface Message {
  id: string;
  role: 'ai' | 'user';
  content: { en: string; zh: string };
  timestamp: string;
}

export function ValueConfirmationChat() {
  const [language, setLanguage] = useState<'en' | 'zh'>('en');
  const [userHasConfirmed, setUserHasConfirmed] = useState(false);
  const [showCompleteButton, setShowCompleteButton] = useState(false);
  const [conversationCompleted, setConversationCompleted] = useState(false);
  const [inputValue, setInputValue] = useState('');
  const [isHoveringDisabledInput, setIsHoveringDisabledInput] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const [messages, setMessages] = useState<Message[]>([
    {
      id: '1',
      role: 'ai',
      content: {
        en: "Based on our conversation, I've identified your 5 core values:\n\n1. **Creativity** - Express yourself through innovative solutions\n2. **Impact** - Make a meaningful difference in people's lives\n3. **Autonomy** - Control your own schedule and decisions\n4. **Growth** - Continuously learn and develop new skills\n5. **Collaboration** - Work with talented people toward shared goals\n\nDo you accept these 5 values keywords as your non-negotiable principles?",
        zh: "根据我们的对话，我确定了您的5个核心价值观：\n\n1. **创造力** - 通过创新解决方案表达自己\n2. **影响力** - 对人们的生活产生有意义的影响\n3. **自主权** - 控制自己的时间表和决策\n4. **成长** - 持续学习和发展新技能\n5. **协作** - 与有才华的人一起实现共同目标\n\n您是否接受这5个价值观关键词作为您不可妥协的原则？"
      },
      timestamp: '3:45 PM'
    }
  ]);

  const text = {
    en: {
      sessionTopic: 'Value Confirmation',
      sessionTitle: 'Confirm Your 5 Core Values',
      placeholder: 'Type your response here...',
      placeholderDisabled: 'Conversation completed - no further input allowed',
      send: 'Send',
      completeConversation: 'Complete Conversation',
      completeAndContinue: 'Complete & Continue',
      conversationInProgress: 'Please complete the conversation first',
      inputDisabled: 'Input disabled - conversation completed',
    },
    zh: {
      sessionTopic: '价值确认',
      sessionTitle: '确认您的5个核心价值观',
      placeholder: '在此输入您的回复...',
      placeholderDisabled: '对话已完成 - 不允许进一步输入',
      send: '发送',
      completeConversation: '完成对话',
      completeAndContinue: '完成并继续',
      conversationInProgress: '请先完成对话',
      inputDisabled: '输入已禁用 - 对话已完成',
    },
  };

  const t = text[language];

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages, showCompleteButton]);

  const handleSendMessage = () => {
    if (!inputValue.trim() || conversationCompleted) return;

    const userMessage: Message = {
      id: Date.now().toString(),
      role: 'user',
      content: {
        en: inputValue,
        zh: inputValue
      },
      timestamp: new Date().toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit' })
    };

    setMessages(prev => [...prev, userMessage]);
    setInputValue('');

    // Check if user confirmed the values
    const confirmationKeywords = ['yes', 'accept', 'confirm', 'agree', '是', '接受', '确认', '同意', 'ok', 'okay'];
    const hasConfirmed = confirmationKeywords.some(keyword => 
      inputValue.toLowerCase().includes(keyword)
    );

    if (hasConfirmed && !userHasConfirmed) {
      setUserHasConfirmed(true);
      
      // AI acknowledges confirmation
      setTimeout(() => {
        const aiMessage: Message = {
          id: (Date.now() + 1).toString(),
          role: 'ai',
          content: {
            en: "Excellent! Your 5 core values have been recorded. When you're ready, please click the 'Complete Conversation' button below to finalize this session and move forward.",
            zh: "太好了！您的5个核心价值观已记录。准备好后，请点击下面的「完成对话」按钮以完成此会话并继续前进。"
          },
          timestamp: new Date().toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit' })
        };
        setMessages(prev => [...prev, aiMessage]);
        setShowCompleteButton(true);
      }, 1000);
    }
  };

  const handleKeyPress = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSendMessage();
    }
  };

  const handleCompleteConversation = () => {
    setConversationCompleted(true);
    setShowCompleteButton(false);
  };

  const handleCompleteAndContinue = () => {
    alert(language === 'en' 
      ? 'Moving to the next step in your career exploration journey!' 
      : '进入职业探索之旅的下一步！'
    );
  };

  return (
    <div className="h-screen flex flex-col" style={{ background: '#faf9f8' }}>
      {/* Top Menu */}
      <TopMenu language={language} onLanguageChange={setLanguage} />

      {/* Animated Background */}
      <AnimatedBackground />

      {/* Main Content */}
      <div className="flex-1 flex flex-col relative mt-[72px]" style={{ zIndex: 10 }}>
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
                  {t.sessionTitle}
                </h1>
              </div>
              <button
                onClick={handleCompleteAndContinue}
                disabled={!conversationCompleted}
                title={!conversationCompleted ? t.conversationInProgress : ''}
                className={`px-6 py-3 rounded-full text-white transition-all duration-400 ${
                  !conversationCompleted
                    ? 'opacity-40 cursor-not-allowed' 
                    : 'hover:scale-[0.96] hover:translate-y-0.5'
                }`}
                style={{
                  background: !conversationCompleted
                    ? '#ccc' 
                    : 'linear-gradient(135deg, #4A90E2 0%, #50E3C2 100%)',
                  boxShadow: !conversationCompleted
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

            {/* Complete Conversation Button */}
            {showCompleteButton && (
              <div className="flex justify-center mt-8 mb-4">
                <button
                  onClick={handleCompleteConversation}
                  className="px-8 py-4 rounded-full text-white transition-all duration-400 hover:scale-[0.98] hover:translate-y-0.5 shadow-lg"
                  style={{
                    background: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)',
                    boxShadow: '0 20px 40px -10px rgba(102, 126, 234, 0.4)',
                    fontFamily: 'var(--font-cn)',
                    fontSize: '16px',
                    fontWeight: 500
                  }}
                >
                  ✓ {t.completeConversation}
                </button>
              </div>
            )}

            {/* Conversation Completed Notice */}
            {conversationCompleted && (
              <div className="flex justify-center mt-8 mb-4">
                <div 
                  className="px-6 py-3 rounded-full"
                  style={{
                    background: 'rgba(102, 126, 234, 0.15)',
                    color: '#667eea',
                    fontFamily: 'var(--font-cn)',
                    fontSize: '14px',
                    border: '1px solid rgba(102, 126, 234, 0.3)'
                  }}
                >
                  ✓ Conversation completed - Ready to continue
                </div>
              </div>
            )}

            <div ref={messagesEndRef} />
          </div>
        </div>

        {/* Input Area */}
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
              <div 
                className="flex-1 relative"
                onMouseEnter={() => conversationCompleted && setIsHoveringDisabledInput(true)}
                onMouseLeave={() => setIsHoveringDisabledInput(false)}
              >
                <textarea
                  value={inputValue}
                  onChange={(e) => !conversationCompleted && setInputValue(e.target.value)}
                  onKeyPress={handleKeyPress}
                  disabled={conversationCompleted}
                  placeholder={conversationCompleted ? t.placeholderDisabled : t.placeholder}
                  className="w-full px-6 py-4 rounded-3xl resize-none overflow-hidden border transition-all duration-300 focus:outline-none focus:shadow-lg disabled:cursor-not-allowed"
                  style={{
                    fontFamily: 'var(--font-cn)',
                    background: conversationCompleted ? 'rgba(240, 240, 240, 0.9)' : 'rgba(255, 255, 255, 0.9)',
                    borderColor: conversationCompleted ? 'rgba(255, 0, 0, 0.2)' : 'rgba(0, 0, 0, 0.08)',
                    color: conversationCompleted ? '#999' : 'var(--text-main)',
                    minHeight: '56px',
                    maxHeight: '150px',
                    opacity: conversationCompleted ? 0.6 : 1
                  }}
                  rows={1}
                />
                
                {/* Forbidden Icon on Hover */}
                {isHoveringDisabledInput && conversationCompleted && (
                  <div 
                    className="absolute inset-0 flex items-center justify-center pointer-events-none"
                    style={{
                      background: 'rgba(0, 0, 0, 0.05)',
                      borderRadius: '1.5rem'
                    }}
                  >
                    <div className="flex flex-col items-center gap-2">
                      <span style={{ fontSize: '48px' }}>🚫</span>
                      <span 
                        className="text-xs px-3 py-1 rounded-full"
                        style={{
                          background: 'rgba(255, 255, 255, 0.95)',
                          color: '#999',
                          fontFamily: 'var(--font-cn)',
                          border: '1px solid rgba(0, 0, 0, 0.1)'
                        }}
                      >
                        {t.inputDisabled}
                      </span>
                    </div>
                  </div>
                )}
              </div>
              <button
                onClick={handleSendMessage}
                disabled={!inputValue.trim() || conversationCompleted}
                className="px-8 py-4 rounded-full text-white transition-all duration-400 disabled:opacity-50 disabled:cursor-not-allowed hover:scale-[0.96] hover:translate-y-0.5"
                style={{
                  background: inputValue.trim() && !conversationCompleted ? 'var(--text-main)' : '#ccc',
                  boxShadow: inputValue.trim() && !conversationCompleted ? '0 20px 40px -10px rgba(0,0,0,0.2)' : 'none',
                  fontFamily: 'var(--font-cn)'
                }}
              >
                {t.send}
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}