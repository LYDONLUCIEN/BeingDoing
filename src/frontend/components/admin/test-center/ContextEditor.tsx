'use client';

import { useState } from 'react';
import { testAuthorApi, type ContextMessage, type ContextSpec, type TestContext } from '@/lib/api/testCenter';
import { getApiErrorMessage } from '@/lib/api/client';

const input = 'w-full rounded-lg border border-bd-border bg-transparent p-2 text-sm';
const button = 'rounded-lg border border-bd-border px-3 py-2 text-sm disabled:opacity-40';
const phases = { values: '价值观', strengths: '优势', interests: '热忱', purpose: '使命', rumination: '沉淀 v4' };
export default function ContextEditor({ saved }: { saved: (context: TestContext) => void }) {
  const [spec, setSpec] = useState<ContextSpec>({ name: '', phase: 'rumination', thread_id: 'combo_1', user_context: '', values_keywords: [], combo: { combo_id: 'combo_1', passion: '', strengths: [], messages: [], conclusion_card: { hypothesis: '' } } });
  const [code, setCode] = useState('');
  const [reviewed, setReviewed] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [seedEnabled, setSeedEnabled] = useState(false);
  const [seedText, setSeedText] = useState('{"completed_phases": [], "basic_info": {}, "conclusions": {}, "thread_metadata": {}, "anchor": {}}');
  const change = (update: Partial<ContextSpec>) => { setSpec(old => ({ ...old, ...update })); setReviewed(false); };
  const combo = (update: Partial<NonNullable<ContextSpec['combo']>>) => change({ combo: { combo_id: spec.thread_id, passion: '', strengths: [], ...spec.combo, ...update } });
  const messages = spec.phase === 'rumination' ? spec.combo?.messages || [] : spec.messages || [];
  const setMessages = (next: ContextMessage[]) => spec.phase === 'rumination' ? combo({ messages: next }) : change({ messages: next });
  const perform = async (operation: () => Promise<void>) => { setBusy(true); setError(''); try { await operation(); } catch (err) { setError(getApiErrorMessage(err)); } finally { setBusy(false); } };
  return <details className="rounded-xl border border-bd-border p-4" data-testid="context-editor">
    <summary className="cursor-pointer font-medium">新建 AI 上下文起点</summary>
    <div className="space-y-3 pt-4">
      <p className="text-sm text-bd-muted">保存待测操作之前的背景与历史。独立单轮每条输入重置；连续多轮及业务回放每次整组重复重置。修改会另存起点。业务回放使用下面的结构化状态，上方背景文字供历史回放使用。</p>
      {error && <p role="alert" className="text-red-600">{error}</p>}
      <div className="grid md:grid-cols-3 gap-3">
        <label>保存点名称<input aria-label="保存点名称" className={input} value={spec.name} onChange={e => change({ name: e.target.value })} /></label>
        <label>阶段<select aria-label="保存点阶段" className={input} value={spec.phase} onChange={e => { const phase = e.target.value as ContextSpec['phase']; change({ phase, combo: phase === 'rumination' ? { combo_id: spec.thread_id, passion: '', strengths: [] } : null, messages: [] }); }}>{Object.entries(phases).map(([id, title]) => <option key={id} value={id}>{title}</option>)}</select></label>
        <label>线程 / 组合 ID<input aria-label="保存点线程" className={input} value={spec.thread_id} onChange={e => { const id = e.target.value; change({ thread_id: id, ...(spec.combo ? { combo: { ...spec.combo, combo_id: id } } : {}) }); }} /></label>
      </div>
      <div className="flex gap-2 items-center"><input aria-label="调试激活码" placeholder="已有调试激活码（可选）" className={input} value={code} onChange={e => setCode(e.target.value)} /><button className={`${button} whitespace-nowrap`} disabled={busy || !code || !spec.name} onClick={() => void perform(async () => { const value = await testAuthorApi.capture({ activation_code: code, phase: spec.phase, thread_id: spec.thread_id, name: spec.name }); setSpec(value); setSeedEnabled(!!value.workflow_seed); setSeedText(JSON.stringify(value.workflow_seed || {}, null, 2)); setReviewed(false); })}>读取当前上下文</button></div>
      <p className="text-xs text-bd-muted">只读取调试工作区。导入后请检查并替换姓名、联系方式等敏感内容，再保存。</p>
      {spec.phase === 'rumination' ? <>
        <div className="grid md:grid-cols-2 gap-3"><label>热爱<input aria-label="组合热爱" className={input} value={spec.combo?.passion || ''} onChange={e => combo({ passion: e.target.value })} /></label><label>优势（逗号分隔）<input aria-label="组合优势" className={input} value={spec.combo?.strengths.join('，') || ''} onChange={e => combo({ strengths: e.target.value.split(/[,，]/).filter(Boolean) })} /></label></div>
        <label className="block">用户背景及前四阶段结论<textarea aria-label="用户背景" className={input} rows={3} value={spec.user_context || ''} onChange={e => change({ user_context: e.target.value })} /></label>
        <label className="block">价值观关键词（逗号分隔）<input className={input} value={spec.values_keywords?.join('，') || ''} onChange={e => change({ values_keywords: e.target.value.split(/[,，]/).filter(Boolean) })} /></label>
        <label className="block">用户已填写的结论卡<textarea aria-label="保存点结论卡" className={input} rows={2} value={spec.combo?.conclusion_card?.hypothesis || ''} onChange={e => combo({ conclusion_card: { hypothesis: e.target.value } })} /></label>
        <label className="block">历史摘要<textarea className={input} value={spec.combo?.summary || ''} onChange={e => combo({ summary: e.target.value })} /></label>
        <label className="block">摘要包含的用户轮数<input type="number" min={0} className={input} value={spec.combo?.summary_last_round || 0} onChange={e => combo({ summary_last_round: Number(e.target.value) })} /></label>
        <label className="block">“再聊聊”的反馈<textarea className={input} value={spec.combo?.reopen_feedback || ''} onChange={e => combo({ reopen_feedback: e.target.value })} /></label>
      </> : <>{([
        ['question_bank', '固定题库'], ['basic_info', '基本资料'], ['prior_context', '前序结论'], ['values_info', '价值观资料'],
        ['anchor_text', '此前对话摘要'], ['purpose_progress_injection', '使命进度'], ['conclusion_state_injection', '当前结论状态'],
      ] as const).map(([key, title]) => <label className="block" key={key}>{title}<textarea aria-label={title} className={input} rows={2} value={spec[key] || ''} onChange={e => change({ [key]: e.target.value })} /></label>)}</>}
      <b className="block text-sm">历史消息（不包含待测输入与期望回复）</b>
      {messages.map((message, i) => <div className="flex gap-2" key={i}><select aria-label={`历史角色 ${i + 1}`} className={button} value={message.role} onChange={e => setMessages(messages.map((m, j) => j === i ? { ...m, role: e.target.value as ContextMessage['role'] } : m))}><option value="user">用户</option><option value="assistant">AI</option><option value="system">背景</option></select><textarea aria-label={`历史内容 ${i + 1}`} className={input} value={message.content} onChange={e => setMessages(messages.map((m, j) => j === i ? { ...m, content: e.target.value } : m))} /><button className={button} onClick={() => setMessages(messages.filter((_, j) => i !== j))}>删除</button></div>)}
      <button className={button} onClick={() => setMessages([...messages, { role: 'user', content: '' }])}>添加历史消息</button>
      <div className="space-y-2 rounded border border-bd-border p-3">
        <label className="block text-sm"><input aria-label="包含业务状态起点" type="checkbox" checked={seedEnabled} onChange={e => { setSeedEnabled(e.target.checked); setReviewed(false); }} /> 包含业务状态起点（业务回放必需）</label>
        {seedEnabled && <>
          <p className="text-xs text-bd-muted">读取调试上下文会自动填入。此副本仅包含所选线程/组合：completed_phases 是实际已完成的前置阶段；basic_info 是基本资料；conclusions 是前四维结论；thread_metadata 是当前结论/使命进度；anchor 是锚点摘要。请检查并脱敏，不要把尚未完成的阶段填为已完成。</p>
          <textarea aria-label="业务状态起点 JSON" className={input} rows={8} value={seedText} onChange={e => { setSeedText(e.target.value); setReviewed(false); }} />
        </>}
      </div>
      <label className="block text-sm"><input type="checkbox" checked={reviewed} onChange={e => setReviewed(e.target.checked)} /> 已检查并脱敏这些背景与历史，适合发送到测试模型</label>
      <button className={button} disabled={busy || !reviewed || !spec.name} onClick={() => void perform(async () => { let seed: ContextSpec['workflow_seed'] = null; if (seedEnabled) { try { seed = JSON.parse(seedText); } catch { throw new Error('业务状态 JSON 格式无效，请检查后保存'); } if (!seed || Array.isArray(seed) || typeof seed !== 'object') throw new Error('业务状态必须是 JSON 对象'); } const result = await testAuthorApi.context({ ...spec, workflow_seed: seed }); saved(result); })}>保存上下文起点</button>
    </div>
  </details>;
}
