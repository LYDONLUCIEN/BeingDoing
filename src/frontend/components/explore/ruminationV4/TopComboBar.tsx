'use client';

/**
 * v4 顶部 combo tag 条
 *
 * - 横排展示所有 combo_session 的 tag(combo_1、combo_2、...)
 * - 可滚轮左右滑动
 * - 点击切换 active(直接切换,自动保存草稿)
 * - 每个 tag 可删除(二次确认)
 * - 右侧"+"按钮 = 回到矩阵页新建组合
 *
 * 见 wiki/开发文档/0707-tag1.6.0.md 第二节"顶部 combo tag 条"
 */

import { useState } from 'react';
import { useRuminationV4Store } from '@/stores/ruminationV4Store';

export default function TopComboBar() {
  const { state, switchCombo, removeCombo } = useRuminationV4Store();
  const [confirmingId, setConfirmingId] = useState<string | null>(null);
  if (!state) return null;

  const combos = state.combo_sessions || [];
  const activeId = state.active_combo_id;

  return (
    <div className="flex items-center gap-2 px-4 py-2 border-b border-gray-100 bg-white overflow-x-auto">
      {combos.map((c, idx) => {
        const isActive = c.combo_id === activeId;
        const isConfirming = confirmingId === c.combo_id;
        return (
          <div
            key={c.combo_id}
            className={`flex items-center gap-1 px-3 py-1 rounded-full border whitespace-nowrap text-sm cursor-pointer transition ${
              isActive
                ? 'border-bd-phase-rumination bg-bd-phase-rumination/10 text-bd-phase-rumination'
                : c.status === 'abandoned'
                ? 'border-gray-200 bg-gray-50 text-gray-400 line-through'
                : 'border-gray-200 bg-white text-gray-600 hover:border-gray-300'
            }`}
            onClick={() => !isConfirming && switchCombo(c.combo_id)}
            title={`${c.passion} + ${c.strengths.join(', ')}`}
          >
            <span className="font-mono text-xs opacity-70">#{String(idx + 1).padStart(2, '0')}</span>
            <span className="truncate max-w-[140px]">
              {c.passion} · {c.strengths.join('+')}
            </span>
            {c.status === 'concluded' && c.conclusion_card && (
              <span className="ml-1 text-xs">✓</span>
            )}
            {isConfirming ? (
              <span
                className="ml-1 flex items-center gap-1 text-xs"
                onClick={(e) => e.stopPropagation()}
              >
                <button
                  type="button"
                  className="text-red-500 hover:underline"
                  onClick={async () => {
                    await removeCombo(c.combo_id);
                    setConfirmingId(null);
                  }}
                >
                  确认删
                </button>
                <button
                  type="button"
                  className="text-gray-400 hover:underline"
                  onClick={() => setConfirmingId(null)}
                >
                  取消
                </button>
              </span>
            ) : (
              <button
                type="button"
                className="ml-1 text-gray-300 hover:text-red-500 text-xs"
                onClick={(e) => {
                  e.stopPropagation();
                  setConfirmingId(c.combo_id);
                }}
                title="删除该组合"
              >
                ×
              </button>
            )}
          </div>
        );
      })}

      {combos.length === 0 && (
        <span className="text-xs text-gray-400">还没有组合,在下方矩阵选择后创建</span>
      )}
    </div>
  );
}
