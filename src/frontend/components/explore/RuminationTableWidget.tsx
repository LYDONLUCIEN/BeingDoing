'use client';

import {
  useState,
  useCallback,
  useEffect,
  useLayoutEffect,
  useRef,
  useMemo,
  type ChangeEvent,
  type MouseEvent,
} from 'react';
import { createPortal } from 'react-dom';
import { Loader2, RefreshCw } from 'lucide-react';
import {
  HYP_CONFIRM_KEY,
  OTHER_SELECT_VALUE,
  LEGACY_VALUE_MAP,
  normalizeRuminationValue,
} from '@/lib/explore/ruminationConstants';

export { HYP_CONFIRM_KEY, OTHER_SELECT_VALUE, LEGACY_VALUE_MAP, normalizeRuminationValue };

export interface RuminationTableColumn {
  key: string;
  label: string;
  /** 下拉选项；无则使用文本输入 */
  options?: string[];
}

export interface RuminationTablePayload {
  columns: RuminationTableColumn[];
  rows: Record<string, unknown>[];
  editableCols: string[];
  /** 可选：引导语 */
  guideText?: string;
  /** 可选：步骤标识 */
  step?: number;
  singleRowMode?: boolean;
  rowCursor?: number;
  totalRows?: number;
  rowSelectionMode?: 'multi';
  rowSelectionMin?: number;
  rowSelectionMax?: number;
  /** 价值观关键词来源标签（step 4 专用：confirmed_card / report_anchor / prior_text / none） */
  valuesSource?: string;
}

interface RuminationTableWidgetProps {
  payload: RuminationTablePayload;
  onConfirm: (rows: Record<string, unknown>[]) => void;
  disabled?: boolean;
  className?: string;
  /** glass：毛玻璃左栏内嵌，表头 Confirm 使用黑色圆角按钮 */
  uiVariant?: 'default' | 'glass';
  /** glass 时卡片标题（由页面传入 i18n 文案） */
  cardTitle?: string;
  /** 主按钮文案（i18n） */
  confirmLabel?: string;
  refillLabel?: string;
  /** true：主按钮变为「重新填写」，点击走 onRefill（恢复该步 initial 表） */
  tableRefillMode?: boolean;
  onRefill?: () => void;
  /** true：本步已提交过快照时禁用「确认」，需先「重新填写」才可再次提交 */
  confirmDisabledAfterCommit?: boolean;
  /** 闸门中：按钮置灰但可点击触发引导动画/提示，不直接提交 */
  confirmSoftBlocked?: boolean;
  /** 软阻断态点击时，父层可触发提示（例如抖动） */
  onConfirmSoftBlocked?: () => void;
  /** 递增 tick 触发强调动画 */
  confirmSoftBlockedPulseTick?: number;
  selectPlaceholder?: string;
  inputPlaceholder?: string;
  /** 提交表格时遮罩文案（仅 embeddedSubmitOverlay 为 true 时使用） */
  loadingLabel?: string;
  submitting?: boolean;
  /** 为 true 时在表格外壳内显示提交遮罩；默认 false（由页面全屏遮罩承担） */
  embeddedSubmitOverlay?: boolean;
  /** 选中行摘要，用于输入框上下文 */
  onRowContextChange?: (ctx: { rowIndex: number; label: string } | null) => void;
  /** 假设确认列：「无」文案 */
  hypothesisPendingLabel?: string;
  /** 假设确认列：「自定义」文案（替代旧「其他」） */
  hypothesisOtherLabel?: string;
  /** 选「自定义」后出现的输入框占位 */
  otherTextPlaceholder?: string;
  /** 为 true 时隐藏表头「确认」按钮（如终步改由对话/结论卡确认） */
  hideConfirmButton?: boolean;
  /** true：回看模式（只读），所有单元格不可编辑，隐藏确认/重填按钮 */
  reviewReadOnly?: boolean;
  /** 假设列：假设1 侧色块标签（个人事业向） */
  hypothesisTagFreelanceLabel?: string;
  /** 假设列：假设2 侧色块标签（职业路径向） */
  hypothesisTagCompanyLabel?: string;
  /** 假设列：第三条等额外假设的标签 */
  hypothesisTagExtraLabel?: string;
  /** 子步 3：重新生成本行两条推荐假设（+ 自定义 / 无由下拉选择） */
  hypothesisRegenerateLabel?: string;
  hypothesisRegeneratingLabel?: string;
  /** 右上角重新生成图标的悬停说明 */
  hypothesisRegenerateHint?: string;
  /** 悬停假设下拉时浮层标题（i18n） */
  hypothesisPreviewTitle?: string;
  /** 原生 title，提示可悬停查看全文 */
  hypothesisPreviewHint?: string;
  hypothesisRegeneratingRowIndex?: number | null;
  /** 第三参为当前表格内存快照（含未点「确认」的编辑），供重新生成单行时与其它行合并 */
  onHypothesisRegenerate?: (
    rowIndex: number,
    rowId: string,
    currentTableRows: Record<string, unknown>[]
  ) => void | Promise<void>;
}

export default function RuminationTableWidget({
  payload,
  onConfirm,
  disabled = false,
  className = '',
  uiVariant = 'default',
  cardTitle,
  confirmLabel = '确认',
  refillLabel = '重新填写',
  tableRefillMode = false,
  onRefill,
  confirmDisabledAfterCommit = false,
  confirmSoftBlocked = false,
  onConfirmSoftBlocked,
  confirmSoftBlockedPulseTick = 0,
  selectPlaceholder = '请选择',
  inputPlaceholder = '填写',
  loadingLabel = '…',
  submitting = false,
  onRowContextChange,
  hypothesisPendingLabel = '无',
  hypothesisOtherLabel = '自定义',
  otherTextPlaceholder = '请填写自定义内容…',
  hideConfirmButton = false,
  reviewReadOnly = false,
  hypothesisTagFreelanceLabel = '个人事业',
  hypothesisTagCompanyLabel = '职业路径',
  hypothesisTagExtraLabel = '',
  hypothesisRegenerateLabel = '重新生成',
  hypothesisRegeneratingLabel = '生成中…',
  hypothesisRegenerateHint = '重新生成本行的假设选项',
  hypothesisPreviewTitle = '两条推荐假设',
  hypothesisPreviewHint,
  hypothesisRegeneratingRowIndex = null,
  onHypothesisRegenerate,
  embeddedSubmitOverlay = false,
}: RuminationTableWidgetProps) {
  const [rows, setRows] = useState<Record<string, unknown>[]>(
    () => JSON.parse(JSON.stringify(payload.rows)) || []
  );
  /** glass：当前高亮行；null 表示未选中（再点同一行可取消） */
  const [selectedRowIdx, setSelectedRowIdx] = useState<number | null>(null);
  /** 校验动画：与单元格 class 绑定，动画结束后清空 */
  const [validationFlashKey, setValidationFlashKey] = useState<string | null>(null);
  const [validationCycle, setValidationCycle] = useState(0);
  const [hypOtherDraftByKey, setHypOtherDraftByKey] = useState<Record<string, string>>({});
  const cellWrapRefs = useRef<Map<string, HTMLDivElement | null>>(new Map());
  /** 已确认本步 / 回看模式：锁定格内与选行 */
  const cellDisabled = disabled || confirmDisabledAfterCommit || reviewReadOnly;

  const tableRowRefs = useRef<Map<number, HTMLTableRowElement | null>>(new Map());
  const [hypRegenOverlayW, setHypRegenOverlayW] = useState(0);

  const [hypothesisPreview, setHypothesisPreview] = useState<{
    anchorRect: DOMRect;
    h1: string;
    h2: string;
  } | null>(null);
  const hypothesisPreviewCloseTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const tableScrollContainerRef = useRef<HTMLDivElement | null>(null);

  const cancelHypothesisPreviewClose = useCallback(() => {
    if (hypothesisPreviewCloseTimer.current) {
      clearTimeout(hypothesisPreviewCloseTimer.current);
      hypothesisPreviewCloseTimer.current = null;
    }
  }, []);

  const scheduleHypothesisPreviewClose = useCallback(() => {
    if (hypothesisPreviewCloseTimer.current) {
      clearTimeout(hypothesisPreviewCloseTimer.current);
    }
    hypothesisPreviewCloseTimer.current = setTimeout(() => {
      setHypothesisPreview(null);
      hypothesisPreviewCloseTimer.current = null;
    }, 200);
  }, []);

  const openHypothesisPreview = useCallback(
    (anchor: HTMLElement, h1s: string, h2s: string) => {
      if (!h1s.trim() && !h2s.trim()) return;
      cancelHypothesisPreviewClose();
      setHypothesisPreview({
        anchorRect: anchor.getBoundingClientRect(),
        h1: h1s,
        h2: h2s,
      });
    },
    [cancelHypothesisPreviewClose]
  );

  /*
   * Close tooltip on page-level interactions, but **not** when the user is
   * scrolling *inside* the tooltip itself.
   *
   * - pointerdown on anything outside the tooltip → close.
   * - wheel outside the tooltip → close.
   * - wheel inside the tooltip → let it scroll naturally (do nothing).
   */
  useEffect(() => {
    if (!hypothesisPreview || typeof document === 'undefined') return;
    const close = () => setHypothesisPreview(null);

    const onPointerDown = (e: Event) => {
      const tooltipEl = document.querySelector('[role="tooltip"]');
      if (!tooltipEl || !tooltipEl.contains(e.target as Node)) {
        close();
      }
    };

    const onWheel = (e: WheelEvent) => {
      const tooltipEl = document.querySelector('[role="tooltip"]');
      if (!tooltipEl || !tooltipEl.contains(e.target as Node)) {
        close();
      }
    };

    const onResize = () => close();

    document.addEventListener('pointerdown', onPointerDown, true);
    document.addEventListener('wheel', onWheel, true);
    window.addEventListener('resize', onResize);
    return () => {
      document.removeEventListener('pointerdown', onPointerDown, true);
      document.removeEventListener('wheel', onWheel, true);
      window.removeEventListener('resize', onResize);
    };
  }, [hypothesisPreview]);

  useEffect(
    () => () => {
      if (hypothesisPreviewCloseTimer.current) {
        clearTimeout(hypothesisPreviewCloseTimer.current);
      }
    },
    []
  );

  const setTableRowRef = useCallback((idx: number) => (el: HTMLTableRowElement | null) => {
    if (el) tableRowRefs.current.set(idx, el);
    else tableRowRefs.current.delete(idx);
  }, []);

  useLayoutEffect(() => {
    if (hypothesisRegeneratingRowIndex == null) {
      setHypRegenOverlayW(0);
      return;
    }
    const measure = () => {
      const tr = tableRowRefs.current.get(hypothesisRegeneratingRowIndex);
      if (tr) setHypRegenOverlayW(tr.getBoundingClientRect().width);
    };
    measure();
    const id = requestAnimationFrame(() => measure());
    return () => cancelAnimationFrame(id);
  }, [hypothesisRegeneratingRowIndex, rows, payload.step]);

  const rowsPayloadSig = JSON.stringify(payload.rows ?? []);
  useEffect(() => {
    try {
      setRows(JSON.parse(rowsPayloadSig) || []);
    } catch {
      setRows([]);
    }
  }, [rowsPayloadSig]);

  // 仅随子步、游标、行数变化重置选中；默认不选中任何行（单行模式仍跟 rowCursor）
  useEffect(() => {
    const n = (payload.rows ?? []).length;
    if (n <= 0) {
      setSelectedRowIdx(null);
      return;
    }
    if (payload.singleRowMode) {
      const c = payload.rowCursor ?? 0;
      setSelectedRowIdx(Math.min(Math.max(0, c), n - 1));
      return;
    }
    setSelectedRowIdx(null);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- 故意不依赖 payload.rows 全文
  }, [
    payload.step,
    payload.rowCursor,
    payload.totalRows,
    payload.rows?.length,
    payload.singleRowMode,
  ]);

  const setCellWrapRef = useCallback((rowIdx: number, colKey: string) => {
    const key = `${rowIdx}:${colKey}`;
    return (el: HTMLDivElement | null) => {
      if (el) cellWrapRefs.current.set(key, el);
      else cellWrapRefs.current.delete(key);
    };
  }, []);

  const handleGlassRowActivate = useCallback(
    (rowIdx: number) => {
      if (cellDisabled) return;
      setSelectedRowIdx((prev) => (prev === rowIdx ? null : rowIdx));
    },
    [cellDisabled]
  );

  useEffect(() => {
    if (!confirmDisabledAfterCommit) return;
    setSelectedRowIdx(null);
  }, [confirmDisabledAfterCommit]);

  useEffect(() => {
    if (!onRowContextChange) return;
    if (selectedRowIdx == null || selectedRowIdx < 0) {
      onRowContextChange(null);
      return;
    }
    const row = rows[selectedRowIdx];
    if (!row || !payload.columns?.length) {
      onRowContextChange(null);
      return;
    }
    const bits = payload.columns
      .slice(0, 3)
      .map((c) => String(row[c.key] ?? '').trim())
      .filter(Boolean);
    const label = bits.join(' · ') || `${selectedRowIdx + 1}`;
    onRowContextChange({ rowIndex: selectedRowIdx, label });
  }, [selectedRowIdx, rows, payload.columns, onRowContextChange]);

  const editableSet = new Set(payload.editableCols || []);
  const filterStep = payload.step ?? 0;
  const rowSelectionMulti = payload.rowSelectionMode === 'multi';
  const selMin = payload.rowSelectionMin ?? 1;
  const selMax = payload.rowSelectionMax ?? 3;

  /** 需要从展示中隐藏的列 key（与后端 P-06 对齐：移除匹配原因列） */
  const HIDDEN_COL_KEYS = useMemo(() => new Set(['匹配原因']), []);

  const displayColumns = useMemo(() => {
    const cols = payload.columns ?? [];
    return cols.filter((c) => {
      if (c.key === '__pick') return false; // __pick 是行选择内部状态，不作为展示列
      if (HIDDEN_COL_KEYS.has(c.key)) return false;
      return true;
    });
  }, [payload.columns, HIDDEN_COL_KEYS]);

  const handleRowPickToggle = useCallback(
    (rowIdx: number) => {
      if (cellDisabled) return;
      const cap = payload.rowSelectionMax ?? 3;
      setRows((prev) => {
        const row = prev[rowIdx];
        if (!row) return prev;
        const isOn = row.__pick === true;
        const currently = prev.filter((r) => r.__pick === true).length;
        if (!isOn && currently >= cap) {
          setValidationCycle((c) => c + 1);
          setValidationFlashKey(`${rowIdx}:__pick`);
          return prev;
        }
        const next = [...prev];
        next[rowIdx] = { ...row, __pick: !isOn };
        return next;
      });
      setSelectedRowIdx(rowIdx);
    },
    [cellDisabled, payload.rowSelectionMax]
  );

  /** 数据列超过该宽度时由单元格内换行，避免整表被单格撑得过宽 */
  const DATA_COL_MAX_PX = 272;
  /** 假设确认列（子步 3）放宽上限：左侧窄下拉 ~132px + 右侧约 15 字文本 ~210px + 间距 */
  const HYP_COL_MAX_PX = 380;

  const colMinWidth = (col: RuminationTableColumn) => {
    if (col.key === '__pick') return 52;
    if (col.key === 'id') return 40;
    const labelLen = col.label?.length ?? 0;
    /** 子步 3：左窄下拉 + 右侧长文案；上限放宽以支持 ~15 字再换行 */
    if (col.key === HYP_CONFIRM_KEY && filterStep === 3) {
      return Math.min(HYP_COL_MAX_PX, Math.max(160, 8 + labelLen * 9));
    }
    return Math.min(DATA_COL_MAX_PX, Math.max(76, 8 + labelLen * 11));
  };

  const colMaxWidth = (col: RuminationTableColumn): number | undefined => {
    if (col.key === 'id' || col.key === '__pick') return undefined;
    if (col.key === HYP_CONFIRM_KEY && filterStep === 3) return HYP_COL_MAX_PX;
    return DATA_COL_MAX_PX;
  };

  const handleCellChange = useCallback((rowIdx: number, colKey: string, value: unknown) => {
    if (cellDisabled) return;
    setRows((prev) => {
      const next = [...prev];
      if (rowIdx < 0 || rowIdx >= next.length) return prev;
      next[rowIdx] = { ...next[rowIdx], [colKey]: value };
      return next;
    });
  }, [cellDisabled]);

  const normalizeOptionText = useCallback((s: unknown) => {
    return String(s)
      .replace(/[\u200B-\u200D\uFEFF]/g, '')
      .replace(/\s+/g, ' ')
      .trim();
  }, []);

  const isPlaceholderToken = useCallback(
    (s: string) => {
      const t = normalizeOptionText(s);
      if (!t) return true;
      const ph = normalizeOptionText(selectPlaceholder);
      if (t === ph || t.toLowerCase() === ph.toLowerCase()) return true;
      if (/^请\s*选\s*择$/.test(t) || /^請\s*選\s*擇$/.test(t)) return true;
      if (['请选择', '请選擇', '請選擇', '选择', '選擇'].includes(t)) return true;
      const lower = t.toLowerCase();
      if (
        [
          'select',
          'choose',
          'please select',
          'please choose',
          '--',
          '—',
          '-',
          'placeholder',
        ].includes(lower)
      ) {
        return true;
      }
      return false;
    },
    [normalizeOptionText, selectPlaceholder]
  );

  /** 占位文案不得作为真实选项（含后端误下发的「请选择」及空白项） */
  const optionsWithoutPlaceholder = useCallback(
    (opts: string[]) =>
      (opts ?? []).filter((o) => {
        const n = normalizeOptionText(o);
        return n.length > 0 && !isPlaceholderToken(n);
      }),
    [isPlaceholderToken, normalizeOptionText]
  );

  const findFirstInvalidCell = useCallback((): { rowIdx: number; colKey: string } | null => {
    const cols = payload.columns || [];
    for (let rowIdx = 0; rowIdx < rows.length; rowIdx++) {
      const row = rows[rowIdx];
      for (const col of cols) {
        if (!editableSet.has(col.key)) continue;
        const raw = row[col.key];
        const strVal = raw != null ? String(raw).trim() : '';

        if (col.key === HYP_CONFIRM_KEY && filterStep === 3) {
          continue;
        }

        if (col.options?.includes(hypothesisOtherLabel) || col.options?.includes('其他')) {
          if (!strVal || isPlaceholderToken(strVal)) return { rowIdx, colKey: col.key };
          if (strVal === OTHER_SELECT_VALUE) return { rowIdx, colKey: col.key };
          continue;
        }

        if (col.options?.length) {
          if (!strVal || isPlaceholderToken(strVal)) return { rowIdx, colKey: col.key };
          continue;
        }

        if (!strVal || isPlaceholderToken(strVal)) return { rowIdx, colKey: col.key };
      }
    }
    if (rowSelectionMulti) {
      const n = rows.filter((r) => r.__pick === true).length;
      if (n < selMin || n > selMax) {
        return { rowIdx: 0, colKey: '__pick' };
      }
    }
    return null;
  }, [
    rows,
    payload.columns,
    editableSet,
    filterStep,
    hypothesisOtherLabel,
    isPlaceholderToken,
    rowSelectionMulti,
    selMin,
    selMax,
  ]);

  const handleConfirm = useCallback(() => {
    if (cellDisabled) return;
    setValidationFlashKey(null);
    const bad = findFirstInvalidCell();
    if (bad) {
      const key = `${bad.rowIdx}:${bad.colKey}`;
      setValidationCycle((c) => c + 1);
      setValidationFlashKey(key);
      requestAnimationFrame(() => {
        cellWrapRefs.current.get(key)?.scrollIntoView({
          behavior: 'smooth',
          block: 'center',
          inline: 'nearest',
        });
      });
      return;
    }
    const sanitized = rows.map((row) => {
      const next = { ...row };
      for (const k of Object.keys(next)) {
        if (next[k] === OTHER_SELECT_VALUE) next[k] = '';
      }
      return next;
    });
    onConfirm(sanitized);
  }, [rows, onConfirm, findFirstInvalidCell, cellDisabled]);

  if (!payload.columns?.length) return null;

  const isGlass = uiVariant === 'glass';

  const confirmBtnCls = isGlass
    ? `bd-btn-black shrink-0 rounded-full px-4 py-2 text-sm font-medium text-white transition-all disabled:opacity-40 disabled:cursor-not-allowed ${
        confirmSoftBlocked ? 'opacity-45 cursor-not-allowed' : ''
      } ${confirmSoftBlocked ? 'rumination-neg-confirm-soft-blocked' : ''}`
    : 'rounded-lg bg-violet-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-violet-700 disabled:cursor-not-allowed disabled:opacity-50';

  const refillBtnCls = isGlass
    ? 'shrink-0 rounded-full border border-neutral-200 bg-white/70 px-4 py-2 text-sm font-medium text-neutral-600 transition-all hover:bg-white disabled:opacity-40 disabled:cursor-not-allowed'
    : 'rounded-lg border border-neutral-300 bg-white px-4 py-2 text-sm font-medium text-neutral-600 transition-colors hover:bg-neutral-50 disabled:cursor-not-allowed disabled:opacity-50';

  /** 回看模式但仍可重新填写：仅显示重填按钮 */
  const tableHeaderActions =
    (hideConfirmButton && !(tableRefillMode && onRefill))
      ? null
      : (reviewReadOnly && !(tableRefillMode && onRefill))
        ? null
        : (
          <div className="flex items-center gap-3">
            {tableRefillMode && onRefill && (
              <button type="button" onClick={() => onRefill?.()} disabled={disabled} className={refillBtnCls}>
                {refillLabel}
              </button>
            )}
        {!hideConfirmButton && (
          <button
            type="button"
            onClick={() => {
              if (confirmSoftBlocked) {
                onConfirmSoftBlocked?.();
                return;
              }
              handleConfirm();
            }}
            disabled={cellDisabled}
            data-soft-pulse={confirmSoftBlocked ? String(confirmSoftBlockedPulseTick) : undefined}
            aria-disabled={confirmSoftBlocked || undefined}
            className={confirmBtnCls}
          >
            {confirmLabel}
          </button>
        )}
      </div>
    );

  const selectArrowSvg =
    'url("data:image/svg+xml,%3Csvg xmlns=%22http://www.w3.org/2000/svg%22 width=%2220%22 height=%2220%22 viewBox=%220 0 24 24%22 fill=%22none%22 stroke=%22%236b7280%22 stroke-width=%222%22%3E%3Cpolyline points=%226 9 12 15 18 9%22/%3E%3C/svg%3E")';

  const selectShellClass = isGlass
    ? 'rumination-glass-select w-full min-w-[120px] appearance-none px-2 py-1.5 pr-8 text-sm border border-neutral-200/90 rounded-lg bg-white/80 focus:ring-2 focus:ring-[rgba(145,194,255,0.55)] focus:border-[#91C2FF]/80'
    : 'w-full min-w-[120px] px-2 py-1 text-sm border border-neutral-200 rounded-md bg-white focus:ring-2 focus:ring-sky-300/50 focus:border-sky-400/70';

  const selectArrowStyle = isGlass
    ? {
        backgroundImage: selectArrowSvg,
        backgroundRepeat: 'no-repeat' as const,
        backgroundPosition: 'right 0.45rem center',
        backgroundSize: '14px',
      }
    : undefined;

  const textareaShellClass = isGlass
    ? 'w-full min-h-[2.75rem] min-w-[100px] resize-y px-2 py-1.5 text-sm leading-snug border border-neutral-200/90 rounded-lg bg-white/80 focus:ring-2 focus:ring-[rgba(145,194,255,0.55)] break-words whitespace-pre-wrap'
    : 'w-full min-w-[100px] px-2 py-1 text-sm border border-neutral-200 rounded-md focus:ring-2 focus:ring-sky-300/50 focus:border-sky-400/70';

  const tagLabels = {
    freelance: hypothesisTagFreelanceLabel,
    company: hypothesisTagCompanyLabel,
    extra: hypothesisTagExtraLabel,
  } as const;

  const renderHypothesisConfirmCell = (row: Record<string, unknown>, rowIdx: number, strVal: string) => {
    const h1 = String(row['假设1'] ?? '').trim();
    const h2 = String(row['假设2'] ?? '').trim();
    const h3 = String(row['假设3'] ?? '').trim();
    const pendingOk =
      hypothesisPendingLabel && !isPlaceholderToken(hypothesisPendingLabel);

    type HypPick = 'h1' | 'h2' | 'h3' | 'pending' | 'other' | '';
    let active: HypPick = '';
    if (strVal === OTHER_SELECT_VALUE) active = 'other';
    else if (!strVal) active = '';
    else if (
      pendingOk &&
      (strVal === hypothesisPendingLabel || strVal === '待定' || strVal === '暂未选定')
    )
      active = 'pending';
    else if (h1 && strVal === h1) active = 'h1';
    else if (h2 && strVal === h2) active = 'h2';
    else if (h3 && strVal === h3) active = 'h3';
    else active = 'other';

    const draftKey = `h${filterStep}-${rowIdx}`;
    const storedDraft = hypOtherDraftByKey[draftKey] ?? '';
    const otherInputValue =
      active === 'other'
        ? strVal === OTHER_SELECT_VALUE
          ? storedDraft
          : strVal
        : storedDraft;

    const OPT_H1 = '__rum_hyp_h1__';
    const OPT_H2 = '__rum_hyp_h2__';
    const OPT_H3 = '__rum_hyp_h3__';
    const OPT_OTHER = '__rum_hyp_other__';
    const OPT_PENDING = '__rum_hyp_pending__';

    const selectControlValue =
      active === ''
        ? ''
        : active === 'h1'
          ? OPT_H1
          : active === 'h2'
            ? OPT_H2
            : active === 'h3'
              ? OPT_H3
              : active === 'pending'
                ? OPT_PENDING
                : OPT_OTHER;

    const h3TagLabel = String(tagLabels.extra ?? '').trim() || '备选方向';
    const showRegen = Boolean(onHypothesisRegenerate && filterStep === 3);

    const persistOtherDraftFromCell = () => {
      if (active !== 'other') return;
      if (strVal && strVal !== OTHER_SELECT_VALUE) {
        setHypOtherDraftByKey((p) => ({ ...p, [draftKey]: strVal }));
      } else if (storedDraft.trim()) {
        setHypOtherDraftByKey((p) => ({ ...p, [draftKey]: storedDraft }));
      }
    };

    const onHypSelectChange = (e: ChangeEvent<HTMLSelectElement>) => {
      const v = e.target.value;
      if (active === 'other' && v !== OPT_OTHER) persistOtherDraftFromCell();
      if (v === '') {
        handleCellChange(rowIdx, HYP_CONFIRM_KEY, '');
        return;
      }
      if (v === OPT_H1 && h1) {
        handleCellChange(rowIdx, HYP_CONFIRM_KEY, h1);
        return;
      }
      if (v === OPT_H2 && h2) {
        handleCellChange(rowIdx, HYP_CONFIRM_KEY, h2);
        return;
      }
      if (v === OPT_H3) {
        if (h3) handleCellChange(rowIdx, HYP_CONFIRM_KEY, h3);
        return;
      }
      if (v === OPT_PENDING && pendingOk) {
        handleCellChange(rowIdx, HYP_CONFIRM_KEY, hypothesisPendingLabel);
        return;
      }
      if (v === OPT_OTHER) {
        // 从三条假设/待定切到「自定义」时，不得把当前选项的完整文案当成自定义内容
        const wasOtherCustom =
          Boolean(strVal && strVal !== OTHER_SELECT_VALUE) &&
          !(
            (pendingOk &&
              (strVal === hypothesisPendingLabel ||
                strVal === '待定' ||
                strVal === '暂未选定')) ||
            (h1 && strVal === h1) ||
            (h2 && strVal === h2) ||
            (h3 && strVal === h3)
          );
        const fromCell = wasOtherCustom ? strVal : '';
        const d = (fromCell || hypOtherDraftByKey[draftKey] || '').trim();
        if (d) handleCellChange(rowIdx, HYP_CONFIRM_KEY, d);
        else handleCellChange(rowIdx, HYP_CONFIRM_KEY, OTHER_SELECT_VALUE);
        return;
      }
    };

    const otherTextInputCls = isGlass
      ? 'min-w-0 w-full rounded-lg border border-neutral-200/90 bg-white/90 px-2.5 py-1.5 text-sm leading-snug text-neutral-800 placeholder:text-neutral-400 focus:border-[#91C2FF] focus:outline-none focus:ring-2 focus:ring-[rgba(145,194,255,0.4)]'
      : 'min-w-0 w-full rounded-lg border border-neutral-200 bg-white px-2.5 py-1.5 text-sm leading-snug focus:border-sky-400 focus:outline-none focus:ring-2 focus:ring-sky-300/50';

    /** 子步 3：左侧窄下拉（覆盖 selectShellClass 的 w-full） */
    const hypSelectNarrowClass = isGlass
      ? `${selectShellClass} !w-[7rem] sm:!w-[8.25rem] !min-w-0 shrink-0`
      : `${selectShellClass} !w-[7rem] sm:!w-[8.25rem] !min-w-0 shrink-0`;

    const hypRightTextCls =
      'text-sm leading-snug text-neutral-800 break-words [overflow-wrap:anywhere] min-w-0';

    const regenBtn = showRegen ? (
      <div
        className="flex shrink-0 flex-col justify-center self-stretch border-l border-neutral-200/75 pl-2 pr-0.5"
        onMouseDown={(e) => isGlass && e.stopPropagation()}
        onClick={(e) => isGlass && e.stopPropagation()}
      >
        <button
          type="button"
          title={hypothesisRegenerateHint}
          aria-label={hypothesisRegenerateHint}
          disabled={cellDisabled || hypothesisRegeneratingRowIndex === rowIdx}
          className="shrink-0 border-0 bg-transparent p-1 text-blue-950 opacity-90 transition-opacity hover:opacity-100 disabled:cursor-not-allowed disabled:opacity-35"
          onMouseDown={(e) => isGlass && e.stopPropagation()}
          onClick={(e) => {
            if (isGlass) e.stopPropagation();
            const rid = String(row.id ?? rowIdx);
            void onHypothesisRegenerate?.(rowIdx, rid, rows);
          }}
        >
          <RefreshCw className="h-4 w-4" strokeWidth={2.25} aria-hidden />
        </button>
      </div>
    ) : null;

    const rightSlot =
      active === 'h1' ? (
        <p className={`${hypRightTextCls} m-0`}>{h1}</p>
      ) : active === 'h2' ? (
        <p className={`${hypRightTextCls} m-0`}>{h2}</p>
      ) : active === 'h3' ? (
        <p className={`${hypRightTextCls} m-0`}>{h3}</p>
      ) : active === 'other' ? (
        <input
          type="text"
          value={otherInputValue}
          disabled={cellDisabled}
          placeholder={otherTextPlaceholder}
          onMouseDown={(e) => isGlass && e.stopPropagation()}
          onClick={(e) => isGlass && e.stopPropagation()}
          onChange={(e) => {
            const v = e.target.value;
            setHypOtherDraftByKey((p) => ({ ...p, [draftKey]: v }));
            if (v === '') handleCellChange(rowIdx, HYP_CONFIRM_KEY, OTHER_SELECT_VALUE);
            else handleCellChange(rowIdx, HYP_CONFIRM_KEY, v);
          }}
          className={otherTextInputCls}
        />
      ) : null;

    return (
      <div className="flex min-w-0 flex-row items-center gap-2 pb-1 pl-0.5 pr-1 pt-0.5">
        <div
          className="relative shrink-0"
          title={hypothesisPreviewHint || undefined}
          onMouseEnter={(e) => {
            if (cellDisabled) return;
            openHypothesisPreview(e.currentTarget, h1, h2);
          }}
          onMouseLeave={scheduleHypothesisPreviewClose}
        >
          <select
            value={selectControlValue}
            disabled={cellDisabled}
            onMouseDown={(e) => e.stopPropagation()}
            onClick={(e) => e.stopPropagation()}
            onChange={onHypSelectChange}
            className={hypSelectNarrowClass}
            style={selectArrowStyle}
          >
            <option value="" disabled className="text-neutral-400">{selectPlaceholder}</option>
            {h1 ? <option value={OPT_H1}>{tagLabels.freelance}</option> : null}
            {h2 ? <option value={OPT_H2}>{tagLabels.company}</option> : null}
            {h3 ? <option value={OPT_H3}>{h3TagLabel}</option> : null}
            <option value={OPT_OTHER}>{hypothesisOtherLabel}</option>
            {pendingOk ? <option value={OPT_PENDING}>{hypothesisPendingLabel}</option> : null}
          </select>
        </div>
        <div className="flex min-h-0 min-w-0 flex-1 items-center">{rightSlot}</div>
        {regenBtn}
      </div>
    );
  };

  const hypothesisPreviewLayer = (() => {
    if (!hypothesisPreview || typeof document === 'undefined') return null;

    const { anchorRect, h1: ph1, h2: ph2 } = hypothesisPreview;
    const pad = 12;
    const vw = window.innerWidth;
    const vh = window.innerHeight;
    const cardW = Math.min(400, Math.max(260, vw - pad * 2));

    /* ── Horizontal: center on anchor, clamp to viewport edges ── */
    let left = anchorRect.left + anchorRect.width / 2 - cardW / 2;
    left = Math.max(pad, Math.min(left, vw - pad - cardW));

    /* ── Vertical: use table scroll container as boundary ── */
    const gap = 6;
    const MIN_SHOW = 60;

    // Default to viewport edges; prefer table container if available
    const container = tableScrollContainerRef.current;
    const containerRect = container?.getBoundingClientRect() ?? null;
    const boundTop = containerRect ? containerRect.top : pad;
    const boundBottom = containerRect ? containerRect.bottom : vh - pad;

    const spaceBelow = boundBottom - anchorRect.bottom;
    const spaceAbove = anchorRect.top - boundTop;

    // If neither side has enough room, skip rendering entirely
    if (spaceBelow < MIN_SHOW && spaceAbove < MIN_SHOW) return null;

    /*
     * Decide direction: prefer the side with more room.
     * When space is roughly equal (within 20%), prefer above — users
     * naturally expect a hover card near the bottom to go upward.
     */
    const useBelow = spaceBelow > spaceAbove * 1.2;

    // max-height: use as much available space as possible
    const availSpace = useBelow ? spaceBelow : spaceAbove;
    const maxCardH = availSpace - gap;

    /* ── Position: pin to anchor on the chosen side, clamp to container ── */
    let top: number;
    if (useBelow) {
      top = anchorRect.bottom + gap;
      if (top + maxCardH > boundBottom) top = boundBottom - maxCardH;
    } else {
      // Bottom of card sits `gap` above anchor top
      top = anchorRect.top - gap - maxCardH;
      if (top < boundTop) top = boundTop;
    }

    // Final viewport safety clamp
    if (top < pad) top = pad;
    if (top + maxCardH > vh - pad) {
      const clamped = vh - pad - top;
      if (clamped < MIN_SHOW) return null; // truly no room
    }

    const shellCls = isGlass
      ? 'rounded-2xl border border-white/55 bg-white/[0.93] shadow-[0_24px_56px_-14px_rgba(15,23,42,0.38)] backdrop-blur-xl ring-1 ring-neutral-900/[0.05]'
      : 'rounded-2xl border border-neutral-200/95 bg-white shadow-[0_24px_56px_-14px_rgba(15,23,42,0.26)] ring-1 ring-black/[0.04]';

    return createPortal(
      <div
        role="tooltip"
        aria-label={hypothesisPreviewTitle}
        style={{
          position: 'fixed',
          top,
          left,
          width: cardW,
          maxHeight: maxCardH,
          zIndex: 10040,
        }}
        className={`pointer-events-auto flex flex-col overflow-hidden ${shellCls}`}
        onMouseEnter={cancelHypothesisPreviewClose}
        onMouseLeave={scheduleHypothesisPreviewClose}
      >
        <div className="shrink-0 border-b border-neutral-200/55 bg-gradient-to-r from-violet-600/[0.08] via-white to-fuchsia-600/[0.07] px-3.5 py-2">
          <p className="text-[0.65rem] font-bold uppercase tracking-[0.14em] text-neutral-500">
            {hypothesisPreviewTitle}
          </p>
        </div>
        <div className="rumination-hyp-preview-scroll min-h-0 flex-1 space-y-3 overflow-y-auto px-3.5 py-3">
          {ph1.trim() ? (
            <div className="space-y-1.5">
              <div className="inline-flex items-center gap-1.5 rounded-full bg-violet-500/10 px-2 py-0.5">
                <span className="h-1.5 w-1.5 rounded-full bg-violet-500 ring-2 ring-violet-400/30" />
                <span className="text-[10px] font-semibold uppercase tracking-wide text-violet-800">
                  {hypothesisTagFreelanceLabel}
                </span>
              </div>
              <p className="text-[0.8125rem] leading-relaxed text-neutral-800">{ph1}</p>
            </div>
          ) : null}
          {ph1.trim() && ph2.trim() ? (
            <div className="h-px bg-gradient-to-r from-transparent via-neutral-200/90 to-transparent" />
          ) : null}
          {ph2.trim() ? (
            <div className="space-y-1.5">
              <div className="inline-flex items-center gap-1.5 rounded-full bg-fuchsia-500/10 px-2 py-0.5">
                <span className="h-1.5 w-1.5 rounded-full bg-fuchsia-500 ring-2 ring-fuchsia-400/30" />
                <span className="text-[10px] font-semibold uppercase tracking-wide text-fuchsia-900/80">
                  {hypothesisTagCompanyLabel}
                </span>
              </div>
              <p className="text-[0.8125rem] leading-relaxed text-neutral-800">{ph2}</p>
            </div>
          ) : null}
        </div>
      </div>,
      document.body
    );
  })();

  /** 列自带 options 且含「自定义」：选「自定义」后出现输入框（如工作目的） */
  const renderSelectWithOther = (
    col: RuminationTableColumn,
    rowIdx: number,
    strVal: string,
    otherLabel: string,
  ) => {
    const opts = optionsWithoutPlaceholder(col.options ?? []).filter(
      (o) => !isPlaceholderToken(normalizeOptionText(o))
    );
    // 兼容历史选项「其他」：后端可能仍下发「其他」，统一视为「自定义」
    const legacyOther = '其他';
    const rest = opts.filter((o) => o !== otherLabel && o !== legacyOther);
    const known = new Set([...opts, legacyOther]); // 旧值也能匹配
    const selectVal =
      strVal === ''
        ? ''
        : strVal === OTHER_SELECT_VALUE
          ? OTHER_SELECT_VALUE
          : known.has(strVal)
            ? strVal
            : OTHER_SELECT_VALUE;
    const otherTextareaDisplay =
      selectVal === OTHER_SELECT_VALUE
        ? strVal === OTHER_SELECT_VALUE
          ? ''
          : strVal
        : '';

    const stopRow = (e: MouseEvent) => {
      if (isGlass) e.stopPropagation();
    };

    return (
      <div className="space-y-2" onMouseDown={stopRow} onClick={stopRow}>
        <select
          value={selectVal}
          disabled={cellDisabled}
          onChange={(e) => {
            const v = e.target.value;
            if (v === OTHER_SELECT_VALUE) handleCellChange(rowIdx, col.key, OTHER_SELECT_VALUE);
            else handleCellChange(rowIdx, col.key, v);
          }}
          className={selectShellClass}
          style={selectArrowStyle}
        >
          <option value="" disabled className="text-neutral-400">{selectPlaceholder}</option>
          {rest
            .filter((opt) => !isPlaceholderToken(normalizeOptionText(opt)))
            .map((opt) => (
              <option key={opt} value={opt} title={opt}>
                {opt.length > 72 ? `${opt.slice(0, 69)}…` : opt}
              </option>
            ))}
          <option value={OTHER_SELECT_VALUE}>{otherLabel}</option>
        </select>
        {selectVal === OTHER_SELECT_VALUE && (
          <textarea
            value={otherTextareaDisplay}
            disabled={cellDisabled}
            onChange={(e) => handleCellChange(rowIdx, col.key, e.target.value)}
            placeholder={otherTextPlaceholder}
            rows={2}
            className={textareaShellClass}
          />
        )}
      </div>
    );
  };

  const tableInner = (
    <table className="w-full min-w-0 max-w-full text-sm border-separate border-spacing-0 table-auto">
        {/* glass 模式：表头使用高不透明背景 + 独立 z-index 层，防止内容穿透 */}
        <thead className={isGlass ? 'sticky top-0 z-20' : ''}>
          <tr className={isGlass ? 'bg-white/90 backdrop-blur-md' : 'bg-neutral-50'}>
            {displayColumns.map((col) => (
              <th
                key={col.key}
                style={{ minWidth: colMinWidth(col), maxWidth: colMaxWidth(col) ?? (col.key === 'id' ? 48 : undefined) }}
                className={
                  col.key === 'id'
                    ? isGlass
                      ? 'px-1 py-3 text-center font-medium text-neutral-500 whitespace-nowrap border-b border-neutral-300/70 text-[0.6rem] uppercase tracking-[0.04em] align-top'
                      : 'px-1 py-2 text-center font-medium text-neutral-500 whitespace-nowrap border-b border-neutral-200 text-xs'
                    : isGlass
                      ? 'px-2.5 py-3 text-left font-medium text-neutral-600 whitespace-nowrap border-b border-neutral-300/70 text-[0.65rem] uppercase tracking-[0.06em] align-middle'
                      : 'px-2.5 py-2 text-left font-medium text-neutral-700 whitespace-nowrap border-b border-neutral-200 align-middle'
                }
              >
                {col.key === 'id' ? '#' : col.label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, rowIdx) => (
            <tr
              key={rowIdx}
              ref={setTableRowRef(rowIdx)}
              role={isGlass && !cellDisabled ? 'button' : undefined}
              tabIndex={isGlass && !cellDisabled ? 0 : undefined}
              onClick={(e) => {
                if (!isGlass || cellDisabled) return;
                if (
                  (e.target as HTMLElement).closest(
                    'input,select,textarea,button,a,label,option'
                  )
                ) {
                  return;
                }
                if (rowSelectionMulti) handleRowPickToggle(rowIdx);
                else handleGlassRowActivate(rowIdx);
              }}
              onKeyDown={(e) => {
                if (!isGlass || cellDisabled) return;
                if (e.key === 'Enter' || e.key === ' ') {
                  e.preventDefault();
                  if (rowSelectionMulti) handleRowPickToggle(rowIdx);
                  else handleGlassRowActivate(rowIdx);
                }
              }}
              className={
                isGlass
                  ? `border-b border-neutral-200/80 transition-colors last:border-b-0 outline-none focus-visible:ring-2 focus-visible:ring-[rgba(145,194,255,0.65)] focus-visible:ring-inset ${
                      rowSelectionMulti && row.__pick === true
                        ? 'bg-[rgba(145,194,255,0.38)] text-neutral-900 shadow-[inset_3px_0_0_0_#91C2FF]'
                        : !rowSelectionMulti && selectedRowIdx === rowIdx
                          ? 'bg-[rgba(145,194,255,0.38)] text-neutral-900 shadow-[inset_3px_0_0_0_#91C2FF]'
                          : cellDisabled
                            ? ''
                            : 'hover:bg-white/30'
                    } ${isGlass && !cellDisabled ? 'cursor-pointer' : isGlass ? 'cursor-default' : ''}`
                  : 'border-b border-neutral-100 hover:bg-neutral-50/50'
              }
            >
              {displayColumns.map((col, colIdx) => {
                const isEditable = editableSet.has(col.key);
                const val = row[col.key];
                const strVal =
                  col.key === 'id' ? String(rowIdx + 1) : val != null ? String(val) : '';

                const cellKey = `${rowIdx}:${col.key}`;
                const firstColKey = displayColumns[0]?.key;
                const cellFlash =
                  (validationFlashKey === cellKey && isEditable) ||
                  (rowSelectionMulti &&
                    validationFlashKey === `${rowIdx}:__pick` &&
                    col.key === firstColKey);

                const filterStepNow = payload.step ?? 0;
                const showHypRegenOverlay =
                  colIdx === 0 &&
                  hypothesisRegeneratingRowIndex === rowIdx &&
                  filterStepNow === 3;

                const tdBase =
                  col.key === 'id'
                    ? isGlass
                      ? 'px-1 py-2 align-middle text-center text-neutral-600'
                      : 'px-1 py-2 align-middle text-center'
                    : isGlass
                      ? 'px-2.5 py-3 align-middle text-neutral-700 break-words whitespace-normal [overflow-wrap:anywhere]'
                      : 'px-2.5 py-2 align-middle break-words whitespace-normal text-neutral-700 [overflow-wrap:anywhere]';

                return (
                  <td
                    key={col.key}
                    style={{
                      minWidth: colMinWidth(col),
                      maxWidth: colMaxWidth(col) ?? (col.key === 'id' ? 48 : undefined),
                    }}
                    className={`${showHypRegenOverlay ? 'relative overflow-visible ' : ''}${tdBase}`}
                  >
                    {showHypRegenOverlay && (
                      <div
                        className="absolute left-0 top-0 z-[45] flex min-h-full items-center justify-center bg-white/80 backdrop-blur-[6px]"
                        style={{
                          width:
                            hypRegenOverlayW > 0 ? `${hypRegenOverlayW}px` : '100%',
                        }}
                        aria-busy="true"
                        aria-live="polite"
                      >
                        <Loader2
                          className="h-7 w-7 shrink-0 animate-spin text-blue-950"
                          aria-hidden
                        />
                      </div>
                    )}
                    <div
                      key={
                        cellFlash ? `${cellKey}-v${validationCycle}` : cellKey
                      }
                      ref={
                        isEditable || (rowSelectionMulti && col.key === firstColKey)
                          ? setCellWrapRef(rowIdx, col.key)
                          : undefined
                      }
                      className={`min-w-0 ${cellFlash ? 'rumination-validation-cell-flash' : ''}`}
                      onAnimationEnd={(e) => {
                        if (e.target !== e.currentTarget) return;
                        const name = (e.animationName || '').split(',')[0]?.trim();
                        if (name !== 'rumination-cell-flash') return;
                        setValidationFlashKey((k) => {
                          if (k === cellKey) return null;
                          if (
                            rowSelectionMulti &&
                            k === `${rowIdx}:__pick` &&
                            col.key === firstColKey
                          ) {
                            return null;
                          }
                          return k;
                        });
                      }}
                    >
                      {isEditable && col.key === HYP_CONFIRM_KEY && filterStep === 3 ? (
                        renderHypothesisConfirmCell(row, rowIdx, strVal)
                      ) : isEditable && (col.options?.includes(hypothesisOtherLabel) || col.options?.includes('其他')) ? (
                        renderSelectWithOther(col, rowIdx, strVal, hypothesisOtherLabel)
                      ) : isEditable && col.options?.length ? (
                        <select
                          value={strVal}
                          onChange={(e) => handleCellChange(rowIdx, col.key, e.target.value)}
                          onMouseDown={(e) => isGlass && e.stopPropagation()}
                          onClick={(e) => isGlass && e.stopPropagation()}
                          disabled={cellDisabled}
                          className={selectShellClass}
                          style={selectArrowStyle}
                        >
                          <option value="" disabled className="text-neutral-400">{selectPlaceholder}</option>
                          {optionsWithoutPlaceholder(col.options ?? [])
                            .filter((opt) => !isPlaceholderToken(normalizeOptionText(opt)))
                            .map((opt) => (
                              <option key={opt} value={opt}>
                                {opt}
                              </option>
                            ))}
                        </select>
                      ) : isEditable ? (
                        isGlass ? (
                          <textarea
                            value={strVal}
                            onChange={(e) => handleCellChange(rowIdx, col.key, e.target.value)}
                            onMouseDown={(e) => isGlass && e.stopPropagation()}
                            onClick={(e) => isGlass && e.stopPropagation()}
                            disabled={cellDisabled}
                            placeholder={inputPlaceholder}
                            rows={2}
                            className="w-full min-h-[2.75rem] min-w-[100px] resize-y px-2 py-1.5 text-sm leading-snug border border-neutral-200/90 rounded-lg bg-white/80 focus:ring-2 focus:ring-[rgba(145,194,255,0.55)] break-words whitespace-pre-wrap"
                          />
                        ) : (
                          <input
                            type="text"
                            value={strVal}
                            onChange={(e) => handleCellChange(rowIdx, col.key, e.target.value)}
                            onMouseDown={(e) => isGlass && e.stopPropagation()}
                            onClick={(e) => isGlass && e.stopPropagation()}
                            disabled={cellDisabled}
                            placeholder={inputPlaceholder}
                            className="w-full min-w-[100px] px-2 py-1 text-sm border border-neutral-200 rounded-md focus:ring-2 focus:ring-sky-300/50 focus:border-sky-400/70"
                          />
                        )
                      ) : (
                        <span
                          className={`text-neutral-700 break-words whitespace-pre-wrap ${
                            col.key === 'id' ? 'block text-center text-xs tabular-nums text-neutral-500' : ''
                          }`}
                        >
                          {strVal || '—'}
                        </span>
                      )}
                    </div>
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
  );

  const tableBlock = isGlass ? (
    <div className="relative flex min-h-0 flex-1 flex-col overflow-hidden rounded-xl border border-neutral-300/50 bg-white/25 shadow-[inset_0_1px_0_rgba(255,255,255,0.65)]">
      <div ref={tableScrollContainerRef} className="rumination-beautiful-table-scroll rumination-beautiful-table-widget min-h-0 flex-1 overflow-x-auto overflow-y-auto">
        {tableInner}
      </div>
      {embeddedSubmitOverlay && submitting && (
        <div
          className="pointer-events-none absolute inset-0 z-30 flex items-center justify-center rounded-xl bg-white/55 backdrop-blur-[20px]"
          aria-live="polite"
          aria-busy="true"
        >
          <span className="rounded-full bg-white/90 px-4 py-2 text-sm font-medium text-neutral-700 shadow-md">
            {loadingLabel}
          </span>
        </div>
      )}
    </div>
  ) : (
    <div className="relative max-h-[320px] overflow-x-auto overflow-y-auto rounded-lg border border-neutral-100">
      {tableInner}
    </div>
  );

  if (isGlass) {
    return (
      <>
        <div className={`flex min-h-0 flex-1 flex-col ${className}`}>
          <div className="mb-3 flex shrink-0 items-center justify-between gap-3">
            <h2 className="truncate text-lg font-semibold text-bd-fg">{cardTitle ?? '表格'}</h2>
            {tableHeaderActions}
          </div>
          {payload.guideText && (
            <p className="mb-2 shrink-0 text-sm leading-relaxed text-neutral-600">{payload.guideText}</p>
          )}
          {/* flex-1 + 表格区 flex-1：撑满左卡剩余高度，避免 max-h 下方大块留白 */}
          <div className="flex min-h-0 flex-1 flex-col">{tableBlock}</div>
        </div>
        {hypothesisPreviewLayer}
      </>
    );
  }

  return (
    <>
      <div
        className={`rumination-table-widget rounded-xl border border-neutral-200 bg-white/90 p-4 ${className}`}
      >
        {payload.guideText && (
          <p className="text-sm text-neutral-600 mb-3">{payload.guideText}</p>
        )}
        {tableBlock}
        <div className="mt-3 flex justify-end">{tableHeaderActions}</div>
      </div>
      {hypothesisPreviewLayer}
    </>
  );
}
