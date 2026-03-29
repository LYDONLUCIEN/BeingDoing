'use client';

import { useEffect, useState } from 'react';
import { ruminationApi, type RuminationProgress } from '@/lib/api/rumination';

const SECTION_LABELS: Record<string, string> = {
  opening: '开场',
  review: '回顾',
  filter: '筛选',
  final_choice: '最终选择',
  recommend: '推荐',
  end: '结束',
};

interface RuminationSectionProgressProps {
  activationCode: string;
  className?: string;
}

export default function RuminationSectionProgress({
  activationCode,
  className = '',
}: RuminationSectionProgressProps) {
  const [progress, setProgress] = useState<RuminationProgress | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!activationCode) return;
    let cancelled = false;
    setLoading(true);
    ruminationApi
      .get(activationCode)
      .then((res) => {
        if (!cancelled && res?.data?.progress) {
          setProgress(res.data.progress);
        }
      })
      .catch(() => {})
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [activationCode]);

  if (loading || !progress) return null;

  const sectionOrder = ['opening', 'review', 'filter', 'final_choice', 'recommend', 'end'];
  const currentIdx = sectionOrder.indexOf(progress.main_section);
  const inFilter = progress.main_section === 'filter' && progress.filter_step > 0;
  const cursor = progress.filter_row_cursor ?? 0;
  const totalHint =
    inFilter && Array.isArray(progress.filter_table)
      ? progress.filter_table.length
      : 0;

  return (
    <div className={`flex items-center gap-2 text-xs text-neutral-500 ${className}`}>
      <span className="font-medium text-neutral-600">当前进度：</span>
      <span>
        {SECTION_LABELS[progress.main_section] || progress.main_section}
        {inFilter &&
          ` (步骤 ${progress.filter_step}/9${totalHint > 0 ? ` · 行 ${Math.min(cursor + 1, totalHint)}/${totalHint}` : ''})`}
      </span>
      <div className="flex-1 max-w-[120px] h-1 rounded-full bg-neutral-200 overflow-hidden">
        <div
          className="h-full rounded-full bg-violet-400 transition-all duration-300"
          style={{ width: `${((currentIdx + 1) / sectionOrder.length) * 100}%` }}
        />
      </div>
    </div>
  );
}
