'use client';

import { useState } from 'react';
import { useSpring, animated, config } from '@react-spring/web';
import { CheckCircle2, MessageCircle, Edit3, X, Check, ChevronDown, ChevronUp, Sparkles, Lightbulb } from 'lucide-react';
import MessageContent from '@/components/explore/MessageContent';

interface EnhancedAnswerCardProps {
  questionContent: string;
  userAnswer: string;
  /** AI 对用户回答的简短总结 */
  aiSummary?: string;
  /** AI 深层分析 */
  aiAnalysis?: string;
  /** AI 提取的关键洞察标签 */
  keyInsights?: string[];
  onConfirm?: () => void;  // 可选，已确认时不需要
  onDiscussMore?: () => void;  // 可选，已确认时不需要
  onEdit?: (newAnswer: string) => Promise<void>;
  /** 是否处于折叠（已确认）状态 */
  isCollapsed?: boolean;
  /** 切换展开/折叠 */
  onToggleExpand?: () => void;
}

export default function EnhancedAnswerCard({
  questionContent,
  userAnswer,
  aiSummary,
  aiAnalysis,
  keyInsights,
  onConfirm,
  onDiscussMore,
  onEdit,
  isCollapsed = false,
  onToggleExpand,
}: EnhancedAnswerCardProps) {
  const [isEditing, setIsEditing] = useState(false);
  const [editValue, setEditValue] = useState(userAnswer);
  const [isSaving, setIsSaving] = useState(false);
  const [showUserAnswer, setShowUserAnswer] = useState(false);

  // 入场动画
  const cardSpring = useSpring({
    from: { opacity: 0, transform: 'scale(0.95) translateY(12px)' },
    to: { opacity: 1, transform: 'scale(1) translateY(0px)' },
    config: config.gentle,
  });

  const handleSaveEdit = async () => {
    if (!onEdit || editValue.trim() === userAnswer.trim()) {
      setIsEditing(false);
      return;
    }
    setIsSaving(true);
    try {
      await onEdit(editValue.trim());
      setIsEditing(false);
    } catch (error) {
      console.error('编辑失败:', error);
    } finally {
      setIsSaving(false);
    }
  };

  // 折叠态：只显示一行
  if (isCollapsed) {
    return (
      <div
        onClick={onToggleExpand}
        className="answer-card answer-card--collapsed mb-3 rounded-xl border border-emerald-500/20 bg-slate-800/40 cursor-pointer hover:bg-slate-800/60 transition-colors"
      >
        <div className="answer-card__header px-4 py-3 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <CheckCircle2 className="w-4 h-4 text-emerald-400" />
            <span className="text-xs bg-emerald-500/20 text-emerald-300 px-2 py-0.5 rounded">已确认</span>
            <span className="text-sm text-white/70 truncate max-w-md">{questionContent}</span>
          </div>
          <div className="flex items-center gap-2">
            {aiSummary && (
              <span className="text-xs text-white/40 truncate max-w-[200px] hidden sm:inline">{aiSummary}</span>
            )}
            <ChevronDown className="w-4 h-4 text-white/40" />
          </div>
        </div>
      </div>
    );
  }

  // 展开态：完整卡片
  return (
    <animated.div style={cardSpring} className="my-4">
      <div className="answer-card relative rounded-2xl bg-gradient-to-br from-emerald-500/20 via-emerald-500/10 to-transparent border border-emerald-500/30 shadow-2xl overflow-hidden">
        {/* 背景装饰 */}
        <div className="absolute inset-0 bg-gradient-to-br from-white/5 to-transparent pointer-events-none" />
        <div className="absolute top-0 right-0 w-32 h-32 bg-emerald-400/10 rounded-full blur-3xl pointer-events-none" />

        <div className="relative p-6 space-y-4">
          {/* Header */}
          <div className="answer-card__header flex items-start gap-3">
            <div className="p-2 rounded-lg bg-emerald-500/20">
              <CheckCircle2 className="w-5 h-5 text-emerald-400" />
            </div>
            <div className="flex-1">
              <h3 className="font-semibold text-emerald-300 mb-1">回答总结</h3>
              <p className="text-sm text-white/60">{questionContent}</p>
            </div>
            {onToggleExpand && (
              <button
                type="button"
                onClick={onToggleExpand}
                className="p-1 rounded hover:bg-white/10 text-white/40 hover:text-white/70 transition-colors"
              >
                <ChevronUp className="w-4 h-4" />
              </button>
            )}
          </div>

          {/* AI Summary - 核心发现 */}
          {aiSummary && (
            <div className="answer-card__summary">
              <div className="flex items-center gap-2 mb-2">
                <Sparkles className="w-4 h-4 text-emerald-400" />
                <span className="text-xs font-medium text-emerald-300 uppercase tracking-wide">核心发现</span>
              </div>
              <div className="pl-1 border-l-[3px] border-emerald-500/50 ml-1">
                <p className="text-sm text-white/90 leading-relaxed pl-3">{aiSummary}</p>
              </div>
            </div>
          )}

          {/* AI Analysis - 深层分析 */}
          {aiAnalysis && (
            <div className="answer-card__analysis">
              <div className="flex items-center gap-2 mb-2">
                <Lightbulb className="w-4 h-4 text-amber-400" />
                <span className="text-xs font-medium text-amber-300 uppercase tracking-wide">深层分析</span>
              </div>
              <p className="text-sm text-white/80 leading-relaxed">{aiAnalysis}</p>
            </div>
          )}

          {/* Key Insights - 关键洞察标签 */}
          {keyInsights && keyInsights.length > 0 && (
            <div className="answer-card__insights">
              <span className="text-xs font-medium text-white/50 mb-2 block">关键洞察</span>
              <div className="flex flex-wrap gap-2">
                {keyInsights.map((insight, i) => (
                  <span
                    key={i}
                    className="answer-card__insight-tag inline-block px-3 py-1 rounded-full text-xs
                               bg-emerald-500/15 border border-emerald-500/30 text-emerald-300"
                  >
                    {insight}
                  </span>
                ))}
              </div>
            </div>
          )}

          {/* User Answer - 你的原话（可折叠） */}
          <div className="answer-card__user-answer">
            <button
              type="button"
              onClick={() => setShowUserAnswer(!showUserAnswer)}
              className="flex items-center gap-1 text-xs text-white/40 hover:text-white/60 transition-colors"
            >
              {showUserAnswer ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
              您的回答(摘要)
            </button>
            {showUserAnswer && (
              <div className="mt-2 bg-white/5 rounded-xl p-4 backdrop-blur-sm">
                {isEditing ? (
                  <div className="space-y-3">
                    <textarea
                      value={editValue}
                      onChange={(e) => setEditValue(e.target.value)}
                      className="w-full min-h-[100px] px-3 py-2 rounded-lg bg-slate-800/80 border border-white/20 text-white placeholder-white/40 focus:outline-none focus:ring-2 focus:ring-emerald-500/50 resize-none"
                      placeholder="编辑您的回答..."
                    />
                    <div className="flex gap-2">
                      <button
                        type="button"
                        onClick={handleSaveEdit}
                        disabled={isSaving}
                        className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-emerald-500/20 hover:bg-emerald-500/30 text-emerald-300 text-sm transition-colors disabled:opacity-50"
                      >
                        <Check className="w-4 h-4" />
                        {isSaving ? '保存中...' : '保存'}
                      </button>
                      <button
                        type="button"
                        onClick={() => {
                          setIsEditing(false);
                          setEditValue(userAnswer);
                        }}
                        className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-white/10 hover:bg-white/20 text-white/70 text-sm transition-colors"
                      >
                        <X className="w-4 h-4" />
                        取消
                      </button>
                    </div>
                  </div>
                ) : (
                  <div className="flex items-start gap-3">
                    <MessageContent content={userAnswer} className="flex-1 text-white/70 leading-relaxed text-xs" />
                    {onEdit && (
                      <button
                        type="button"
                        onClick={() => setIsEditing(true)}
                        className="flex-shrink-0 p-1.5 rounded-lg hover:bg-white/10 text-white/50 hover:text-white/80 transition-colors"
                        title="编辑回答"
                      >
                        <Edit3 className="w-4 h-4" />
                      </button>
                    )}
                  </div>
                )}
              </div>
            )}
          </div>

          {/* Actions */}
          <div className="answer-card__actions flex gap-3 pt-2">
            {onConfirm && (
              <button
                type="button"
                onClick={onConfirm}
                className="flex-1 flex items-center justify-center gap-2 px-4 py-3 rounded-xl bg-emerald-500 hover:bg-emerald-400 text-white font-medium transition-all transform hover:scale-[1.02] active:scale-[0.98]"
              >
                <CheckCircle2 className="w-5 h-5" />
                确认并继续
              </button>
            )}
            {onDiscussMore && (
              <button
                type="button"
                onClick={onDiscussMore}
                className={`flex items-center justify-center gap-2 px-4 py-3 rounded-xl border border-white/20 transition-colors ${
                  isCollapsed
                    ? 'bg-white/5 text-white/40 cursor-not-allowed'
                    : 'hover:bg-white/10 text-white/80'
                }`}
                disabled={isCollapsed}
              >
                <MessageCircle className="w-5 h-5" />
                继续讨论
              </button>
            )}
          </div>
        </div>
      </div>
    </animated.div>
  );
}
