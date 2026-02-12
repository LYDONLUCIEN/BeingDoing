'use client';

import { useState } from 'react';
import { useSpring, animated } from '@react-spring/web';
import { ChevronDown, ChevronUp, CheckCircle2 } from 'lucide-react';
import { type ConversationItem } from './ConversationThread';
import MessageContent from './MessageContent';

interface CollapsibleQuestionCardProps {
  questionId: number;
  questionContent: string;
  conversationItems: ConversationItem[];
  isCompleted: boolean;
  isCurrentQuestion: boolean;
  onExpand?: () => void;
}

export default function CollapsibleQuestionCard({
  questionId,
  questionContent,
  conversationItems,
  isCompleted,
  isCurrentQuestion,
  onExpand,
}: CollapsibleQuestionCardProps) {
  const [isExpanded, setIsExpanded] = useState(!isCompleted || isCurrentQuestion);

  const contentSpring = useSpring({
    to: { height: isExpanded ? 'auto' : '0px', opacity: isExpanded ? 1 : 0 },
  });

  const cardSpring = useSpring({
    to: {
      transform: isExpanded ? 'scale(1)' : 'scale(0.98)',
      boxShadow: isExpanded
        ? '0 20px 25px -5px rgba(0, 0, 0, 0.3), 0 10px 10px -5px rgba(0, 0, 0, 0.2)'
        : '0 4px 6px -1px rgba(0, 0, 0, 0.1), 0 2px 4px -1px rgba(0, 0, 0, 0.06)',
    },
  });

  const handleToggle = () => {
    setIsExpanded(!isExpanded);
    if (!isExpanded && onExpand) {
      onExpand();
    }
  };

  const borderClass = isCompleted ? 'border-emerald-500/30 bg-emerald-500/5' : 'border-primary-500/30 bg-primary-500/10';
  const ringClass = isCurrentQuestion ? 'ring-2 ring-primary-500/50' : '';

  return (
    <animated.div style={cardSpring} className={`rounded-xl border overflow-hidden mb-4 transition-colors ${borderClass} ${ringClass}`}>
      {/* Header */}
      <button type="button" onClick={handleToggle} className="w-full px-4 py-3 flex items-center justify-between hover:bg-white/5 transition-colors">
        <div className="flex items-center gap-3 flex-1 text-left">
          {isCompleted && <CheckCircle2 className="w-5 h-5 text-emerald-400 flex-shrink-0" />}
          <div className="flex-1 min-w-0">
            <p className={`font-medium truncate ${isCompleted ? 'text-emerald-300' : 'text-white'}`}>
              {questionContent}
            </p>
            <p className="text-xs text-white/50 mt-0.5">
              {isCompleted ? '已完成' : isCurrentQuestion ? '进行中' : '未开始'} {' · '} {conversationItems.length} 条对话
            </p>
          </div>
        </div>
        <div className="ml-3 flex-shrink-0">
          {isExpanded ? <ChevronUp className="w-5 h-5 text-white/60" /> : <ChevronDown className="w-5 h-5 text-white/60" />}
        </div>
      </button>

      {/* Content */}
      <animated.div style={contentSpring} className="overflow-hidden">
        <div className="px-4 pb-4 space-y-3">
          <div className="h-px bg-white/10 mb-3" />
          
          {conversationItems.length > 0 ? (
            <div className="space-y-2 max-h-96 overflow-y-auto custom-scrollbar">
              {conversationItems.map((item, idx) => {
                const isChat = item.type === 'chat';
                const content = isChat 
                  ? (item as any).message?.content ?? '' 
                  : (item as any).answer?.content ?? (item as any).questionContent ?? '';
                
                return (
                  <div key={idx} className={`rounded-lg p-3 text-sm ${isChat ? 'bg-primary-500/20 ml-8' : 'bg-white/5 mr-8'}`}>
                    <div className="flex items-start gap-2">
                      <span className={`text-xs font-medium px-2 py-0.5 rounded ${isChat ? 'bg-primary-500/30 text-primary-200' : 'bg-white/10 text-white/70'}`}>
                        {isChat ? ((item as any).role === 'user' ? '你' : 'AI') : '答案'}
                      </span>
                      <div className="flex-1 min-w-0">
                        <MessageContent content={content} />
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          ) : (
            <p className="text-sm text-white/40 text-center py-4">暂无对话记录</p>
          )}
        </div>
      </animated.div>
    </animated.div>
  );
}
