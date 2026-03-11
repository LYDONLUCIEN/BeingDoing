'use client';

import { useState, useEffect } from 'react';
import { getAdminAnalytics, getLikeDetail, type AdminAnalytics } from '@/lib/api/admin';
import {
  Users,
  Activity,
  MessageSquare,
  Type,
  Zap,
  FileText,
  MapPin,
  ThumbsUp,
  Loader2,
  ExternalLink,
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

export default function AnalyticsDashboard() {
  const [data, setData] = useState<AdminAnalytics | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [likeDetail, setLikeDetail] = useState<{ sessionId: string; logIndex: number; content: any } | null>(null);

  useEffect(() => {
    getAdminAnalytics()
      .then((res) => {
        if (res.data) setData(res.data as AdminAnalytics);
      })
      .catch((e) => setError(e?.message || '加载失败'))
      .finally(() => setLoading(false));
  }, []);

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

  const StatCard = ({
    icon: Icon,
    label,
    value,
  }: {
    icon: React.ElementType;
    label: string;
    value: string | number;
  }) => (
    <div className="rounded-xl border border-bd-border bg-bd-card px-4 py-3 flex items-center gap-3">
      <div className="w-10 h-10 rounded-lg flex items-center justify-center" style={{ background: 'var(--bd-overlay)' }}>
        <Icon className="w-5 h-5 text-bd-primary" />
      </div>
      <div>
        <p className="text-xs text-bd-muted">{label}</p>
        <p className="text-lg font-semibold text-bd-fg">{typeof value === 'number' ? value.toLocaleString() : value}</p>
      </div>
    </div>
  );

  return (
    <section className="rounded-xl border border-bd-border bg-bd-card px-5 py-5 space-y-6">
      <div className="flex items-center gap-2">
        <Activity size={18} className="text-bd-primary" />
        <h2 className="text-sm font-semibold text-bd-fg">数据统计</h2>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <StatCard icon={Users} label="用户数量" value={data.user_count} />
        <StatCard icon={Activity} label="访问次数" value={data.visit_count} />
        <StatCard icon={FileText} label="报告生成数" value={data.report_count} />
        <StatCard icon={ThumbsUp} label="点赞总数" value={data.like_count} />
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div className="rounded-lg border border-bd-border p-4">
          <h3 className="text-xs font-medium text-bd-muted mb-3">每维度对话轮次</h3>
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
        <div className="rounded-lg border border-bd-border p-4">
          <h3 className="text-xs font-medium text-bd-muted mb-3">最后停留维度分布</h3>
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

      <div className="rounded-lg border border-bd-border p-4">
        <h3 className="text-xs font-medium text-bd-muted mb-3">输入与 Token</h3>
        <div className="grid grid-cols-3 gap-4 text-sm">
          <div>
            <p className="text-bd-muted">用户输入字数</p>
            <p className="font-semibold text-bd-fg">{data.user_input_total_chars.toLocaleString()}</p>
          </div>
          <div>
            <p className="text-bd-muted">LLM 输入 Tokens</p>
            <p className="font-semibold text-bd-fg">{data.llm_input_tokens.toLocaleString()}</p>
          </div>
          <div>
            <p className="text-bd-muted">LLM 输出 Tokens</p>
            <p className="font-semibold text-bd-fg">{data.llm_output_tokens.toLocaleString()}</p>
          </div>
        </div>
      </div>

      <div>
        <h3 className="text-xs font-medium text-bd-muted mb-3">点赞记录（可点击查看详情）</h3>
        <div className="max-h-64 overflow-y-auto rounded-lg border border-bd-border">
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
          <div className="mt-4 rounded-lg border border-bd-border bg-bd-overlay p-4 max-h-48 overflow-y-auto">
            <p className="text-xs font-medium text-bd-muted mb-2">
              详情：session_id={likeDetail.sessionId} · log_index={likeDetail.logIndex}
            </p>
            <pre className="text-xs text-bd-fg whitespace-pre-wrap break-words">
              {typeof likeDetail.content === 'object'
                ? JSON.stringify(likeDetail.content, null, 2)
                : String(likeDetail.content)}
            </pre>
          </div>
        )}
      </div>
    </section>
  );
}
