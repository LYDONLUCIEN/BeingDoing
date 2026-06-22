'use client';

import {
  useState,
  useCallback,
  useEffect,
  useRef,
  useMemo,
  type ChangeEvent,
  type MouseEvent,
} from 'react';
import { createPortal } from 'react-dom';
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
  /** step3 子步标识：matrix / discussion。discussion 模式下不自动清行选中 */
  subStep?: string;
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
  /** 子步 3：表格内存行变更时通知父级（用于 debounce 同步 filter_table） */
  onLiveRowsChange?: (rows: Record<string, unknown>[]) => void;
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
  /** 子步 3：用户在假设列选「无」 */
  onStep3NoneSelected?: (rowIndex: number, rows: Record<string, unknown>[]) => void;
  /** 子步 3：用户填写假设后失焦/回车提交 */
  onStep3HypothesisCommit?: (rowIndex: number, text: string, rows: Record<string, unknown>[]) => void;
  /** 子步 3：选「无」后短暂冷却，期间禁用表格交互（防止连点） */
  step3Cooldown?: boolean;
  /** 子步 3：外部填入假设 { rowIndex, text }。设为非 null 后组件写入并清空。 */
  step3ExternalHypFill?: { rowIndex: number; text: string } | null;
  /** neg gate 深度讨论时：需要讨论的行 id 集合，非此集合的行模糊化显示 */
  activeItemIds?: Set<string> | null;
  /** neg gate 深度讨论进行中：允许 activeItemIds 行编辑，其余行锁定 */
  negGateExploring?: boolean;
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
  onLiveRowsChange,
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
  onStep3NoneSelected,
  onStep3HypothesisCommit,
  step3Cooldown = false,
  step3ExternalHypFill = null,
  embeddedSubmitOverlay = false,
  activeItemIds = null,
  negGateExploring = false,
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
  /** 已确认本步 / 回看模式：锁定格内编辑 */
  const cellDisabled = disabled || confirmDisabledAfterCommit || reviewReadOnly || step3Cooldown;
  /** 回看模式 / disabled：锁定行选中 */
  const rowPickDisabled = reviewReadOnly || disabled;

  const tableRowRefs = useRef<Map<number, HTMLTableRowElement | null>>(new Map());
  /** step3：tag 点击后需要聚焦的 textarea 行号（-1 表示无） */
  const textareaFocusRowRef = useRef<number>(-1);
  /** step3：per-row textarea ref，用于 tag 点击后自动聚焦 */
  const hypTextareaRefs = useRef<Map<number, HTMLTextAreaElement | null>>(new Map());

  /** 外部填入假设：写入指定行 textarea，不自动 commit */
  useEffect(() => {
    if (!step3ExternalHypFill) return;
    const { rowIndex, text } = step3ExternalHypFill;
    if (rowIndex < 0 || rowIndex >= rows.length) return;
    setRows((prev) => {
      const next = [...prev];
      next[rowIndex] = { ...next[rowIndex], [HYP_CONFIRM_KEY]: text };
      return next;
    });
    setSelectedRowIdx(rowIndex);
    // 标记需要聚焦，等 textarea 渲染后聚焦
    textareaFocusRowRef.current = rowIndex;
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [step3ExternalHypFill]);

  /** step3：textarea 渲染后自动聚焦（tag 点击后） */
  useEffect(() => {
    const targetRow = textareaFocusRowRef.current;
    if (targetRow < 0) return;
    const raf = requestAnimationFrame(() => {
      const ta = hypTextareaRefs.current.get(targetRow);
      if (ta) {
        ta.focus();
        ta.setSelectionRange(ta.value.length, ta.value.length);
      }
      textareaFocusRowRef.current = -1;
    });
    return () => cancelAnimationFrame(raf);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [rows]);

  const [hypothesisPreview, setHypothesisPreview] = useState<{
    anchorRect: DOMRect;
    h1: string;
    h2: string;
  } | null>(null);
  const hypothesisPreviewCloseTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const tableScrollContainerRef = useRef<HTMLDivElement | null>(null);
  /** 暂存每行「上一个填写过的假设」：选「无」时保存，再选回「填写假设」时恢复，避免丢失 */
  const lastFilledHypRef = useRef<Map<number, string>>(new Map());

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

  const rowsPayloadSig = JSON.stringify(payload.rows ?? []);
  useEffect(() => {
    try {
      setRows(JSON.parse(rowsPayloadSig) || []);
    } catch {
      setRows([]);
    }
  }, [rowsPayloadSig]);

  // 仅随子步、游标、行数变化重置选中；默认不选中任何行（单行模式仍跟 rowCursor）。
  // discussion 子步：用户选了一行后，发消息触发 rows 刷新不应清掉选中——除非行被删光。
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
    if (payload.subStep === 'discussion') {
      // discussion 模式下保持用户选择；仅当当前选中越界时回退到首行
      setSelectedRowIdx((prev) => (prev == null || prev >= n ? 0 : prev));
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
    payload.subStep,
  ]);

  useEffect(() => {
    if ((payload.step ?? 0) !== 3 || !onLiveRowsChange) return;
    onLiveRowsChange(rows);
  }, [rows, onLiveRowsChange, payload.step]);

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
    // discussion 模式：发消息/提交过程中 disabled 翻转不应清掉用户选中的讨论行
    if (payload.subStep === 'discussion') return;
    setSelectedRowIdx(null);
  }, [confirmDisabledAfterCommit, payload.subStep]);

  useEffect(() => {
    if (!disabled) return;
    // discussion 模式：sending → disabled 翻转不应清掉用户选中的讨论行
    if (payload.subStep === 'discussion') return;
    setSelectedRowIdx(null);
  }, [disabled, payload.subStep]);

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
    const nonIdCols = payload.columns.filter((c) => c.key !== 'id');
    const bits = nonIdCols
      .slice(0, 3)
      .map((c) => String(row[c.key] ?? '').trim())
      .filter(Boolean);
    const rowLabel = bits.length > 0 ? bits.join(' · ') : `第${selectedRowIdx + 1}行`;
    const label = `#${selectedRowIdx + 1} ${rowLabel}`;
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
      if (rowPickDisabled) return;
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
    [rowPickDisabled, payload.rowSelectionMax]
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
    const fs = payload.step ?? 0;
    if (fs === 3 && rowIdx > (payload.rowCursor ?? 0)) return;
    setRows((prev) => {
      const next = [...prev];
      if (rowIdx < 0 || rowIdx >= next.length) return prev;
      next[rowIdx] = { ...next[rowIdx], [colKey]: value };
      return next;
    });
  }, [cellDisabled, payload.step, payload.rowCursor]);

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
          if (!strVal || strVal === OTHER_SELECT_VALUE || strVal === STEP3_OPT_FILL) {
            return { rowIdx, colKey: col.key };
          }
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
        if (next[k] === OTHER_SELECT_VALUE || next[k] === STEP3_OPT_FILL) next[k] = '';
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

  const STEP3_OPT_NONE = '__rum_s3_none__';
  const STEP3_OPT_FILL = '__rum_s3_fill__';
  const step3FillLabel = '填写假设';

  const renderHypothesisConfirmCell = (
    row: Record<string, unknown>,
    rowIdx: number,
    strVal: string,
    rowLocked: boolean,
    overrideCellDisabled?: boolean,
  ) => {
    const pendingOk =
      hypothesisPendingLabel && !isPlaceholderToken(hypothesisPendingLabel);
    const isNone =
      pendingOk &&
      (strVal === hypothesisPendingLabel || strVal === '待定' || strVal === '暂未选定');
    const isFillMarker = strVal === STEP3_OPT_FILL;
    const isFill = Boolean(strVal && !isNone && !isFillMarker);
    let selectControlValue = '';
    if (isNone) selectControlValue = STEP3_OPT_NONE;
    else if (isFillMarker || isFill) selectControlValue = STEP3_OPT_FILL;

    const fillText = isFill ? strVal : '';
    const fieldDisabled = (overrideCellDisabled ?? cellDisabled) || rowLocked;

    const onStep3SelectChange = (e: ChangeEvent<HTMLSelectElement>) => {
      const v = e.target.value;
      if (!v) {
        handleCellChange(rowIdx, HYP_CONFIRM_KEY, '');
        return;
      }
      if (v === STEP3_OPT_NONE && pendingOk) {
        // 选「无」前，若当前已有填写的假设文本，暂存起来，便于用户后续切回「填写假设」时恢复。
        if (isFill && fillText.trim()) {
          lastFilledHypRef.current.set(rowIdx, fillText);
        }
        setRows((prev) => {
          const next = [...prev];
          if (rowIdx >= 0 && rowIdx < next.length) {
            next[rowIdx] = { ...next[rowIdx], [HYP_CONFIRM_KEY]: hypothesisPendingLabel };
          }
          onStep3NoneSelected?.(rowIdx, next);
          return next;
        });
        return;
      }
      if (v === STEP3_OPT_FILL) {
        // 切回「填写假设」：优先恢复此前暂存的假设文本，没有才用标记占位。
        const restored = lastFilledHypRef.current.get(rowIdx);
        if (restored && restored.trim()) {
          lastFilledHypRef.current.delete(rowIdx);
          handleCellChange(rowIdx, HYP_CONFIRM_KEY, restored);
        } else {
          handleCellChange(rowIdx, HYP_CONFIRM_KEY, STEP3_OPT_FILL);
        }
        return;
      }
    };

    const commitHypothesisIfFilled = () => {
      const text = fillText.trim();
      if (!text) return;
      setRows((prev) => {
        const next = [...prev];
        if (rowIdx >= 0 && rowIdx < next.length) {
          next[rowIdx] = { ...next[rowIdx], [HYP_CONFIRM_KEY]: text };
        }
        onStep3HypothesisCommit?.(rowIdx, text, next);
        return next;
      });
    };

    const hypSelectStep3Class = isGlass
      ? `${selectShellClass} !min-w-0 shrink max-w-[8rem] sm:max-w-[12rem]`
      : `${selectShellClass} !min-w-0 shrink max-w-[8rem] sm:max-w-[12rem]`;

    const hasFilledHypothesis =
      isFill && fillText.trim().length > 0 && fillText !== STEP3_OPT_FILL;
    const canRegenerateHyp =
      Boolean(onHypothesisRegenerate) && !fieldDisabled && hasFilledHypothesis;
    const isRegenerating = hypothesisRegeneratingRowIndex === rowIdx;

    const regenerateIconBtnClass = isGlass
      ? 'inline-flex h-6 w-6 shrink-0 items-center justify-center rounded-md border border-white/60 bg-white/75 text-neutral-500 shadow-sm backdrop-blur-sm transition hover:border-sky-300/70 hover:bg-sky-50/90 hover:text-sky-600 disabled:pointer-events-none disabled:opacity-40'
      : 'inline-flex h-6 w-6 shrink-0 items-center justify-center rounded-md border border-neutral-200/90 bg-white text-neutral-500 shadow-sm transition hover:border-sky-300/70 hover:bg-sky-50 hover:text-sky-600 disabled:pointer-events-none disabled:opacity-40';

    const renderRegenerateIconButton = () =>
      canRegenerateHyp ? (
        <button
          type="button"
          title={hypothesisRegenerateHint}
          aria-label={hypothesisRegenerateLabel}
          disabled={isRegenerating}
          onMouseDown={(e) => e.stopPropagation()}
          onClick={(e) => {
            e.stopPropagation();
            const rowId = String(row.id ?? rowIdx + 1);
            onHypothesisRegenerate!(rowIdx, rowId, rows);
          }}
          className={regenerateIconBtnClass}
        >
          {isRegenerating ? (
            <span className="inline-block h-3 w-3 animate-spin rounded-full border-2 border-sky-400/30 border-t-sky-500" />
          ) : (
            <svg
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
              className="h-3.5 w-3.5"
              aria-hidden
            >
              <path d="M21 12a9 9 0 0 0-9-9 9.75 9.75 0 0 0-6.74 2.74L3 8" />
              <path d="M3 3v5h5" />
              <path d="M3 12a9 9 0 0 0 9 9 9.75 9.75 0 0 0 6.74-2.74L21 16" />
              <path d="M16 21h5v-5" />
            </svg>
          )}
        </button>
      ) : null;

    return (
      <div
        className="flex min-w-0 max-w-full flex-col gap-2 sm:flex-row sm:items-start sm:gap-3"
        onMouseDown={(e) => isGlass && e.stopPropagation()}
        onClick={(e) => isGlass && e.stopPropagation()}
      >
        <select
          value={selectControlValue}
          disabled={fieldDisabled}
          onMouseDown={(e) => e.stopPropagation()}
          onClick={(e) => e.stopPropagation()}
          onChange={onStep3SelectChange}
          className={hypSelectStep3Class}
          style={selectArrowStyle}
        >
          <option value="" disabled className="text-neutral-400">
            {selectPlaceholder}
          </option>
          {pendingOk ? <option value={STEP3_OPT_NONE}>{hypothesisPendingLabel}</option> : null}
          <option value={STEP3_OPT_FILL}>{step3FillLabel}</option>
        </select>
        {selectControlValue === STEP3_OPT_FILL ? (
          isGlass ? (
            <div className="relative min-w-0 flex-1">
              <textarea
                ref={(el) => { hypTextareaRefs.current.set(rowIdx, el); }}
                value={fillText}
                disabled={fieldDisabled}
                placeholder={otherTextPlaceholder}
                onMouseDown={(e) => isGlass && e.stopPropagation()}
                onClick={(e) => isGlass && e.stopPropagation()}
                onChange={(e) =>
                  handleCellChange(rowIdx, HYP_CONFIRM_KEY, e.target.value)
                }
                onBlur={commitHypothesisIfFilled}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault();
                    commitHypothesisIfFilled();
                  }
                }}
                rows={3}
                className={`${textareaShellClass} !min-w-0 shrink-1 ${canRegenerateHyp ? '!pr-9' : ''}`}
              />
              {canRegenerateHyp ? (
                <div className="pointer-events-none absolute right-1.5 top-1.5">
                  <div className="pointer-events-auto">{renderRegenerateIconButton()}</div>
                </div>
              ) : null}
            </div>
          ) : (
            <div className="relative min-w-0 flex-1">
              <textarea
                ref={(el) => { hypTextareaRefs.current.set(rowIdx, el); }}
                value={fillText}
                disabled={fieldDisabled}
                placeholder={otherTextPlaceholder}
                onChange={(e) =>
                  handleCellChange(rowIdx, HYP_CONFIRM_KEY, e.target.value)
                }
                onBlur={commitHypothesisIfFilled}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault();
                    commitHypothesisIfFilled();
                  }
                }}
                rows={3}
                className={`min-w-0 shrink-1 flex-1 px-2 py-1.5 text-sm border border-neutral-200 rounded-md focus:ring-2 focus:ring-sky-300/50 focus:border-sky-400/70 ${canRegenerateHyp ? 'pr-9' : ''}`}
              />
              {canRegenerateHyp ? (
                <div className="pointer-events-none absolute right-1.5 top-1.5">
                  <div className="pointer-events-auto">{renderRegenerateIconButton()}</div>
                </div>
              ) : null}
            </div>
          )
        ) : null}
      </div>
    );
  };

  const hypothesisPreviewLayer = (() => {
    if ((payload.step ?? 0) === 3) return null;
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
    overrideCellDisabled?: boolean,
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

    const cd = overrideCellDisabled ?? cellDisabled;

    return (
      <div className="space-y-2" onMouseDown={stopRow} onClick={stopRow}>
        <select
          value={selectVal}
          disabled={cd}
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
            disabled={cd}
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
          {rows.map((row, rowIdx) => {
            const rowId = String(row.id ?? '');
            const rowDimmed = activeItemIds && activeItemIds.size > 0 && !activeItemIds.has(rowId);
            /** neg gate 探索中：非讨论行锁定单元格编辑；讨论行保持可编辑 */
            const rowNegLocked = negGateExploring && rowDimmed;
            /** per-row 单元格禁用：全局禁用 + neg gate 非讨论行锁定 */
            const rowCellDisabled = !!(cellDisabled || rowNegLocked);
            return (
            <tr
              key={rowIdx}
              ref={setTableRowRef(rowIdx)}
              role={isGlass && !rowPickDisabled ? 'button' : undefined}
              tabIndex={isGlass && !rowPickDisabled ? 0 : undefined}
              onClick={(e) => {
                if (!isGlass || rowPickDisabled || rowNegLocked) return;
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
                if (!isGlass || rowPickDisabled || rowNegLocked) return;
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
                          : rowPickDisabled
                            ? ''
                            : 'hover:bg-white/30'
                    } ${isGlass && !rowPickDisabled ? 'cursor-pointer' : isGlass ? 'cursor-default' : ''} ${
                      rowDimmed ? 'rumination-row-dimmed' : ''
                    }`
                  : `border-b border-neutral-100 hover:bg-neutral-50/50 ${rowDimmed ? 'rumination-row-dimmed' : ''}`
              }
            >
              {displayColumns.map((col) => {
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

                const step3RowLocked = filterStep === 3 && rowIdx > (payload.rowCursor ?? 0);

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
                      overflow: 'hidden',
                    }}
                    className={tdBase}
                  >
                    <div
                      key={
                        cellFlash ? `${cellKey}-v${validationCycle}` : cellKey
                      }
                      ref={
                        isEditable || (rowSelectionMulti && col.key === firstColKey)
                          ? setCellWrapRef(rowIdx, col.key)
                          : undefined
                      }
                      className={`min-w-0 max-w-full overflow-hidden ${cellFlash ? 'rumination-validation-cell-flash' : ''}`}
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
                        renderHypothesisConfirmCell(row, rowIdx, strVal, step3RowLocked, rowCellDisabled)
                      ) : isEditable && (col.options?.includes(hypothesisOtherLabel) || col.options?.includes('其他')) ? (
                        renderSelectWithOther(col, rowIdx, strVal, hypothesisOtherLabel, rowCellDisabled)
                      ) : isEditable && col.options?.length ? (
                        <select
                          value={strVal}
                          onChange={(e) => handleCellChange(rowIdx, col.key, e.target.value)}
                          onMouseDown={(e) => isGlass && e.stopPropagation()}
                          onClick={(e) => isGlass && e.stopPropagation()}
                          disabled={rowCellDisabled || step3RowLocked}
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
                            disabled={rowCellDisabled || step3RowLocked}
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
                            disabled={rowCellDisabled || step3RowLocked}
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
            );
          })}
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
