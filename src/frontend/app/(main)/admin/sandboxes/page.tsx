'use client';

import { Fragment, useCallback, useEffect, useMemo, useState } from 'react';
import Link from 'next/link';
import {
  cleanupAdminGeneratedScenarioBatchJobHistory,
  cancelAdminGeneratedScenarioBatchJob,
  fetchAdminGeneratedScenarioBatchJobs,
  fetchAdminGeneratedScenarioBatchJobHistory,
  fetchAdminGeneratedScenarios,
  fetchAdminSavepointReplayLogs,
  deleteAdminSavepoint,
  exportAdminSavepoint,
  fetchAdminSavepoints,
  deleteAdminSandbox,
  ensureAdminWorkspace,
  fetchAdminSandboxes,
  forkAdminSandbox,
  purgeExpiredAdminSandboxes,
  fetchAdminGeneratedScenarioBatchJob,
  runAdminGeneratedScenario,
  startAdminGeneratedScenarioBatchJob,
  type AdminSandboxItem,
  type AdminGeneratedScenarioItem,
  type AdminSavepointItem,
  type AdminSavepointReplayLogItem,
} from '@/lib/api/admin';
import { loadSavepointAndNavigate } from '@/hooks/useAdminSavepoints';
import { formatLocalDateTime } from '@/lib/utils/formatTime';
import { FlaskConical, ExternalLink, Trash2, Copy, RefreshCw } from 'lucide-react';

export default function AdminSandboxesPage() {
  const SAVEPOINT_PAGE_SIZE = 10;
  const [items, setItems] = useState<AdminSandboxItem[]>([]);
  const [retentionDays, setRetentionDays] = useState(15);
  const [savepoints, setSavepoints] = useState<AdminSavepointItem[]>([]);
  const [generatedScenarios, setGeneratedScenarios] = useState<AdminGeneratedScenarioItem[]>([]);
  const [replayLogs, setReplayLogs] = useState<AdminSavepointReplayLogItem[]>([]);
  const [replayOnlyFailed, setReplayOnlyFailed] = useState(false);
  const [savepointQuery, setSavepointQuery] = useState('');
  const [savepointPhaseFilter, setSavepointPhaseFilter] = useState<'all' | string>('all');
  const [savepointPage, setSavepointPage] = useState(1);
  const [savepointSort, setSavepointSort] = useState<'newest' | 'oldest'>('newest');
  const [lastLoadedInfo, setLastLoadedInfo] = useState<{
    savepointName: string;
    phase: string;
    threadId: string;
    at: string;
  } | null>(null);
  const [lastExportInfo, setLastExportInfo] = useState<{
    savepointName: string;
    fixtureDir: string;
    fixtureReportDir: string;
    casesFile: string;
    scenarioFile: string;
    playwrightCommand?: string;
    replayCommand: string;
  } | null>(null);

  const filteredReplayLogs = useMemo(() => {
    if (!replayOnlyFailed) return replayLogs;
    return replayLogs.filter((x) => x.status === 'failed');
  }, [replayLogs, replayOnlyFailed]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [sourceCode, setSourceCode] = useState('');
  const [working, setWorking] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [runningGeneratedSavepointId, setRunningGeneratedSavepointId] = useState<string | null>(null);
  const [expandedGeneratedLogSavepointId, setExpandedGeneratedLogSavepointId] = useState<string | null>(null);
  const [generatedStatusFilter, setGeneratedStatusFilter] = useState<'all' | 'failed' | 'passed'>('all');
  const [batchRunningGenerated, setBatchRunningGenerated] = useState(false);
  const [batchMaxRetries, setBatchMaxRetries] = useState(1);
  const [selectedGeneratedIds, setSelectedGeneratedIds] = useState<string[]>([]);
  const [batchJobHistory, setBatchJobHistory] = useState<
    Array<{
      job_id: string;
      status: 'running' | 'completed' | 'cancelled' | 'interrupted';
      created_at?: string;
      finished_at?: string;
      total: number;
      processed: number;
      passed: number;
      failed: number;
      engine?: string;
      max_retries?: number;
    }>
  >([]);
  const [batchHistoryStatusFilter, setBatchHistoryStatusFilter] = useState<
    'all' | 'running' | 'completed' | 'cancelled' | 'interrupted'
  >('all');
  const [generatedBatchJob, setGeneratedBatchJob] = useState<{
    jobId: string;
    status: 'running' | 'completed' | 'cancelled' | 'interrupted';
    total: number;
    processed: number;
    passed: number;
    failed: number;
    cancelRequested?: boolean;
  } | null>(null);

  const filteredBatchJobHistory = useMemo(() => {
    if (batchHistoryStatusFilter === 'all') return batchJobHistory;
    return batchJobHistory.filter((x) => x.status === batchHistoryStatusFilter);
  }, [batchJobHistory, batchHistoryStatusFilter]);
  const [batchJobDetailLoading, setBatchJobDetailLoading] = useState(false);
  const [batchJobDetail, setBatchJobDetail] = useState<{
    job_id: string;
    status: 'running' | 'completed' | 'cancelled' | 'interrupted';
    total: number;
    processed: number;
    passed: number;
    failed: number;
    items?: Array<{
      savepoint_id: string;
      status: 'passed' | 'failed';
      exit_code: number;
      summary: string;
      report_file?: string | null;
      log_file?: string | null;
      run_code?: string;
    }>;
  } | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetchAdminSandboxes();
      setItems(res.items ?? []);
      setRetentionDays(res.retention_days ?? 15);
      const sp = await fetchAdminSavepoints();
      setSavepoints(sp.items ?? []);
      const generated = await fetchAdminGeneratedScenarios(300);
      setGeneratedScenarios(generated.items ?? []);
      const runningJobs = await fetchAdminGeneratedScenarioBatchJobs(20);
      const hist = await fetchAdminGeneratedScenarioBatchJobHistory(50);
      setBatchJobHistory(hist.items ?? []);
      const active = (runningJobs.items ?? []).find((x) => x.status === 'running');
      if (active) {
        setGeneratedBatchJob({
          jobId: active.job_id,
          status: active.status,
          total: active.total,
          processed: active.processed,
          passed: active.passed,
          failed: active.failed,
          cancelRequested: active.cancel_requested,
        });
        setBatchRunningGenerated(true);
      } else {
        setGeneratedBatchJob(null);
        setBatchRunningGenerated(false);
      }
      const logs = await fetchAdminSavepointReplayLogs(300);
      setReplayLogs(logs.items ?? []);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : '加载失败');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const formatTime = (iso?: string | null) => {
    if (!iso) return '—';
    // 委托 formatLocalDateTime，确保 tz-aware 字符串按浏览器本地时区显示
    const formatted = formatLocalDateTime(iso);
    return formatted === '-' ? iso : formatted;
  };

  const copyText = async (text: string) => {
    try {
      await navigator.clipboard.writeText(text);
      setNotice('已复制到剪贴板');
      setTimeout(() => setNotice(null), 2000);
    } catch {
      setNotice('复制失败');
    }
  };

  const handleFork = async () => {
    const c = sourceCode.trim().toUpperCase();
    if (!c) return;
    setWorking(true);
    setError(null);
    try {
      const data = await forkAdminSandbox(c);
      setNotice(`已创建沙箱激活码：${data.sandbox_activation_code}`);
      setSourceCode('');
      await load();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Fork 失败');
    } finally {
      setWorking(false);
    }
  };

  const handleEnterResidentWorkspace = async () => {
    setWorking(true);
    setError(null);
    try {
      const data = await ensureAdminWorkspace();
      setNotice(
        data.created
          ? `已创建常驻调试工作区：${data.activation_code}`
          : `已进入常驻调试工作区：${data.activation_code}`
      );
      window.location.href = `/explore/activate?code=${encodeURIComponent(data.activation_code)}`;
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : '进入常驻工作区失败');
    } finally {
      setWorking(false);
    }
  };

  const handleDelete = async (code: string) => {
    if (!confirm(`确定删除沙箱 ${code}？磁盘目录与激活记录将一并移除。`)) return;
    setWorking(true);
    setError(null);
    try {
      await deleteAdminSandbox(code);
      await load();
      setNotice('已删除');
      setTimeout(() => setNotice(null), 2000);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : '删除失败');
    } finally {
      setWorking(false);
    }
  };

  const handlePurge = async () => {
    if (!confirm('清理所有已超过保留期限的沙箱？')) return;
    setWorking(true);
    setError(null);
    try {
      const { removed } = await purgeExpiredAdminSandboxes();
      await load();
      setNotice(`已清理 ${removed} 个过期沙箱`);
      setTimeout(() => setNotice(null), 3000);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : '清理失败');
    } finally {
      setWorking(false);
    }
  };

  const handleLoadSavepoint = async (sp: AdminSavepointItem) => {
    if (!confirm(`确定加载检查点「${sp.display_name}」？将覆盖当前调试 report 状态。`)) return;
    setWorking(true);
    setError(null);
    try {
      const ret = await loadSavepointAndNavigate(sp);
      setNotice(`已加载检查点：${sp.display_name}（${ret.phase}/${ret.thread_id}）`);
      setLastLoadedInfo({
        savepointName: sp.display_name,
        phase: ret.phase,
        threadId: ret.thread_id,
        at: new Date().toISOString(),
      });
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : '加载检查点失败');
    } finally {
      setWorking(false);
    }
  };

  const handleDeleteSavepoint = async (sp: AdminSavepointItem) => {
    const detail = [
      `名称：${sp.display_name}`,
      `savepoint_id：${sp.savepoint_id}`,
      `将删除目录：data/test/simple/savepoints/${sp.savepoint_id}`,
      `索引条目：index.json + savepoints_registry.json`,
    ].join('\n');
    if (!confirm(`确定删除检查点？\n\n${detail}`)) return;
    setWorking(true);
    setError(null);
    try {
      await deleteAdminSavepoint({ savepoint_id: sp.savepoint_id });
      setNotice('检查点已删除');
      await load();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : '删除检查点失败');
    } finally {
      setWorking(false);
    }
  };

  const handleExportSavepoint = async (sp: AdminSavepointItem) => {
    setWorking(true);
    setError(null);
    try {
      const ret = await exportAdminSavepoint({ savepoint_id: sp.savepoint_id });
      setNotice(`导出完成：${ret.scenario_file}`);
      setLastExportInfo({
        savepointName: sp.display_name,
        fixtureDir: ret.fixture_dir,
        fixtureReportDir: ret.fixture_report_dir,
        casesFile: ret.cases_file,
        scenarioFile: ret.playwright_scenario_file || ret.scenario_file,
        playwrightCommand: ret.playwright_command,
        replayCommand: ret.replay_command,
      });
      await load();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : '导出检查点失败');
    } finally {
      setWorking(false);
    }
  };

  const handleRunGeneratedScenario = async (row: AdminGeneratedScenarioItem) => {
    if (!confirm(`执行场景「${row.display_name}」？\n\nsavepoint_id: ${row.savepoint_id}`)) return;
    setRunningGeneratedSavepointId(row.savepoint_id);
    setError(null);
    try {
      const ret = await runAdminGeneratedScenario({
        savepoint_id: row.savepoint_id,
        engine: 'auto',
        dry_run: false,
        timeout_sec: 900,
      });
      setNotice(
        `执行完成：${row.display_name} · ${ret.status} · exit=${ret.exit_code}${
          ret.report_file ? ` · report=${ret.report_file}` : ''
        }`,
      );
      if (ret.status === 'failed') {
        setExpandedGeneratedLogSavepointId(row.savepoint_id);
      }
      await load();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : '执行场景失败');
    } finally {
      setRunningGeneratedSavepointId(null);
    }
  };

  const filteredGeneratedScenarios = useMemo(() => {
    if (generatedStatusFilter === 'all') return generatedScenarios;
    return generatedScenarios.filter((x) => x.last_run_status === generatedStatusFilter);
  }, [generatedScenarios, generatedStatusFilter]);

  useEffect(() => {
    const valid = new Set(generatedScenarios.map((x) => x.savepoint_id));
    setSelectedGeneratedIds((prev) => prev.filter((id) => valid.has(id)));
  }, [generatedScenarios]);

  const allFilteredGeneratedSelected = useMemo(() => {
    if (filteredGeneratedScenarios.length === 0) return false;
    const ids = new Set(selectedGeneratedIds);
    return filteredGeneratedScenarios.every((x) => ids.has(x.savepoint_id));
  }, [filteredGeneratedScenarios, selectedGeneratedIds]);

  const handleToggleSelectAllFilteredGenerated = () => {
    if (filteredGeneratedScenarios.length === 0) return;
    const current = new Set(selectedGeneratedIds);
    if (allFilteredGeneratedSelected) {
      filteredGeneratedScenarios.forEach((x) => current.delete(x.savepoint_id));
    } else {
      filteredGeneratedScenarios.forEach((x) => current.add(x.savepoint_id));
    }
    setSelectedGeneratedIds(Array.from(current));
  };

  const handleToggleGeneratedSelection = (savepointId: string) => {
    setSelectedGeneratedIds((prev) => {
      const current = new Set(prev);
      if (current.has(savepointId)) current.delete(savepointId);
      else current.add(savepointId);
      return Array.from(current);
    });
  };

  const handleBatchRerunFailedGenerated = async () => {
    const failedCount = generatedScenarios.filter((x) => x.last_run_status === 'failed').length;
    if (failedCount <= 0) {
      setNotice('没有失败场景需要重跑');
      return;
    }
    if (!confirm(`批量重跑失败场景？共 ${failedCount} 条`)) return;
    setBatchRunningGenerated(true);
    setError(null);
    try {
      const ret = await startAdminGeneratedScenarioBatchJob({
        only_failed: true,
        engine: 'auto',
        timeout_sec: 900,
        max_retries: batchMaxRetries,
      });
      setGeneratedBatchJob({
        jobId: ret.job_id,
        status: ret.status,
        total: ret.total,
        processed: ret.processed,
        passed: ret.passed,
        failed: ret.failed,
      });
      setNotice(`批量任务已启动：job=${ret.job_id}`);
      if (ret.status === 'completed') {
        setBatchRunningGenerated(false);
        setNotice(`批量执行完成：total=${ret.total}, passed=${ret.passed}, failed=${ret.failed}`);
        await load();
      }
    } catch (e: unknown) {
      setBatchRunningGenerated(false);
      setError(e instanceof Error ? e.message : '批量执行失败');
    }
  };

  const handleBatchRunSelectedGenerated = async () => {
    const targets = filteredGeneratedScenarios
      .map((x) => x.savepoint_id)
      .filter((id) => selectedGeneratedIds.includes(id));
    if (targets.length === 0) {
      setNotice('请先选择要执行的场景');
      return;
    }
    if (!confirm(`批量执行选中场景？共 ${targets.length} 条`)) return;
    setBatchRunningGenerated(true);
    setError(null);
    try {
      const ret = await startAdminGeneratedScenarioBatchJob({
        savepoint_ids: targets,
        engine: 'auto',
        timeout_sec: 900,
        max_retries: batchMaxRetries,
      });
      setGeneratedBatchJob({
        jobId: ret.job_id,
        status: ret.status,
        total: ret.total,
        processed: ret.processed,
        passed: ret.passed,
        failed: ret.failed,
      });
      setNotice(`批量任务已启动：job=${ret.job_id}`);
      if (ret.status === 'completed') {
        setBatchRunningGenerated(false);
        setNotice(`批量执行完成：total=${ret.total}, passed=${ret.passed}, failed=${ret.failed}`);
        await load();
      }
    } catch (e: unknown) {
      setBatchRunningGenerated(false);
      setError(e instanceof Error ? e.message : '批量执行失败');
    }
  };

  const handleCancelGeneratedBatchJob = async () => {
    if (!generatedBatchJob || generatedBatchJob.status !== 'running') return;
    if (!confirm(`取消批量任务 ${generatedBatchJob.jobId}？`)) return;
    try {
      const ret = await cancelAdminGeneratedScenarioBatchJob(generatedBatchJob.jobId);
      setNotice(`已请求取消任务：${ret.job_id}`);
      setGeneratedBatchJob((prev) =>
        prev
          ? {
              ...prev,
              cancelRequested: ret.cancel_requested,
            }
          : prev,
      );
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : '取消任务失败');
    }
  };

  const handleLoadBatchJobDetail = async (jobId: string) => {
    setBatchJobDetailLoading(true);
    setError(null);
    try {
      const ret = await fetchAdminGeneratedScenarioBatchJob(jobId);
      setBatchJobDetail(ret);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : '加载任务详情失败');
    } finally {
      setBatchJobDetailLoading(false);
    }
  };

  const handleCleanupBatchJobHistory = async () => {
    if (!confirm('清理旧批量任务历史？将仅保留最近 200 条。')) return;
    try {
      const ret = await cleanupAdminGeneratedScenarioBatchJobHistory({ keep_latest: 200 });
      setNotice(`历史清理完成：removed=${ret.removed}, remaining=${ret.remaining}`);
      await load();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : '清理批量任务历史失败');
    }
  };

  useEffect(() => {
    if (!generatedBatchJob || generatedBatchJob.status !== 'running') return;
    const timer = window.setInterval(() => {
      void (async () => {
        try {
          const ret = await fetchAdminGeneratedScenarioBatchJob(generatedBatchJob.jobId);
          const next = {
            jobId: ret.job_id,
            status: ret.status,
            total: ret.total,
            processed: ret.processed,
            passed: ret.passed,
            failed: ret.failed,
          } as const;
          setGeneratedBatchJob(next);
          if (ret.status === 'completed' || ret.status === 'cancelled' || ret.status === 'interrupted') {
            setBatchRunningGenerated(false);
            setNotice(
              ret.status === 'completed'
                ? `批量执行完成：total=${ret.total}, passed=${ret.passed}, failed=${ret.failed}`
                : ret.status === 'cancelled'
                  ? `批量任务已取消：processed=${ret.processed}/${ret.total}, passed=${ret.passed}, failed=${ret.failed}`
                  : `批量任务已中断（服务重启）：processed=${ret.processed}/${ret.total}, passed=${ret.passed}, failed=${ret.failed}`,
            );
            await load();
          }
        } catch {
          // 忽略单次轮询异常，等待下次轮询
        }
      })();
    }, 2000);
    return () => window.clearInterval(timer);
  }, [generatedBatchJob, load]);

  const filteredSavepoints = savepoints.filter((sp) => {
    const q = savepointQuery.trim().toLowerCase();
    const phaseOk = savepointPhaseFilter === 'all' || sp.phase === savepointPhaseFilter;
    if (!phaseOk) return false;
    if (!q) return true;
    return (
      sp.display_name.toLowerCase().includes(q) ||
      sp.savepoint_id.toLowerCase().includes(q) ||
      sp.source_activation_code.toLowerCase().includes(q)
    );
  });

  const sortedSavepoints = useMemo(() => {
    const arr = [...filteredSavepoints];
    arr.sort((a, b) => {
      const ta = new Date(a.created_at).getTime();
      const tb = new Date(b.created_at).getTime();
      if (savepointSort === 'oldest') return ta - tb;
      return tb - ta;
    });
    return arr;
  }, [filteredSavepoints, savepointSort]);

  const totalSavepointPages = Math.max(1, Math.ceil(filteredSavepoints.length / SAVEPOINT_PAGE_SIZE));
  const pagedSavepoints = useMemo(() => {
    const start = (savepointPage - 1) * SAVEPOINT_PAGE_SIZE;
    return sortedSavepoints.slice(start, start + SAVEPOINT_PAGE_SIZE);
  }, [sortedSavepoints, savepointPage]);

  useEffect(() => {
    setSavepointPage(1);
  }, [savepointQuery, savepointPhaseFilter, savepointSort]);

  useEffect(() => {
    if (savepointPage > totalSavepointPages) setSavepointPage(totalSavepointPages);
  }, [savepointPage, totalSavepointPages]);

  return (
    <div className="max-w-6xl">
      <div className="flex items-start gap-3 mb-8">
        <div
          className="p-3 rounded-2xl bg-violet-500/15 text-violet-600 dark:text-violet-300"
          aria-hidden
        >
          <FlaskConical className="w-7 h-7" />
        </div>
        <div>
          <h1 className="text-2xl font-semibold text-bd-fg">调试沙箱 Fork</h1>
          <p className="text-sm text-bd-muted mt-1 max-w-2xl">
            从正式激活码复制报告与问卷到独立目录 <code className="text-xs bg-bd-overlay-md px-1 rounded">data/simple/sandboxes/</code>
            ，生成 <code className="text-xs bg-bd-overlay-md px-1 rounded">SBX</code> 前缀新码，便于以管理员身份继续对话测试。默认保留{' '}
            {retentionDays} 天，可手动删除；禁止从沙箱再次 Fork。
          </p>
        </div>
      </div>

      {error && (
        <div className="mb-4 rounded-xl border border-rose-200 bg-rose-50 dark:bg-rose-950/30 dark:border-rose-800 px-4 py-3 text-sm text-rose-800 dark:text-rose-200">
          {error}
        </div>
      )}
      {notice && (
        <div className="mb-4 rounded-xl border border-emerald-200 bg-emerald-50 dark:bg-emerald-950/30 dark:border-emerald-800 px-4 py-3 text-sm text-emerald-800 dark:text-emerald-200">
          {notice}
        </div>
      )}

      <section className="rounded-2xl border border-bd-border bg-bd-card/60 p-6 mb-8">
        <h2 className="text-sm font-medium text-bd-fg mb-4">新建 Fork</h2>
        <div className="flex flex-wrap gap-3 items-end">
          <div className="flex-1 min-w-[200px]">
            <label className="block text-xs text-bd-muted mb-1">源激活码（正式用户）</label>
            <input
              className="w-full rounded-xl border border-bd-border bg-bd-bg px-3 py-2 text-sm text-bd-fg"
              placeholder="例如 ABCD123456"
              value={sourceCode}
              onChange={(e) => setSourceCode(e.target.value)}
              disabled={working}
            />
          </div>
          <button
            type="button"
            disabled={working || !sourceCode.trim()}
            onClick={() => void handleFork()}
            className="rounded-xl px-4 py-2 text-sm font-medium bg-violet-600 text-white hover:bg-violet-500 disabled:opacity-50"
          >
            {working ? '处理中…' : 'Fork 沙箱'}
          </button>
          <button
            type="button"
            onClick={() => void handleEnterResidentWorkspace()}
            disabled={working}
            className="rounded-xl px-4 py-2 text-sm font-medium bg-emerald-600 text-white hover:bg-emerald-500 disabled:opacity-50"
          >
            进入我的常驻调试工作区
          </button>
          <button
            type="button"
            onClick={() => void load()}
            disabled={loading}
            className="inline-flex items-center gap-2 rounded-xl border border-bd-border px-4 py-2 text-sm text-bd-fg hover:bg-bd-overlay-md disabled:opacity-50"
          >
            <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
            刷新列表
          </button>
          <button
            type="button"
            onClick={() => void handlePurge()}
            disabled={working}
            className="rounded-xl border border-amber-200 dark:border-amber-800 px-4 py-2 text-sm text-amber-800 dark:text-amber-200 hover:bg-amber-50 dark:hover:bg-amber-950/30"
          >
            清理过期沙箱
          </button>
        </div>
        <p className="text-xs text-bd-subtle mt-3">
          审计日志：<code>sandbox_fork_audit.jsonl</code>（项目 data/simple 下）
        </p>
      </section>

      <section className="rounded-2xl border border-bd-border bg-bd-card/60 overflow-hidden">
        <div className="px-6 py-4 border-b border-bd-border flex items-center justify-between">
          <h2 className="text-sm font-medium text-bd-fg">沙箱列表</h2>
          <span className="text-xs text-bd-muted">{items.length} 条</span>
        </div>
        {loading && !items.length ? (
          <div className="p-8 text-center text-bd-muted text-sm">加载中…</div>
        ) : items.length === 0 ? (
          <div className="p-8 text-center text-bd-muted text-sm">暂无沙箱，请在上方输入正式激活码创建。</div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-xs text-bd-muted border-b border-bd-border">
                  <th className="px-4 py-3 font-medium">沙箱激活码</th>
                  <th className="px-4 py-3 font-medium">来源激活码</th>
                  <th className="px-4 py-3 font-medium">过期时间</th>
                  <th className="px-4 py-3 font-medium">状态</th>
                  <th className="px-4 py-3 font-medium text-right">操作</th>
                </tr>
              </thead>
              <tbody>
                {items.map((row) => (
                  <tr key={row.activation_code} className="border-b border-bd-border/80 hover:bg-bd-overlay-sm">
                    <td className="px-4 py-3 font-mono text-xs">
                      <div className="flex items-center gap-2 flex-wrap">
                        {row.activation_code}
                        <button
                          type="button"
                          className="p-1 rounded text-bd-muted hover:text-bd-fg"
                          title="复制"
                          onClick={() => void copyText(row.activation_code)}
                        >
                          <Copy className="w-3.5 h-3.5" />
                        </button>
                      </div>
                    </td>
                    <td className="px-4 py-3 font-mono text-xs text-bd-muted">
                      {row.forked_from_code || '—'}
                    </td>
                    <td className="px-4 py-3 text-xs text-bd-muted">
                      {formatTime(row.sandbox_expires_at)}
                      {row.expired && (
                        <span className="ml-2 text-amber-600 dark:text-amber-400">已过期</span>
                      )}
                    </td>
                    <td className="px-4 py-3 text-xs">{row.status}</td>
                    <td className="px-4 py-3 text-right">
                      <div className="inline-flex items-center gap-1">
                        <Link
                          href={`/explore/activate?code=${encodeURIComponent(row.activation_code)}`}
                          className="inline-flex items-center gap-1 rounded-lg px-2 py-1.5 text-xs text-violet-600 dark:text-violet-300 hover:bg-violet-500/10"
                        >
                          <ExternalLink className="w-3.5 h-3.5" />
                          进入探索
                        </Link>
                        <button
                          type="button"
                          disabled={working}
                          className="inline-flex items-center gap-1 rounded-lg px-2 py-1.5 text-xs text-rose-600 dark:text-rose-400 hover:bg-rose-500/10 disabled:opacity-50"
                          onClick={() => void handleDelete(row.activation_code)}
                        >
                          <Trash2 className="w-3.5 h-3.5" />
                          删除
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <section className="rounded-2xl border border-bd-border bg-bd-card/60 overflow-hidden mt-8">
        <div className="px-6 py-4 border-b border-bd-border flex items-center justify-between">
          <h2 className="text-sm font-medium text-bd-fg">已导出场景（generated_index）</h2>
          <div className="flex items-center gap-2 flex-wrap justify-end">
            <select
              className="rounded-lg border border-bd-border bg-bd-bg px-2 py-1 text-xs text-bd-fg"
              value={generatedStatusFilter}
              onChange={(e) => setGeneratedStatusFilter(e.target.value as 'all' | 'failed' | 'passed')}
            >
              <option value="all">全部状态</option>
              <option value="failed">仅失败</option>
              <option value="passed">仅通过</option>
            </select>
            <label className="inline-flex items-center gap-1 text-xs text-bd-muted">
              retry
              <input
                type="number"
                min={0}
                max={3}
                value={batchMaxRetries}
                onChange={(e) => setBatchMaxRetries(Math.max(0, Math.min(3, Number(e.target.value || 0))))}
                className="w-12 rounded border border-bd-border bg-bd-bg px-1 py-0.5 text-[11px] text-bd-fg"
              />
            </label>
            <button
              type="button"
              className="rounded-lg border border-bd-border px-2.5 py-1 text-xs text-bd-fg hover:bg-bd-overlay-md"
              onClick={handleToggleSelectAllFilteredGenerated}
            >
              {allFilteredGeneratedSelected ? '取消全选' : '全选筛选'}
            </button>
            <button
              type="button"
              disabled={batchRunningGenerated}
              className="rounded-lg border border-emerald-300 dark:border-emerald-700 px-2.5 py-1 text-xs text-emerald-700 dark:text-emerald-300 hover:bg-emerald-500/10 disabled:opacity-50"
              onClick={() => void handleBatchRunSelectedGenerated()}
            >
              {batchRunningGenerated ? '执行中…' : `执行选中(${selectedGeneratedIds.length})`}
            </button>
            <button
              type="button"
              disabled={batchRunningGenerated}
              className="rounded-lg border border-amber-300 dark:border-amber-700 px-2.5 py-1 text-xs text-amber-700 dark:text-amber-300 hover:bg-amber-500/10 disabled:opacity-50"
              onClick={() => void handleBatchRerunFailedGenerated()}
            >
              {batchRunningGenerated ? '重跑中…' : '重跑失败项'}
            </button>
            <span className="text-xs text-bd-muted">{filteredGeneratedScenarios.length} 条</span>
          </div>
        </div>
        {generatedBatchJob && (
          <div className="px-6 py-2 border-b border-bd-border text-xs text-bd-muted">
            批量任务 {generatedBatchJob.jobId} · {generatedBatchJob.status} ·
            {' '}progress {generatedBatchJob.processed}/{generatedBatchJob.total} ·
            {' '}passed={generatedBatchJob.passed} failed={generatedBatchJob.failed}
            {generatedBatchJob.status === 'running' && (
              <button
                type="button"
                className="ml-3 rounded border border-rose-300 dark:border-rose-700 px-2 py-0.5 text-[11px] text-rose-700 dark:text-rose-300 hover:bg-rose-500/10"
                onClick={() => void handleCancelGeneratedBatchJob()}
              >
                {generatedBatchJob.cancelRequested ? '取消中…' : '取消任务'}
              </button>
            )}
          </div>
        )}
        {filteredGeneratedScenarios.length === 0 ? (
          <div className="p-6 text-sm text-bd-muted">暂无导出场景。先在上方 Savepoint 行点 Export。</div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-xs text-bd-muted border-b border-bd-border">
                  <th className="px-4 py-3 font-medium">选中</th>
                  <th className="px-4 py-3 font-medium">导出时间</th>
                  <th className="px-4 py-3 font-medium">名称 / savepoint_id</th>
                  <th className="px-4 py-3 font-medium">phase/thread</th>
                  <th className="px-4 py-3 font-medium">最近执行</th>
                  <th className="px-4 py-3 font-medium">scenario</th>
                  <th className="px-4 py-3 font-medium text-right">命令</th>
                </tr>
              </thead>
              <tbody>
                {filteredGeneratedScenarios.map((row) => (
                  <Fragment key={`${row.savepoint_id}_${row.exported_at}`}>
                    <tr className="border-b border-bd-border/80 hover:bg-bd-overlay-sm">
                      <td className="px-4 py-3">
                        <input
                          type="checkbox"
                          checked={selectedGeneratedIds.includes(row.savepoint_id)}
                          onChange={() => handleToggleGeneratedSelection(row.savepoint_id)}
                        />
                      </td>
                      <td className="px-4 py-3 text-xs text-bd-muted">{formatTime(row.exported_at)}</td>
                      <td className="px-4 py-3">
                        <div>{row.display_name || '—'}</div>
                        <div className="font-mono text-xs text-bd-muted">{row.savepoint_id}</div>
                      </td>
                      <td className="px-4 py-3 text-xs text-bd-muted">{row.phase || '—'} / {row.thread_id || '—'}</td>
                      <td className="px-4 py-3 text-xs text-bd-muted">
                        {row.last_run_status ? (
                          <div className="space-y-0.5">
                            <div className={row.last_run_status === 'passed' ? 'text-emerald-600' : 'text-rose-600'}>
                              {row.last_run_status}
                            </div>
                            <div>{formatTime(row.last_run_at)}</div>
                            <div className="font-mono">exit={String(row.last_run_exit_code ?? '-')}</div>
                          </div>
                        ) : (
                          '—'
                        )}
                      </td>
                      <td className="px-4 py-3 text-xs font-mono text-bd-muted">{row.scenario_file}</td>
                      <td className="px-4 py-3 text-right">
                        <div className="inline-flex items-center gap-1">
                          <button
                            type="button"
                            disabled={runningGeneratedSavepointId === row.savepoint_id}
                            className="rounded-lg px-2 py-1.5 text-xs text-emerald-600 dark:text-emerald-300 hover:bg-emerald-500/10 disabled:opacity-50"
                            onClick={() => void handleRunGeneratedScenario(row)}
                          >
                            {runningGeneratedSavepointId === row.savepoint_id ? '执行中…' : '执行'}
                          </button>
                          <button
                            type="button"
                            disabled={!row.last_run_stdout_tail && !row.last_run_stderr_tail}
                            className="rounded-lg px-2 py-1.5 text-xs text-amber-600 dark:text-amber-300 hover:bg-amber-500/10 disabled:opacity-50"
                            onClick={() =>
                              setExpandedGeneratedLogSavepointId((id) =>
                                id === row.savepoint_id ? null : row.savepoint_id,
                              )
                            }
                          >
                            {expandedGeneratedLogSavepointId === row.savepoint_id ? '收起日志' : '日志'}
                          </button>
                          <button
                            type="button"
                            disabled={!row.playwright_command}
                            className="rounded-lg px-2 py-1.5 text-xs text-violet-600 dark:text-violet-300 hover:bg-violet-500/10 disabled:opacity-50"
                            onClick={() => row.playwright_command && void copyText(row.playwright_command)}
                          >
                            复制 Playwright
                          </button>
                          <button
                            type="button"
                            disabled={!row.replay_command}
                            className="rounded-lg px-2 py-1.5 text-xs text-sky-600 dark:text-sky-300 hover:bg-sky-500/10 disabled:opacity-50"
                            onClick={() => row.replay_command && void copyText(row.replay_command)}
                          >
                            复制 Replay
                          </button>
                          <button
                            type="button"
                            className="rounded-lg px-2 py-1.5 text-xs text-emerald-600 dark:text-emerald-300 hover:bg-emerald-500/10"
                            onClick={() => void copyText(row.scenario_file)}
                          >
                            复制路径
                          </button>
                          <button
                            type="button"
                            disabled={!row.last_run_log_file}
                            className="rounded-lg px-2 py-1.5 text-xs text-bd-fg hover:bg-bd-overlay-md disabled:opacity-50"
                            onClick={() => row.last_run_log_file && void copyText(row.last_run_log_file)}
                          >
                            复制日志路径
                          </button>
                          <button
                            type="button"
                            className="rounded-lg px-2 py-1.5 text-xs text-violet-600 dark:text-violet-300 hover:bg-violet-500/10"
                            onClick={() => {
                              window.location.href =
                                `/explore/chat/${encodeURIComponent(row.phase || 'values')}` +
                                `?code=${encodeURIComponent(row.source_activation_code || '')}` +
                                `&thread_id=${encodeURIComponent(row.thread_id || '')}`;
                            }}
                          >
                            进入检查点
                          </button>
                        </div>
                      </td>
                    </tr>
                    {expandedGeneratedLogSavepointId === row.savepoint_id && (
                      <tr className="border-b border-bd-border/80 bg-bd-overlay-sm/40">
                        <td className="px-4 py-3 text-xs text-bd-muted" colSpan={7}>
                          <div className="space-y-2">
                            <div className="text-[11px] text-bd-subtle">
                              code={row.last_run_code || '-'} attempts={String(row.last_run_attempts ?? '-')}
                            </div>
                            <div className="text-[11px] text-bd-subtle">stdout tail</div>
                            <pre className="max-h-44 overflow-auto rounded border border-bd-border bg-bd-bg p-2 font-mono text-[11px] leading-relaxed text-bd-fg">
                              {row.last_run_stdout_tail || '（空）'}
                            </pre>
                            <div className="text-[11px] text-bd-subtle">stderr tail</div>
                            <pre className="max-h-44 overflow-auto rounded border border-bd-border bg-bd-bg p-2 font-mono text-[11px] leading-relaxed text-bd-fg">
                              {row.last_run_stderr_tail || '（空）'}
                            </pre>
                          </div>
                        </td>
                      </tr>
                    )}
                  </Fragment>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <section className="rounded-2xl border border-bd-border bg-bd-card/60 overflow-hidden mt-8">
        <div className="px-6 py-4 border-b border-bd-border flex items-center justify-between">
          <h2 className="text-sm font-medium text-bd-fg">批量任务历史</h2>
          <div className="flex items-center gap-2">
            <select
              className="rounded-lg border border-bd-border bg-bd-bg px-2 py-1 text-xs text-bd-fg"
              value={batchHistoryStatusFilter}
              onChange={(e) =>
                setBatchHistoryStatusFilter(
                  e.target.value as 'all' | 'running' | 'completed' | 'cancelled' | 'interrupted',
                )
              }
            >
              <option value="all">全部状态</option>
              <option value="running">running</option>
              <option value="completed">completed</option>
              <option value="cancelled">cancelled</option>
              <option value="interrupted">interrupted</option>
            </select>
            <button
              type="button"
              className="rounded-lg border border-rose-300 dark:border-rose-700 px-2.5 py-1 text-xs text-rose-700 dark:text-rose-300 hover:bg-rose-500/10"
              onClick={() => void handleCleanupBatchJobHistory()}
            >
              清理旧历史
            </button>
            <span className="text-xs text-bd-muted">{filteredBatchJobHistory.length} 条</span>
          </div>
        </div>
        {filteredBatchJobHistory.length === 0 ? (
          <div className="p-6 text-sm text-bd-muted">暂无批量任务历史。</div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-xs text-bd-muted border-b border-bd-border">
                  <th className="px-4 py-3 font-medium">job_id</th>
                  <th className="px-4 py-3 font-medium">状态</th>
                  <th className="px-4 py-3 font-medium">时间</th>
                  <th className="px-4 py-3 font-medium">参数</th>
                  <th className="px-4 py-3 font-medium">结果</th>
                  <th className="px-4 py-3 font-medium text-right">操作</th>
                </tr>
              </thead>
              <tbody>
                {filteredBatchJobHistory.map((row) => (
                  <tr key={`${row.job_id}_${row.created_at || ''}`} className="border-b border-bd-border/80 hover:bg-bd-overlay-sm">
                    <td className="px-4 py-3 font-mono text-xs">{row.job_id}</td>
                    <td className="px-4 py-3 text-xs">
                      <span
                        className={
                          row.status === 'completed'
                            ? 'text-emerald-600'
                            : row.status === 'cancelled'
                              ? 'text-amber-600'
                              : row.status === 'interrupted'
                                ? 'text-rose-600'
                                : 'text-sky-600'
                        }
                      >
                        {row.status}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-xs text-bd-muted">
                      <div>{formatTime(row.created_at)}</div>
                      <div>{formatTime(row.finished_at)}</div>
                    </td>
                    <td className="px-4 py-3 text-xs text-bd-muted">
                      engine={row.engine || 'auto'}, retry={String(row.max_retries ?? 1)}
                    </td>
                    <td className="px-4 py-3 text-xs text-bd-muted">
                      {row.processed}/{row.total} · passed={row.passed} failed={row.failed}
                    </td>
                    <td className="px-4 py-3 text-right">
                      <button
                        type="button"
                        className="rounded-lg px-2 py-1.5 text-xs text-violet-600 dark:text-violet-300 hover:bg-violet-500/10"
                        onClick={() => void handleLoadBatchJobDetail(row.job_id)}
                      >
                        查看详情
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {batchJobDetail && (
          <div className="border-t border-bd-border px-6 py-3">
            <div className="mb-2 flex items-center justify-between text-xs text-bd-muted">
              <span>
                任务详情 {batchJobDetail.job_id} · {batchJobDetail.status} ·
                {' '}processed={batchJobDetail.processed}/{batchJobDetail.total}
              </span>
              {batchJobDetailLoading && <span>加载中…</span>}
            </div>
            {!batchJobDetail.items || batchJobDetail.items.length === 0 ? (
              <div className="text-xs text-bd-muted">暂无明细项。</div>
            ) : (
              <div className="max-h-72 overflow-auto rounded border border-bd-border">
                <table className="w-full text-xs">
                  <thead>
                    <tr className="text-left text-bd-muted border-b border-bd-border">
                      <th className="px-3 py-2 font-medium">savepoint_id</th>
                      <th className="px-3 py-2 font-medium">状态</th>
                      <th className="px-3 py-2 font-medium">退出码</th>
                      <th className="px-3 py-2 font-medium">摘要</th>
                      <th className="px-3 py-2 font-medium text-right">操作</th>
                    </tr>
                  </thead>
                  <tbody>
                    {batchJobDetail.items.map((it, idx) => (
                      <tr key={`${it.savepoint_id}_${idx}`} className="border-b border-bd-border/60">
                        <td className="px-3 py-2 font-mono">{it.savepoint_id}</td>
                        <td className="px-3 py-2">
                          <span className={it.status === 'passed' ? 'text-emerald-600' : 'text-rose-600'}>
                            {it.status}
                          </span>
                        </td>
                        <td className="px-3 py-2">{String(it.exit_code)}</td>
                        <td className="px-3 py-2 text-bd-muted">
                          <div className="max-w-[420px] truncate" title={it.summary}>
                            {it.summary}
                          </div>
                        </td>
                        <td className="px-3 py-2 text-right">
                          <div className="inline-flex items-center gap-1">
                            <button
                              type="button"
                              className="rounded px-1.5 py-0.5 text-[11px] text-sky-600 hover:bg-sky-500/10"
                              onClick={() => void copyText(it.summary || '')}
                            >
                              复制摘要
                            </button>
                            <button
                              type="button"
                              disabled={!it.report_file}
                              className="rounded px-1.5 py-0.5 text-[11px] text-emerald-600 hover:bg-emerald-500/10 disabled:opacity-50"
                              onClick={() => it.report_file && void copyText(it.report_file)}
                            >
                              复制报告路径
                            </button>
                            <button
                              type="button"
                              disabled={!it.log_file}
                              className="rounded px-1.5 py-0.5 text-[11px] text-violet-600 hover:bg-violet-500/10 disabled:opacity-50"
                              onClick={() => it.log_file && void copyText(it.log_file)}
                            >
                              复制日志路径
                            </button>
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        )}
      </section>

      <section className="rounded-2xl border border-bd-border bg-bd-card/60 overflow-hidden mt-8">
        <div className="px-6 py-4 border-b border-bd-border flex items-center justify-between">
          <h2 className="text-sm font-medium text-bd-fg">Savepoints（检查点）</h2>
          <span className="text-xs text-bd-muted">{filteredSavepoints.length} 条（第 {savepointPage}/{totalSavepointPages} 页）</span>
        </div>
        <div className="px-6 py-3 border-b border-bd-border">
          <div className="flex flex-wrap gap-2">
            <input
              className="min-w-[260px] flex-1 rounded-xl border border-bd-border bg-bd-bg px-3 py-2 text-sm text-bd-fg"
              placeholder="搜索名称 / savepoint_id / 激活码"
              value={savepointQuery}
              onChange={(e) => setSavepointQuery(e.target.value)}
            />
            <select
              className="rounded-xl border border-bd-border bg-bd-bg px-3 py-2 text-sm text-bd-fg"
              value={savepointPhaseFilter}
              onChange={(e) => setSavepointPhaseFilter(e.target.value)}
            >
              <option value="all">全部 phase</option>
              <option value="values">values</option>
              <option value="strengths">strengths</option>
              <option value="interests">interests</option>
              <option value="purpose">purpose</option>
              <option value="rumination">rumination</option>
            </select>
          </div>
        </div>
        {lastLoadedInfo && (
          <div className="px-6 py-2 border-b border-bd-border text-xs text-bd-muted">
            最近一次 Load：{lastLoadedInfo.savepointName} · {lastLoadedInfo.phase}/{lastLoadedInfo.threadId} · {formatTime(lastLoadedInfo.at)}
          </div>
        )}
        {lastExportInfo && (
          <div className="px-6 py-3 border-b border-bd-border text-xs text-bd-muted space-y-1">
            <div>最近一次 Export：{lastExportInfo.savepointName}</div>
            <div className="flex flex-wrap items-center gap-2">
              <span className="font-mono">fixture: {lastExportInfo.fixtureDir}</span>
              <button
                type="button"
                className="rounded border border-bd-border px-1.5 py-0.5 text-[11px] hover:bg-bd-overlay-md"
                onClick={() => void copyText(lastExportInfo.fixtureDir)}
              >
                复制
              </button>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <span className="font-mono">playwright: {lastExportInfo.playwrightCommand || '—'}</span>
              <button
                type="button"
                disabled={!lastExportInfo.playwrightCommand}
                className="rounded border border-bd-border px-1.5 py-0.5 text-[11px] hover:bg-bd-overlay-md disabled:opacity-50"
                onClick={() =>
                  lastExportInfo.playwrightCommand && void copyText(lastExportInfo.playwrightCommand)
                }
              >
                复制命令
              </button>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <span className="font-mono">replay: {lastExportInfo.replayCommand}</span>
              <button
                type="button"
                className="rounded border border-bd-border px-1.5 py-0.5 text-[11px] hover:bg-bd-overlay-md"
                onClick={() => void copyText(lastExportInfo.replayCommand)}
              >
                复制命令
              </button>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <span className="font-mono">case: {lastExportInfo.casesFile}</span>
              <button
                type="button"
                className="rounded border border-bd-border px-1.5 py-0.5 text-[11px] hover:bg-bd-overlay-md"
                onClick={() => void copyText(lastExportInfo.casesFile)}
              >
                复制
              </button>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <span className="font-mono">scenario: {lastExportInfo.scenarioFile}</span>
              <button
                type="button"
                className="rounded border border-bd-border px-1.5 py-0.5 text-[11px] hover:bg-bd-overlay-md"
                onClick={() => void copyText(lastExportInfo.scenarioFile)}
              >
                复制
              </button>
            </div>
          </div>
        )}
        {filteredSavepoints.length === 0 ? (
          <div className="p-6 text-sm text-bd-muted">暂无 Savepoint。请在调试聊天页点击 AI 消息下方“保存为检查点”。</div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-xs text-bd-muted border-b border-bd-border">
                  <th className="px-4 py-3 font-medium">名称</th>
                  <th className="px-4 py-3 font-medium">savepoint_id</th>
                  <th className="px-4 py-3 font-medium">
                    <button
                      type="button"
                      className="inline-flex items-center gap-1 hover:text-bd-fg"
                      onClick={() => setSavepointSort((s) => (s === 'newest' ? 'oldest' : 'newest'))}
                    >
                      创建时间
                      <span>{savepointSort === 'newest' ? '↓' : '↑'}</span>
                    </button>
                  </th>
                  <th className="px-4 py-3 font-medium">phase</th>
                  <th className="px-4 py-3 font-medium">来源激活码</th>
                  <th className="px-4 py-3 font-medium">最近回放</th>
                  <th className="px-4 py-3 font-medium text-right">操作</th>
                </tr>
              </thead>
              <tbody>
                {pagedSavepoints.map((sp) => (
                  <tr key={sp.savepoint_id} className="border-b border-bd-border/80 hover:bg-bd-overlay-sm">
                    <td className="px-4 py-3">{sp.display_name}</td>
                    <td className="px-4 py-3 font-mono text-xs">{sp.savepoint_id}</td>
                    <td className="px-4 py-3 text-xs text-bd-muted">{formatTime(sp.created_at)}</td>
                    <td className="px-4 py-3 text-xs text-bd-muted">{sp.phase}</td>
                    <td className="px-4 py-3 font-mono text-xs text-bd-muted">{sp.source_activation_code}</td>
                    <td className="px-4 py-3 text-xs text-bd-muted">
                      {sp.last_replay_status ? (
                        <div className="space-y-0.5">
                          <div className={sp.last_replay_status === 'passed' ? 'text-emerald-600' : 'text-rose-600'}>
                            {sp.last_replay_status}
                          </div>
                          <div>{formatTime(sp.last_replay_at || undefined)}</div>
                        </div>
                      ) : (
                        '—'
                      )}
                    </td>
                    <td className="px-4 py-3 text-right">
                      <div className="inline-flex items-center gap-1">
                        <button
                          type="button"
                          disabled={working}
                          className="rounded-lg px-2 py-1.5 text-xs text-violet-600 dark:text-violet-300 hover:bg-violet-500/10 disabled:opacity-50"
                          onClick={() => void handleLoadSavepoint(sp)}
                        >
                          Load
                        </button>
                        <button
                          type="button"
                          disabled={working || !sp.replay_command}
                          className="rounded-lg px-2 py-1.5 text-xs text-sky-600 dark:text-sky-300 hover:bg-sky-500/10 disabled:opacity-50"
                          onClick={() => sp.replay_command && void copyText(sp.replay_command)}
                        >
                          复制回放
                        </button>
                        <button
                          type="button"
                          disabled={working}
                          className="rounded-lg px-2 py-1.5 text-xs text-emerald-600 dark:text-emerald-300 hover:bg-emerald-500/10 disabled:opacity-50"
                          onClick={() => void handleExportSavepoint(sp)}
                        >
                          Export
                        </button>
                        <button
                          type="button"
                          disabled={working}
                          className="rounded-lg px-2 py-1.5 text-xs text-rose-600 dark:text-rose-300 hover:bg-rose-500/10 disabled:opacity-50"
                          onClick={() => void handleDeleteSavepoint(sp)}
                        >
                          Delete
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            <div className="flex items-center justify-end gap-2 px-4 py-3 border-t border-bd-border">
              <button
                type="button"
                className="rounded-lg border border-bd-border px-2 py-1 text-xs text-bd-fg disabled:opacity-40"
                disabled={savepointPage <= 1}
                onClick={() => setSavepointPage((p) => Math.max(1, p - 1))}
              >
                上一页
              </button>
              <button
                type="button"
                className="rounded-lg border border-bd-border px-2 py-1 text-xs text-bd-fg disabled:opacity-40"
                disabled={savepointPage >= totalSavepointPages}
                onClick={() => setSavepointPage((p) => Math.min(totalSavepointPages, p + 1))}
              >
                下一页
              </button>
            </div>
          </div>
        )}
      </section>

      <section className="rounded-2xl border border-bd-border bg-bd-card/60 overflow-hidden mt-8">
        <div className="px-6 py-4 border-b border-bd-border flex items-center justify-between">
          <h2 className="text-sm font-medium text-bd-fg">回放历史记录</h2>
          <div className="flex items-center gap-3">
            <label className="inline-flex items-center gap-2 text-xs text-bd-muted">
              <input
                type="checkbox"
                checked={replayOnlyFailed}
                onChange={(e) => setReplayOnlyFailed(e.target.checked)}
              />
              仅看失败
            </label>
            <span className="text-xs text-bd-muted">{filteredReplayLogs.length} 条</span>
          </div>
        </div>
        {filteredReplayLogs.length === 0 ? (
          <div className="p-6 text-sm text-bd-muted">暂无回放历史。执行带 `--savepoint-id` 的回放命令后会自动记录。</div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-xs text-bd-muted border-b border-bd-border">
                  <th className="px-4 py-3 font-medium">时间</th>
                  <th className="px-4 py-3 font-medium">状态</th>
                  <th className="px-4 py-3 font-medium">检查点</th>
                  <th className="px-4 py-3 font-medium">phase/thread</th>
                  <th className="px-4 py-3 font-medium">摘要</th>
                  <th className="px-4 py-3 font-medium text-right">操作</th>
                </tr>
              </thead>
              <tbody>
                {filteredReplayLogs.map((log, idx) => (
                  <tr key={`${log.savepoint_id}_${log.at}_${idx}`} className="border-b border-bd-border/80 hover:bg-bd-overlay-sm">
                    <td className="px-4 py-3 text-xs text-bd-muted">{formatTime(log.at)}</td>
                    <td className="px-4 py-3 text-xs">
                      <span className={log.status === 'passed' ? 'text-emerald-600' : 'text-rose-600'}>
                        {log.status}
                      </span>
                    </td>
                    <td className="px-4 py-3">
                      <div className="text-xs font-mono">{log.savepoint_id}</div>
                      <div className="text-xs text-bd-muted">{log.display_name || '—'}</div>
                    </td>
                    <td className="px-4 py-3 text-xs text-bd-muted">{log.phase || '—'} / {log.thread_id || '—'}</td>
                    <td className="px-4 py-3 text-xs text-bd-muted">{log.summary || '—'}</td>
                    <td className="px-4 py-3 text-right">
                      <button
                        type="button"
                        disabled={!log.command}
                        className="rounded-lg px-2 py-1.5 text-xs text-sky-600 dark:text-sky-300 hover:bg-sky-500/10 disabled:opacity-50"
                        onClick={() => log.command && void copyText(log.command)}
                      >
                        复制命令
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  );
}
