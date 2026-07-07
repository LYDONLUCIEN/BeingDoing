'use client';

/**
 * v4 可编辑结论卡
 *
 * - hypothesis 是核心字段(必填),支持 string 或 dict(分优势)
 * - 其他 4 个字段选填
 * - 用户可在 textarea 中直接编辑,失焦自动保存(走 PATCH 端点)
 * - 操作按钮:确认(进只读)、继续讨论、放弃
 *
 * 见 wiki/开发文档/0707-tag1.6.0.md 第八节"用户对结论卡的操作"
 */

import { useEffect, useState } from 'react';
import { useRuminationV4Store } from '@/stores/ruminationV4Store';
import { ConclusionCard } from '@/lib/explore/ruminationV4Api';

interface Props {
  comboId: string;
  card: ConclusionCard;
  strengths: string[];
}

export default function ConclusionCardEditable({ comboId, card, strengths }: Props) {
  const { patchCard, setStatus } = useRuminationV4Store();
  const [localHypothesis, setLocalHypothesis] = useState<string | Record<string, string>>(
    card.hypothesis || ''
  );
  const [localMotivation, setLocalMotivation] = useState(card.motivation || '');
  const [saving, setSaving] = useState(false);

  // 卡内容变化时同步本地状态
  useEffect(() => {
    setLocalHypothesis(card.hypothesis || '');
    setLocalMotivation(card.motivation || '');
  }, [card.updated_at]);

  const isDict = typeof localHypothesis === 'object' && localHypothesis !== null;

  const handleSave = async () => {
    setSaving(true);
    try {
      await patchCard(comboId, { hypothesis: localHypothesis, motivation: localMotivation });
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="border-2 border-bd-phase-rumination/30 rounded-xl bg-gradient-to-br from-orange-50 to-yellow-50 p-4 shadow-sm">
      <div className="flex items-center justify-between mb-3">
        <h3 className="font-bold text-bd-phase-rumination">结论卡</h3>
        {saving && <span className="text-xs text-gray-400">保存中…</span>}
      </div>

      {/* hypothesis(核心)*/}
      <div className="mb-3">
        <label className="text-xs font-medium text-gray-600 block mb-1">
          假设(核心)
        </label>
        {isDict ? (
          <div className="space-y-2">
            {Object.entries(localHypothesis as Record<string, string>).map(([k, v]) => (
              <div key={k}>
                <div className="text-xs text-gray-500 mb-1">{k}</div>
                <textarea
                  className="w-full p-2 border border-gray-200 rounded text-sm bg-white resize-none focus:outline-none focus:border-orange-300"
                  rows={2}
                  value={v}
                  onChange={(e) =>
                    setLocalHypothesis({ ...(localHypothesis as Record<string, string>), [k]: e.target.value })
                  }
                  onBlur={handleSave}
                />
              </div>
            ))}
          </div>
        ) : (
          <textarea
            className="w-full p-2 border border-gray-200 rounded text-sm bg-white resize-none focus:outline-none focus:border-orange-300"
            rows={4}
            value={localHypothesis as string}
            onChange={(e) => setLocalHypothesis(e.target.value)}
            onBlur={handleSave}
            placeholder="我假设这个方向能带给我什么…"
          />
        )}
      </div>

      {/* motivation */}
      <div className="mb-3">
        <label className="text-xs font-medium text-gray-600 block mb-1">动机</label>
        <input
          className="w-full p-2 border border-gray-200 rounded text-sm bg-white focus:outline-none focus:border-orange-300"
          value={localMotivation}
          onChange={(e) => setLocalMotivation(e.target.value)}
          onBlur={handleSave}
        />
      </div>

      {/* 其他字段(只读展示)*/}
      <div className="grid grid-cols-3 gap-2 text-xs">
        <div>
          <div className="text-gray-500">工作目的</div>
          <div className="text-gray-800">{card.work_purposes?.join('、') || '—'}</div>
        </div>
        <div>
          <div className="text-gray-500">激情感受</div>
          <div className="text-gray-800">{card.passion_mark || '—'}</div>
        </div>
        <div>
          <div className="text-gray-500">时机</div>
          <div className="text-gray-800">{card.timing_mark || '—'}</div>
        </div>
      </div>

      {/* 操作按钮 */}
      <div className="flex gap-2 mt-4 pt-3 border-t border-orange-100">
        <button
          type="button"
          className="flex-1 py-1.5 rounded bg-bd-phase-rumination text-white text-sm hover:opacity-90"
          onClick={async () => {
            await handleSave();
            await setStatus(comboId, 'concluded');
          }}
        >
          确认
        </button>
        <button
          type="button"
          className="flex-1 py-1.5 rounded border border-gray-200 text-gray-600 text-sm hover:bg-gray-50"
          onClick={() => setStatus(comboId, 'discussing')}
        >
          继续讨论
        </button>
        <button
          type="button"
          className="flex-1 py-1.5 rounded border border-red-200 text-red-500 text-sm hover:bg-red-50"
          onClick={() => {
            if (confirm('放弃这个组合?将不出结论卡。')) {
              setStatus(comboId, 'abandoned');
            }
          }}
        >
          放弃
        </button>
      </div>
    </div>
  );
}
