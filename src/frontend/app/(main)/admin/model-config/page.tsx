'use client';

import { useCallback, useEffect, useState } from 'react';
import {
  fetchAdminModelConfigs,
  createAdminModelConfig,
  updateAdminModelConfig,
  deleteAdminModelConfig,
  setAdminDefaultModelConfig,
  revealAdminModelConfigKey,
  testAdminModelConfig,
  fetchAdminUserLlmBindings,
  bindAdminUserLlm,
  unbindAdminUserLlm,
  type AdminModelConfig,
  type AdminUserLlmBinding,
  type LlmProvider,
  type ModelConfigTestResult,
} from '@/lib/api/admin';
import { getApiErrorMessage } from '@/lib/api/client';

const PROVIDERS: { value: LlmProvider; label: string }[] = [
  { value: 'deepseek', label: 'DeepSeek' },
  { value: 'kimi', label: 'Kimi (Moonshot)' },
  { value: 'qwen', label: 'Qwen (通义)' },
  { value: 'openai', label: 'OpenAI' },
];

interface EditForm {
  name: string;
  provider: LlmProvider;
  model: string;
  base_url: string;
  api_key: string;
  is_default: boolean;
  enabled: boolean;
  notes: string;
}

const EMPTY_FORM: EditForm = {
  name: '',
  provider: 'deepseek',
  model: '',
  base_url: '',
  api_key: '',
  is_default: false,
  enabled: true,
  notes: '',
};

export default function AdminModelConfigPage() {
  const [configs, setConfigs] = useState<AdminModelConfig[]>([]);
  const [bindings, setBindings] = useState<AdminUserLlmBinding[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [toast, setToast] = useState<string | null>(null);

  // 编辑/新建 modal
  const [editing, setEditing] = useState<AdminModelConfig | null>(null);
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState<EditForm>(EMPTY_FORM);
  const [saving, setSaving] = useState(false);
  const [revealKeyFor, setRevealKeyFor] = useState<string | null>(null);
  const [revealedKey, setRevealedKey] = useState<string | null>(null);

  // 联通测试 modal
  const [testingConfig, setTestingConfig] = useState<AdminModelConfig | null>(null);
  const [testPrompt, setTestPrompt] = useState('ping');
  const [testResult, setTestResult] = useState<ModelConfigTestResult | null>(null);
  const [testing, setTesting] = useState(false);

  // 用户绑定
  const [bindUserId, setBindUserId] = useState('');
  const [bindConfigId, setBindConfigId] = useState('');

  const showToast = (msg: string) => {
    setToast(msg);
    setTimeout(() => setToast(null), 2500);
  };

  const loadAll = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [cs, bs] = await Promise.all([
        fetchAdminModelConfigs(),
        fetchAdminUserLlmBindings(),
      ]);
      setConfigs(cs);
      setBindings(bs);
    } catch (e) {
      setError(getApiErrorMessage(e, '加载失败'));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadAll();
  }, [loadAll]);

  const openCreate = () => {
    setEditing(null);
    setForm(EMPTY_FORM);
    setShowForm(true);
  };

  const openEdit = (c: AdminModelConfig) => {
    setEditing(c);
    setForm({
      name: c.name,
      provider: c.provider,
      model: c.model,
      base_url: c.base_url ?? '',
      api_key: '',
      is_default: c.is_default,
      enabled: c.enabled,
      notes: c.notes ?? '',
    });
    setShowForm(true);
  };

  const handleSave = async () => {
    setSaving(true);
    setError(null);
    try {
      const basePayload = {
        name: form.name.trim(),
        provider: form.provider,
        model: form.model.trim(),
        base_url: form.base_url.trim() || null,
        is_default: form.is_default,
        enabled: form.enabled,
        notes: form.notes.trim() || null,
      };
      if (editing) {
        // api_key 为空串 → 不传（不变）；有内容 → 传
        const payload: Record<string, unknown> = { ...basePayload };
        if (form.api_key.trim() !== '') payload.api_key = form.api_key.trim();
        await updateAdminModelConfig(editing.id, payload);
        showToast('已更新');
      } else {
        await createAdminModelConfig({
          ...basePayload,
          api_key: form.api_key.trim() || null,
        });
        showToast('已创建');
      }
      setShowForm(false);
      await loadAll();
    } catch (e) {
      setError(getApiErrorMessage(e, '保存失败'));
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async (c: AdminModelConfig) => {
    if (!confirm(`确认删除「${c.name}」？此操作不可撤销。`)) return;
    try {
      await deleteAdminModelConfig(c.id);
      showToast('已删除');
      await loadAll();
    } catch (e) {
      setError(getApiErrorMessage(e, '删除失败'));
    }
  };

  const handleSetDefault = async (c: AdminModelConfig) => {
    try {
      await setAdminDefaultModelConfig(c.id);
      showToast(`已将「${c.name}」设为默认`);
      await loadAll();
    } catch (e) {
      setError(getApiErrorMessage(e, '设置默认失败'));
    }
  };

  const handleReveal = async (c: AdminModelConfig) => {
    if (revealKeyFor === c.id) {
      setRevealKeyFor(null);
      setRevealedKey(null);
      return;
    }
    try {
      const key = await revealAdminModelConfigKey(c.id);
      setRevealKeyFor(c.id);
      setRevealedKey(key);
    } catch (e) {
      setError(getApiErrorMessage(e, '查看 Key 失败'));
    }
  };

  const openTest = (c: AdminModelConfig) => {
    setTestingConfig(c);
    setTestPrompt('ping');
    setTestResult(null);
  };

  const runTest = async (promptOverride?: string) => {
    if (!testingConfig) return;
    setTesting(true);
    setTestResult(null);
    try {
      const result = await testAdminModelConfig(testingConfig.id, {
        prompt: promptOverride ?? testPrompt,
      });
      setTestResult(result);
    } catch (e) {
      setTestResult({
        success: false,
        content: '',
        model: testingConfig.model,
        latency_ms: 0,
        error: getApiErrorMessage(e, '请求失败'),
      });
    } finally {
      setTesting(false);
    }
  };

  const handleBind = async () => {
    if (!bindUserId.trim() || !bindConfigId) {
      setError('请填写用户 ID 并选择目标模型');
      return;
    }
    try {
      await bindAdminUserLlm({
        user_id: bindUserId.trim(),
        config_id: bindConfigId,
      });
      setBindUserId('');
      setBindConfigId('');
      showToast('已绑定');
      await loadAll();
    } catch (e) {
      setError(getApiErrorMessage(e, '绑定失败'));
    }
  };

  const handleUnbind = async (userId: string) => {
    try {
      await unbindAdminUserLlm(userId);
      showToast('已解绑');
      await loadAll();
    } catch (e) {
      setError(getApiErrorMessage(e, '解绑失败'));
    }
  };

  return (
    <div className="max-w-5xl mx-auto space-y-6">
      <header className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-xl font-semibold mb-2" style={{ color: 'var(--bd-fg)' }}>
            LLM 模型配置
          </h1>
          <p className="text-sm" style={{ color: 'var(--bd-fg-muted)' }}>
            管理可用的模型端点（provider/model/base_url/api_key）。数据库配置优先，.env 作为兜底。未单独绑定的用户走默认模型。
          </p>
        </div>
        <button
          onClick={openCreate}
          className="shrink-0 px-3 py-1.5 rounded-lg text-xs font-medium border"
          style={{
            background: 'var(--bd-accent)',
            color: '#fff',
            borderColor: 'var(--bd-accent)',
          }}
        >
          + 新建配置
        </button>
      </header>

      {error && (
        <section
          className="rounded-xl border px-4 py-3 text-xs"
          style={{
            borderColor: 'rgba(239,68,68,0.4)',
            background: 'rgba(239,68,68,0.08)',
            color: 'rgb(220,38,38)',
          }}
        >
          {error}
        </section>
      )}
      {toast && (
        <section
          className="rounded-xl border px-4 py-2 text-xs"
          style={{
            borderColor: 'rgba(34,197,94,0.4)',
            background: 'rgba(34,197,94,0.08)',
            color: 'rgb(22,101,52)',
          }}
        >
          {toast}
        </section>
      )}

      {/* 配置列表 */}
      <section
        className="rounded-2xl border overflow-hidden"
        style={{ borderColor: 'var(--bd-border)', background: 'var(--bd-card)' }}
      >
        <div className="px-4 py-3 border-b text-sm font-medium" style={{ borderColor: 'var(--bd-border)', color: 'var(--bd-fg)' }}>
          模型列表 {loading && <span className="text-xs opacity-60">加载中…</span>}
        </div>
        {configs.length === 0 && !loading ? (
          <div className="px-4 py-8 text-center text-xs" style={{ color: 'var(--bd-fg-muted)' }}>
            暂无配置，点击右上角新建。
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr style={{ color: 'var(--bd-fg-muted)' }}>
                  <th className="text-left px-4 py-2 font-medium">名称</th>
                  <th className="text-left px-4 py-2 font-medium">Provider</th>
                  <th className="text-left px-4 py-2 font-medium">模型</th>
                  <th className="text-left px-4 py-2 font-medium">API Key</th>
                  <th className="text-left px-4 py-2 font-medium">状态</th>
                  <th className="text-right px-4 py-2 font-medium">操作</th>
                </tr>
              </thead>
              <tbody>
                {configs.map((c) => (
                  <tr key={c.id} style={{ borderTop: '1px solid var(--bd-border)' }}>
                    <td className="px-4 py-3" style={{ color: 'var(--bd-fg)' }}>
                      <div className="font-medium">{c.name}</div>
                      {c.notes && (
                        <div className="opacity-60 mt-0.5 whitespace-pre-wrap">{c.notes}</div>
                      )}
                    </td>
                    <td className="px-4 py-3 capitalize" style={{ color: 'var(--bd-fg-muted)' }}>
                      {c.provider}
                    </td>
                    <td className="px-4 py-3" style={{ color: 'var(--bd-fg-muted)' }}>
                      <code className="text-[11px]">{c.model}</code>
                    </td>
                    <td className="px-4 py-3" style={{ color: 'var(--bd-fg-muted)' }}>
                      <div className="flex items-center gap-2">
                        <span className="text-[11px]">
                          {c.has_api_key ? c.api_key_masked : '— 未设置 —'}
                        </span>
                        {c.has_api_key && (
                          <button
                            onClick={() => handleReveal(c)}
                            className="text-[10px] underline opacity-70 hover:opacity-100"
                          >
                            {revealKeyFor === c.id ? '隐藏' : '查看'}
                          </button>
                        )}
                      </div>
                      {revealKeyFor === c.id && revealedKey && (
                        <div
                          className="mt-1 text-[10px] font-mono break-all rounded px-2 py-1"
                          style={{ background: 'var(--bd-bg-end)' }}
                        >
                          {revealedKey}
                        </div>
                      )}
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex flex-wrap gap-1">
                        {c.is_default && (
                          <span
                            className="px-1.5 py-0.5 rounded text-[10px] font-medium"
                            style={{ background: 'var(--bd-accent)', color: '#fff' }}
                          >
                            默认
                          </span>
                        )}
                        <span
                          className="px-1.5 py-0.5 rounded text-[10px] font-medium"
                          style={{
                            background: c.enabled
                              ? 'rgba(34,197,94,0.15)'
                              : 'rgba(148,163,184,0.15)',
                            color: c.enabled ? 'rgb(22,101,52)' : 'var(--bd-fg-muted)',
                          }}
                        >
                          {c.enabled ? '启用' : '停用'}
                        </span>
                      </div>
                    </td>
                    <td className="px-4 py-3 text-right">
                      <div className="flex justify-end gap-2 flex-wrap">
                        {!c.is_default && c.enabled && (
                          <button
                            onClick={() => handleSetDefault(c)}
                            className="text-[11px] underline opacity-70 hover:opacity-100"
                          >
                            设默认
                          </button>
                        )}
                        <button
                          onClick={() => openTest(c)}
                          className="text-[11px] underline opacity-70 hover:opacity-100"
                        >
                          测试
                        </button>
                        <button
                          onClick={() => openEdit(c)}
                          className="text-[11px] underline opacity-70 hover:opacity-100"
                        >
                          编辑
                        </button>
                        <button
                          onClick={() => handleDelete(c)}
                          className="text-[11px] underline opacity-70 hover:opacity-100"
                          style={{ color: 'rgb(220,38,38)' }}
                        >
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

      {/* 用户绑定 */}
      <section
        className="rounded-2xl border"
        style={{ borderColor: 'var(--bd-border)', background: 'var(--bd-card)' }}
      >
        <div className="px-4 py-3 border-b text-sm font-medium" style={{ borderColor: 'var(--bd-border)', color: 'var(--bd-fg)' }}>
          用户 → 模型 绑定
        </div>
        <div className="px-4 py-3 space-y-3">
          <div className="flex flex-wrap items-end gap-2">
            <div className="flex-1 min-w-[180px]">
              <label className="block text-[10px] mb-1" style={{ color: 'var(--bd-fg-muted)' }}>
                用户 ID
              </label>
              <input
                value={bindUserId}
                onChange={(e) => setBindUserId(e.target.value)}
                placeholder="从用户管理页复制 user_id"
                className="w-full px-2 py-1.5 rounded text-xs border"
                style={{ borderColor: 'var(--bd-border)', background: 'var(--bd-bg)', color: 'var(--bd-fg)' }}
              />
            </div>
            <div className="flex-1 min-w-[180px]">
              <label className="block text-[10px] mb-1" style={{ color: 'var(--bd-fg-muted)' }}>
                目标模型
              </label>
              <select
                value={bindConfigId}
                onChange={(e) => setBindConfigId(e.target.value)}
                className="w-full px-2 py-1.5 rounded text-xs border"
                style={{ borderColor: 'var(--bd-border)', background: 'var(--bd-bg)', color: 'var(--bd-fg)' }}
              >
                <option value="">— 选择 —</option>
                {configs.filter((c) => c.enabled).map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.name}（{c.provider}/{c.model}）
                  </option>
                ))}
              </select>
            </div>
            <button
              onClick={handleBind}
              className="px-3 py-1.5 rounded text-xs font-medium border"
              style={{
                background: 'var(--bd-accent)',
                color: '#fff',
                borderColor: 'var(--bd-accent)',
              }}
            >
              绑定
            </button>
          </div>

          {bindings.length === 0 ? (
            <div className="text-xs py-4 text-center" style={{ color: 'var(--bd-fg-muted)' }}>
              暂无用户绑定（未绑定的用户走默认模型）。
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-xs">
                <thead>
                  <tr style={{ color: 'var(--bd-fg-muted)' }}>
                    <th className="text-left px-2 py-2 font-medium">用户</th>
                    <th className="text-left px-2 py-2 font-medium">user_id</th>
                    <th className="text-left px-2 py-2 font-medium">绑定模型</th>
                    <th className="text-right px-2 py-2 font-medium">操作</th>
                  </tr>
                </thead>
                <tbody>
                  {bindings.map((b) => (
                    <tr key={b.id} style={{ borderTop: '1px solid var(--bd-border)' }}>
                      <td className="px-2 py-2" style={{ color: 'var(--bd-fg)' }}>
                        {b.user_username || b.user_email || '—'}
                        {b.user_email && b.user_username && (
                          <div className="opacity-60 text-[10px]">{b.user_email}</div>
                        )}
                      </td>
                      <td className="px-2 py-2 font-mono text-[10px]" style={{ color: 'var(--bd-fg-muted)' }}>
                        {b.user_id}
                      </td>
                      <td className="px-2 py-2" style={{ color: 'var(--bd-fg-muted)' }}>
                        {b.config_name}（{b.config_provider}/{b.config_model}）
                      </td>
                      <td className="px-2 py-2 text-right">
                        <button
                          onClick={() => handleUnbind(b.user_id)}
                          className="text-[11px] underline opacity-70 hover:opacity-100"
                          style={{ color: 'rgb(220,38,38)' }}
                        >
                          解绑
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </section>

      {/* 编辑/新建 Modal */}
      {showForm && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center p-4"
          style={{ background: 'rgba(0,0,0,0.5)' }}
          onClick={() => setShowForm(false)}
        >
          <div
            className="max-w-lg w-full rounded-2xl border p-5 space-y-3 max-h-[90vh] overflow-y-auto"
            style={{ background: 'var(--bd-card)', borderColor: 'var(--bd-border)' }}
            onClick={(e) => e.stopPropagation()}
          >
            <h2 className="text-base font-semibold" style={{ color: 'var(--bd-fg)' }}>
              {editing ? '编辑配置' : '新建配置'}
            </h2>

            <Field label="名称">
              <input
                value={form.name}
                onChange={(e) => setForm({ ...form, name: e.target.value })}
                className="w-full px-2 py-1.5 rounded text-xs border"
                style={{ borderColor: 'var(--bd-border)', background: 'var(--bd-bg)', color: 'var(--bd-fg)' }}
                placeholder="例：DeepSeek 主管道"
              />
            </Field>

            <div className="grid grid-cols-2 gap-3">
              <Field label="Provider">
                <select
                  value={form.provider}
                  onChange={(e) => setForm({ ...form, provider: e.target.value as LlmProvider })}
                  className="w-full px-2 py-1.5 rounded text-xs border"
                  style={{ borderColor: 'var(--bd-border)', background: 'var(--bd-bg)', color: 'var(--bd-fg)' }}
                >
                  {PROVIDERS.map((p) => (
                    <option key={p.value} value={p.value}>
                      {p.label}
                    </option>
                  ))}
                </select>
              </Field>
              <Field label="模型名">
                <input
                  value={form.model}
                  onChange={(e) => setForm({ ...form, model: e.target.value })}
                  className="w-full px-2 py-1.5 rounded text-xs border font-mono"
                  style={{ borderColor: 'var(--bd-border)', background: 'var(--bd-bg)', color: 'var(--bd-fg)' }}
                  placeholder="deepseek-v4-pro / moonshot-v1-8k / ..."
                />
              </Field>
            </div>

            <Field label="Base URL（可选）">
              <input
                value={form.base_url}
                onChange={(e) => setForm({ ...form, base_url: e.target.value })}
                className="w-full px-2 py-1.5 rounded text-xs border font-mono"
                style={{ borderColor: 'var(--bd-border)', background: 'var(--bd-bg)', color: 'var(--bd-fg)' }}
                placeholder="https://api.deepseek.com"
              />
            </Field>

            <Field label={editing ? 'API Key（留空 = 不修改）' : 'API Key'}>
              <input
                type="password"
                value={form.api_key}
                onChange={(e) => setForm({ ...form, api_key: e.target.value })}
                className="w-full px-2 py-1.5 rounded text-xs border font-mono"
                style={{ borderColor: 'var(--bd-border)', background: 'var(--bd-bg)', color: 'var(--bd-fg)' }}
                placeholder="sk-..."
                autoComplete="off"
              />
            </Field>

            <Field label="备注（可选）">
              <textarea
                value={form.notes}
                onChange={(e) => setForm({ ...form, notes: e.target.value })}
                rows={2}
                className="w-full px-2 py-1.5 rounded text-xs border"
                style={{ borderColor: 'var(--bd-border)', background: 'var(--bd-bg)', color: 'var(--bd-fg)' }}
              />
            </Field>

            <div className="flex items-center gap-4 text-xs" style={{ color: 'var(--bd-fg-muted)' }}>
              <label className="flex items-center gap-1.5 cursor-pointer">
                <input
                  type="checkbox"
                  checked={form.enabled}
                  onChange={(e) => setForm({ ...form, enabled: e.target.checked })}
                />
                启用
              </label>
              <label className="flex items-center gap-1.5 cursor-pointer">
                <input
                  type="checkbox"
                  checked={form.is_default}
                  onChange={(e) => setForm({ ...form, is_default: e.target.checked })}
                />
                设为默认
              </label>
            </div>

            <div className="flex justify-end gap-2 pt-2">
              <button
                onClick={() => setShowForm(false)}
                className="px-3 py-1.5 rounded text-xs border"
                style={{ borderColor: 'var(--bd-border)', color: 'var(--bd-fg-muted)' }}
              >
                取消
              </button>
              <button
                onClick={handleSave}
                disabled={saving || !form.name.trim() || !form.model.trim()}
                className="px-3 py-1.5 rounded text-xs font-medium border disabled:opacity-50"
                style={{ background: 'var(--bd-accent)', color: '#fff', borderColor: 'var(--bd-accent)' }}
              >
                {saving ? '保存中…' : '保存'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* 联通测试 Modal */}
      {testingConfig && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center p-4"
          style={{ background: 'rgba(0,0,0,0.5)' }}
          onClick={() => setTestingConfig(null)}
        >
          <div
            className="max-w-xl w-full rounded-2xl border p-5 space-y-3"
            style={{ background: 'var(--bd-card)', borderColor: 'var(--bd-border)' }}
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-start justify-between">
              <div>
                <h2 className="text-base font-semibold" style={{ color: 'var(--bd-fg)' }}>
                  联通测试
                </h2>
                <div className="text-[11px] mt-0.5" style={{ color: 'var(--bd-fg-muted)' }}>
                  {testingConfig.name} · {testingConfig.provider}/{testingConfig.model}
                </div>
              </div>
              <button
                onClick={() => setTestingConfig(null)}
                className="text-xs opacity-60 hover:opacity-100"
                style={{ color: 'var(--bd-fg)' }}
              >
                关闭
              </button>
            </div>

            <Field label="测试 Prompt">
              <textarea
                value={testPrompt}
                onChange={(e) => setTestPrompt(e.target.value)}
                rows={3}
                className="w-full px-2 py-1.5 rounded text-xs border"
                style={{ borderColor: 'var(--bd-border)', background: 'var(--bd-bg)', color: 'var(--bd-fg)' }}
              />
            </Field>

            <div className="flex items-center gap-2">
              <button
                onClick={() => runTest()}
                disabled={testing}
                className="px-3 py-1.5 rounded text-xs font-medium border disabled:opacity-50"
                style={{ background: 'var(--bd-accent)', color: '#fff', borderColor: 'var(--bd-accent)' }}
              >
                {testing ? '发送中…' : '发送测试'}
              </button>
              <button
                onClick={() => {
                  setTestPrompt('ping');
                  runTest('ping');
                }}
                disabled={testing}
                className="px-3 py-1.5 rounded text-xs border disabled:opacity-50"
                style={{ borderColor: 'var(--bd-border)', color: 'var(--bd-fg-muted)' }}
              >
                一键 ping
              </button>
            </div>

            {testResult && (
              <div
                className="rounded-xl border px-3 py-2 space-y-1"
                style={{
                  borderColor: testResult.success
                    ? 'rgba(34,197,94,0.4)'
                    : 'rgba(239,68,68,0.4)',
                  background: testResult.success
                    ? 'rgba(34,197,94,0.06)'
                    : 'rgba(239,68,68,0.06)',
                }}
              >
                <div className="flex items-center gap-2 text-xs">
                  <span
                    className="px-1.5 py-0.5 rounded text-[10px] font-medium"
                    style={{
                      background: testResult.success ? 'rgb(22,101,52)' : 'rgb(220,38,38)',
                      color: '#fff',
                    }}
                  >
                    {testResult.success ? '成功' : '失败'}
                  </span>
                  <span style={{ color: 'var(--bd-fg-muted)' }}>
                    {testResult.latency_ms} ms · {testResult.model}
                  </span>
                </div>
                {testResult.success ? (
                  <pre
                    className="text-[11px] whitespace-pre-wrap break-words font-mono"
                    style={{ color: 'var(--bd-fg)' }}
                  >
{testResult.content || '(空响应)'}
                  </pre>
                ) : (
                  <pre
                    className="text-[11px] whitespace-pre-wrap break-words font-mono"
                    style={{ color: 'rgb(220,38,38)' }}
                  >
{testResult.error || '未知错误'}
                  </pre>
                )}
              </div>
            )}

            <div className="text-[10px]" style={{ color: 'var(--bd-fg-muted)' }}>
              测试不经过运行时缓存，直接使用当前数据库中的配置构造请求。
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <label className="block text-[10px] mb-1" style={{ color: 'var(--bd-fg-muted)' }}>
        {label}
      </label>
      {children}
    </div>
  );
}
