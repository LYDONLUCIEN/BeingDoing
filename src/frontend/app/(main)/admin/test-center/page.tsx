'use client';

import Link from 'next/link';
import CaseEditor from '@/components/admin/test-center/CaseEditor';
import AiEvidence from '@/components/admin/test-center/AiEvidence';
import { useCallback, useEffect, useRef, useState } from 'react';
import { getApiErrorMessage } from '@/lib/api/client';
import { testCenterApi, testAuthorApi, type AiCapability, type TestCase, type TestCatalog, type TestRun, type TestStatus } from '@/lib/api/testCenter';

const labels: Record<TestStatus, string> = { queued: '排队中', running: '运行中', pass: '通过', fail: '失败', error: '环境/执行错误', incomplete: '未完整执行', cancelled: '已取消', needs_review: '待复核' };
const active = (run: TestRun) => run.status === 'queued' || run.status === 'running';
const button = 'rounded-lg border border-bd-border px-3 py-2 text-sm disabled:opacity-40 hover:bg-bd-overlay-md';
function Status({ status }: { status?: TestStatus }) {
  return <span className={status === 'pass' ? 'text-emerald-700' : status === 'fail' || status === 'error' ? 'text-red-600' : 'text-bd-muted'}>{status ? labels[status] : '待测'}</span>;
}

export default function TestCenterPage() {
  const [editorOpen, setEditorOpen] = useState(false);
  const [editing, setEditing] = useState<TestCase | null>(null);
  const [capability, setCapability] = useState<AiCapability | null>(null);
  const [maxCalls, setMaxCalls] = useState('');
  const [maxTokens, setMaxTokens] = useState('');
  const [catalog, setCatalog] = useState<TestCatalog | null>(null);
  const [runs, setRuns] = useState<TestRun[]>([]);
  const [selected, setSelected] = useState<string[]>([]);
  const [collection, setCollection] = useState('all');
  const [kind, setKind] = useState('all');
  const [query, setQuery] = useState('');
  const [showArchived, setShowArchived] = useState(false);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [currentId, setCurrentId] = useState('');
  const selectedRunId = useRef('');
  const [detail, setDetail] = useState<TestRun | null>(null);
  const refreshing = useRef(false);
  const refresh = useCallback(async () => {
    if (refreshing.current) return;
    refreshing.current = true;
    const requestedRunId = selectedRunId.current;
    try {
      const [nextCatalog, nextRuns] = await Promise.all([testCenterApi.catalog(), testCenterApi.runs()]);
      setCatalog(nextCatalog); setRuns(nextRuns);
      setCapability(await testAuthorApi.capabilities());
      if (requestedRunId) {
        const nextDetail = await testCenterApi.run(requestedRunId);
        if (selectedRunId.current === requestedRunId) setDetail(nextDetail);
      }
    } catch (err) { setError(getApiErrorMessage(err)); }
    finally { refreshing.current = false; }
  }, []);
  useEffect(() => { void refresh(); const timer = window.setInterval(() => void refresh(), 5000); return () => window.clearInterval(timer); }, [refresh, currentId]);
  const act = async (operation: () => Promise<unknown>) => {
    setBusy(true); setError('');
    try { await operation(); await refresh(); }
    catch (err) { setError(getApiErrorMessage(err)); }
    finally { setBusy(false); }
  };
  const start = async (ids: string[], mode: 'diagnostic' | 'release' = 'diagnostic') => {
    if (!!maxCalls !== !!maxTokens) throw new Error('请同时填写调用次数和 token 上限，或同时留空使用已配置预算');
    const budget = maxCalls && maxTokens ? { max_calls: Number(maxCalls), max_tokens: Number(maxTokens) } : undefined;
    const run = await testCenterApi.start(ids, mode, budget); selectedRunId.current = run.id; setCurrentId(run.id); setDetail(run);
  };
  const visible = (catalog?.cases || []).filter(test =>
    (showArchived || !test.archived) &&
    (collection === 'all' || (collection === 'core' ? test.core : test.version)) &&
    (kind === 'all' || test.definition.kind === kind) &&
    `${test.definition.title} ${test.definition.module} ${test.id}`.toLowerCase().includes(query.toLowerCase())
  );
  const runnable = visible.filter(test => !test.archived && test.available);
  const required = catalog?.cases.filter(test => !test.archived && test.available && (test.core || test.version)).map(test => test.id) || [];
  const releaseReady = catalog && !catalog.build.dirty && !!catalog.build.tag && !catalog.coverage_gaps.length && !catalog.unknown_cases.length;
  const hasWorkflow = (catalog?.cases || []).some(test => selected.includes(test.id) && test.definition.conversation_mode === 'workflow');
  const plannedAiCalls = (catalog?.cases || []).filter(test => selected.includes(test.id) && test.definition.kind === 'ai').reduce((sum, test) => sum + test.definition.inputs.reduce((calls, _, index) => calls + 1 + Number(test.definition.assertions.some(text => /^语义[：:]/.test(text) || new RegExp(`^第${index + 1}轮[：:]\\s*语义[：:]`).test(text))), 0) * (test.definition.repeats || 1), 0);
  const latestResult = (test: TestCase) => runs.flatMap(run => run.cases).find(item => item.id === test.id && item.revision === test.revision)?.status;
  const update = (test: TestCase, core: boolean, archived: boolean) => act(async () => {
    await testCenterApi.update(test, core, archived); if (archived) setSelected(items => items.filter(id => id !== test.id));
  });

  return <div className="space-y-6 max-w-7xl mx-auto" data-testid="test-center">
    <header className="flex flex-wrap items-start justify-between gap-4">
      <div><h1 className="text-2xl font-semibold">测试中心</h1><p className="text-sm text-bd-muted mt-2">选择固定用例，在独立副本中运行；输入与断言分别展示，历史结果持续保留。</p></div>
      <div className="flex gap-3 text-sm"><Link href="/admin/sandboxes" className="underline">调试沙箱</Link><Link href="/admin/prompt-lab" className="underline">Prompt Lab</Link></div>
    </header>
    {error && <div role="alert" className="rounded-xl border border-red-300 bg-red-50 text-red-800 p-4">{error}<button className={`${button} ml-4`} onClick={() => { setError(''); void refresh(); }}>重新加载</button></div>}
    {!catalog ? <p className="text-bd-muted">正在加载测试目录…</p> : <>
      <section className="rounded-2xl border border-bd-border bg-bd-card p-5 space-y-3">
        <div className="flex justify-between gap-4"><b>{catalog.build.label}</b><span>{catalog.worker.ready ? '执行器在线 · 串行运行' : '执行器离线 · 新任务将排队'}</span></div>
        <p className="text-sm text-bd-muted">提交 {catalog.build.sha.slice(0, 12)}{catalog.build.dirty ? ' · 含未提交改动，仅可诊断' : ''}。API 使用临时数据；UI 使用真实浏览器和受控接口。AI 用例使用固定上下文及该构建的现行提示词，明确配置后才会调用真实模型。</p>
        {catalog.storage && <p className="text-xs text-bd-muted">测试资产占用 {(catalog.storage.used_bytes / 1024 / 1024).toFixed(1)} MiB · 磁盘剩余 {(catalog.storage.free_bytes / 1024 / 1024 / 1024).toFixed(1)} GiB。执行副本自动丢弃，用例和证据保留；归档不会删除历史文件。</p>}
        {(catalog.coverage_gaps.length > 0 || catalog.unknown_cases.length > 0) && <details className="text-sm text-amber-700"><summary>有 {catalog.coverage_gaps.length} 个改动文件未关联用例、{catalog.unknown_cases.length} 个未知用例，不能作为发布验收</summary><pre className="whitespace-pre-wrap mt-2">{[...catalog.coverage_gaps, ...catalog.unknown_cases].join('\n')}</pre></details>}
        <button className={button} disabled={busy || !releaseReady || required.length === 0} onClick={() => void act(() => start(required, 'release'))}>运行完整发布验收（{required.length} 项）</button>
        <span className="text-xs text-bd-muted ml-3">要求干净 tag 与完整必测清单。普通勾选运行只用于诊断。</span>
      </section>
      <section className="rounded-2xl border border-bd-border bg-bd-card p-5 space-y-3">
        <h2 className="font-semibold">真实 AI 运行设置</h2><p className="text-sm">{hasWorkflow ? '含业务回放：入队时按步骤估算调用上限，包含业务自身的重试和后台任务。' : `当前勾选预计调用 ${plannedAiCalls} 次（包含语义判定）`}</p>
        <p className="text-sm text-bd-muted">{capability?.configured ? `模型已配置：前四阶段 ${capability.config?.chat.model} / 沉淀 ${capability.config?.rumination.model}。${capability.worker_key_ready ? '执行器凭据就绪。' : '执行器尚未报告凭据就绪。'}` : capability?.reason || '正在读取模型配置…'}</p>
        <div className="flex flex-wrap gap-4"><label className="text-sm">批次最多调用数<input aria-label="AI 调用预算" className={`${button} ml-2 w-28 bg-transparent`} type="number" min={1} max={1000} value={maxCalls} onChange={e => setMaxCalls(e.target.value)} /></label><label className="text-sm">批次 token 上限<input aria-label="AI token 预算" className={`${button} ml-2 w-40 bg-transparent`} type="number" min={1} max={20000000} value={maxTokens} onChange={e => setMaxTokens(e.target.value)} /></label></div>
        <p className="text-xs text-bd-muted">历史回放每轮 1 次回复，有语义标准时追加判定。业务回放按实际对话、结论、摘要、判定、报告及重试计数，入队预估不等于实际花费。留空使用运维已配置的批次上限；两者均未配置时不能运行 AI。逐次预留预算，用量缺失保留额度并停止后续调用。</p>
        <p className="text-xs text-bd-muted">{capability?.config?.input_price !== undefined ? `计费估算配置：每百万输入 ${capability.config.input_price} / 输出 ${capability.config.output_price} ${capability.config.currency}；以供应商账单为准。` : '尚未配置计费单价，费用未知；报告仍记录实际调用及 token。'}</p>
      </section>
      <button className={button} onClick={() => { setEditing(null); setEditorOpen(true); }}>编写新用例</button>
      {editorOpen && <CaseEditor cases={catalog.cases} editing={editing} close={() => setEditorOpen(false)} saved={async id => { await refresh(); setSelected(items => Array.from(new Set([...items, id]))); }} />}
      <section className="rounded-2xl border border-bd-border bg-bd-card p-5 space-y-4">
        <div className="flex flex-wrap gap-3 items-center">
          <h2 className="font-semibold mr-2">用例库</h2>
          <select aria-label="用例集合" className={button} value={collection} onChange={e => setCollection(e.target.value)}><option value="all">全部用例</option><option value="core">核心常驻</option><option value="version">当前版本</option></select>
          <select aria-label="测试类型" className={button} value={kind} onChange={e => setKind(e.target.value)}><option value="all">全部类型</option><option value="api">业务 / API</option><option value="ui">UI 交互</option><option value="ai">AI 对话</option></select>
          <input aria-label="搜索用例" placeholder="名称、模块或 ID" className={`${button} bg-transparent`} value={query} onChange={e => setQuery(e.target.value)} />
          <label className="text-sm"><input type="checkbox" checked={showArchived} onChange={e => setShowArchived(e.target.checked)} /> 显示归档</label>
        </div>
        <div className="flex gap-3 items-center"><button className={button} disabled={busy} onClick={() => setSelected(runnable.map(test => test.id))}>选择当前列表</button><button className={button} onClick={() => setSelected([])}>清空选择</button><button className={button} disabled={busy || !runnable.length} onClick={() => void act(() => start(runnable.map(test => test.id)))}>一键运行当前列表</button><button className={button} disabled={busy || !required.length} onClick={() => void act(() => start((catalog?.cases || []).filter(test => test.core && test.available && !test.archived).map(test => test.id)))}>一键核心回归</button><button className={`${button} bg-bd-ui-accent text-bd-ui-accent-fg`} disabled={busy || !selected.length} onClick={() => void act(() => start(selected))}>运行已选（{selected.length}）</button></div>
        {visible.length === 0 && <p className="text-bd-muted py-4">当前筛选下没有用例。</p>}
        <div className="divide-y divide-bd-border">{visible.map(test => <article key={test.id} className="py-4">
          <div className="flex gap-3 items-start">
            <input type="checkbox" aria-label={`选择 ${test.definition.title}`} className="mt-1" disabled={!!test.archived || !test.available} checked={selected.includes(test.id)} onChange={e => setSelected(items => e.target.checked ? [...items, test.id] : items.filter(id => id !== test.id))} />
            <div className="flex-1 min-w-0"><div className="flex flex-wrap gap-3"><b>{test.definition.title}</b><span className="text-sm text-bd-muted">{test.definition.module} · {test.definition.kind.toUpperCase()} · {test.core ? '核心' : test.version ? '版本' : test.definition.origin === 'authored' ? '自建' : '历史规则'}{test.archived ? ' · 已归档' : ''}{!test.available ? ' · 源码入口已移除' : ''}{test.definition.origin === 'authored' ? ' · 人工修订' : ''}</span><Status status={latestResult(test)} /></div>
              <p className="text-sm mt-2 text-bd-muted">{test.definition.purpose}</p><details className="text-sm mt-2"><summary className="cursor-pointer text-bd-muted">查看输入与断言 · 修订 {test.revision.slice(0, 8)}</summary><div className="grid md:grid-cols-2 gap-5 mt-3"><div><b>用户输入 / 操作</b><ul className="list-disc pl-5 mt-2">{test.definition.inputs.map(text => <li key={text}>{text}</li>)}</ul></div><div><b>断言标准</b><ul className="list-disc pl-5 mt-2">{test.definition.assertions.map(text => <li key={text}>{text}</li>)}</ul></div></div><ul className="mt-3 text-xs text-bd-muted">{test.definition.sources?.map((source, index) => <li key={index}>依据：{source.path} — {source.rule}</li>)}</ul><p className="text-xs text-bd-muted mt-3 break-all">执行入口：{test.definition.targets.join('、')}</p></details>
              {test.upstream && test.upstream.revision !== test.definition.template_revision && <details className="text-sm text-amber-700 mt-2"><summary>源码中有待核对的定义，人工修订保持不变</summary><pre className="whitespace-pre-wrap max-h-64 overflow-auto">{JSON.stringify(test.upstream.definition, null, 2)}</pre></details>}
            </div>
            <button className={button} onClick={() => { setEditing(test); setEditorOpen(true); }}>编辑</button>
            <button className={button} onClick={() => void act(async () => {
              const revisions = await testAuthorApi.revisions(test.id);
              const contexts = test.definition.kind === 'ai' ? (await testAuthorApi.contexts()).filter(c => revisions.some(r => r.definition.context_id === c.id)) : [];
              const url = URL.createObjectURL(new Blob([JSON.stringify({ revisions, contexts }, null, 2)], { type: 'application/json' }));
              const link = document.createElement('a'); link.href = url; link.download = `${test.id}-revisions.json`; link.click(); window.setTimeout(() => URL.revokeObjectURL(url), 1000);
            })}>导出修订</button>
            <button className={button} disabled={busy} onClick={() => void update(test, !test.core, !!test.archived)}>{test.core ? '取消常驻' : '设为常驻'}</button>
            <button className={button} disabled={busy} onClick={() => void update(test, !!test.core, !test.archived)}>{test.archived ? '恢复' : '归档'}</button>
          </div>
        </article>)}</div>
      </section>
    </>}
    <section className="rounded-2xl border border-bd-border bg-bd-card p-5 space-y-4">
      <h2 className="font-semibold">运行记录</h2><p className="text-sm text-bd-muted">重跑创建新批次，首次失败不会被覆盖。历史中的“通过”只适用于该次固定源码、修订与运行配置。</p>
      {!runs.length && <p className="text-bd-muted">还没有运行记录。</p>}
      <div className="max-h-64 overflow-y-auto divide-y divide-bd-border">{runs.map(run => <button key={run.id} className="w-full text-left py-3 flex flex-wrap gap-4 hover:bg-bd-overlay-md" onClick={() => { selectedRunId.current = run.id; setCurrentId(run.id); setDetail(run); }}><span>{new Date(run.created * 1000).toLocaleString()}</span><span>{run.mode === 'release' ? '发布验收' : '诊断'}</span><Status status={run.status} /><span className="text-bd-muted">{run.cases.filter(test => test.status !== 'queued' && test.status !== 'running').length}/{run.cases.length} · {run.build.sha.slice(0, 8)}</span></button>)}</div>
      {detail && <div className="border-t border-bd-border pt-4 space-y-3">
        <div className="flex flex-wrap gap-3 items-center"><b>批次 {detail.id.slice(0, 8)}</b><Status status={detail.status} />{active(detail) ? <button className={button} disabled={busy} onClick={() => void act(() => testCenterApi.cancel(detail.id))}>取消批次</button> : <button className={button} disabled={busy || detail.cases.every(test => test.status === 'pass')} onClick={() => void act(() => start(detail.cases.filter(test => test.status !== 'pass').map(test => test.id)))}>失败 / 未完成项重跑</button>}</div>
        <p className="text-xs text-bd-muted break-all">源码摘要：{detail.build.source_digest} · {detail.build.label}</p>
        {detail.usage && detail.ai && <div className="text-sm space-y-1"><p>入队预估 {detail.ai.planned_calls} 次调用 · 已发起 {detail.usage.calls} 次 · 已知用量 {detail.usage.total_tokens} token · 预算占用 {detail.usage.charged_tokens}/{detail.ai.budget.max_tokens} token · {detail.usage.unknown_calls} 次用量待核对</p><p>费用：{detail.usage.cost === null ? '未知（未配置单价或用量不完整）' : `${detail.usage.cost.toFixed(6)} ${detail.usage.currency || ''}`}</p></div>}
        {detail.error && <p role="alert" className="text-red-600">{detail.error}</p>}
        {detail.cases.map(test => <div key={test.id} className="rounded-lg border border-bd-border p-3 text-sm space-y-2"><div className="flex gap-3"><b>{test.definition.title}</b><Status status={test.status} /><span>{test.duration_ms !== undefined ? `${(test.duration_ms / 1000).toFixed(1)} 秒` : ''}</span></div>{test.error && <pre className="whitespace-pre-wrap text-red-600">{test.error}</pre>}{test.counts && <p className="text-bd-muted">{test.definition.kind === 'ai' ? `${test.counts.tests || 0}/${test.counts.planned || 0} 次已执行 · ${test.counts.passed || 0} 通过 · ${test.counts.failures || 0} 失败 · ${test.counts.needs_review || 0} 待复核` : test.counts.tests !== undefined ? `${test.counts.tests} 项测试 · ${test.counts.failures || 0} 失败 · ${test.counts.errors || 0} 错误 · ${test.counts.skipped || 0} 跳过` : `${test.counts.assertions || 0} 项浏览器断言`}</p>}{test.definition.kind === 'ai' && <AiEvidence key={`${detail.id}:${test.id}`} run={detail} test={test} refresh={refresh} />}<div className="flex flex-wrap gap-3">{test.artifacts?.map(name => <button key={name} className="underline" onClick={() => void act(() => testCenterApi.download(detail.id, test.id, name))}>{name}</button>)}</div></div>)}
      </div>}
    </section>
  </div>;
}
