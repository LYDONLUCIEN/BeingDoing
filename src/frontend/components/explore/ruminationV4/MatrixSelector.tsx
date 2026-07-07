'use client';

/**
 * v4 矩阵选择器(入口)
 *
 * 用户在此:
 * 1. 选定一个热爱(从 matrix_snapshot.passions)
 * 2. 勾选若干优势(从 matrix_snapshot.strengths,可单选/多选)
 * 3. 点击"确认创建组合"→ 调 createCombo → 进入 combo_session 视图
 *
 * 见 wiki/开发文档/0707-tag1.6.0.md 第二节"阶段一:矩阵页"
 */

import { useState } from 'react';
import { useRuminationV4Store } from '@/stores/ruminationV4Store';

export default function MatrixSelector() {
  const { state, createCombo } = useRuminationV4Store();
  const [selectedPassion, setSelectedPassion] = useState<string | null>(null);
  const [selectedStrengths, setSelectedStrengths] = useState<string[]>([]);
  const [submitting, setSubmitting] = useState(false);

  if (!state) return null;
  const passions = state.matrix_snapshot.passions || [];
  const strengths = state.matrix_snapshot.strengths || [];

  const toggleStrength = (s: string) => {
    setSelectedStrengths((prev) => (prev.includes(s) ? prev.filter((x) => x !== s) : [...prev, s]));
  };

  const canSubmit = selectedPassion && selectedStrengths.length > 0 && !submitting;

  const handleSubmit = async () => {
    if (!canSubmit) return;
    setSubmitting(true);
    try {
      await createCombo(selectedPassion!, selectedStrengths);
      // 创建成功后 store 会切到 combo_session 视图,本组件自动 unmount
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="flex flex-col h-full p-6 bg-white">
      <h2 className="text-xl font-bold text-bd-phase-rumination mb-2">选择你的组合</h2>
      <p className="text-sm text-gray-500 mb-6">
        选一个「热爱」,再勾选若干个「优势」(可多选)。确认后我们会进入针对这个组合的深度对话。
      </p>

      {/* 热爱选择(单选)*/}
      <div className="mb-6">
        <div className="text-sm font-medium text-gray-700 mb-2">热爱(选 1 个)</div>
        <div className="flex flex-wrap gap-2">
          {passions.map((p) => (
            <button
              key={p}
              type="button"
              onClick={() => setSelectedPassion(p)}
              className={`px-4 py-2 rounded-lg border-2 transition ${
                selectedPassion === p
                  ? 'border-orange-400 bg-orange-50 text-orange-700'
                  : 'border-gray-200 bg-white text-gray-700 hover:border-orange-200'
              }`}
            >
              {p}
            </button>
          ))}
          {passions.length === 0 && (
            <span className="text-xs text-gray-400">暂无可选热爱(请先完成前置阶段)</span>
          )}
        </div>
      </div>

      {/* 优势选择(多选)*/}
      <div className="mb-6 flex-1">
        <div className="text-sm font-medium text-gray-700 mb-2">
          优势(可选多个,当前选 {selectedStrengths.length} 个)
        </div>
        <div className="flex flex-wrap gap-2">
          {strengths.map((s) => (
            <button
              key={s}
              type="button"
              onClick={() => toggleStrength(s)}
              className={`px-3 py-1.5 rounded-lg border transition text-sm ${
                selectedStrengths.includes(s)
                  ? 'border-green-500 bg-green-50 text-green-700'
                  : 'border-gray-200 bg-white text-gray-600 hover:border-green-300'
              }`}
            >
              {s}
            </button>
          ))}
          {strengths.length === 0 && (
            <span className="text-xs text-gray-400">暂无可选优势</span>
          )}
        </div>
      </div>

      {/* 确认按钮 */}
      <div className="pt-4 border-t border-gray-100">
        <button
          type="button"
          disabled={!canSubmit}
          onClick={handleSubmit}
          className={`w-full py-3 rounded-lg font-medium transition ${
            canSubmit
              ? 'bg-bd-phase-rumination text-white hover:opacity-90'
              : 'bg-gray-100 text-gray-400 cursor-not-allowed'
          }`}
        >
          {submitting ? '创建中…' : '确认创建组合'}
        </button>
        {!selectedPassion && (
          <p className="text-xs text-gray-400 mt-2 text-center">请先选一个热爱</p>
        )}
      </div>
    </div>
  );
}
