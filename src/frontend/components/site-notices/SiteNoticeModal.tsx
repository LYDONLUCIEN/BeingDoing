'use client';

import { useEffect } from 'react';
import { X, MessageCircle, BookOpen, ExternalLink } from 'lucide-react';
import type { SiteNoticeChannel, SiteNoticeItem } from '@/lib/api/siteNotices';

interface Props {
  notice: SiteNoticeItem | null;
  onClose: () => void;
}

/** 渠道入口渲染 */
function ChannelRow({ ch }: { ch: SiteNoticeChannel }) {
  const label = ch.label ?? defaultLabel(ch.type);
  // 图片型：微信群二维码
  if (ch.type === 'wechat' && ch.qr_url) {
    return (
      <div className="flex flex-col items-center gap-2 p-3 rounded-lg bg-bd-surface-2">
        <img
          src={ch.qr_url}
          alt={label}
          className="w-32 h-32 object-contain rounded-md bg-white"
        />
        <span className="text-xs text-bd-muted flex items-center gap-1">
          <MessageCircle className="w-3 h-3" />
          {label}
        </span>
      </div>
    );
  }
  // 链接型：博客 / 小红书 / 其他
  const href = ch.url;
  if (!href) return null;
  const Icon = ch.type === 'blog' ? BookOpen : ExternalLink;
  return (
    <a
      href={href}
      target="_blank"
      rel="noopener noreferrer"
      className="flex items-center gap-2 px-3 py-2 rounded-lg bg-bd-surface-2 hover:bg-bd-surface-3 transition text-sm"
    >
      <Icon className="w-4 h-4" />
      <span>{label}</span>
      <ExternalLink className="w-3 h-3 ml-auto opacity-50" />
    </a>
  );
}

function defaultLabel(type: string): string {
  switch (type) {
    case 'wechat':
      return '微信群';
    case 'blog':
      return '博客';
    case 'xiaohongshu':
      return '小红书';
    default:
      return '了解详情';
  }
}

export default function SiteNoticeModal({ notice, onClose }: Props) {
  useEffect(() => {
    if (!notice) return;
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && onClose();
    window.addEventListener('keydown', onKey);
    document.body.style.overflow = 'hidden';
    return () => {
      window.removeEventListener('keydown', onKey);
      document.body.style.overflow = '';
    };
  }, [notice, onClose]);

  if (!notice) return null;
  const channels = notice.channels ?? [];

  return (
    <div
      className="fixed inset-0 z-[100] flex items-center justify-center bg-black/40 backdrop-blur-sm p-4"
      onClick={onClose}
      role="dialog"
      aria-modal="true"
    >
      <div
        className="bg-bd-surface rounded-xl shadow-xl max-w-lg w-full max-h-[85vh] overflow-y-auto"
        onClick={(e) => e.stopPropagation()}
      >
        {/* 头部 */}
        <div className="flex items-center justify-between p-5 border-b border-bd-border">
          <h2 className="text-lg font-semibold text-bd-text">{notice.title}</h2>
          <button
            onClick={onClose}
            className="text-bd-muted hover:text-bd-text transition p-1 rounded"
            aria-label="关闭"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* 正文 */}
        {notice.content_md && (
          <div className="p-5 text-sm text-bd-text whitespace-pre-wrap leading-relaxed">
            {notice.content_md}
          </div>
        )}

        {/* 渠道入口 */}
        {channels.length > 0 && (
          <div className="p-5 border-t border-bd-border">
            <p className="text-xs text-bd-muted mb-3">如需联系或了解更多：</p>
            <div className="flex flex-wrap gap-3">
              {channels.map((ch, i) => (
                <ChannelRow key={i} ch={ch} />
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
