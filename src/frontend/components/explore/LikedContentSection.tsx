'use client';

import { useState, useEffect, useCallback } from 'react';
import { Heart, ExternalLink, AlertCircle, ChevronDown, ChevronUp } from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';
import { getLikes, getLikedMessageTrace, type LikedRecord } from '@/lib/api/analytics';
import { useLocale } from '@/hooks/useLocale';

interface LikedContentSectionProps {
  /** 激活码（用于筛选该用户的点赞） */
  activationCode?: string;
}

/** 阶段标签映射 */
const PHASE_LABELS: Record<string, string> = {
  values: '信念',
  strengths: '禀赋',
  interests: '热忱',
  purpose: '使命',
  rumination: '沉淀',
};

export default function LikedContentSection({ activationCode }: LikedContentSectionProps) {
  const { t } = useLocale();
  const [records, setRecords] = useState<LikedRecord[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [traceMap, setTraceMap] = useState<Record<string, string>>({});
  const [traceSource, setTraceSource] = useState<Record<string, string>>({});

  const loadLikes = useCallback(async () => {
    if (!activationCode) return;
    setLoading(true);
    try {
      const res = await getLikes({ activation_code: activationCode, limit: 100 });
      if (res.data) {
        setRecords(res.data.records);
        setTotal(res.data.total);
      }
    } catch (err) {
      console.warn('[LikedContentSection] load failed:', err);
    } finally {
      setLoading(false);
    }
  }, [activationCode]);

  useEffect(() => {
    loadLikes();
  }, [loadLikes]);

  const handleExpand = async (record: LikedRecord) => {
    const mid = record.message_id;
    if (expandedId === mid) {
      setExpandedId(null);
      return;
    }
    setExpandedId(mid);

    // 加载原文溯源
    if (!traceMap[mid]) {
      try {
        const res = await getLikedMessageTrace(mid);
        if (res.data) {
          setTraceMap((prev) => ({ ...prev, [mid]: res.data.content }));
          setTraceSource((prev) => ({ ...prev, [mid]: res.data.source }));
        }
      } catch {
        // 回退到 content_snapshot
        setTraceMap((prev) => ({
          ...prev,
          [mid]: record.content_snapshot || record.content_preview || '(内容不可用)',
        }));
        setTraceSource((prev) => ({ ...prev, [mid]: 'snapshot' }));
      }
    }
  };

  // 无点赞内容时不展示模块
  if (!loading && total === 0) return null;

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.5, delay: 0.3 }}
      className="rounded-xl border border-bd-border bg-bd-card overflow-hidden"
    >
      {/* 标题栏 */}
      <div className="flex items-center gap-3 px-6 py-4 border-b border-bd-border">
        <div className="w-8 h-8 rounded-full bg-rose-500/10 flex items-center justify-center">
          <Heart size={16} className="fill-rose-500 text-rose-500" />
        </div>
        <div>
          <h3 className="font-semibold text-bd-fg text-sm">
            {t('explore.report.likedContentTitle') || '点赞精选'}
          </h3>
          <p className="text-xs text-bd-subtle">
            {total > 0
              ? `${total} ${t('explore.report.likedContentCount') || '条点赞内容'}`
              : t('explore.report.likedContentEmpty') || '暂无点赞'}
          </p>
        </div>
      </div>

      {/* 内容列表 */}
      <div className="divide-y divide-bd-border/50">
        {loading ? (
          <div className="px-6 py-8 text-center text-bd-subtle text-sm">
            <div className="w-5 h-5 border-2 border-current border-t-transparent rounded-full animate-spin mx-auto mb-2" />
            加载中…
          </div>
        ) : (
          records.map((record) => {
            const isExpanded = expandedId === record.message_id;
            const phaseLabel = PHASE_LABELS[record.phase || ''] || record.phase || '';
            return (
              <div key={record.id} className="group">
                {/* 条目行 */}
                <button
                  type="button"
                  onClick={() => handleExpand(record)}
                  className="w-full text-left px-6 py-3 flex items-start gap-3 hover:bg-bd-overlay-sm transition-colors"
                >
                  <Heart size={14} className="fill-rose-400 text-rose-400 mt-1 shrink-0" />
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 mb-1">
                      {phaseLabel && (
                        <span className="text-[10px] px-1.5 py-0.5 rounded bg-bd-overlay-sm text-bd-subtle font-medium">
                          {phaseLabel}
                        </span>
                      )}
                      {record.created_at && (
                        <span className="text-[10px] text-bd-ghost">
                          {new Date(record.created_at).toLocaleDateString('zh-CN')}
                        </span>
                      )}
                    </div>
                    <p className="text-sm text-bd-muted line-clamp-2 leading-relaxed">
                      {record.content_preview || record.content_snapshot || '(无内容)'}
                    </p>
                  </div>
                  {isExpanded ? (
                    <ChevronUp size={14} className="text-bd-subtle mt-1 shrink-0" />
                  ) : (
                    <ChevronDown size={14} className="text-bd-subtle mt-1 shrink-0" />
                  )}
                </button>

                {/* 展开详情：原文溯源 */}
                <AnimatePresence>
                  {isExpanded && (
                    <motion.div
                      initial={{ height: 0, opacity: 0 }}
                      animate={{ height: 'auto', opacity: 1 }}
                      exit={{ height: 0, opacity: 0 }}
                      transition={{ duration: 0.2 }}
                      className="overflow-hidden"
                    >
                      <div className="px-6 pb-4 ml-7">
                        {/* 溯源标记 */}
                        <div className="flex items-center gap-1.5 mb-2">
                          <ExternalLink size={12} className="text-bd-subtle" />
                          <span className="text-[11px] text-bd-subtle">
                            {traceSource[record.message_id] === 'snapshot'
                              ? '来源：点赞时快照'
                              : traceSource[record.message_id] === 'history_recovery'
                                ? '来源：对话历史恢复'
                                : '原文溯源'}
                          </span>
                        </div>
                        {/* 原文内容 */}
                        <div className="rounded-lg bg-bd-overlay-sm p-3 text-sm text-bd-fg/90 leading-relaxed whitespace-pre-wrap max-h-60 overflow-y-auto">
                          {traceMap[record.message_id] || (
                            <span className="text-bd-ghost italic">(加载中…)</span>
                          )}
                        </div>
                      </div>
                    </motion.div>
                  )}
                </AnimatePresence>
              </div>
            );
          })
        )}
      </div>

      {/* 兜底提示 */}
      {!loading && records.length > 0 && (
        <div className="px-6 py-2 border-t border-bd-border/50 flex items-center gap-1.5 text-[11px] text-bd-ghost">
          <AlertCircle size={12} />
          <span>
            {t('explore.report.likedContentNote') ||
              '所有点赞内容均以快照留存；即使原消息被修改或删除，仍可在此查看原文。'}
          </span>
        </div>
      )}
    </motion.div>
  );
}
