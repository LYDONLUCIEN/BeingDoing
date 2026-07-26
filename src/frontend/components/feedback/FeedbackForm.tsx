'use client';

import { useRef, useState } from 'react';
import { Bug, Lightbulb, Loader2, Send } from 'lucide-react';
import { createFeedback, type FeedbackType } from '@/lib/api/feedback';
import { getApiErrorMessage } from '@/lib/api/client';
import { toDate } from '@/lib/utils/formatTime';
import AttachmentUploader, { type AttachmentUploaderHandle } from './AttachmentUploader';

/** 类型 → 承诺处理时限（工作日），与后端 FEEDBACK_DUE_WORKDAYS 保持一致 */
const TYPE_LABEL: Record<FeedbackType, string> = {
  bug: '问题反馈',
  idea: '意见建议',
};
const TYPE_WORKDAYS: Record<FeedbackType, number> = {
  bug: 3,
  idea: 5,
};

interface Props {
  onSubmitted?: () => void;
}

export default function FeedbackForm({ onSubmitted }: Props) {
  const [type, setType] = useState<FeedbackType | ''>('');
  const [content, setContent] = useState('');
  const [attachmentIds, setAttachmentIds] = useState<string[]>([]);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState('');
  const [successInfo, setSuccessInfo] = useState<{
    type: FeedbackType;
    dueAt: string | null;
  } | null>(null);
  const uploaderRef = useRef<AttachmentUploaderHandle>(null);

  // 粘贴截图：自动作为图片附件上传，显示在上方截图区
  const handlePaste = (e: React.ClipboardEvent<HTMLTextAreaElement>) => {
    const items = e.clipboardData?.items;
    if (!items) return;
    const files: File[] = [];
    for (const item of Array.from(items)) {
      if (item.kind === 'file' && item.type.startsWith('image/')) {
        const file = item.getAsFile();
        if (file) files.push(file);
      }
    }
    if (files.length > 0) {
      e.preventDefault();
      uploaderRef.current?.addFiles(files);
    }
  };

  const handleSubmit = async () => {
    setError('');

    if (!type) {
      setError('请选择反馈类型');
      return;
    }
    if (content.trim().length < 5) {
      setError('反馈内容至少 5 个字');
      return;
    }
    if (content.length > 2000) {
      setError('反馈内容不能超过 2000 字');
      return;
    }

    setSubmitting(true);
    try {
      const res = await createFeedback({
        type: type as FeedbackType,
        content: content.trim(),
        attachment_ids: attachmentIds,
      });
      setSuccessInfo({ type: type as FeedbackType, dueAt: res.due_at ?? null });
      // 重置
      setType('');
      setContent('');
      setAttachmentIds([]);
      // 5 秒后自动切回通知页，给用户足够时间看到成功提示
      setTimeout(() => {
        setSuccessInfo(null);
        onSubmitted?.();
      }, 5000);
    } catch (e) {
      setError(getApiErrorMessage(e, '提交失败，请稍后重试'));
    } finally {
      setSubmitting(false);
    }
  };

  if (successInfo) {
    const dueDate = toDate(successInfo.dueAt);
    return (
      <div className="h-full flex flex-col items-center justify-center px-6 text-center gap-3">
        <div className="w-14 h-14 rounded-full bg-bd-ui-accent/15 flex items-center justify-center">
          <Send className="w-6 h-6" style={{ color: 'var(--bd-ui-accent)' }} />
        </div>
        <div>
          <p className="text-sm font-semibold" style={{ color: 'var(--bd-fg)' }}>
            反馈已提交
          </p>
          <p className="text-xs mt-1" style={{ color: 'var(--bd-fg-muted)' }}>
            感谢您的反馈，我们将在 {TYPE_WORKDAYS[successInfo.type]} 个工作日内
            {dueDate && (
              <>（预计 {dueDate.getMonth() + 1} 月 {dueDate.getDate()} 日前）</>
            )}
            通过邮箱与您联系
          </p>
          <p className="text-[11px] mt-1" style={{ color: 'var(--bd-fg-muted)' }}>
            法定节假日可能略有延期，请留意您注册邮箱的邮件
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="h-full flex flex-col">
      <div className="flex-1 overflow-y-auto px-5 py-4 space-y-4">
        {/* 类型选择 */}
        <div>
          <label className="text-xs font-medium mb-2 block" style={{ color: 'var(--bd-fg)' }}>
            类型 <span style={{ color: 'var(--bd-error)' }}>*</span>
          </label>
          <div className="grid grid-cols-2 gap-2">
            <TypeButton
              active={type === 'bug'}
              onClick={() => setType('bug')}
              icon={<Bug className="w-4 h-4" />}
              label="问题反馈"
              accentColor="#ef4444"
            />
            <TypeButton
              active={type === 'idea'}
              onClick={() => setType('idea')}
              icon={<Lightbulb className="w-4 h-4" />}
              label="意见建议"
              accentColor="#f59e0b"
            />
          </div>
          {/* 选中类型后提示对应的承诺处理时限 */}
          {type && (
            <p className="text-[11px] mt-1.5" style={{ color: 'var(--bd-fg-muted)' }}>
              {TYPE_LABEL[type as FeedbackType]}承诺 {TYPE_WORKDAYS[type as FeedbackType]} 个工作日内通过邮箱回复（法定节假日可能略有延期）
            </p>
          )}
        </div>

        {/* 截图（置于内容上方：粘贴的截图会自动显示在这里） */}
        <div>
          <label className="text-xs font-medium mb-2 block" style={{ color: 'var(--bd-fg)' }}>
            截图（可选）
          </label>
          <AttachmentUploader
            ref={uploaderRef}
            attachmentIds={attachmentIds}
            onChange={setAttachmentIds}
          />
        </div>

        {/* 内容 */}
        <div>
          <label className="text-xs font-medium mb-2 block" style={{ color: 'var(--bd-fg)' }}>
            内容 <span style={{ color: 'var(--bd-error)' }}>*</span>
          </label>
          <textarea
            value={content}
            onChange={(e) => setContent(e.target.value)}
            onPaste={handlePaste}
            placeholder="请描述您遇到的问题或建议（5-2000 字），可直接 Ctrl+V 粘贴截图"
            rows={6}
            maxLength={2000}
            className="w-full text-sm px-3 py-2.5 rounded-xl border border-bd-border bg-bd-bg/60 resize-none focus:outline-none focus:ring-2 focus:ring-bd-ui-accent/40"
            style={{ color: 'var(--bd-fg)' }}
          />
          <div className="flex justify-end mt-1">
            <span className="text-[10px] text-bd-subtle">{content.length}/2000</span>
          </div>
        </div>

        {/* 错误 */}
        {error && (
          <p className="text-xs px-3 py-2 rounded-lg bg-red-50 text-red-700">{error}</p>
        )}
      </div>

      {/* 提交 */}
      <div className="px-5 py-3 border-t border-bd-border">
        <button
          onClick={handleSubmit}
          disabled={submitting}
          className="w-full py-2.5 rounded-xl text-sm font-medium text-white disabled:opacity-50 flex items-center justify-center gap-2 transition-transform active:scale-[0.98]"
          style={{
            background:
              'linear-gradient(145deg, var(--bd-ui-accent), var(--bd-primary))',
          }}
        >
          {submitting ? (
            <>
              <Loader2 className="w-4 h-4 animate-spin" />
              提交中…
            </>
          ) : (
            <>
              <Send className="w-4 h-4" />
              提交反馈
            </>
          )}
        </button>
      </div>
    </div>
  );
}

function TypeButton({
  active,
  onClick,
  icon,
  label,
  accentColor,
}: {
  active: boolean;
  onClick: () => void;
  icon: React.ReactNode;
  label: string;
  accentColor: string;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="flex items-center gap-2 px-3 py-2.5 rounded-xl border-2 text-sm font-medium transition-all"
      style={{
        borderColor: active ? accentColor : 'var(--bd-border)',
        background: active ? `${accentColor}10` : 'transparent',
        color: active ? accentColor : 'var(--bd-fg-muted)',
      }}
    >
      {icon}
      {label}
    </button>
  );
}
