'use client';

import { MessageSquare, ChevronDown, ChevronRight } from 'lucide-react';
import MessageContent from '@/components/explore/MessageContent';

export interface DimensionConclusionData {
  summary?: string;
  keywords?: string[];
  ai_summary?: string;
  dimension_goal?: string;
  final_answer?: string;
}

interface DimensionConclusionCardProps {
  phase: 'values' | 'strength' | 'interest' | 'purpose';
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

const phaseBorderClass: Record<string, string> = {
  values: 'flow-msg-ai-content values',
  strength: 'flow-msg-ai-content strength',
  interest: 'flow-msg-ai-content interest',
  purpose: 'flow-msg-ai-content purpose',
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
  const borderClass = phaseBorderClass[phase] || phaseBorderClass.values;
  const summaryText = data.summary ?? data.ai_summary ?? '';
  const keywords = data.keywords ?? (data.final_answer ? data.final_answer.split(/[,，、]/).map((k) => k.trim()).filter(Boolean) : []);

  const toggleCollapsed = () => {
    if (inline && onCollapsedChange) onCollapsedChange(!collapsed);
  };

  return (
    <div className={`flow-conclusion-card ${borderClass} ${inline ? 'flow-conclusion-inline' : ''}`}>
      <div
        className={`flow-conclusion-header ${inline ? 'flow-conclusion-header-clickable' : ''}`}
        onClick={inline ? toggleCollapsed : undefined}
        role={inline ? 'button' : undefined}
        tabIndex={inline ? 0 : undefined}
        onKeyDown={inline ? (e) => e.key === 'Enter' && toggleCollapsed() : undefined}
      >
        <MessageSquare size={18} className="flow-conclusion-icon" />
        <span className="flow-conclusion-title">
          {inline && isCollapsed ? '探索结论汇总 · 点击展开' : '探索结论汇总'}
        </span>
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
              {keywords.map((k) => (
                <span key={k} className="flow-conclusion-tag">
                  {k}
                </span>
              ))}
            </div>
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
