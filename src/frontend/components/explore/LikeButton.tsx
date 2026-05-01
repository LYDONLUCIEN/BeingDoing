'use client';

import { useState, useCallback } from 'react';
import { Heart } from 'lucide-react';
import { toggleLike, type ToggleLikeParams } from '@/lib/api/analytics';
import { getApiErrorMessage } from '@/lib/api/client';

interface LikeButtonProps {
  /** 消息 ID（唯一标识，用于点赞去重） */
  messageId: string;
  /** 消息内容（点赞时快照留存） */
  content: string;
  /** 消息角色 */
  role?: 'user' | 'assistant';
  /** session_id */
  sessionId?: string;
  /** thread_id */
  threadId?: string;
  /** 探索阶段 */
  phase?: string;
  /** 激活码 */
  activationCode?: string;
  /** 尺寸 */
  size?: 'sm' | 'md';
  /** 外部控制初始状态（从后端批量查询获得） */
  initialLiked?: boolean;
  /** 紧凑模式：无文字标签 */
  compact?: boolean;
}

const SIZE_MAP = {
  sm: { icon: 14, gap: 'gap-1', text: 'text-xs' },
  md: { icon: 18, gap: 'gap-1.5', text: 'text-sm' },
};

export default function LikeButton({
  messageId,
  content,
  role = 'assistant',
  sessionId = '',
  threadId,
  phase,
  activationCode,
  size = 'sm',
  initialLiked = false,
  compact = false,
}: LikeButtonProps) {
  const [liked, setLiked] = useState(initialLiked);
  const [loading, setLoading] = useState(false);
  const { icon, gap, text } = SIZE_MAP[size];

  const handleToggle = useCallback(async () => {
    if (loading) return;
    setLoading(true);
    try {
      const params: ToggleLikeParams = {
        session_id: sessionId,
        thread_id: threadId,
        message_id: messageId,
        role,
        content_preview: content.slice(0, 500),
        content_snapshot: content,
        phase,
        activation_code: activationCode,
      };
      const res = await toggleLike(params);
      const newLiked = res.data?.liked ?? !liked;
      setLiked(newLiked);
    } catch (err) {
      console.warn('[LikeButton] toggle failed:', getApiErrorMessage(err));
    } finally {
      setLoading(false);
    }
  }, [loading, liked, sessionId, threadId, messageId, role, content, phase, activationCode]);

  return (
    <button
      type="button"
      onClick={handleToggle}
      disabled={loading}
      className={`
        inline-flex items-center ${gap} transition-all duration-200 select-none
        ${compact ? 'px-0' : 'px-2 py-1 rounded-lg'}
        ${liked
          ? 'text-rose-400 hover:text-rose-300'
          : 'text-white/30 hover:text-white/60 hover:bg-white/5'
        }
        ${loading ? 'opacity-50 cursor-wait' : 'cursor-pointer'}
      `}
      title={liked ? '取消点赞' : '点赞'}
      aria-label={liked ? '取消点赞' : '点赞'}
      aria-pressed={liked}
    >
      {/* 彩色填充爱心：点赞时 rose 渐变 + 微缩放动画 */}
      <Heart
        size={icon}
        className={`
          transition-all duration-200
          ${liked
            ? 'fill-rose-400 text-rose-400 scale-110'
            : 'fill-none'
          }
        `}
      />
      {!compact && (
        <span className={`${text} ${liked ? 'text-rose-400 font-medium' : ''}`}>
          {liked ? '已赞' : '点赞'}
        </span>
      )}
    </button>
  );
}
