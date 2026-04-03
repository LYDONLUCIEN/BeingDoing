'use client';

import { useEffect, useMemo, useState } from 'react';
import {
  ruminationApi,
  type RuminationMainSection,
  type RuminationProgress,
} from '@/lib/api/rumination';
import { useLocale } from '@/hooks/useLocale';

const SECTION_ORDER: RuminationMainSection[] = [
  'opening',
  'review',
  'filter',
  'final_choice',
  'recommend',
  'end',
];

/** 与后端 MAIN_SECTIONS、filter_step(0–9)、review_sub_index(0–3) 对齐的整体完成度 0–100 */
export function computeRuminationJourneyPercent(progress: RuminationProgress): number {
  const idx = SECTION_ORDER.indexOf(progress.main_section);
  const safeIdx = idx < 0 ? 0 : idx;
  let within = 0;

  switch (progress.main_section) {
    case 'opening':
      within = 0.38;
      break;
    case 'review': {
      const ri = Math.max(0, Math.min(3, progress.review_sub_index));
      within = (ri + 1) / 4;
      break;
    }
    case 'filter': {
      const fs = progress.filter_step;
      if (fs <= 0) within = 0.08;
      else within = Math.min(1, fs / 9);
      break;
    }
    case 'final_choice':
      within = 0.82;
      break;
    case 'recommend':
      within = 0.9;
      break;
    case 'end':
      within = 1;
      break;
    default:
      within = 0.15;
  }

  const pct = ((safeIdx + within) / SECTION_ORDER.length) * 100;
  return Math.min(100, Math.max(0, pct));
}

const BAR_GRADIENT_DEFAULT =
  'linear-gradient(90deg, #1d4ed8 0%, #2563eb 18%, #6366f1 38%, #9333ea 58%, #ea580c 78%, #dc2626 100%)';

/** 对齐 uidesign/beautiful/rumination.html */
const BAR_GRADIENT_BEAUTIFUL = 'linear-gradient(90deg, #7c83fd 0%, #f06292 100%)';

export interface RuminationFilterStepNavConfig {
  onPrev: () => void;
  onNext: () => void;
  prevDisabled: boolean;
  nextDisabled: boolean;
}

interface RuminationSectionProgressProps {
  activationCode: string;
  className?: string;
  /** 递增则重新拉取进度（如表格提交成功后） */
  refreshNonce?: number;
  variant?: 'default' | 'beautiful';
  /** 筛选子步（filter_step 1–9）上一阶段 / 下一阶段 */
  filterStepNav?: RuminationFilterStepNavConfig;
}

export default function RuminationSectionProgress({
  activationCode,
  className = '',
  refreshNonce = 0,
  variant = 'default',
  filterStepNav,
}: RuminationSectionProgressProps) {
  const { t } = useLocale();
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
      .catch(() => {
        if (!cancelled) setProgress(null);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [activationCode, refreshNonce]);

  const fillPercent = useMemo(
    () => (progress ? computeRuminationJourneyPercent(progress) : 0),
    [progress]
  );

  const currentIdx = progress ? SECTION_ORDER.indexOf(progress.main_section) : -1;
  const safeCurrentIdx = currentIdx < 0 ? 0 : currentIdx;

  const inFilter = progress?.main_section === 'filter' && (progress.filter_step ?? 0) > 0;
  const cursor = progress?.filter_row_cursor ?? 0;
  const totalRows =
    inFilter && Array.isArray(progress?.filter_table) ? progress.filter_table.length : 0;

  const detailLine = useMemo(() => {
    if (!progress) return '';
    const sectionKey = `explore.chat.ruminationProgress.sections.${progress.main_section}`;
    const sectionLabel = t(sectionKey);
    let extra = '';
    if (inFilter) {
      extra += t('explore.chat.ruminationProgress.filterDetail', {
        step: String(progress.filter_step),
      });
      if (totalRows > 0) {
        extra += t('explore.chat.ruminationProgress.rowDetail', {
          current: String(Math.min(cursor + 1, totalRows)),
          total: String(totalRows),
        });
      }
    }
    return extra ? `${sectionLabel} ${extra}` : sectionLabel;
  }, [progress, inFilter, cursor, totalRows, t]);

  if (!activationCode) return null;

  const barGradient =
    variant === 'beautiful' ? BAR_GRADIENT_BEAUTIFUL : BAR_GRADIENT_DEFAULT;
  const showSegments = variant !== 'beautiful';

  if (loading) {
    return (
      <div
        className={`w-full space-y-2 ${className}`}
        aria-busy="true"
        aria-label={t('explore.chat.ruminationProgress.loading')}
      >
        <div className="h-3 w-28 rounded bg-neutral-200/90 animate-pulse" />
        <div
          className={`h-2.5 w-full rounded-full bg-neutral-200/90 animate-pulse ${
            variant === 'beautiful' ? 'max-w-3xl mx-auto' : 'max-w-4xl'
          }`}
        />
        {showSegments && (
          <div className="flex gap-0.5">
            {SECTION_ORDER.map((k) => (
              <div key={k} className="flex-1 h-3 rounded bg-neutral-100 animate-pulse" />
            ))}
          </div>
        )}
      </div>
    );
  }

  if (!progress) return null;

  if (variant === 'beautiful') {
    const navBtnClass =
      'shrink-0 rounded-full border border-neutral-200/90 bg-white/70 px-3 py-2 text-xs font-semibold text-neutral-800 shadow-sm transition-all hover:bg-white disabled:cursor-not-allowed disabled:opacity-40 sm:px-4 sm:text-sm';
    const barBlock = (
      <div className="min-w-0 flex-1 space-y-2">
        <div className="flex items-center justify-between gap-3 text-sm font-medium text-neutral-600">
          <span>{t('explore.chat.ruminationProgress.barLabel')}</span>
          <span className="tabular-nums text-neutral-500">{Math.round(fillPercent)}%</span>
        </div>
        <div
          className="relative w-full"
          role="progressbar"
          aria-valuemin={0}
          aria-valuemax={100}
          aria-valuenow={Math.round(fillPercent)}
          aria-label={`${detailLine} ${Math.round(fillPercent)}%`}
        >
          <div className="relative h-2 w-full overflow-hidden rounded-[10px] bg-white/80 shadow-[inset_0_1px_2px_rgba(0,0,0,0.04)]">
            <div
              className="h-full rounded-[10px] transition-[width] duration-500 ease-out"
              style={{
                width: `${fillPercent}%`,
                backgroundImage: barGradient,
                boxShadow: '0 0 14px rgba(124, 131, 253, 0.35)',
              }}
            />
          </div>
        </div>
        <p className="text-center text-xs text-neutral-500">{detailLine}</p>
      </div>
    );

    if (filterStepNav) {
      return (
        <div className={`mx-auto flex w-full max-w-4xl items-stretch gap-3 sm:gap-5 ${className}`}>
          <button
            type="button"
            className={navBtnClass}
            onClick={filterStepNav.onPrev}
            disabled={filterStepNav.prevDisabled}
          >
            ← {t('explore.chat.ruminationUi.navPrev')}
          </button>
          {barBlock}
          <button
            type="button"
            className={navBtnClass}
            onClick={filterStepNav.onNext}
            disabled={filterStepNav.nextDisabled}
          >
            {t('explore.chat.ruminationUi.navNext')} →
          </button>
        </div>
      );
    }

    return <div className={`mx-auto w-full max-w-3xl ${className}`}>{barBlock}</div>;
  }

  return (
    <div className={`w-full max-w-4xl space-y-2 ${className}`}>
      <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
        <span className="text-xs font-medium text-neutral-600">
          {t('explore.chat.ruminationProgress.caption')}
        </span>
        <span className="text-xs text-neutral-500 tabular-nums">{detailLine}</span>
      </div>

      <div
        className="relative w-full"
        role="progressbar"
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={Math.round(fillPercent)}
        aria-label={detailLine}
      >
        <div className="relative h-2.5 w-full overflow-hidden rounded-full bg-neutral-200/90 shadow-[inset_0_1px_2px_rgba(0,0,0,0.06)]">
          <div
            className="h-full rounded-full transition-[width] duration-500 ease-out"
            style={{
              width: `${fillPercent}%`,
              backgroundImage: barGradient,
              boxShadow: '0 0 12px rgba(37, 99, 235, 0.25)',
            }}
          />
          <div
            className="pointer-events-none absolute inset-0 flex"
            aria-hidden
          >
            {SECTION_ORDER.map((_, i) => (
              <div
                key={i}
                className="flex-1 border-r border-white/35 last:border-r-0"
              />
            ))}
          </div>
        </div>
      </div>

      <div className="flex gap-0.5">
        {SECTION_ORDER.map((key, i) => {
          const label = t(`explore.chat.ruminationProgress.sections.${key}`);
          const done = i < safeCurrentIdx;
          const active = i === safeCurrentIdx;
          return (
            <div key={key} className="min-w-0 flex-1 text-center leading-tight">
              <span
                className={`block truncate text-[10px] sm:text-xs ${
                  done
                    ? 'text-blue-800/85'
                    : active
                      ? 'font-semibold text-neutral-900'
                      : 'text-neutral-400'
                }`}
                title={label}
              >
                {label}
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
}
