'use client';

import { useMemo, useState } from 'react';
import MessageContent from '@/components/explore/MessageContent';
import { formatLocalDateTime } from '@/lib/utils/formatTime';

/**
 * Admin 会话详情：Rumination 表格区块
 *
 * 渲染：前置结论(keywords) + 每个 step 区块(表格 + 该 step 对话切片)。
 * step 区块默认展开，单击标题条折叠整个区块(表格+对话)。
 *
 * 数据来源：admin 会话详情接口返回的
 *   detail.rumination_tables  —— prerequisites + steps[1-7] + combo
 *   detail.conversation_by_step —— {step_str: [msg]} | {_unified: [msg]}
 */

type StepStatus = 'submitted' | 'submitted_empty' | 'skipped' | 'not_reached';

interface StepData {
  status: StepStatus;
  row_count: number;
  columns: string[];
  rows: Record<string, any>[];
}

interface RuminationTables {
  report_id?: string;
  prerequisites?: Record<string, string[]>;
  steps?: Record<string, StepData>;
  combo_matrix?: any[] | null;
  combo_conclusions?: Record<string, any> | null;
}

interface Msg {
  role?: string;
  content?: string;
  card_payload?: any;
  message_id?: string;
  id?: string;
  created_at?: string;
  combo_id?: string;
}

interface Props {
  tables: RuminationTables;
  conversationByStep?: Record<string, Msg[]>;
}

const STATUS_LABEL: Record<StepStatus, string> = {
  submitted: '✅ 已提交',
  submitted_empty: '✅ 已提交（0 行）',
  skipped: '⏭ 已跳过',
  not_reached: '— 未进行',
};

const STATUS_COLOR: Record<StepStatus, string> = {
  submitted: 'text-emerald-600',
  submitted_empty: 'text-emerald-600',
  skipped: 'text-amber-600',
  not_reached: 'text-bd-subtle',
};

const PHASE_LABEL: Record<string, string> = {
  values: '价值观',
  strengths: '优势',
  interests: '热爱',
  purpose: '使命',
};

export default function RuminationTablesView({ tables, conversationByStep }: Props) {
  const steps = tables.steps || {};
  const stepKeys = useMemo(() => Object.keys(steps).sort((a, b) => Number(a) - Number(b)), [steps]);
  const prereq = tables.prerequisites || {};
  const hasPrereq = Object.values(prereq).some((arr) => arr && arr.length > 0);
  const unified = conversationByStep?._unified;
  // 只有当 conversation_by_step 仅含 _unified（无任何数字 step key）时，才算真正的「老数据兜底」。
  // 此时 unified 是完整对话，挂在 step1 展示；否则按各 step 的切片显示。
  const hasStepKeys = Object.keys(conversationByStep || {}).some((k) => k !== '_unified');
  const isUnifiedOnly = !hasStepKeys && Array.isArray(unified) && unified.length > 0;

  return (
    <div className="space-y-4">
      {/* 前置结论 */}
      {hasPrereq && (
        <section className="rounded-xl border border-bd-border bg-bd-overlay-md p-4">
          <h3 className="text-sm font-medium mb-2" style={{ color: 'var(--bd-fg)' }}>
            前置结论
          </h3>
          <ul className="text-[13px] space-y-1" style={{ color: 'var(--bd-fg)' }}>
            {(['values', 'strengths', 'interests', 'purpose'] as const).map((ph) => {
              const kws = prereq[ph] || [];
              if (!kws.length) return null;
              return (
                <li key={ph}>
                  <span className="font-medium">{PHASE_LABEL[ph] || ph}：</span>
                  <span>{kws.join('、')}</span>
                </li>
              );
            })}
          </ul>
        </section>
      )}

      {/* 每个 step 区块 */}
      {stepKeys.map((sk) => (
        <StepBlock
          key={sk}
          stepKey={sk}
          step={steps[sk]}
          comboMatrix={Number(sk) === 3 ? tables.combo_matrix : null}
          comboConclusions={Number(sk) === 3 ? tables.combo_conclusions : null}
          msgs={isUnifiedOnly ? (Number(sk) === 1 ? (unified || []) : []) : (conversationByStep?.[sk] || [])}
          isUnified={isUnifiedOnly}
        />
      ))}
    </div>
  );
}

function StepBlock({
  stepKey,
  step,
  comboMatrix,
  comboConclusions,
  msgs,
  isUnified,
}: {
  stepKey: string;
  step: StepData;
  comboMatrix: any[] | null | undefined;
  comboConclusions: Record<string, any> | null | undefined;
  msgs: Msg[];
  isUnified: boolean;
}) {
  const [open, setOpen] = useState(true);
  const status = step.status || 'not_reached';
  const hasTable = step.row_count > 0 && step.columns.length > 0;

  return (
    <section className="rounded-xl border border-bd-border bg-bd-card overflow-hidden">
      {/* 标题条（单击折叠整个区块） */}
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="w-full flex items-center justify-between px-4 py-2.5 text-left hover:bg-bd-overlay-md transition-colors"
      >
        <div className="flex items-center gap-2">
          <span className="text-[11px] text-bd-subtle">{open ? '▼' : '▶'}</span>
          <span className="text-sm font-medium" style={{ color: 'var(--bd-fg)' }}>
            Step {stepKey}
          </span>
          <span className="text-[11px] text-bd-subtle">({step.row_count} 行)</span>
          <span className={`text-[11px] ${STATUS_COLOR[status]}`}>{STATUS_LABEL[status]}</span>
        </div>
      </button>

      {open && (
        <div className="px-4 pb-4 space-y-3">
          {/* 表格 */}
          {hasTable && (
            <div className="overflow-x-auto">
              <table className="text-[12px] border-collapse" style={{ color: 'var(--bd-fg)' }}>
                <thead>
                  <tr>
                    {step.columns.map((c) => (
                      <th
                        key={c}
                        className="border border-bd-border px-2 py-1 bg-bd-overlay-md text-left font-medium whitespace-nowrap"
                      >
                        {c}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {step.rows.map((row, i) => (
                    <tr key={row.id || i}>
                      {step.columns.map((c) => (
                        <td
                          key={c}
                          className="border border-bd-border px-2 py-1 align-top whitespace-normal break-words"
                          style={{ maxWidth: '320px' }}
                        >
                          {formatCell(row[c])}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {/* step3 组合矩阵 */}
          {comboMatrix && comboMatrix.length > 0 && (
            <div>
              <p className="text-[12px] font-medium mb-1" style={{ color: 'var(--bd-fg)' }}>
                组合矩阵
              </p>
              <div className="overflow-x-auto">
                <table className="text-[12px] border-collapse" style={{ color: 'var(--bd-fg)' }}>
                  <thead>
                    <tr>
                      <th className="border border-bd-border px-2 py-1 bg-bd-overlay-md">combo_id</th>
                      <th className="border border-bd-border px-2 py-1 bg-bd-overlay-md">热爱</th>
                      <th className="border border-bd-border px-2 py-1 bg-bd-overlay-md">优势</th>
                    </tr>
                  </thead>
                  <tbody>
                    {comboMatrix.map((m, i) => (
                      <tr key={m?.combo_id || i}>
                        <td className="border border-bd-border px-2 py-1">{m?.combo_id || ''}</td>
                        <td className="border border-bd-border px-2 py-1">{m?.passion_name || ''}</td>
                        <td className="border border-bd-border px-2 py-1">{m?.strength_name || ''}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {/* step3 组合讨论结论 */}
          {comboConclusions && Object.keys(comboConclusions).length > 0 && (
            <div>
              <p className="text-[12px] font-medium mb-1" style={{ color: 'var(--bd-fg)' }}>
                组合讨论结论
              </p>
              <pre className="text-[11px] whitespace-pre-wrap bg-bd-overlay-md rounded-lg p-2 border border-bd-border">
                {JSON.stringify(comboConclusions, null, 2)}
              </pre>
            </div>
          )}

          {/* 对话记录 */}
          <div>
            <p className="text-[12px] font-medium mb-2" style={{ color: 'var(--bd-fg)' }}>
              对话记录
            </p>
            {isUnified && Number(stepKey) !== 1 ? (
              <p className="text-[11px] text-bd-subtle">（完整对话见 Step 1）</p>
            ) : isUnified && Number(stepKey) === 1 ? (
              <>
                <p className="text-[11px] text-amber-600 mb-2">
                  该会话为旧格式，对话未按步骤细分，完整对话如下：
                </p>
                <DialogueList msgs={msgs} />
              </>
            ) : Number(stepKey) === 3 && comboMatrix && comboMatrix.length > 0 ? (
              <ComboGroupedDialogue msgs={msgs} comboMatrix={comboMatrix} comboConclusions={comboConclusions} />
            ) : msgs.length > 0 ? (
              <DialogueList msgs={msgs} />
            ) : (
              <p className="text-[11px] text-bd-subtle">（本步骤无对话记录）</p>
            )}
          </div>
        </div>
      )}
    </section>
  );
}

function ComboGroupedDialogue({
  msgs,
  comboMatrix,
  comboConclusions,
}: {
  msgs: Msg[];
  comboMatrix: any[] | null | undefined;
  comboConclusions: Record<string, any> | null | undefined;
}) {
  // 按 combo_id 分组（无 combo_id 的归到 __general）
  const groups: Record<string, Msg[]> = {};
  const order: string[] = [];
  for (const m of msgs) {
    const cid = m?.combo_id || '__general';
    if (!groups[cid]) {
      groups[cid] = [];
      order.push(cid);
    }
    groups[cid].push(m);
  }

  // combo_id -> 标题（热爱×优势）
  const titleMap: Record<string, string> = {};
  for (const cm of comboMatrix || []) {
    if (cm?.combo_id) {
      const tag = cm.is_non_matching ? '（标记为不匹配）' : '';
      titleMap[cm.combo_id] = `组合 ${cm.combo_id}：${cm.passion_name || '?'} × ${cm.strength_name || '?'}${tag}`;
    }
  }

  // 排序：按 combo_matrix 顺序；__general（step3 全表讨论）放到所有 combo 之后
  const matrixOrder = (comboMatrix || []).map((cm) => cm?.combo_id).filter(Boolean);
  order.sort((a, b) => {
    if (a === '__general') return 1;
    if (b === '__general') return -1;
    const ia = matrixOrder.indexOf(a);
    const ib = matrixOrder.indexOf(b);
    if (ia >= 0 && ib >= 0) return ia - ib;
    if (ia >= 0) return -1;
    if (ib >= 0) return 1;
    return a.localeCompare(b);
  });

  return (
    <div className="space-y-3">
      {order.map((cid) => {
        const groupMsgs = groups[cid] || [];
        if (groupMsgs.length === 0) return null;
        const isGeneral = cid === '__general';
        const title = isGeneral ? 'Step 3 全表讨论（discussion）' : (titleMap[cid] || `组合 ${cid}`);
        const conc = !isGeneral && comboConclusions ? comboConclusions[cid] : null;
        const concState = conc?.state;
        const concText = conc?.text;
        return (
          <div key={cid} className="rounded-lg border border-bd-border bg-bd-overlay-md/50 p-2.5">
            <div className="flex items-center gap-2 mb-2 pb-1.5 border-b border-bd-border">
              <span className="text-[12px] font-medium" style={{ color: 'var(--bd-fg)' }}>{title}</span>
              <span className="text-[10px] text-bd-subtle">{groupMsgs.length} 条</span>
              {concState && (
                <span className={`text-[10px] px-1.5 py-0.5 rounded ${concState === 'confirmed' ? 'bg-emerald-100 text-emerald-700' : concState === 'skipped' ? 'bg-amber-100 text-amber-700' : 'bg-gray-100 text-gray-600'}`}>
                  {concState === 'confirmed' ? '已确认假设' : concState === 'skipped' ? '已跳过' : concState}
                </span>
              )}
            </div>
            {concText && (
              <p className="text-[11px] mb-2 p-1.5 bg-bd-card rounded border border-bd-border" style={{ color: 'var(--bd-fg)' }}>
                <span className="font-medium">确认的假设：</span>{concText}
              </p>
            )}
            <DialogueList msgs={groupMsgs} />
          </div>
        );
      })}
    </div>
  );
}

function DialogueList({ msgs }: { msgs: Msg[] }) {
  return (
    <div className="space-y-2">
      {msgs.map((msg, idx) => {
        const role = String(msg?.role || 'assistant');
        const key = String(msg?.message_id || msg?.id || idx);
        const isUser = role === 'user';
        const title = isUser ? '用户' : role;
        let content = String(msg?.content || '');
        if ((role === 'conclusion_card' || role === 'table') && !content.trim() && msg?.card_payload) {
          content = JSON.stringify(msg.card_payload, null, 2);
        }
        return (
          <div
            key={key}
            className={`rounded-lg border p-2.5 ${isUser ? 'bg-blue-50 border-blue-200' : 'bg-bd-overlay-md border-bd-border'}`}
          >
            <div className="flex items-center justify-between mb-1.5">
              <p className="text-[10px] font-medium uppercase tracking-wide">{title}</p>
              <p className="text-[10px] text-bd-subtle">{msg?.created_at ? formatLocalDateTime(msg.created_at) : ''}</p>
            </div>
            <MessageContent content={content} markdown className="text-[12px]" colorMode="light" />
          </div>
        );
      })}
    </div>
  );
}

function formatCell(value: unknown): string {
  if (value === null || value === undefined) return '';
  if (typeof value === 'string') return value;
  if (typeof value === 'number' || typeof value === 'boolean') return String(value);
  try {
    return JSON.stringify(value);
  } catch {
    return String(value);
  }
}
