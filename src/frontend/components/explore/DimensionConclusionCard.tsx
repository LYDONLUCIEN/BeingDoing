'use client';

import { MessageSquare, ChevronDown, ChevronRight } from 'lucide-react';
import MessageContent from '@/components/explore/MessageContent';

/** 使命阶段结构化「经历 → 价值观」行（与后端 payload 一致） */
export interface ExperienceValueRow {
  experience?: string;
  value?: string;
}

export interface DimensionConclusionData {
  summary?: string;
  keywords?: string[];
  ai_summary?: string;
  dimension_goal?: string;
  final_answer?: string;
  /** 与 keywords 等长的简短理解（价值观阶段） */
  keyword_notes?: string[];
  /** 与 keywords 等长：a/b/c 禀赋标记 */
  strength_markers?: string[];
  /** 与 keywords 等长：选择理由（热忱阶段） */
  interest_reasons?: string[];
  mission_core?: string;
  mission_detail?: string;
  mission_aim?: string;
  experience_value_rows?: ExperienceValueRow[];
}

const STRENGTH_MARKER_LABEL: Record<string, string> = {
  a: '有充实感且与成功有关',
  b: '有充实感',
  c: '目前还不确定',
};

interface DimensionConclusionCardProps {
  phase: 'values' | 'strength' | 'interest' | 'purpose' | 'rumination';
  data: DimensionConclusionData;
  isCompleted?: boolean;
  /** 是否作为聊天记录内联展示（可折叠） */
  inline?: boolean;
  /** 是否已折叠 */
  collapsed?: boolean;
  /** 切换折叠时回调（inline 时必传） */
  onCollapsedChange?: (collapsed: boolean) => void;
  /** 是否显示确认/再聊聊按钮（仅最新结论可操作） */
  showActions?: boolean;
  onConfirm?: () => void;
  onContinueChat?: () => void;
}

/** 仅作主题色类名，勿叠加 flow-msg-ai-content（会套用 AI 气泡边框与字体） */
const phaseThemeClass: Record<string, string> = {
  values: 'values',
  strength: 'strength',
  interest: 'interest',
  purpose: 'purpose',
  rumination: 'rumination',
};

export default function DimensionConclusionCard({
  phase,
  data,
  isCompleted = false,
  inline = false,
  collapsed = false,
  onCollapsedChange,
  showActions = true,
  onConfirm,
  onContinueChat,
}: DimensionConclusionCardProps) {
  const isCollapsed = inline && collapsed;
  const themeClass = phaseThemeClass[phase] || phaseThemeClass.values;
  const summaryText = data.summary ?? data.ai_summary ?? '';
  const keywords = data.keywords ?? (data.final_answer ? data.final_answer.split(/[,，、]/).map((k) => k.trim()).filter(Boolean) : []);
  const keywordNotes = Array.isArray(data.keyword_notes) ? data.keyword_notes : [];
  const strengthMarkers = Array.isArray(data.strength_markers) ? data.strength_markers : [];
  const interestReasons = Array.isArray(data.interest_reasons) ? data.interest_reasons : [];
  const expRowsRaw = Array.isArray(data.experience_value_rows) ? data.experience_value_rows : [];
  const expRows = expRowsRaw.filter(
    (row) => (row.experience || '').trim() || (row.value || '').trim()
  );

  const toggleCollapsed = () => {
    if (inline && onCollapsedChange) onCollapsedChange(!collapsed);
  };

  return (
    <div className={`flow-conclusion-card ${themeClass} ${inline ? 'flow-conclusion-inline' : ''}`}>
      <div
        className={`flow-conclusion-header ${inline ? 'flow-conclusion-header-clickable' : ''}`}
        onClick={inline ? toggleCollapsed : undefined}
        role={inline ? 'button' : undefined}
        tabIndex={inline ? 0 : undefined}
        onKeyDown={inline ? (e) => e.key === 'Enter' && toggleCollapsed() : undefined}
      >
        <div className="flow-conclusion-header-left">
          <div className="flow-conclusion-icon-box">
            <MessageSquare size={16} className="flow-conclusion-icon" />
          </div>
          <span className="flow-conclusion-title">
            {inline && isCollapsed ? '探索结论汇总 · 点击展开' : '探索结论汇总'}
          </span>
        </div>
        {inline && (
          <span className="flow-conclusion-chevron" onClick={(e) => { e.stopPropagation(); toggleCollapsed(); }}>
            {isCollapsed ? <ChevronRight size={16} /> : <ChevronDown size={16} />}
          </span>
        )}
      </div>
      {(!inline || !isCollapsed) && (
      <div className="flow-conclusion-body">
        <div className="flow-conclusion-section flow-conclusion-summary">
          {summaryText && (
            <div className="flow-conclusion-text flow-conclusion-markdown">
              <MessageContent content={summaryText} markdown colorMode="light" />
            </div>
          )}
        </div>
        {keywords.length > 0 && (
          <div className="flow-conclusion-section flow-conclusion-keywords">
            <div className="flow-conclusion-tags">
              {keywords.map((k, i) => {
                const mk = (strengthMarkers[i] || '').trim().toLowerCase();
                return (
                  <span key={`kw-${i}-${k}`} className="flow-conclusion-tag">
                    {phase === 'strength' && mk && STRENGTH_MARKER_LABEL[mk] && (
                      <span className="flow-conclusion-tag-marker" title={STRENGTH_MARKER_LABEL[mk]}>
                        {mk.toUpperCase()}
                      </span>
                    )}
                    {k}
                  </span>
                );
              })}
            </div>
          </div>
        )}
        {phase === 'values' && keywordNotes.some((t) => (t || '').trim()) && (
          <div className="flow-conclusion-section flow-conclusion-ext">
            <div className="flow-conclusion-label">关键词理解</div>
            <ul className="flow-conclusion-ext-ul">
              {keywords.map((k, i) => {
                const note = (keywordNotes[i] || '').trim();
                if (!note) return null;
                return (
                  <li key={`vn-${i}`}>
                    <strong>{k}</strong>
                    {' — '}
                    {note}
                  </li>
                );
              })}
            </ul>
          </div>
        )}
        {phase === 'interest' && interestReasons.some((t) => (t || '').trim()) && (
          <div className="flow-conclusion-section flow-conclusion-ext">
            <div className="flow-conclusion-label">选择理由</div>
            <ul className="flow-conclusion-ext-ul">
              {keywords.map((k, i) => {
                const reason = (interestReasons[i] || '').trim();
                if (!reason) return null;
                return (
                  <li key={`ir-${i}`}>
                    <strong>{k}</strong>
                    {' — '}
                    {reason}
                  </li>
                );
              })}
            </ul>
          </div>
        )}
        {phase === 'purpose' &&
          (data.mission_core?.trim() ||
            data.mission_detail?.trim() ||
            data.mission_aim?.trim()) && (
            <div className="flow-conclusion-section flow-conclusion-mission">
              {data.mission_core?.trim() && (
                <p className="flow-conclusion-text flow-conclusion-mission-core">{data.mission_core.trim()}</p>
              )}
              {data.mission_detail?.trim() && (
                <p className="flow-conclusion-text">{data.mission_detail.trim()}</p>
              )}
              {data.mission_aim?.trim() && (
                <p className="flow-conclusion-text flow-conclusion-mission-aim">{data.mission_aim.trim()}</p>
              )}
            </div>
          )}
        {phase === 'purpose' && expRows.length > 0 && (
          <div className="flow-conclusion-section flow-conclusion-ext">
            <div className="flow-conclusion-label">经历与价值观</div>
            <table className="flow-conclusion-ev-table">
              <thead>
                <tr>
                  <th scope="col">经历</th>
                  <th scope="col">对应价值观</th>
                </tr>
              </thead>
              <tbody>
                {expRows.map((row, ri) => {
                  const ex = (row.experience || '').trim();
                  const val = (row.value || '').trim();
                  return (
                    <tr key={`ev-${ri}`}>
                      <td>{ex || '—'}</td>
                      <td>{val || '—'}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
      )}
      {showActions && (
      <div className="flow-conclusion-actions" onClick={(e) => e.stopPropagation()}>
        <button
          type="button"
          onClick={() => onContinueChat?.()}
          className="flow-conclusion-btn flow-conclusion-btn-secondary"
        >
          {isCompleted ? '完善答案' : '我想再聊聊'}
        </button>
        {isCompleted ? (
          <span className="flow-conclusion-btn flow-conclusion-btn-confirmed">
            已确认
          </span>
        ) : (
          <button
            type="button"
            onClick={(e) => {
              e.stopPropagation();
              onConfirm?.();
            }}
            className="flow-conclusion-btn flow-conclusion-btn-primary"
          >
            确认没有问题
          </button>
        )}
      </div>
      )}
    </div>
  );
}
