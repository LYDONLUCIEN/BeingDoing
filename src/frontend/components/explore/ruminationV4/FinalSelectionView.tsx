'use client';

/**
 * v4 第 8 步:最终选择视图
 *
 * - 展示所有 concluded 状态的结论卡(并排)
 * - 用户勾选 1-3 个
 * - "返回矩阵"按钮可回头(A1)
 * - "提交最终选择"按钮锁定
 *
 * 见 wiki/开发文档/0707-tag1.6.0.md 第二节"阶段三"
 */

import { useEffect, useState } from 'react';
import { useRuminationV4Store } from '@/stores/ruminationV4Store';
import { ConclusionCard } from '@/lib/explore/ruminationV4Api';

export default function FinalSelectionView() {
  const { state, selectFinal, submitFinal } = useRuminationV4Store();
  const [selected, setSelected] = useState<string[]>([]);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (state?.final_selection?.selected_combo_ids) {
      setSelected(state.final_selection.selected_combo_ids);
    }
  }, [state?.final_selection]);

  if (!state) return null;

  const concludedCombos = state.combo_sessions.filter((c) => c.conclusion_card);

  const toggle = (id: string) => {
    setSelected((prev) => {
      if (prev.includes(id)) return prev.filter((x) => x !== id);
      if (prev.length >= 3) return prev; // 最多 3 个
      return [...prev, id];
    });
  };

  const handleSelect = async () => {
    if (selected.length < 1 || selected.length > 3) return;
    await selectFinal(selected);
  };

  const handleSubmit = async () => {
    setSubmitting(true);
    try {
      await selectFinal(selected);
      await submitFinal();
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="flex-1 overflow-y-auto p-6 bg-gradient-to-br from-orange-50/30 to-white">
      <div className="max-w-5xl mx-auto">
        <h2 className="text-2xl font-bold text-bd-phase-rumination mb-2">最终选择</h2>
        <p className="text-sm text-gray-500 mb-6">
          从所有已确认的方向中,选定 1-3 个作为你的最终方向。已选 {selected.length} / 3。
        </p>

        {concludedCombos.length === 0 ? (
          <div className="text-center py-12 text-gray-400">
            还没有任何已确认的结论卡。请回到矩阵页,为某个组合完成对话与确认。
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4 mb-8">
            {concludedCombos.map((c) => {
              const isSel = selected.includes(c.combo_id);
              return (
                <div
                  key={c.combo_id}
                  className={`relative p-4 rounded-xl border-2 cursor-pointer transition ${
                    isSel
                      ? 'border-bd-phase-rumination bg-orange-50'
                      : 'border-gray-200 bg-white hover:border-orange-200'
                  }`}
                  onClick={() => toggle(c.combo_id)}
                >
                  <div className="absolute top-2 right-2">
                    <input
                      type="checkbox"
                      checked={isSel}
                      onChange={() => toggle(c.combo_id)}
                      className="w-5 h-5 accent-orange-500"
                    />
                  </div>
                  <div className="text-xs text-gray-500 mb-1">
                    {c.passion} · {c.strengths.join(' + ')}
                  </div>
                  <CardPreview card={c.conclusion_card!} />
                </div>
              );
            })}
          </div>
        )}

        <div className="flex gap-3 sticky bottom-0 bg-white/80 backdrop-blur py-3 border-t border-gray-100">
          <button
            type="button"
            onClick={handleSelect}
            disabled={selected.length < 1 || selected.length > 3}
            className="flex-1 py-2.5 rounded-lg border border-gray-300 text-gray-700 hover:bg-gray-50 disabled:opacity-50"
          >
            保存选择(可继续回矩阵调整)
          </button>
          <button
            type="button"
            onClick={handleSubmit}
            disabled={selected.length < 1 || selected.length > 3 || submitting}
            className="flex-1 py-2.5 rounded-lg bg-bd-phase-rumination text-white hover:opacity-90 disabled:opacity-50"
          >
            {submitting ? '提交中…' : '提交最终方向(锁定)'}
          </button>
        </div>
      </div>
    </div>
  );
}

function CardPreview({ card }: { card: ConclusionCard }) {
  const hyp = card.hypothesis;
  return (
    <div className="text-sm">
      {typeof hyp === 'string' || hyp === null ? (
        <div className="text-gray-800 line-clamp-3">{(hyp as string) || '(暂无)'}</div>
      ) : (
        <div className="space-y-1">
          {Object.entries(hyp).map(([k, v]) => (
            <div key={k} className="text-xs">
              <span className="text-gray-500">{k}:</span> <span className="text-gray-800">{v}</span>
            </div>
          ))}
        </div>
      )}
      <div className="mt-2 flex flex-wrap gap-1 text-[10px] text-gray-400">
        {card.work_purposes?.map((w) => (
          <span key={w} className="px-1.5 py-0.5 rounded bg-gray-100">{w}</span>
        ))}
        {card.passion_mark && <span className="px-1.5 py-0.5 rounded bg-gray-100">{card.passion_mark}</span>}
        {card.timing_mark && <span className="px-1.5 py-0.5 rounded bg-gray-100">{card.timing_mark}</span>}
      </div>
    </div>
  );
}
