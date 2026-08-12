'use client';

/**
 * v4 终选方向卡片（设计稿：uidesign/beautiful/nto3.png）
 *
 * 卡片结构（2 列网格中的单卡）：
 * - 左上：方形圆角紫底编号徽章（01/02/…）
 * - 「热爱」小标签 + 紫色标题（combo.passion，line-clamp-2，悬停看全文）
 * - 「优势」小标签 + 顿号连接文字（combo.strengths，单行缩略，悬停看全文）
 * - 灰色 hypothesis 正文（line-clamp-3 缩略，悬停气泡看全文）
 * - 平衡点判定不通过时：标题旁 ⚠ 图标（悬停显示原因），不改变卡面布局
 *
 * 选中态：紫边 + 紫色阴影 + 右上 ✓ + 徽章/标题高亮（正文不变紫）；
 * 默认态 hover：边框变紫 + 轻微上浮，提示可点击。
 */

import { useState } from 'react';
import HoverTooltip from '@/components/ui/HoverTooltip';
import type { ComboSession, ConclusionCard } from '@/lib/explore/ruminationV4Api';

/** 终选统一主题色（rumination 主题紫，与主按钮渐变 #826aff→#553df2 同族） */
export const THEME_PURPLE = {
  color: '#553df2',
  tagBg: '#f4f1ff',
  tagColor: '#5d49ef',
};

interface Props {
  index: number;
  combo: ComboSession;
  card: ConclusionCard | null;
  selected: boolean;
  /** 已最终提交：锁定只读，不可改选 */
  locked: boolean;
  onToggle: (comboId: string) => void;
}

/** 防御：dict 形态已废弃，统一转纯字符串 */
function hypToString(h: ConclusionCard['hypothesis']): string {
  if (!h) return '';
  if (typeof h === 'string') return h;
  return Object.values(h).filter(Boolean).join('\n');
}

export default function V4FinalSelectionCard({
  index,
  combo,
  card,
  selected,
  locked,
  onToggle,
}: Props) {
  const [hovered, setHovered] = useState(false);

  const hypothesis = hypToString(card?.hypothesis ?? null).trim();
  const desc =
    hypothesis || `基于「${combo.passion}」与「${combo.strengths.join('、')}」的探索方向。`;
  const strengthsText = combo.strengths.join('、');
  const balanceFailed = card?.balance_found === false;
  const failReason = card?.balance_fail_reason?.trim() || '未找到平衡点';

  const interactive = !locked;
  const highlight = selected || (interactive && hovered);

  return (
    <button
      type="button"
      onClick={() => onToggle(combo.combo_id)}
      disabled={locked}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      className="direction-card relative flex flex-col rounded-[15px] border text-left transition-all duration-200"
      style={{
        background: selected ? THEME_PURPLE.tagBg : '#f8f7fe',
        borderColor: selected
          ? THEME_PURPLE.color
          : highlight
            ? '#b3a6f5'
            : '#e6e2f5',
        borderWidth: selected ? '2px' : '1px',
        padding: selected ? '17px' : '18px',
        boxShadow: selected
          ? `0 10px 24px ${THEME_PURPLE.color}26`
          : highlight
            ? '0 8px 18px rgba(83,61,242,0.12)'
            : 'none',
        transform: interactive && hovered && !selected ? 'translateY(-2px)' : 'none',
        cursor: locked ? 'default' : 'pointer',
      }}
    >
      {/* 方形圆角编号徽章 */}
      <span
        className="direction-index grid h-9 w-9 place-items-center rounded-[10px] text-[13px] font-extrabold text-white"
        style={{
          background: selected
            ? 'linear-gradient(135deg,#826aff,#553df2)'
            : THEME_PURPLE.color,
          boxShadow: `0 5px 12px ${THEME_PURPLE.color}${selected ? '4d' : '30'}`,
        }}
      >
        {String(index + 1).padStart(2, '0')}
      </span>

      {/* 右上角勾选标记（仅选中时显示） */}
      <span
        className="direction-check absolute right-3 top-3 grid h-[22px] w-[22px] place-items-center rounded-[6px] text-white"
        style={{
          background: THEME_PURPLE.color,
          display: selected ? 'grid' : 'none',
          border: '2px solid white',
        }}
      >
        ✓
      </span>

      {/* 热爱：小标签 + 标题 */}
      <div className="mt-3 flex items-center gap-2">
        <span
          className="shrink-0 rounded-md px-1.5 py-0.5 text-[11px] font-medium"
          style={{ background: '#ece9f7', color: '#8b86a8' }}
        >
          热爱
        </span>
        <HoverTooltip content={combo.passion} className="min-w-0">
          <span
            className="line-clamp-2 text-[15px] font-bold leading-snug"
            style={{ color: selected || highlight ? THEME_PURPLE.color : '#5d49ef' }}
          >
            {combo.passion}
          </span>
        </HoverTooltip>
        {balanceFailed && (
          <HoverTooltip content={`⚠ 不推荐：${failReason}`} maxWidth={280}>
            <span className="shrink-0 self-start text-[13px]" style={{ color: '#d97706' }}>
              ⚠
            </span>
          </HoverTooltip>
        )}
      </div>

      {/* 优势：小标签 + 顿号连接文字（单行缩略） */}
      <div className="mt-2 flex items-center gap-2">
        <span
          className="shrink-0 rounded-md px-1.5 py-0.5 text-[11px] font-medium"
          style={{ background: '#ece9f7', color: '#8b86a8' }}
        >
          优势
        </span>
        <HoverTooltip content={strengthsText} className="min-w-0 flex-1">
          <span className="block truncate text-[13px] font-semibold text-[#33415c]">
            {strengthsText}
          </span>
        </HoverTooltip>
      </div>

      {/* hypothesis 正文（3 行缩略，悬停看全文） */}
      <HoverTooltip content={desc} className="mt-3 block">
        <span className="line-clamp-3 text-[13px] leading-relaxed text-[#6b7686]">
          {desc}
        </span>
      </HoverTooltip>
    </button>
  );
}
