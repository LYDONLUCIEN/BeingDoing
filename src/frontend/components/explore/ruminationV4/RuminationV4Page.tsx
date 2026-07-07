'use client';

/**
 * Rumination v4 主入口
 *
 * 根据 main_section 渲染:
 * - matrix         → MatrixSelector(选择热爱+优势)
 * - combo_session  → ComboSessionView(某个组合的对话)
 * - final_selection→ FinalSelectionView(第 8 步)
 * - end            → 完成页
 *
 * 顶部永远显示 TopComboBar(tag 条 + 新建按钮)
 *
 * 见 wiki/开发文档/0707-tag1.6.0.md 第九节"组件树"
 */

import { useEffect } from 'react';
import { useRuminationV4Store } from '@/stores/ruminationV4Store';
import TopComboBar from './TopComboBar';
import MatrixSelector from './MatrixSelector';
import ComboSessionView from './ComboSessionView';
import FinalSelectionView from './FinalSelectionView';

interface Props {
  activationCode: string;
}

export default function RuminationV4Page({ activationCode }: Props) {
  const { state, init, switchCombo } = useRuminationV4Store();

  useEffect(() => {
    if (activationCode) {
      init(activationCode);
    }
  }, [activationCode, init]);

  // 切到 combo_session 时,确保该 combo 已加载
  useEffect(() => {
    if (state?.main_section === 'combo_session' && state.active_combo_id) {
      useRuminationV4Store.getState().loadCombo(state.active_combo_id);
    }
  }, [state?.main_section, state?.active_combo_id]);

  if (!state) {
    return <div className="flex-1 flex items-center justify-center text-gray-400">加载中…</div>;
  }

  return (
    <div className="flex flex-col h-full">
      <TopComboBar />

      {/* 第二行:导航(矩阵页 / 第 8 步)*/}
      <div className="flex items-center justify-between px-4 py-2 bg-white border-b border-gray-100 text-xs">
        <div className="flex gap-2">
          <button
            type="button"
            className={`px-2 py-1 rounded ${state.main_section === 'matrix' ? 'text-bd-phase-rumination font-medium' : 'text-gray-500 hover:text-gray-700'}`}
            onClick={() => {
              // 用 store 的内部能力:把 active 清空(回到矩阵)
              // 这里需要后端支持"回矩阵"——前端直接刷新 state
              useRuminationV4Store.setState((s) => ({
                state: s.state ? { ...s.state, main_section: 'matrix', active_combo_id: null } : s.state,
              }));
            }}
          >
            矩阵
          </button>
          <button
            type="button"
            disabled={state.combo_sessions.filter((c) => c.conclusion_card).length === 0}
            className={`px-2 py-1 rounded ${
              state.main_section === 'final_selection' || state.main_section === 'end'
                ? 'text-bd-phase-rumination font-medium'
                : 'text-gray-500 hover:text-gray-700 disabled:opacity-30'
            }`}
            onClick={() => {
              useRuminationV4Store.setState((s) => ({
                state: s.state ? { ...s.state, main_section: 'final_selection' } : s.state,
              }));
            }}
          >
            最终选择({state.combo_sessions.filter((c) => c.conclusion_card).length})
          </button>
        </div>
        {state.main_section === 'end' && (
          <span className="text-green-600 font-medium">✓ 已提交最终方向</span>
        )}
      </div>

      {/* 主区域:根据 main_section 渲染 */}
      <div className="flex-1 flex overflow-hidden">
        {state.main_section === 'matrix' && <MatrixSelector />}
        {state.main_section === 'combo_session' && state.active_combo_id && (
          <ComboSessionView comboId={state.active_combo_id} />
        )}
        {(state.main_section === 'final_selection' || state.main_section === 'end') && (
          <FinalSelectionView />
        )}
      </div>
    </div>
  );
}
