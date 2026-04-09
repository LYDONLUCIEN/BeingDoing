'use client';

import { useEffect, useMemo, useState } from 'react';
import { ChevronLeft, ChevronRight } from 'lucide-react';
import {
  ruminationApi,
  type RuminationMainSection,
  type RuminationProgress,
} from '@/lib/api/rumination';
import { useLocale } from '@/hooks/useLocale';
import { isRuminationFilterStepReachable } from '@/lib/explore/ruminationProgressNav';

const SECTION_ORDER: RuminationMainSection[] = [
  'opening',
  'review',
  'filter',
  'final_choice',
  'recommend',
  'end',
];

/** 各主阶段在总进度条中占的权重（合计 100，避免一进入筛选就跳到 ~35%） */
const SECTION_SPAN: Record<RuminationMainSection, number> = {
  opening: 10,
  review: 14,
  filter: 46,
  final_choice: 12,
  recommend: 10,
  end: 8,
};

const FILTER_STEP_CAP = 7;

/**
 * 已有 submitted 快照的筛选子步数量（1..7 各计一次，不要求连续，与后端快照一致）。
 */
function countFilterSubmittedSteps(progress: RuminationProgress): number {
  const snaps = progress.filter_step_snapshots ?? {};
  let n = 0;
  for (let k = 1; k <= FILTER_STEP_CAP; k++) {
    const ent = snaps[String(k)];
    if (ent != null && ent.submitted != null) n++;
  }
  return n;
}

/**
 * 筛选表界面刻度（0..8）→ 映射到进度条填充比例的分母：
 * - 0：尚未有任何子步提交快照
 * - 1..7：已有 submitted 的子步个数
 * - 8：已进入 final_choice / recommend / end
 */
export function computeRuminationFilterMilestone11(progress: RuminationProgress): number {
  const ms = progress.main_section;
  if (ms === 'final_choice' || ms === 'recommend' || ms === 'end') return 8;
  return Math.min(8, countFilterSubmittedSteps(progress));
}

/**
 * 筛选表进度展示刻度（0..10）：与「上一阶段/下一阶段」联动——
 * 取「已提交子步数」与「当前查看子步」的较小值，回退查看时进度条随之回落。
 */
export function computeDisplayedRuminationMilestone(
  progress: RuminationProgress,
  viewFilterStep?: number | null
): number {
  const ms = progress.main_section;
  if (ms === 'final_choice' || ms === 'recommend' || ms === 'end') return 8;
  const submitted = countFilterSubmittedSteps(progress);
  const fs = progress.filter_step ?? 0;
  /** 短链可能未在每子步写入 submitted；服务端已到第 7 子步时，进度条至少按 7 档计，避免重置再走满仍显示约 50% */
  const effectiveSubmitted =
    fs >= FILTER_STEP_CAP ? Math.max(submitted, FILTER_STEP_CAP) : submitted;
  if (viewFilterStep == null || viewFilterStep < 1) return Math.min(8, effectiveSubmitted);
  const v = Math.min(FILTER_STEP_CAP, Math.max(1, viewFilterStep));
  return Math.min(effectiveSubmitted, v);
}

/** 当前阶段内部完成比例 0–1（与后端 main_section / review_sub_index / filter_step 对齐） */
function withinCurrentSection(
  progress: RuminationProgress,
  viewFilterStep?: number | null
): number {
  switch (progress.main_section) {
    case 'opening':
      return 0.12;
    case 'review': {
      const ri = Math.max(0, Math.min(3, progress.review_sub_index));
      return (ri + 1) / 4;
    }
    case 'filter': {
      return Math.min(1, computeDisplayedRuminationMilestone(progress, viewFilterStep) / 8);
    }
    case 'final_choice':
      return 1;
    case 'recommend':
      return 0.55;
    case 'end':
      return 1;
    default:
      return 0.06;
  }
}

/**
 * 整体完成度 0–100。
 * 在筛选表界面（含 final_choice 回看表）：进度刻度 0..8（7 个子步提交 + 进入最终选择档），详情文案为「筛选 n/7」——
 * 0% 空白/未提交 → 每多一个子步 submitted +1 档 → 8 档为进入最终选择及之后；满档为 100%。
 * 详情文案仍显示「筛选 n/7」。
 */
export function computeRuminationJourneyPercent(
  progress: RuminationProgress,
  viewFilterStep?: number | null
): number {
  const useViewForFilterBar =
    viewFilterStep != null &&
    viewFilterStep >= 1 &&
    (progress.main_section === 'filter' || progress.main_section === 'final_choice');

  if (useViewForFilterBar) {
    const m = computeDisplayedRuminationMilestone(progress, viewFilterStep);
    return Math.min(100, Math.max(0, (m / 8) * 100));
  }

  const idx = SECTION_ORDER.indexOf(progress.main_section);
  const safeIdx = idx < 0 ? 0 : idx;
  let base = 0;
  for (let i = 0; i < safeIdx; i++) {
    base += SECTION_SPAN[SECTION_ORDER[i]];
  }
  const span = SECTION_SPAN[progress.main_section] ?? SECTION_SPAN.opening;
  const w = withinCurrentSection(progress, viewFilterStep);
  const pct = base + w * span;
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
  /** 第 1 子步不展示「上一阶段」 */
  hidePrev?: boolean;
  /** 第 7 子步不展示「下一阶段」 */
  hideNext?: boolean;
  /**
   * 进度条拆成 7 段可点：跳到对应筛选子步（与 furthest 对齐，不可达段禁用）。
   */
  segmentJump?: {
    jumpDisabled?: boolean;
    onJump: (step: number) => void;
  };
}

interface RuminationSectionProgressProps {
  activationCode: string;
  className?: string;
  /** 递增则重新拉取进度（如表格提交成功后） */
  refreshNonce?: number;
  variant?: 'default' | 'beautiful';
  /** 筛选子步（filter_step 1–7）上一阶段 / 下一阶段 */
  filterStepNav?: RuminationFilterStepNavConfig;
  /**
   * 与对话页同源进度（getTable / submit 后立即更新），避免仅依赖本组件轮询时百分比滞后。
   * 有值时优先用于百分比与文案。
   */
  serverProgress?: RuminationProgress | null;
  /**
   * 为 true 时不发起 rumination-progress GET，仅用父组件传入的 serverProgress。
   * 对话页父级已统一拉取，避免同屏重复请求（含 refreshNonce 触发的二次拉取）。
   */
  externalProgressOnly?: boolean;
  /** 筛选段用户正在查看的子步 1–7，与上一阶段/下一阶段联动，驱动进度条与「筛选 n/7」文案 */
  viewFilterStep?: number | null;
}

export default function RuminationSectionProgress({
  activationCode,
  className = '',
  refreshNonce = 0,
  variant = 'default',
  filterStepNav,
  serverProgress = null,
  externalProgressOnly = false,
  viewFilterStep = null,
}: RuminationSectionProgressProps) {
  const { t } = useLocale();
  const [progress, setProgress] = useState<RuminationProgress | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!activationCode || externalProgressOnly) return;
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
  }, [activationCode, refreshNonce, externalProgressOnly]);

  const displayProgress = serverProgress ?? progress;

  const fillPercent = useMemo(
    () =>
      displayProgress
        ? computeRuminationJourneyPercent(displayProgress, viewFilterStep)
        : 0,
    [displayProgress, viewFilterStep]
  );

  const currentIdx = displayProgress
    ? SECTION_ORDER.indexOf(displayProgress.main_section)
    : -1;
  const safeCurrentIdx = currentIdx < 0 ? 0 : currentIdx;

  const inFilter =
    displayProgress?.main_section === 'filter' && (displayProgress.filter_step ?? 0) > 0;

  /** 与进度条一致：正在查看某筛选子步时展示「筛选 n/7」（含 final_choice 回看表） */
  const showFilterSubstepCaption =
    viewFilterStep != null &&
    viewFilterStep >= 1 &&
    (inFilter || displayProgress?.main_section === 'final_choice');

  const detailLine = useMemo(() => {
    if (!displayProgress) return '';
    const sectionKey = `explore.chat.ruminationProgress.sections.${displayProgress.main_section}`;
    const sectionLabel = t(sectionKey);
    if (showFilterSubstepCaption && viewFilterStep != null) {
      const extra = t('explore.chat.ruminationProgress.filterDetail', {
        step: String(viewFilterStep),
      });
      return `${sectionLabel} ${extra}`;
    }
    return sectionLabel;
  }, [displayProgress, showFilterSubstepCaption, t, viewFilterStep]);

  if (!activationCode) return null;

  const barGradient =
    variant === 'beautiful' ? BAR_GRADIENT_BEAUTIFUL : BAR_GRADIENT_DEFAULT;
  const showSegments = variant !== 'beautiful';

  const showProgressSkeleton = externalProgressOnly
    ? serverProgress == null
    : loading && !serverProgress;

  if (showProgressSkeleton) {
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

  if (!displayProgress) return null;

  if (variant === 'beautiful') {
    const navBtnClass =
      'shrink-0 inline-flex items-center gap-0.5 rounded-full border border-neutral-200/50 bg-white/35 px-2 py-1 text-[10px] font-medium tracking-wide text-neutral-600 shadow-none backdrop-blur-md transition-[color,background-color,border-color,opacity] duration-200 hover:border-neutral-300/70 hover:bg-white/65 hover:text-neutral-900 disabled:cursor-not-allowed disabled:opacity-35 sm:gap-1 sm:px-2.5 sm:py-1 sm:text-[11px]';
    const segJump = filterStepNav?.segmentJump;
    const trackH = segJump ? 'h-3' : 'h-2';
    const barBlock = (
      <div className="min-w-0 flex-1 space-y-2">
        <div className="flex items-center justify-between gap-3 text-sm font-medium text-neutral-600">
          <span>{t('explore.chat.ruminationProgress.barLabel')}</span>
          <span className="tabular-nums text-neutral-500">{Math.round(fillPercent)}%</span>
        </div>
        <div
          className="relative w-full"
          role={segJump ? 'group' : 'progressbar'}
          aria-valuemin={segJump ? undefined : 0}
          aria-valuemax={segJump ? undefined : 100}
          aria-valuenow={segJump ? undefined : Math.round(fillPercent)}
          aria-label={
            segJump
              ? t('explore.chat.ruminationProgress.filterStepSegmentsGroup')
              : `${detailLine} ${Math.round(fillPercent)}%`
          }
        >
          <div
            className={`relative ${trackH} w-full overflow-hidden rounded-[10px] bg-white/80 shadow-[inset_0_1px_2px_rgba(0,0,0,0.04)]`}
          >
            {!segJump ? (
              <div
                className="h-full rounded-[10px] transition-[width] duration-500 ease-out"
                style={{
                  width: `${fillPercent}%`,
                  backgroundImage: barGradient,
                  boxShadow: '0 0 14px rgba(124, 131, 253, 0.35)',
                }}
              />
            ) : (
              <>
                <div
                  className="pointer-events-none absolute inset-y-0 left-0 z-0 rounded-[10px] transition-[width] duration-500 ease-out"
                  style={{
                    width: `${fillPercent}%`,
                    backgroundImage: barGradient,
                    boxShadow: '0 0 14px rgba(124, 131, 253, 0.35)',
                  }}
                  aria-hidden
                />
                <div
                  className="absolute inset-0 z-[1] flex items-stretch"
                  role="presentation"
                >
                  {Array.from({ length: FILTER_STEP_CAP }, (_, i) => {
                    const step = i + 1;
                    const vf = viewFilterStep ?? 0;
                    const reachable = isRuminationFilterStepReachable(step, displayProgress);
                    const current = vf === step;
                    const disabled = Boolean(segJump.jumpDisabled) || !reachable;
                    return (
                      <button
                        key={step}
                        type="button"
                        disabled={disabled}
                        title={t('explore.chat.ruminationProgress.jumpToFilterStep', {
                          step: String(step),
                        })}
                        aria-label={t('explore.chat.ruminationProgress.jumpToFilterStep', {
                          step: String(step),
                        })}
                        aria-current={current ? 'step' : undefined}
                        className={`rumination-filter-seg relative min-w-0 flex-1 border-l border-white/45 first:border-l-0 first:rounded-l-[10px] last:rounded-r-[10px] transition-[background-color,box-shadow] duration-200 ease-out ${
                          current
                            ? 'bg-white/[0.22] shadow-[inset_0_0_0_1px_rgba(255,255,255,0.55)]'
                            : ''
                        } ${
                          !disabled
                            ? 'cursor-pointer hover:bg-white/14 active:bg-white/20 focus:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-violet-400/50'
                            : ''
                        } disabled:cursor-not-allowed disabled:opacity-30`}
                        onClick={() => segJump.onJump(step)}
                      />
                    );
                  })}
                </div>
              </>
            )}
          </div>
        </div>
        <p className="text-center text-xs text-neutral-500">{detailLine}</p>
      </div>
    );

    if (filterStepNav) {
      const effHidePrev =
        filterStepNav.hidePrev === true ||
        (viewFilterStep != null && viewFilterStep <= 1);
      const effHideNext =
        filterStepNav.hideNext === true ||
        (viewFilterStep != null && viewFilterStep >= FILTER_STEP_CAP);
      return (
        <div className={`mx-auto flex w-full max-w-4xl items-center gap-2 sm:gap-3 ${className}`}>
          {!effHidePrev ? (
            <button
              type="button"
              className={navBtnClass}
              onClick={filterStepNav.onPrev}
              disabled={filterStepNav.prevDisabled}
              aria-label={t('explore.chat.ruminationUi.navPrev')}
            >
              <ChevronLeft className="h-3.5 w-3.5 shrink-0 opacity-80" strokeWidth={2.25} aria-hidden />
              <span className="max-[380px]:sr-only">{t('explore.chat.ruminationUi.navPrev')}</span>
            </button>
          ) : (
            <span className="hidden w-8 shrink-0 sm:block sm:w-14" aria-hidden />
          )}
          {barBlock}
          {!effHideNext ? (
            <button
              type="button"
              className={navBtnClass}
              onClick={filterStepNav.onNext}
              disabled={filterStepNav.nextDisabled}
              aria-label={t('explore.chat.ruminationUi.navNext')}
            >
              <span className="max-[380px]:sr-only">{t('explore.chat.ruminationUi.navNext')}</span>
              <ChevronRight className="h-3.5 w-3.5 shrink-0 opacity-80" strokeWidth={2.25} aria-hidden />
            </button>
          ) : (
            <span className="hidden w-8 shrink-0 sm:block sm:w-14" aria-hidden />
          )}
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
