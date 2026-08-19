'use client';

/**
 * 报告复核申请弹窗（2026-08-18，tasks/report-review-plan.md）
 *
 * - 分类必选：内容有问题（content_issue）/ 下载或打开失败（download_issue）
 * - 描述选填
 * - content_issue → 建复核单，管理员人工复核、必要时重新生成（期间报告不锁定）
 * - download_issue → 直接转故障反馈（与右侧「反馈 bug」同流程同结果）
 */

import { useState } from 'react';
import { X, Loader2, CheckCircle2 } from 'lucide-react';
import {
  submitReportRecheck,
  type RecheckCategory,
  type RecheckSubmitResult,
} from '@/lib/api/report';

interface ReportRecheckModalProps {
  open: boolean;
  onClose: () => void;
  reportId: string;
  activationCode: string;
  /** 提交成功回调（recheck 路径时父组件可刷新复核状态） */
  onSubmitted: (result: RecheckSubmitResult) => void;
}

const CATEGORY_OPTIONS: Array<{ value: RecheckCategory; label: string; hint: string }> = [
  {
    value: 'content_issue',
    label: '报告内容有问题',
    hint: '内容与你的情况不符、表述不准确等，由管理员人工复核，必要时重新生成',
  },
  {
    value: 'download_issue',
    label: '下载或打开失败',
    hint: '按故障处理，与页面右侧「反馈 bug」同一流程',
  },
];

export default function ReportRecheckModal({
  open,
  onClose,
  reportId,
  activationCode,
  onSubmitted,
}: ReportRecheckModalProps) {
  const [category, setCategory] = useState<RecheckCategory>('content_issue');
  const [description, setDescription] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<RecheckSubmitResult | null>(null);

  if (!open) return null;

  const handleClose = () => {
    if (submitting) return;
    setResult(null);
    setError(null);
    onClose();
  };

  const handleSubmit = async () => {
    setSubmitting(true);
    setError(null);
    try {
      const res = await submitReportRecheck(reportId, {
        activationCode,
        category,
        description: description.trim(),
      });
      setResult(res);
      onSubmitted(res);
    } catch (e: any) {
      setError(e?.response?.data?.detail || e?.message || '提交失败，请稍后重试');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div
      className="fixed inset-0 z-[120] bg-black/40 backdrop-blur-[1px] flex items-center justify-center p-4"
      onClick={handleClose}
    >
      <div
        className="w-full max-w-md rounded-2xl bg-bd-card border border-bd-border shadow-2xl p-6 space-y-5"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between">
          <h2 className="text-base font-semibold text-bd-fg">申请报告复核</h2>
          <button
            type="button"
            onClick={handleClose}
            className="p-1 rounded-lg text-bd-subtle hover:bg-bd-overlay-md transition-colors"
            aria-label="关闭"
          >
            <X size={16} />
          </button>
        </div>

        {result ? (
          <div className="space-y-4 text-center py-2">
            <CheckCircle2 size={36} className="mx-auto text-emerald-500" />
            {result.path === 'recheck' ? (
              <p className="text-sm text-bd-muted leading-relaxed">
                复核申请已提交。管理员将人工复核你的报告，必要时重新生成；
                期间你仍可正常查看和下载当前报告，复核完成后会通知你。
              </p>
            ) : (
              <p className="text-sm text-bd-muted leading-relaxed">
                已提交故障反馈，我们会按「反馈 bug」流程尽快处理，请留意站内信与邮箱。
              </p>
            )}
            <button
              type="button"
              onClick={handleClose}
              className="inline-flex items-center gap-2 rounded-xl bg-[var(--bd-ui-accent)] text-bd-ui-accent-fg px-6 py-2.5 text-sm font-medium hover:opacity-90 transition-opacity"
            >
              知道了
            </button>
          </div>
        ) : (
          <>
            <div className="space-y-2">
              {CATEGORY_OPTIONS.map((opt) => (
                <label
                  key={opt.value}
                  className={`flex items-start gap-3 rounded-xl border px-4 py-3 cursor-pointer transition-colors ${
                    category === opt.value
                      ? 'border-[var(--bd-ui-accent)] bg-bd-overlay-md'
                      : 'border-bd-border hover:bg-bd-overlay-md'
                  }`}
                >
                  <input
                    type="radio"
                    name="recheck-category"
                    value={opt.value}
                    checked={category === opt.value}
                    onChange={() => setCategory(opt.value)}
                    className="mt-1"
                  />
                  <span>
                    <span className="block text-sm font-medium text-bd-fg">{opt.label}</span>
                    <span className="block text-xs text-bd-subtle mt-0.5">{opt.hint}</span>
                  </span>
                </label>
              ))}
            </div>

            <div className="space-y-1.5">
              <label className="text-xs text-bd-subtle" htmlFor="recheck-desc">
                具体描述（选填）
              </label>
              <textarea
                id="recheck-desc"
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                maxLength={2000}
                rows={4}
                placeholder={
                  category === 'content_issue'
                    ? '例如：报告中的职业方向与我的实际情况不符…'
                    : '例如：点击下载后浏览器提示文件损坏…'
                }
                className="w-full rounded-xl border border-bd-border bg-bd-overlay px-3 py-2 text-sm text-bd-fg placeholder:text-bd-ghost focus:outline-none focus:border-[var(--bd-ui-accent)]"
              />
            </div>

            {error && <p className="text-xs text-red-500">{error}</p>}

            <div className="flex justify-end gap-2">
              <button
                type="button"
                onClick={handleClose}
                disabled={submitting}
                className="rounded-xl border border-bd-border px-4 py-2.5 text-sm text-bd-muted hover:bg-bd-overlay-md transition-colors disabled:opacity-60"
              >
                取消
              </button>
              <button
                type="button"
                onClick={handleSubmit}
                disabled={submitting}
                className="inline-flex items-center gap-2 rounded-xl bg-[var(--bd-ui-accent)] text-bd-ui-accent-fg px-5 py-2.5 text-sm font-medium hover:opacity-90 transition-opacity disabled:opacity-60"
              >
                {submitting && <Loader2 size={14} className="animate-spin" />}
                提交
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
