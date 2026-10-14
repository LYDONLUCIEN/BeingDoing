'use client';

import { useEffect, useState } from 'react';
import { getApiErrorMessage } from '@/lib/api/client';
import { testAuthorApi, type DraftRequest, type TestCase, type TestContext, type TestDraft } from '@/lib/api/testCenter';
import ContextEditor from './ContextEditor';

const button = 'rounded-lg border border-bd-border px-3 py-2 text-sm disabled:opacity-40';
const input = 'w-full rounded-lg border border-bd-border bg-transparent p-2 text-sm';
const empty = (): DraftRequest => ({ title: '', purpose: '', kind: 'ui', inputs: [''], assertions: [''], repeats: 1, conversation_mode: 'independent' });
export default function CaseEditor({ cases, editing, close, saved }: { cases: TestCase[]; editing: TestCase | null; close: () => void; saved: (id: string) => Promise<void> }) {
  const [form, setForm] = useState<DraftRequest>(empty);
  const [draft, setDraft] = useState<TestDraft | null>(null);
  const [drafts, setDrafts] = useState<TestDraft[]>([]);
  const [contexts, setContexts] = useState<TestContext[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  useEffect(() => {
    void Promise.all([testAuthorApi.contexts(), testAuthorApi.drafts()]).then(([c, d]) => { setContexts(c); setDrafts(d); }).catch(err => setError(getApiErrorMessage(err)));
  }, []);
  useEffect(() => {
    if (!editing) { setForm(empty()); setDraft(null); return; }
    const d = editing.definition;
    setForm({ title: d.title, purpose: d.purpose, conversation_mode: d.conversation_mode || 'independent', kind: d.kind, inputs: d.inputs, assertions: d.assertions, template_id: d.template_id || editing.id, context_id: d.context_id, repeats: d.repeats || 1, case_id: editing.id, base_revision: editing.revision });
    setDraft(null); setNotice('');
  }, [editing]);
  const change = (value: Partial<DraftRequest>) => { setForm(old => ({ ...old, ...value })); setDraft(null); setNotice(''); };
  const act = async (fn: () => Promise<void>) => { setBusy(true); setError(''); try { await fn(); } catch (err) { setError(getApiErrorMessage(err)); } finally { setBusy(false); } };
  const openDraft = (item: TestDraft) => {
    const d = item.definition;
    setForm({ title: d.title, purpose: d.purpose, conversation_mode: d.conversation_mode || 'independent', kind: d.kind, inputs: d.inputs, assertions: d.assertions, template_id: d.template_id, context_id: d.context_id, repeats: d.repeats || 1, case_id: d.id, base_revision: item.base_revision });
    setDraft(item); setNotice('');
  };
  return <section className="rounded-2xl border border-bd-border bg-bd-card p-5 space-y-4" data-testid="case-editor">
    <div className="flex justify-between"><h2 className="font-semibold">{editing ? `编辑：${editing.definition.title}` : '编写测试用例'}</h2><button className={button} onClick={close}>关闭编辑器</button></div>
    <p className="text-sm text-bd-muted">先描述输入与合格标准，再生成固定草稿。从已登记场景开始；UI 可编写新步骤组合，不支持的要求会标记待澄清。AI 支持自由输入和明确的语义关注点，默认每条输入独立测试一次。</p>
    {error && <p role="alert" className="text-red-600">{error}</p>}{notice && <p role="status" className="text-emerald-700">{notice}</p>}
    <div className="grid md:grid-cols-2 gap-3">
      <label>用例名称<input aria-label="用例名称" className={input} value={form.title} onChange={e => change({ title: e.target.value })} /></label>
      <label>测试类型<select aria-label="编辑测试类型" className={input} value={form.kind} onChange={e => change({ kind: e.target.value as DraftRequest['kind'], template_id: undefined, inputs: [''], assertions: [''] })}><option value="api">业务 / API</option><option value="ui">UI 交互</option><option value="ai">AI 对话</option></select></label>
    </div>
    <label className="block">测试目的<textarea aria-label="测试目的" className={input} rows={2} value={form.purpose || ''} onChange={e => change({ purpose: e.target.value })} placeholder="说明要保护的业务规则和这次测试要发现的问题" /></label>
    <div className="space-y-3"><h3 className="font-medium">1. 前置状态</h3>
      {form.kind !== 'ai' ? <label className="block">动作模板<select aria-label="动作模板" className={input} value={form.template_id || ''} onChange={e => {
        const selected = cases.find(c => c.id === e.target.value); if (!selected) return;
        change({ template_id: selected.id, inputs: selected.definition.inputs, assertions: selected.definition.assertions });
      }}><option value="">选择已支持的操作</option>{cases.filter(c => c.available && !c.archived && c.definition.kind === form.kind).map(c => <option key={c.id} value={c.id}>{c.definition.title}</option>)}</select><span className="text-xs text-bd-muted">每次生成全新的隔离数据。模板整体执行，已支持的操作与断言将填入下面两栏。</span></label> : <>
        <label className="block">保存的上下文<select aria-label="保存的上下文" className={input} value={form.context_id || ''} onChange={e => change({ context_id: e.target.value })}><option value="">选择起点</option>{contexts.map(c => <option key={c.id} value={c.id}>{c.spec.name} · {c.spec.phase} · {c.id.slice(0, 8)}</option>)}</select></label>
        {contexts.find(c => c.id === form.context_id) && <details className="text-sm"><summary>检查所选上下文</summary><pre className="whitespace-pre-wrap max-h-80 overflow-auto">{JSON.stringify(contexts.find(c => c.id === form.context_id)?.spec, null, 2)}</pre></details>}
        <ContextEditor saved={context => { setContexts(old => [context, ...old.filter(c => c.id !== context.id)]); change({ context_id: context.id }); setNotice('上下文已保存并选中'); }} />
      </>}
    </div>
    <div className="grid md:grid-cols-2 gap-4">
      <label className="space-y-2"><h3 className="font-medium">2. 用户输入 / 操作步骤</h3><textarea aria-label="编辑用户输入" className={input} rows={7} value={form.inputs.join('\n')} onChange={e => change({ inputs: e.target.value.split('\n') })} /><span className="text-xs text-bd-muted">每行一项。UI 可写「打开首页」「点击：按钮名」「填写：字段名 = 内容」「输入消息：内容」。AI 独立模式逐条重置，连续模式承接历史。业务回放可写「发送消息：内容」「确认结论」「再聊聊」；前四维可「请求结论」，沉淀可「填写结论：内容」「跳过组合」「选入终选」「提交终选」。</span></label>
      <label className="space-y-2"><h3 className="font-medium">3. 断言标准</h3><textarea aria-label="编辑断言标准" className={input} rows={7} value={form.assertions.join('\n')} onChange={e => change({ assertions: e.target.value.split('\n') })} /><span className="text-xs text-bd-muted">{form.kind === 'ai' ? (form.conversation_mode === 'workflow' ? '每一步必须写标准，如「第1步：回复非空」「第2步：结论状态：pending」「第3步：判定状态：done」。可检查接口状态、组合状态、线程完成、阶段锁定、终选提交、结论包含、摘要包含、报告包含，或「第2步：语义：…」。布尔状态填 是/否。' : '每行写：回复非空、回复包含：…、回复不包含：…、或 语义：…（写清必须关注的点）。可用「第2轮：回复包含：…」为指定轮次写标准。语义不确定会进入待复核。') : 'UI 支持「应显示：文字」「按钮禁用：按钮名」「应跳转：/about」「页面无横向溢出」；加「第2步：」可指定检查时机。API 当前使用完整业务模板。'}</span></label>
    </div>
    <div className="space-y-2"><h3 className="font-medium">4. 运行设置</h3>{form.kind === 'ai' ? <><label className="block">对话方式<select aria-label="对话方式" className={input} value={form.conversation_mode || 'independent'} onChange={e => change({ conversation_mode: e.target.value as DraftRequest['conversation_mode'] })}><option value="independent">独立单轮：每条输入恢复同一起点</option><option value="sequence">连续多轮：同一脚本承接前轮回复</option><option value="workflow">业务回放：按步骤执行现有业务流程</option></select></label><label>整组重复次数<input aria-label="重复次数" className={`${input} max-w-24 ml-2`} type="number" min={1} max={10} value={form.repeats} onChange={e => change({ repeats: Number(e.target.value) })} /></label><p className="text-xs text-bd-muted">使用待测构建中的现行提示词；每次整组重复恢复同一起点。业务回放需结构化前置状态；会实际推进结论、摘要、判定与报告，每轮使用全新数据和进程，按真实模型调用（含业务重试）计费。运行时另行设置批次预算；跨提示词对比请使用 Prompt Lab。</p></> : <p className="text-sm text-bd-muted">复用模板超时、真实浏览器与受控外部服务；每例完成后丢弃执行数据。</p>}</div>
    <button className={button} disabled={busy || !form.title} onClick={() => void act(async () => { const result = await testAuthorApi.compile(form); setDraft(result); setDrafts(old => [result, ...old]); })}>生成固定草稿</button>
    {draft && <div className="rounded-lg border border-bd-border p-4 space-y-3" data-testid="compiled-draft">
      <b>{draft.state === 'ready' ? '草稿可执行，请核对后保存' : '待澄清：这些要求尚不能执行'}</b>
      {draft.issues.length > 0 && <ul className="list-disc pl-5 text-amber-700">{draft.issues.map((issue, i) => <li key={i}>{issue}</li>)}</ul>}
      <p className="text-sm">{draft.definition.title} · {draft.definition.inputs.length} 项输入 · {draft.definition.assertions.length} 项断言</p>
      <details className="text-sm"><summary>检查固定执行定义</summary><pre className="whitespace-pre-wrap max-h-64 overflow-auto">{JSON.stringify(draft.definition, null, 2)}</pre></details>
      <button className={button} disabled={busy || draft.state !== 'ready'} onClick={() => void act(async () => { const result = await testAuthorApi.save(draft.id); setForm(old => ({ ...old, case_id: result.id, base_revision: result.revision })); setDraft(null); await saved(result.id); setNotice('用例已保存并选中，可在用例库运行；修改后会形成新修订。'); })}>确认并保存用例</button>
    </div>}
    <details className="text-sm"><summary>已保存的草稿（{drafts.length}）</summary><div className="max-h-48 overflow-auto">{drafts.map(item => <button key={item.id} className="block w-full text-left py-2 border-b border-bd-border" onClick={() => openDraft(item)}>{item.definition.title} · {item.state === 'ready' ? '可执行草稿' : '待澄清'} · {new Date(item.created * 1000).toLocaleString()}</button>)}</div></details>
  </section>;
}
