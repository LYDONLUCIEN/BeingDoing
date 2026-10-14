'use client';

import { useState } from 'react';
import { testAuthorApi, type TestCase, type TestReview, type TestRun } from '@/lib/api/testCenter';
import { getApiErrorMessage } from '@/lib/api/client';

const button = 'rounded-lg border border-bd-border px-3 py-2 text-sm disabled:opacity-40';
const labels: Record<string, string> = { pass: '通过', fail: '失败', needs_review: '待复核', error: '执行错误', incomplete: '未完整执行', cancelled: '已取消', running: '运行中' };
export default function AiEvidence({ run, test, refresh }: { run: TestRun; test: TestCase; refresh: () => Promise<void> }) {
  const [reason, setReason] = useState('');
  const [attempt, setAttempt] = useState(0);
  const [verdict, setVerdict] = useState<TestReview['verdict']>('needs_review');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  return <div className="space-y-3">
    {test.attempts?.map(item => <details key={item.index} className="rounded border border-bd-border p-3"><summary>输入 {item.input_index + 1} · 第 {item.repeat} 次 · 自动判定：{labels[item.status] || item.status}</summary>
      <div className="space-y-2 pt-3"><b>用户输入</b><p className="whitespace-pre-wrap">{item.input}</p><b>本轮 AI 回复</b><p className="whitespace-pre-wrap">{item.reply || '没有取得回复'}</p>
        {item.checks.map((check, i) => <p key={i} className={check.status === 'fail' ? 'text-red-600' : ''}>{labels[check.status]} · {check.reason}</p>)}
        <p className="text-xs text-bd-muted break-all">上下文 {item.context_id.slice(0, 12)}{item.prompt_digest ? ` · 提示词 ${item.prompt_digest.slice(0, 12)} · 实际模型 ${item.actual_model || '未返回'}` : ` · 本步骤模型调用 ${item.model_calls?.length || 0} 次`}</p>
        {item.request && <details><summary>业务步骤证据 · HTTP {item.http_status ?? '未返回'}</summary><pre className="whitespace-pre-wrap max-h-96 overflow-auto">{JSON.stringify({ request: item.request, response: item.response, before_state: item.before_state, state: item.state }, null, 2)}</pre></details>}
        <details><summary>实际发送的提示词与原始回复</summary><pre className="whitespace-pre-wrap max-h-96 overflow-auto">{JSON.stringify(item.model_calls ?? { messages: item.messages, raw_reply: item.raw_reply, judge_reply: item.judge_reply }, null, 2)}</pre></details>
      </div>
    </details>)}
    {!!test.attempts?.length && test.status !== 'running' && <div className="space-y-2 border-t border-bd-border pt-3"><b>追加人工复核</b><p className="text-xs text-bd-muted">保留每次复核人与依据，不覆盖自动判定，也不改变整批验收状态。</p>
      <div className="flex flex-wrap gap-2"><select aria-label="复核目标" className={button} value={attempt} onChange={e => setAttempt(Number(e.target.value))}>{test.attempts.map(item => <option key={item.index} value={item.index}>输入 {item.input_index + 1} / 第 {item.repeat} 次</option>)}</select><select aria-label="复核结论" className={button} value={verdict} onChange={e => setVerdict(e.target.value as TestReview['verdict'])}><option value="needs_review">待复核</option><option value="pass">通过</option><option value="fail">失败</option></select></div>
      <textarea aria-label="复核依据" className="w-full rounded border border-bd-border bg-transparent p-2" placeholder="填写判定依据" value={reason} onChange={e => setReason(e.target.value)} />
      {error && <p role="alert" className="text-red-600">{error}</p>}
      <button className={button} disabled={busy || !reason.trim()} onClick={async () => { setBusy(true); setError(''); try { await testAuthorApi.review(run.id, { case_id: test.id, attempt, verdict, reason }); setReason(''); await refresh(); } catch (err) { setError(getApiErrorMessage(err)); } finally { setBusy(false); } }}>保存复核记录</button>
      {run.reviews?.filter(r => r.case_id === test.id).map(review => <p key={review.id}>{new Date(review.created * 1000).toLocaleString()} · {review.reviewer} · 第 {review.attempt + 1} 项 · {labels[review.verdict]}：{review.reason}</p>)}
    </div>}
  </div>;
}
