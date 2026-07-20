'use client';

/**
 * 团队分析页（P-E，ADR-0008/0010）
 * /dashboard/team-analysis
 *
 * 流程：候选报告多选（2-10 份）→ 命名 → 生成（后台 LLM，轮询）→ 查看 markdown 结果
 * 候选来源：自己码的报告 + 自己购买订单交付且被激活人一键授权的报告
 */

import { useCallback, useEffect, useRef, useState } from 'react';
import {
  Check,
  ChevronLeft,
  Loader2,
  Plus,
  UsersRound,
  XCircle,
} from 'lucide-react';
import MarkdownPreview from '@uiw/react-markdown-preview';
import { useLocale } from '@/hooks/useLocale';
import { getApiErrorMessage } from '@/lib/api/client';
import {
  createTeamAnalysis,
  fetchTeamAnalyses,
  fetchTeamAnalysis,
  fetchTeamCandidates,
  type TeamAnalysisItem,
  type TeamCandidate,
} from '@/lib/api/teamAnalysis';
import { formatLocalDateTime } from '@/lib/utils/formatTime';

export default function TeamAnalysisPage() {
  const { t } = useLocale();

  const [candidates, setCandidates] = useState<TeamCandidate[]>([]);
  const [history, setHistory] = useState<TeamAnalysisItem[]>([]);
  const [historyTotal, setHistoryTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [title, setTitle] = useState('');
  const [creating, setCreating] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);

  const [detail, setDetail] = useState<TeamAnalysisItem | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const stopPolling = () => {
    if (pollRef.current) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }
  };

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [c, h] = await Promise.all([fetchTeamCandidates(), fetchTeamAnalyses(1, 50)]);
      setCandidates(c);
      setHistory(h.items);
      setHistoryTotal(h.total);
    } catch (e) {
      setError(getApiErrorMessage(e, t('team.loadFailed')));
    } finally {
      setLoading(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    void load();
    return stopPolling;
  }, [load]);

  // 轮询生成中的分析
  const startPolling = (id: string) => {
    stopPolling();
    pollRef.current = setInterval(async () => {
      try {
        const a = await fetchTeamAnalysis(id);
        setDetail(a);
        if (a.status !== 'generating') {
          stopPolling();
          void load();
        }
      } catch {
        stopPolling();
      }
    }, 3000);
  };

  const toggle = (code: string) => {
    const next = new Set(selected);
    if (next.has(code)) next.delete(code);
    else if (next.size < 10) next.add(code);
    setSelected(next);
  };

  const handleCreate = async () => {
    setCreateError(null);
    if (selected.size < 2) return setCreateError(t('team.errMin'));
    setCreating(true);
    try {
      const analysis = await createTeamAnalysis({
        code_list: Array.from(selected),
        title: title.trim() || undefined,
      });
      setSelected(new Set());
      setTitle('');
      setDetail(analysis);
      startPolling(analysis.id);
    } catch (e) {
      setCreateError(getApiErrorMessage(e, t('team.createFailed')));
    } finally {
      setCreating(false);
    }
  };

  const openDetail = async (id: string) => {
    try {
      const a = await fetchTeamAnalysis(id);
      setDetail(a);
      if (a.status === 'generating') startPolling(a.id);
    } catch (e) {
      setCreateError(getApiErrorMessage(e, t('team.loadFailed')));
    }
  };

  /* ─── 详情视图 ─── */
  if (detail) {
    return (
      <div className="max-w-3xl mx-auto space-y-6">
        <button
          type="button"
          onClick={() => {
            stopPolling();
            setDetail(null);
            void load();
          }}
          className="flex items-center gap-2 text-sm text-bd-subtle hover:text-bd-muted transition-colors"
        >
          <ChevronLeft size={16} />
          {t('team.backList')}
        </button>

        <header className="space-y-1">
          <h1 className="text-2xl font-bold text-bd-fg">{detail.title}</h1>
          <p className="text-xs text-bd-subtle font-mono">{detail.code_list.join(' · ')}</p>
        </header>

        {detail.status === 'generating' ? (
          <div className="bg-bd-card/80 backdrop-blur-lg border border-bd-border rounded-2xl shadow-sm p-16 text-center space-y-4">
            <Loader2 size={28} className="animate-spin mx-auto text-bd-ui-accent" />
            <p className="text-sm text-bd-muted">{t('team.generating')}</p>
          </div>
        ) : detail.status === 'failed' ? (
          <div className="bg-bd-card/80 backdrop-blur-lg border border-bd-border rounded-2xl shadow-sm p-16 text-center space-y-4">
            <XCircle size={28} className="mx-auto text-bd-err" />
            <p className="text-sm text-bd-err">{t('team.failed')}</p>
            {detail.error && <p className="text-xs text-bd-subtle">{detail.error}</p>}
          </div>
        ) : (
          <div className="bg-bd-card/80 backdrop-blur-lg border border-bd-border rounded-2xl shadow-sm p-8">
            <MarkdownPreview source={detail.result_markdown ?? ''} style={{ background: 'transparent' }} />
          </div>
        )}
      </div>
    );
  }

  /* ─── 列表 + 创建视图 ─── */
  return (
    <div className="max-w-3xl mx-auto space-y-8">
      <header>
        <h1 className="text-2xl font-bold text-bd-fg">{t('team.title')}</h1>
        <p className="text-sm text-bd-muted mt-1">{t('team.subtitle')}</p>
      </header>

      {loading ? (
        <div className="flex justify-center py-16">
          <Loader2 size={24} className="animate-spin text-bd-subtle" />
        </div>
      ) : error ? (
        <div className="bg-bd-card/80 backdrop-blur-lg border border-bd-border rounded-2xl shadow-sm p-8 text-center space-y-4">
          <p className="text-sm text-bd-err">{error}</p>
          <button type="button" onClick={() => void load()} className="text-sm text-bd-ui-accent hover:opacity-80">
            {t('team.retry')}
          </button>
        </div>
      ) : (
        <>
          {/* 创建区：候选多选 */}
          <section className="bg-bd-card/80 backdrop-blur-lg border border-bd-border rounded-2xl shadow-sm p-6 space-y-4">
            <h2 className="font-semibold text-bd-fg">{t('team.createTitle')}</h2>

            {candidates.length === 0 ? (
              <p className="text-sm text-bd-muted py-4 text-center">{t('team.noCandidates')}</p>
            ) : (
              <div className="space-y-2">
                {candidates.map((c) => {
                  const isSelected = selected.has(c.activation_code);
                  return (
                    <button
                      key={c.activation_code}
                      type="button"
                      disabled={!c.selectable}
                      onClick={() => toggle(c.activation_code)}
                      className={`w-full flex items-center gap-3 rounded-xl border px-4 py-3 text-left transition-colors ${
                        isSelected
                          ? 'border-[var(--bd-ui-accent)] bg-bd-ui-accent/10'
                          : c.selectable
                            ? 'border-bd-border bg-bd-card hover:bg-bd-overlay-md'
                            : 'border-bd-border/50 bg-bd-card/50 opacity-60 cursor-not-allowed'
                      }`}
                    >
                      <span
                        className={`flex h-5 w-5 shrink-0 items-center justify-center rounded-md border ${
                          isSelected
                            ? 'border-[var(--bd-ui-accent)] bg-[var(--bd-ui-accent)] text-bd-ui-accent-fg'
                            : 'border-bd-border'
                        }`}
                      >
                        {isSelected && <Check size={14} />}
                      </span>
                      <span className="font-mono text-sm text-bd-fg">{c.activation_code}</span>
                      <span className="text-xs text-bd-muted">
                        {c.role === 'self' ? t('team.roleSelf') : c.owner_label}
                      </span>
                      <span className="ml-auto text-xs">
                        {c.selectable ? (
                          <span className="text-emerald-600">{t('team.reportReady')}</span>
                        ) : c.role === 'purchased' && c.activated && !c.report_authorized ? (
                          <span className="text-amber-600">{t('team.notAuthorized')}</span>
                        ) : !c.has_report ? (
                          <span className="text-bd-subtle">{t('team.noReport')}</span>
                        ) : (
                          <span className="text-bd-subtle">—</span>
                        )}
                      </span>
                    </button>
                  );
                })}
              </div>
            )}

            <input
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder={t('team.titlePlaceholder')}
              className="w-full rounded-lg border border-bd-border bg-bd-card px-3 py-2 text-sm text-bd-fg placeholder:text-bd-subtle focus:outline-none focus:ring-1 focus:ring-bd-ui-accent"
            />

            {createError && <p className="text-xs text-bd-err">{createError}</p>}

            <button
              type="button"
              onClick={() => void handleCreate()}
              disabled={creating || selected.size < 2}
              className="w-full inline-flex items-center justify-center gap-2 rounded-xl bg-bd-ui-accent text-bd-ui-accent-fg px-4 py-3 text-sm font-semibold hover:opacity-90 disabled:opacity-50"
            >
              {creating ? <Loader2 size={16} className="animate-spin" /> : <Plus size={16} />}
              {t('team.generate', { count: String(selected.size) })}
            </button>
            <p className="text-xs text-bd-subtle text-center">{t('team.privacyNote')}</p>
          </section>

          {/* 历史列表 */}
          <section className="space-y-3">
            <h2 className="font-semibold text-bd-fg">
              {t('team.history')}
              {historyTotal > 0 && <span className="ml-2 text-xs text-bd-subtle">({historyTotal})</span>}
            </h2>
            {history.length === 0 ? (
              <div className="bg-bd-card/80 backdrop-blur-lg border border-bd-border rounded-2xl shadow-sm p-8 text-center">
                <UsersRound className="w-8 h-8 mx-auto mb-3 text-bd-subtle" />
                <p className="text-sm text-bd-muted">{t('team.noHistory')}</p>
              </div>
            ) : (
              history.map((a) => (
                <button
                  key={a.id}
                  type="button"
                  onClick={() => void openDetail(a.id)}
                  className="w-full flex items-center gap-3 bg-bd-card/80 backdrop-blur-lg border border-bd-border rounded-2xl shadow-sm px-5 py-4 text-left hover:bg-bd-overlay-md transition-colors"
                >
                  <div className="min-w-0 flex-1">
                    <p className="font-medium text-bd-fg truncate">{a.title}</p>
                    <p className="text-xs text-bd-subtle mt-0.5">
                      {a.created_at ? formatLocalDateTime(a.created_at) : '—'} ·{' '}
                      <span className="font-mono">{a.code_list.length} {t('team.members')}</span>
                    </p>
                  </div>
                  <span
                    className={`shrink-0 rounded-full border px-2 py-0.5 text-xs ${
                      a.status === 'done'
                        ? 'bg-emerald-500/15 text-emerald-600 border-emerald-500/40'
                        : a.status === 'generating'
                          ? 'bg-amber-500/15 text-amber-600 border-amber-500/40'
                          : 'bg-red-500/15 text-red-600 border-red-500/40'
                    }`}
                  >
                    {t(`team.status.${a.status}`)}
                  </span>
                </button>
              ))
            )}
          </section>
        </>
      )}
    </div>
  );
}
