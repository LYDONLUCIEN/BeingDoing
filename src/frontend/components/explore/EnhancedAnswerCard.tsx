'use client';

import { useState } from 'react';
import { useSpring, animated, config } from '@react-spring/web';
import { CheckCircle2, MessageCircle, Edit3, X, Check } from 'lucide-react';

interface EnhancedAnswerCardProps {
  questionContent: string;
  userAnswer: string;
  onConfirm: () => void;
  onDiscussMore: () => void;
  onEdit?: (newAnswer: string) => Promise<void>;
}

export default function EnhancedAnswerCard({
  questionContent,
  userAnswer,
  onConfirm,
  onDiscussMore,
  onEdit,
}: EnhancedAnswerCardProps) {
  const [isEditing, setIsEditing] = useState(false);
  const [editValue, setEditValue] = useState(userAnswer);
  const [isSaving, setIsSaving] = useState(false);

  // 入场动画
  const cardSpring = useSpring({
    from: { opacity: 0, transform: 'scale(0.9) translateY(20px)' },
    to: { opacity: 1, transform: 'scale(1) translateY(0px)' },
    config: config.gentle,
  });

  // 3D卡片效果
  const [cardProps, setCardProps] = useState({ rotateX: 0, rotateY: 0 });

  const handleMouseMove = (e: React.MouseEvent<HTMLDivElement>) => {
    const card = e.currentTarget;
    const rect = card.getBoundingClientRect();
    const x = e.clientX - rect.left;
    const y = e.clientY - rect.top;
    const centerX = rect.width / 2;
    const centerY = rect.height / 2;
    const rotateX = ((y - centerY) / centerY) * -5;
    const rotateY = ((x - centerX) / centerX) * 5;
    setCardProps({ rotateX, rotateY });
  };

  const handleMouseLeave = () => {
    setCardProps({ rotateX: 0, rotateY: 0 });
  };

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

  return (
    <animated.div style={cardSpring} className="my-4">
      <div
        onMouseMove={handleMouseMove}
        onMouseLeave={handleMouseLeave}
        style={{
          transform: `perspective(1000px) rotateX(${cardProps.rotateX}deg) rotateY(${cardProps.rotateY}deg)`,
          transition: 'transform 0.1s ease-out',
        }}
        className="relative rounded-2xl bg-gradient-to-br from-emerald-500/20 via-emerald-500/10 to-transparent border border-emerald-500/30 shadow-2xl overflow-hidden"
      >
        {/* 背景装饰 */}
        <div className="absolute inset-0 bg-gradient-to-br from-white/5 to-transparent pointer-events-none" />
        <div className="absolute top-0 right-0 w-32 h-32 bg-emerald-400/10 rounded-full blur-3xl pointer-events-none" />

        <div className="relative p-6 space-y-4">
          {/* Header */}
          <div className="flex items-start gap-3">
            <div className="p-2 rounded-lg bg-emerald-500/20">
              <CheckCircle2 className="w-5 h-5 text-emerald-400" />
            </div>
            <div className="flex-1">
              <h3 className="font-semibold text-emerald-300 mb-1">回答总结</h3>
              <p className="text-sm text-white/60">{questionContent}</p>
            </div>
          </div>

          {/* Answer Content */}
          <div className="bg-white/5 rounded-xl p-4 backdrop-blur-sm">
            {isEditing ? (
              <div className="space-y-3">
                <textarea
                  value={editValue}
                  onChange={(e) => setEditValue(e.target.value)}
                  className="w-full min-h-[100px] px-3 py-2 rounded-lg bg-slate-800/80 border border-white/20 text-white placeholder-white/40 focus:outline-none focus:ring-2 focus:ring-emerald-500/50 resize-none"
                  placeholder="编辑你的回答..."
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
                <p className="flex-1 text-white/90 leading-relaxed">{userAnswer}</p>
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

          {/* Actions */}
          <div className="flex gap-3 pt-2">
            <button
              type="button"
              onClick={onConfirm}
              className="flex-1 flex items-center justify-center gap-2 px-4 py-3 rounded-xl bg-emerald-500 hover:bg-emerald-400 text-white font-medium transition-all transform hover:scale-[1.02] active:scale-[0.98]"
            >
              <CheckCircle2 className="w-5 h-5" />
              确认并继续
            </button>
            <button
              type="button"
              onClick={onDiscussMore}
              className="flex items-center justify-center gap-2 px-4 py-3 rounded-xl border border-white/20 hover:bg-white/10 text-white/80 transition-colors"
            >
              <MessageCircle className="w-5 h-5" />
              继续讨论
            </button>
          </div>
        </div>
      </div>
    </animated.div>
  );
}
