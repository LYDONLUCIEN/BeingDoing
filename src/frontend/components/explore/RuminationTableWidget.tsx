'use client';

import { useState, useCallback, useEffect, useRef, type MouseEvent } from 'react';
import { Loader2, RefreshCw } from 'lucide-react';

const HYP_CONFIRM_KEY = '用户确认的假设';
const OTHER_SELECT_VALUE = '__RUMINATION_OTHER__';

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
  selectPlaceholder?: string;
  inputPlaceholder?: string;
  /** 提交表格时遮罩文案（仅 embeddedSubmitOverlay 为 true 时使用） */
  loadingLabel?: string;
  submitting?: boolean;
  /** 为 true 时在表格外壳内显示提交遮罩；默认 false（由页面全屏遮罩承担） */
  embeddedSubmitOverlay?: boolean;
  /** 存在未填项时点确认的提示（显著横幅） */
  validationEmptyHint?: string;
  /** 选中行摘要，用于输入框上下文 */
  onRowContextChange?: (ctx: { rowIndex: number; label: string } | null) => void;
  /** 假设确认列：「待定」文案 */
  hypothesisPendingLabel?: string;
  /** 假设确认列：「其他」文案 */
  hypothesisOtherLabel?: string;
  /** 选「其他」后出现的输入框占位 */
  otherTextPlaceholder?: string;
  /** 为 true 时隐藏表头「确认」按钮（如第 9 步改由对话/结论卡确认） */
  hideConfirmButton?: boolean;
  /** 假设列：假设1 侧色块标签（个人事业向） */
  hypothesisTagFreelanceLabel?: string;
  /** 假设列：假设2 侧色块标签（职业路径向） */
  hypothesisTagCompanyLabel?: string;
  /** 假设列：第三条等额外假设的标签 */
  hypothesisTagExtraLabel?: string;
  /** 子步 3–5：重新生成本行两条假设 */
  hypothesisRegenerateLabel?: string;
  hypothesisRegeneratingLabel?: string;
  /** 右上角重新生成图标的悬停说明 */
  hypothesisRegenerateHint?: string;
  hypothesisRegeneratingRowIndex?: number | null;
  onHypothesisRegenerate?: (rowIndex: number, rowId: string) => void | Promise<void>;
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
  selectPlaceholder = '请选择',
  inputPlaceholder = '填写',
  loadingLabel = '…',
  submitting = false,
  onRowContextChange,
  hypothesisPendingLabel = '待定',
  hypothesisOtherLabel = '其他',
  otherTextPlaceholder = '请填写自定义内容…',
  hideConfirmButton = false,
  hypothesisTagFreelanceLabel = '个人事业',
  hypothesisTagCompanyLabel = '职业路径',
  hypothesisTagExtraLabel = '备选',
  hypothesisRegenerateLabel = '重新生成',
  hypothesisRegeneratingLabel = '生成中…',
  hypothesisRegenerateHint = '重新生成本行的假设选项',
  hypothesisRegeneratingRowIndex = null,
  onHypothesisRegenerate,
  embeddedSubmitOverlay = false,
  validationEmptyHint,
}: RuminationTableWidgetProps) {
  const [rows, setRows] = useState<Record<string, unknown>[]>(
    () => JSON.parse(JSON.stringify(payload.rows)) || []
  );
  /** glass：当前高亮行；null 表示未选中（再点同一行可取消） */
  const [selectedRowIdx, setSelectedRowIdx] = useState<number | null>(0);
  const [validationBanner, setValidationBanner] = useState(false);
  /** 校验动画：与单元格 class 绑定，动画结束后清空 */
  const [validationFlashKey, setValidationFlashKey] = useState<string | null>(null);
  const [validationCycle, setValidationCycle] = useState(0);
  const [hypOtherDraftByKey, setHypOtherDraftByKey] = useState<Record<string, string>>({});
  const cellWrapRefs = useRef<Map<string, HTMLDivElement | null>>(new Map());

  const rowsPayloadSig = JSON.stringify(payload.rows ?? []);
  useEffect(() => {
    try {
      setRows(JSON.parse(rowsPayloadSig) || []);
    } catch {
      setRows([]);
    }
  }, [rowsPayloadSig]);

  // 仅随子步、游标、行数变化重置选中；不依赖 payload.rows 引用以免编辑单元格时误重置高亮
  useEffect(() => {
    const n = (payload.rows ?? []).length;
    const c = payload.rowCursor ?? 0;
    if (n <= 0) {
      setSelectedRowIdx(null);
      return;
    }
    setSelectedRowIdx(Math.min(Math.max(0, c), n - 1));
    // eslint-disable-next-line react-hooks/exhaustive-deps -- 故意不依赖 payload.rows 全文
  }, [payload.step, payload.rowCursor, payload.totalRows, payload.rows?.length]);

  const setCellWrapRef = useCallback((rowIdx: number, colKey: string) => {
    const key = `${rowIdx}:${colKey}`;
    return (el: HTMLDivElement | null) => {
      if (el) cellWrapRefs.current.set(key, el);
      else cellWrapRefs.current.delete(key);
    };
  }, []);

  const handleGlassRowActivate = useCallback((rowIdx: number) => {
    setSelectedRowIdx((prev) => (prev === rowIdx ? null : rowIdx));
  }, []);

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

  const colMinWidth = (col: RuminationTableColumn) => {
    if (col.key === 'id') return 40;
    const labelLen = col.label?.length ?? 0;
    return Math.min(220, Math.max(76, 8 + labelLen * 11));
  };

  const handleCellChange = useCallback((rowIdx: number, colKey: string, value: unknown) => {
    setRows((prev) => {
      const next = [...prev];
      if (rowIdx < 0 || rowIdx >= next.length) return prev;
      next[rowIdx] = { ...next[rowIdx], [colKey]: value };
      return next;
    });
  }, []);

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

        if (
          col.key === HYP_CONFIRM_KEY &&
          filterStep >= 3 &&
          filterStep <= 5
        ) {
          if (!strVal || isPlaceholderToken(strVal)) return { rowIdx, colKey: col.key };
          if (strVal === OTHER_SELECT_VALUE) return { rowIdx, colKey: col.key };
          continue;
        }

        if (col.options?.includes(hypothesisOtherLabel)) {
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
    return null;
  }, [rows, payload.columns, editableSet, filterStep, hypothesisOtherLabel, isPlaceholderToken]);

  const handleConfirm = useCallback(() => {
    setValidationBanner(false);
    setValidationFlashKey(null);
    const bad = findFirstInvalidCell();
    if (bad) {
      const key = `${bad.rowIdx}:${bad.colKey}`;
      setValidationCycle((c) => c + 1);
      setValidationBanner(true);
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
  }, [rows, onConfirm, findFirstInvalidCell]);

  if (!payload.columns?.length) return null;

  const isGlass = uiVariant === 'glass';

  const confirmBtnCls = isGlass
    ? 'bd-btn-black shrink-0 rounded-full px-4 py-2 text-sm font-medium text-white transition-all disabled:opacity-40 disabled:cursor-not-allowed'
    : 'rounded-lg bg-violet-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-violet-700 disabled:cursor-not-allowed disabled:opacity-50';

  const refillBtnCls = isGlass
    ? 'shrink-0 rounded-full border border-neutral-200 bg-white/70 px-4 py-2 text-sm font-medium text-neutral-600 transition-all hover:bg-white disabled:opacity-40 disabled:cursor-not-allowed'
    : 'rounded-lg border border-neutral-300 bg-white px-4 py-2 text-sm font-medium text-neutral-600 transition-colors hover:bg-neutral-50 disabled:cursor-not-allowed disabled:opacity-50';

  const tableHeaderActions =
    hideConfirmButton && !(tableRefillMode && onRefill) ? null : (
      <div className="flex items-center gap-3">
        {tableRefillMode && onRefill && (
          <button type="button" onClick={() => onRefill?.()} disabled={disabled} className={refillBtnCls}>
            {refillLabel}
          </button>
        )}
        {!hideConfirmButton && (
          <button type="button" onClick={handleConfirm} disabled={disabled} className={confirmBtnCls}>
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

  type HypTagKind = 'freelance' | 'company' | 'extra';

  const tagLabels: Record<HypTagKind, string> = {
    freelance: hypothesisTagFreelanceLabel,
    company: hypothesisTagCompanyLabel,
    extra: hypothesisTagExtraLabel,
  };

  const tagPillClass = (tag: HypTagKind) =>
    tag === 'freelance'
      ? 'bg-sky-500 text-white'
      : tag === 'company'
        ? 'bg-violet-500 text-white'
        : 'bg-teal-600 text-white';

  const renderHypothesisTag = (tag: HypTagKind) => (
    <span
      className={`inline-flex max-w-[5.5rem] shrink-0 items-center rounded-md px-1.5 py-0.5 text-[10px] font-semibold leading-tight ${tagPillClass(tag)}`}
    >
      {tagLabels[tag]}
    </span>
  );

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
    else if (pendingOk && strVal === hypothesisPendingLabel) active = 'pending';
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

    const stopRow = (e: MouseEvent) => {
      if (isGlass) e.stopPropagation();
    };

    const radioName = `rumination-hyp-${filterStep}-${rowIdx}`;
    const radioBase =
      'h-4 w-4 shrink-0 border-neutral-300 text-sky-600 focus:ring-2 focus:ring-sky-500/40';

    const lineCls =
      'flex cursor-pointer items-center gap-2 rounded-lg py-1.5 pr-1 transition-colors hover:bg-white/45';

    const persistOtherDraftFromCell = () => {
      if (active !== 'other') return;
      if (strVal && strVal !== OTHER_SELECT_VALUE) {
        setHypOtherDraftByKey((p) => ({ ...p, [draftKey]: strVal }));
      } else if (storedDraft.trim()) {
        setHypOtherDraftByKey((p) => ({ ...p, [draftKey]: storedDraft }));
      }
    };

    const setChoice = (pick: HypPick) => {
      if (pick !== 'other') persistOtherDraftFromCell();
      if (pick === 'h1' && h1) handleCellChange(rowIdx, HYP_CONFIRM_KEY, h1);
      else if (pick === 'h2' && h2) handleCellChange(rowIdx, HYP_CONFIRM_KEY, h2);
      else if (pick === 'h3' && h3) handleCellChange(rowIdx, HYP_CONFIRM_KEY, h3);
      else if (pick === 'pending' && pendingOk) {
        handleCellChange(rowIdx, HYP_CONFIRM_KEY, hypothesisPendingLabel);
      } else if (pick === 'other') {
        const fromCell =
          strVal && strVal !== OTHER_SELECT_VALUE ? strVal : '';
        const d = (fromCell || hypOtherDraftByKey[draftKey] || '').trim();
        if (d) handleCellChange(rowIdx, HYP_CONFIRM_KEY, d);
        else handleCellChange(rowIdx, HYP_CONFIRM_KEY, OTHER_SELECT_VALUE);
      }
    };

    const hypLines: { key: HypPick; tag: HypTagKind; text: string; show: boolean }[] = [
      { key: 'h1', tag: 'freelance', text: h1, show: !!h1 },
      { key: 'h2', tag: 'company', text: h2, show: !!h2 },
      { key: 'h3', tag: 'extra', text: h3, show: !!h3 },
    ];

    return (
      <div
        className="relative min-w-[200px] space-y-0.5 pb-2 pl-0.5 pr-8 pt-8"
        onMouseDown={stopRow}
        onClick={stopRow}
      >
        {hypothesisRegeneratingRowIndex === rowIdx && (
          <div
            className="absolute inset-0 z-20 flex items-center justify-center rounded-lg bg-white/70 backdrop-blur-sm"
            aria-busy="true"
            aria-live="polite"
          >
            <Loader2 className="h-7 w-7 animate-spin text-sky-600" aria-hidden />
          </div>
        )}

        {hypLines.map(
          (line) =>
            line.show && (
              <label key={line.key} className={lineCls} onClick={stopRow}>
                <input
                  type="radio"
                  name={radioName}
                  className={radioBase}
                  checked={active === line.key}
                  disabled={disabled}
                  onMouseDown={(e) => isGlass && e.stopPropagation()}
                  onChange={() => setChoice(line.key)}
                />
                {renderHypothesisTag(line.tag)}
                <span className="min-w-0 flex-1 break-words text-sm leading-relaxed text-neutral-800">
                  {line.text}
                </span>
              </label>
            )
        )}

        {pendingOk && (
          <label className={lineCls} onClick={stopRow}>
            <input
              type="radio"
              name={radioName}
              className={radioBase}
              checked={active === 'pending'}
              disabled={disabled}
              onMouseDown={(e) => isGlass && e.stopPropagation()}
              onChange={() => setChoice('pending')}
            />
            <span className="inline-flex max-w-[5.5rem] shrink-0 items-center rounded-md bg-amber-500 px-1.5 py-0.5 text-[10px] font-semibold leading-tight text-white">
              {hypothesisPendingLabel}
            </span>
            <span className="min-w-0 flex-1 text-sm text-neutral-500">—</span>
          </label>
        )}

        <label className={`${lineCls} items-center`} onClick={stopRow}>
          <input
            type="radio"
            name={radioName}
            className={radioBase}
            checked={active === 'other'}
            disabled={disabled}
            onMouseDown={(e) => isGlass && e.stopPropagation()}
            onChange={() => setChoice('other')}
          />
          <span className="inline-flex max-w-[5.5rem] shrink-0 items-center rounded-md bg-slate-500 px-1.5 py-0.5 text-[10px] font-semibold leading-tight text-white">
            {hypothesisOtherLabel}
          </span>
          <input
            type="text"
            value={otherInputValue}
            disabled={disabled || active !== 'other'}
            placeholder={otherTextPlaceholder}
            onMouseDown={(e) => isGlass && e.stopPropagation()}
            onClick={(e) => isGlass && e.stopPropagation()}
            onChange={(e) => {
              const v = e.target.value;
              setHypOtherDraftByKey((p) => ({ ...p, [draftKey]: v }));
              if (active === 'other') {
                if (v === '') handleCellChange(rowIdx, HYP_CONFIRM_KEY, OTHER_SELECT_VALUE);
                else handleCellChange(rowIdx, HYP_CONFIRM_KEY, v);
              }
            }}
            className={
              isGlass
                ? 'min-w-0 flex-1 rounded-lg border border-neutral-200/90 bg-white/80 px-2 py-1.5 text-sm focus:border-[#91C2FF]/80 focus:outline-none focus:ring-2 focus:ring-[rgba(145,194,255,0.55)]'
                : 'min-w-0 flex-1 rounded-md border border-neutral-200 px-2 py-1 text-sm focus:border-sky-400/70 focus:outline-none focus:ring-2 focus:ring-sky-300/50'
            }
          />
        </label>

        {onHypothesisRegenerate && filterStep >= 3 && filterStep <= 5 && (
          <button
            type="button"
            title={hypothesisRegenerateHint}
            aria-label={hypothesisRegenerateHint}
            disabled={disabled || hypothesisRegeneratingRowIndex === rowIdx}
            className="absolute right-0 top-0 rounded-lg p-1.5 text-sky-600 transition-colors hover:bg-sky-500/15 disabled:cursor-not-allowed disabled:opacity-40"
            onMouseDown={(e) => isGlass && e.stopPropagation()}
            onClick={(e) => {
              if (isGlass) e.stopPropagation();
              const rid = String(row.id ?? rowIdx);
              void onHypothesisRegenerate(rowIdx, rid);
            }}
          >
            <RefreshCw className="h-4 w-4" aria-hidden />
          </button>
        )}
      </div>
    );
  };

  /** 列自带 options 且含「其他」：选「其他」后出现输入框（如工作目的） */
  const renderSelectWithOther = (
    col: RuminationTableColumn,
    rowIdx: number,
    strVal: string,
    otherLabel: string,
  ) => {
    const opts = optionsWithoutPlaceholder(col.options ?? []).filter(
      (o) => !isPlaceholderToken(normalizeOptionText(o))
    );
    const rest = opts.filter((o) => o !== otherLabel);
    const known = new Set(opts);
    const selectVal =
      strVal === ''
        ? ''
        : strVal === OTHER_SELECT_VALUE
          ? OTHER_SELECT_VALUE
          : known.has(strVal)
            ? strVal
            : OTHER_SELECT_VALUE;
    const otherTextareaValue = strVal === OTHER_SELECT_VALUE ? '' : strVal;

    const stopRow = (e: MouseEvent) => {
      if (isGlass) e.stopPropagation();
    };

    return (
      <div className="space-y-2" onMouseDown={stopRow} onClick={stopRow}>
        <select
          value={selectVal}
          disabled={disabled}
          onChange={(e) => {
            const v = e.target.value;
            if (v === OTHER_SELECT_VALUE) handleCellChange(rowIdx, col.key, OTHER_SELECT_VALUE);
            else handleCellChange(rowIdx, col.key, v);
          }}
          className={selectShellClass}
          style={selectArrowStyle}
        >
          <option value="">{selectPlaceholder}</option>
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
            value={otherTextareaValue}
            disabled={disabled}
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
    <table className="w-max min-w-full text-sm border-separate border-spacing-0 table-auto">
        <thead className={isGlass ? 'sticky top-0 z-10' : ''}>
          <tr className={isGlass ? 'bg-white/55 backdrop-blur-md' : 'bg-neutral-50'}>
            {payload.columns.map((col) => (
              <th
                key={col.key}
                style={{ minWidth: colMinWidth(col), maxWidth: col.key === 'id' ? 48 : undefined }}
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
                {col.label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, rowIdx) => (
            <tr
              key={rowIdx}
              role={isGlass ? 'button' : undefined}
              tabIndex={isGlass ? 0 : undefined}
              onClick={() => isGlass && handleGlassRowActivate(rowIdx)}
              onKeyDown={(e) => {
                if (!isGlass) return;
                if (e.key === 'Enter' || e.key === ' ') {
                  e.preventDefault();
                  handleGlassRowActivate(rowIdx);
                }
              }}
              className={
                isGlass
                  ? `border-b border-neutral-200/80 transition-colors last:border-b-0 outline-none focus-visible:ring-2 focus-visible:ring-[rgba(145,194,255,0.65)] focus-visible:ring-inset ${
                      selectedRowIdx === rowIdx
                        ? 'bg-[rgba(145,194,255,0.38)] text-neutral-900 shadow-[inset_3px_0_0_0_#91C2FF]'
                        : 'hover:bg-white/30'
                    } cursor-pointer`
                  : 'border-b border-neutral-100 hover:bg-neutral-50/50'
              }
            >
              {payload.columns.map((col) => {
                const isEditable = editableSet.has(col.key);
                const val = row[col.key];
                const strVal = val != null ? String(val) : '';

                const cellKey = `${rowIdx}:${col.key}`;
                const cellFlash = isEditable && validationFlashKey === cellKey;

                return (
                  <td
                    key={col.key}
                    style={{
                      minWidth: colMinWidth(col),
                      maxWidth: col.key === 'id' ? 48 : undefined,
                    }}
                    className={
                      col.key === 'id'
                        ? isGlass
                          ? 'px-1 py-2 align-middle text-center text-neutral-600'
                          : 'px-1 py-2 align-middle text-center'
                        : isGlass
                          ? 'px-2.5 py-3 align-middle text-neutral-700 break-words whitespace-normal'
                          : 'px-2.5 py-2 align-middle'
                    }
                  >
                    <div
                      key={
                        cellFlash ? `${cellKey}-v${validationCycle}` : cellKey
                      }
                      ref={isEditable ? setCellWrapRef(rowIdx, col.key) : undefined}
                      className={`min-w-0 ${cellFlash ? 'rumination-validation-cell-flash' : ''}`}
                      onAnimationEnd={(e) => {
                        if (e.target !== e.currentTarget) return;
                        const name = (e.animationName || '').split(',')[0]?.trim();
                        if (name !== 'rumination-cell-flash') return;
                        setValidationFlashKey((k) => (k === cellKey ? null : k));
                      }}
                    >
                      {isEditable &&
                      col.key === HYP_CONFIRM_KEY &&
                      filterStep >= 3 &&
                      filterStep <= 5 ? (
                        renderHypothesisConfirmCell(row, rowIdx, strVal)
                      ) : isEditable && col.options?.includes(hypothesisOtherLabel) ? (
                        renderSelectWithOther(col, rowIdx, strVal, hypothesisOtherLabel)
                      ) : isEditable && col.options?.length ? (
                        <select
                          value={strVal}
                          onChange={(e) => handleCellChange(rowIdx, col.key, e.target.value)}
                          onMouseDown={(e) => isGlass && e.stopPropagation()}
                          onClick={(e) => isGlass && e.stopPropagation()}
                          disabled={disabled}
                          className={selectShellClass}
                          style={selectArrowStyle}
                        >
                          <option value="">{selectPlaceholder}</option>
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
                            disabled={disabled}
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
                            disabled={disabled}
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
      <div className="rumination-beautiful-table-scroll rumination-beautiful-table-widget min-h-0 flex-1 overflow-x-auto overflow-y-auto">
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
      <div className={`flex min-h-0 flex-1 flex-col ${className}`}>
        <div className="mb-3 flex shrink-0 items-center justify-between gap-3">
          <h2 className="truncate text-lg font-semibold text-bd-fg">{cardTitle ?? '表格'}</h2>
          {tableHeaderActions}
        </div>
        {payload.guideText && (
          <p className="mb-2 shrink-0 text-sm leading-relaxed text-neutral-600">{payload.guideText}</p>
        )}
        {validationBanner && validationEmptyHint && (
          <div
            key={`rumination-val-banner-${validationCycle}`}
            role="alert"
            className="rumination-validation-banner--timed mb-2 shrink-0 overflow-hidden rounded-xl border border-amber-400/90 bg-amber-50 px-3 py-2.5 text-sm font-medium text-amber-950 shadow-sm"
            onAnimationEnd={(e) => {
              if (e.target !== e.currentTarget) return;
              const name = (e.animationName || '').split(',')[0]?.trim();
              if (name === 'rumination-banner-fade') setValidationBanner(false);
            }}
          >
            {validationEmptyHint}
          </div>
        )}
        {/* flex-1 + 表格区 flex-1：撑满左卡剩余高度，避免 max-h 下方大块留白 */}
        <div className="flex min-h-0 flex-1 flex-col">{tableBlock}</div>
      </div>
    );
  }

  return (
    <div
      className={`rumination-table-widget rounded-xl border border-neutral-200 bg-white/90 p-4 ${className}`}
    >
      {payload.guideText && (
        <p className="text-sm text-neutral-600 mb-3">{payload.guideText}</p>
      )}
      {validationBanner && validationEmptyHint && (
        <div
          key={`rumination-val-banner-${validationCycle}`}
          role="alert"
          className="rumination-validation-banner--timed mb-3 overflow-hidden rounded-lg border border-amber-400/90 bg-amber-50 px-3 py-2 text-sm font-medium text-amber-950"
          onAnimationEnd={(e) => {
            if (e.target !== e.currentTarget) return;
            const name = (e.animationName || '').split(',')[0]?.trim();
            if (name === 'rumination-banner-fade') setValidationBanner(false);
          }}
        >
          {validationEmptyHint}
        </div>
      )}
      {tableBlock}
      <div className="mt-3 flex justify-end">{tableHeaderActions}</div>
    </div>
  );
}
