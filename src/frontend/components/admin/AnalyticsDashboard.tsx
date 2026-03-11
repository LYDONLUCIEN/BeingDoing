'use client';

import { useState, useEffect } from 'react';
import { getAdminAnalytics, getLikeDetail, syncAnalyticsFromHistory, type AdminAnalytics } from '@/lib/api/admin';
import {
  Users,
  Activity,
  FileText,
  ThumbsUp,
  Loader2,
  ExternalLink,
  RefreshCw,
} from 'lucide-react';

const DIMENSION_LABELS: Record<string, string> = {
  values_exploration: '信念',
  strengths_exploration: '禀赋',
  interests_exploration: '热忱',
  combination: '组合',
  refinement: '精炼',
  values: '信念',
  strengths: '禀赋',
  interests: '热忱',
  purpose: '使命',
};

function fetchData(setData: (d: AdminAnalytics | null) => void, setError: (e: string | null) => void, setLoading: (l: boolean) => void) {
  setLoading(true);
  setError(null);
  getAdminAnalytics()
    .then((res) => {
      if (res.data) setData(res.data as AdminAnalytics);
    })
    .catch((e) => setError(e?.message || '加载失败'))
    .finally(() => setLoading(false));
}

export default function AnalyticsDashboard() {
  const [data, setData] = useState<AdminAnalytics | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [likeDetail, setLikeDetail] = useState<{ sessionId: string; logIndex: number; content: any } | null>(null);
  const [syncing, setSyncing] = useState(false);
  const [syncResult, setSyncResult] = useState<{ synced: number; skipped: number; total_entries: number; from_simple?: number } | null>(null);

  useEffect(() => {
    fetchData(setData, setError, setLoading);
  }, []);

  const handleSyncFromHistory = async () => {
    setSyncing(true);
    setSyncResult(null);
    try {
      const res = await syncAnalyticsFromHistory();
      if (res.data) setSyncResult(res.data);
      fetchData(setData, setError, setLoading);
    } catch {
      setSyncResult({ synced: 0, skipped: 0, total_entries: 0 });
    } finally {
      setSyncing(false);
    }
  };

  const handleViewLikeDetail = async (sessionId: string, logIndex: number) => {
    try {
      const res = await getLikeDetail(sessionId, logIndex);
      setLikeDetail({ sessionId, logIndex, content: res.data });
    } catch {
      setLikeDetail({ sessionId, logIndex, content: { error: '获取失败' } });
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center py-12">
        <Loader2 className="w-8 h-8 animate-spin text-bd-primary" />
      </div>
    );
  }
  if (error || !data) {
    return (
      <div className="rounded-xl border border-bd-border bg-bd-card px-6 py-4 text-bd-err">
        {error || '暂无数据'}
      </div>
    );
  }

  const STAT_CARD_STYLES = [
    { icon: Users, label: '用户数量', color: 'var(--bd-phase-values)', bg: 'var(--bd-phase-values-dim)' },
    { icon: Activity, label: '访问次数', color: 'var(--bd-phase-strengths)', bg: 'var(--bd-phase-strengths-dim)' },
    { icon: FileText, label: '报告生成数', color: 'var(--bd-phase-purpose)', bg: 'var(--bd-phase-purpose-dim)' },
    { icon: ThumbsUp, label: '点赞总数', color: 'var(--bd-phase-interests)', bg: 'var(--bd-phase-interests-dim)' },
  ] as const;

  const StatCard = ({
    icon: Icon,
    label,
    value,
    color,
    bg,
  }: {
    icon: React.ElementType;
    label: string;
    value: string | number;
    color: string;
    bg: string;
  }) => (
    <div className="rounded-xl border overflow-hidden flex items-center gap-3 transition-all hover:shadow-md" style={{ borderColor: 'var(--bd-border)', background: 'var(--bd-card)' }}>
      <div className="w-12 h-full min-h-[56px] flex items-center justify-center shrink-0" style={{ background: bg }}>
        <Icon className="w-6 h-6" style={{ color }} />
      </div>
      <div className="py-3 pr-4">
        <p className="text-xs font-medium" style={{ color: 'var(--bd-fg-muted)' }}>{label}</p>
        <p className="text-xl font-bold" style={{ color: 'var(--bd-fg)' }}>{typeof value === 'number' ? value.toLocaleString() : value}</p>
      </div>
    </div>
  );

  return (
    <section className="rounded-2xl overflow-hidden shadow-lg space-y-6" style={{ background: 'var(--bd-card)', boxShadow: '0 4px 24px rgba(0,0,0,0.06), 0 1px 3px rgba(0,0,0,0.04)' }}>
      <div className="px-6 pt-6">
      <div className="flex items-center justify-between flex-wrap gap-4">
        <div className="flex items-center gap-2">
          <div className="w-10 h-10 rounded-xl flex items-center justify-center" style={{ background: 'var(--bd-primary-dim)' }}>
            <Activity size={20} style={{ color: 'var(--bd-primary)' }} />
          </div>
          <h2 className="text-base font-semibold" style={{ color: 'var(--bd-fg)' }}>数据统计</h2>
        </div>
        <button
          type="button"
          onClick={handleSyncFromHistory}
          disabled={syncing}
          className="inline-flex items-center gap-2 px-3 py-1.5 rounded-lg text-sm font-medium transition-colors disabled:opacity-50"
          style={{ background: 'var(--bd-phase-values-dim)', color: 'var(--bd-phase-values)' }}
        >
          {syncing ? <Loader2 size={14} className="animate-spin" /> : <RefreshCw size={14} />}
          {syncing ? '同步中…' : '从历史同步'}
        </button>
      </div>
      </div>
      <div className="px-6 pb-6 space-y-6">
      {syncResult && (
        <p className="text-xs" style={{ color: 'var(--bd-fg-muted)' }}>
          已同步 {syncResult.synced} 条
          {typeof syncResult.from_simple === 'number' && syncResult.from_simple > 0 && `（含 simple ${syncResult.from_simple} 条）`}
          ，共扫描 {syncResult.total_entries} 条 runs
        </p>
      )}

      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <StatCard {...STAT_CARD_STYLES[0]} value={data.user_count} />
        <StatCard {...STAT_CARD_STYLES[1]} value={data.visit_count} />
        <StatCard {...STAT_CARD_STYLES[2]} value={data.report_count} />
        <StatCard {...STAT_CARD_STYLES[3]} value={data.like_count} />
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div className="rounded-xl border p-4 transition-colors" style={{ borderColor: 'var(--bd-border)', background: 'var(--bd-bg-overlay)' }}>
          <h3 className="text-xs font-semibold uppercase tracking-wider mb-3" style={{ color: 'var(--bd-phase-values)' }}>每维度对话轮次</h3>
          <div className="space-y-2">
            {Object.entries(data.dialogs_by_dimension).map(([dim, count]) => (
              <div key={dim} className="flex justify-between text-sm">
                <span className="text-bd-fg">{DIMENSION_LABELS[dim] || dim}</span>
                <span className="font-mono text-bd-muted">{count.toLocaleString()}</span>
              </div>
            ))}
            {Object.keys(data.dialogs_by_dimension).length === 0 && (
              <p className="text-sm text-bd-muted">暂无</p>
            )}
          </div>
        </div>
        <div className="rounded-xl border p-4 transition-colors" style={{ borderColor: 'var(--bd-border)', background: 'var(--bd-bg-overlay)' }}>
          <h3 className="text-xs font-semibold uppercase tracking-wider mb-3" style={{ color: 'var(--bd-phase-strengths)' }}>最后停留维度分布</h3>
          <div className="space-y-2">
            {Object.entries(data.last_stop_by_dimension).map(([dim, count]) => (
              <div key={dim} className="flex justify-between text-sm">
                <span className="text-bd-fg">{DIMENSION_LABELS[dim] || dim}</span>
                <span className="font-mono text-bd-muted">{count.toLocaleString()}</span>
              </div>
            ))}
            {Object.keys(data.last_stop_by_dimension).length === 0 && (
              <p className="text-sm text-bd-muted">暂无</p>
            )}
          </div>
        </div>
      </div>

      <div className="rounded-xl border p-5" style={{ borderColor: 'var(--bd-border)', background: 'linear-gradient(135deg, var(--bd-phase-values-dim) 0%, var(--bd-phase-purpose-dim) 100%)' }}>
        <h3 className="text-xs font-semibold uppercase tracking-wider mb-4" style={{ color: 'var(--bd-phase-purpose)' }}>输入与 Token</h3>
        <div className="grid grid-cols-3 gap-6 text-sm">
          <div className="rounded-lg px-4 py-3" style={{ background: 'var(--bd-card)' }}>
            <p className="text-xs font-medium mb-1" style={{ color: 'var(--bd-fg-muted)' }}>用户输入字数</p>
            <p className="text-lg font-bold" style={{ color: 'var(--bd-fg)' }}>{data.user_input_total_chars.toLocaleString()}</p>
          </div>
          <div className="rounded-lg px-4 py-3" style={{ background: 'var(--bd-card)' }}>
            <p className="text-xs font-medium mb-1" style={{ color: 'var(--bd-fg-muted)' }}>LLM 输入 Tokens</p>
            <p className="text-lg font-bold" style={{ color: 'var(--bd-fg)' }}>{data.llm_input_tokens.toLocaleString()}</p>
          </div>
          <div className="rounded-lg px-4 py-3" style={{ background: 'var(--bd-card)' }}>
            <p className="text-xs font-medium mb-1" style={{ color: 'var(--bd-fg-muted)' }}>LLM 输出 Tokens</p>
            <p className="text-lg font-bold" style={{ color: 'var(--bd-fg)' }}>{data.llm_output_tokens.toLocaleString()}</p>
          </div>
        </div>
      </div>

      <div>
        <h3 className="text-xs font-semibold uppercase tracking-wider mb-3" style={{ color: 'var(--bd-phase-interests)' }}>点赞记录（可点击查看详情）</h3>
        <div className="max-h-64 overflow-y-auto rounded-xl border" style={{ borderColor: 'var(--bd-border)' }}>
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-bd-border bg-bd-overlay">
                <th className="px-3 py-2 text-left font-medium text-bd-muted">索引</th>
                <th className="px-3 py-2 text-left font-medium text-bd-muted">Session</th>
                <th className="px-3 py-2 text-left font-medium text-bd-muted">维度</th>
                <th className="px-3 py-2 text-left font-medium text-bd-muted">预览</th>
                <th className="px-3 py-2 text-left font-medium text-bd-muted">操作</th>
              </tr>
            </thead>
            <tbody>
              {data.like_records.map((like) => (
                <tr key={like.id} className="border-b border-bd-border/50 hover:bg-bd-overlay/50">
                  <td className="px-3 py-2 font-mono text-bd-fg">{like.log_index}</td>
                  <td className="px-3 py-2 text-bd-muted truncate max-w-[120px]">{like.session_id}</td>
                  <td className="px-3 py-2 text-bd-fg">{DIMENSION_LABELS[like.dimension || ''] || like.dimension || '-'}</td>
                  <td className="px-3 py-2 text-bd-muted truncate max-w-[200px]">{like.content_preview || '-'}</td>
                  <td className="px-3 py-2">
                    <button
                      type="button"
                      onClick={() => handleViewLikeDetail(like.session_id, like.log_index)}
                      className="inline-flex items-center gap-1 text-bd-primary hover:underline text-xs"
                    >
                      <ExternalLink size={12} /> 查看
                    </button>
                  </td>
                </tr>
              ))}
              {data.like_records.length === 0 && (
                <tr>
                  <td colSpan={5} className="px-3 py-6 text-center text-bd-muted">
                    暂无点赞记录
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
        {likeDetail && (
          <div className="mt-4 rounded-xl overflow-hidden max-h-48 overflow-y-auto" style={{ background: '#f8fafc', border: '1px solid #e2e8f0' }}>
            <p className="px-4 py-2 text-xs font-medium border-b" style={{ color: '#64748b', borderColor: '#e2e8f0', background: '#f1f5f9' }}>
              详情：session_id={likeDetail.sessionId} · log_index={likeDetail.logIndex}
            </p>
            <pre className="p-4 text-xs leading-relaxed whitespace-pre-wrap break-words" style={{ background: '#ffffff', color: '#1e293b' }}>
              {typeof likeDetail.content === 'object'
                ? JSON.stringify(likeDetail.content, null, 2)
                : String(likeDetail.content)}
            </pre>
          </div>
        )}
      </div>
      </div>
    </section>
  );
}
