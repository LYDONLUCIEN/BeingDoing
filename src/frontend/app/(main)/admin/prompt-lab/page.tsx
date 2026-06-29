'use client';

import { useEffect, useMemo, useState } from 'react';
import { PromptCatalogViewer } from '@/components/admin/PromptCatalogViewer';
import {
  activatePromptLabVersion,
  addPromptLabProfileVersion,
  bindPromptLabProfile,
  createPromptLabProfile,
  exportPromptLabCurrent,
  getPromptLabProfile,
  listPromptLabBindings,
  listPromptLabProfiles,
  type PromptLabBinding,
  type PromptLabProfileDetail,
  type PromptLabProfileSummary,
} from '@/lib/api/admin';
import { formatLocalDateTime } from '@/lib/utils/formatTime';

type TabKey = 'lab' | 'catalog';

export default function AdminPromptLabPage() {
  const [activeTab, setActiveTab] = useState<TabKey>('catalog');
  const [profiles, setProfiles] = useState<PromptLabProfileSummary[]>([]);
  const [selectedProfileId, setSelectedProfileId] = useState<string>('');
  const [detail, setDetail] = useState<PromptLabProfileDetail | null>(null);
  const [bindings, setBindings] = useState<PromptLabBinding[]>([]);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [lastCopiedMeta, setLastCopiedMeta] = useState<{
    mode: 'template' | 'merged';
    length: number;
  } | null>(null);

  const [newProfileName, setNewProfileName] = useState('');
  const [newProfileDesc, setNewProfileDesc] = useState('');
  const [newTemplate, setNewTemplate] = useState('');
  const [newGoalHint, setNewGoalHint] = useState('');
  const [bindActivationCode, setBindActivationCode] = useState('');

  const currentVersion = useMemo(() => {
    if (!detail?.current_version_id) return null;
    return (detail.versions || []).find((v) => v.version_id === detail.current_version_id) || null;
  }, [detail]);

  const loadProfiles = async () => {
    const list = await listPromptLabProfiles();
    setProfiles(list);
    if (!selectedProfileId && list.length > 0) {
      setSelectedProfileId(list[0].profile_id);
    }
  };

  const loadBindings = async () => {
    const list = await listPromptLabBindings();
    setBindings(list);
  };

  const loadDetail = async (profileId: string) => {
    if (!profileId) {
      setDetail(null);
      return;
    }
    const d = await getPromptLabProfile(profileId);
    setDetail(d);
    const v = (d.versions || []).find((x) => x.version_id === d.current_version_id);
    setNewTemplate(v?.simple_chat_system_prompt_template || '');
    setNewGoalHint(v?.extra_goal_hint || '');
  };

  const fullReload = async () => {
    setLoading(true);
    setError(null);
    try {
      await Promise.all([loadProfiles(), loadBindings()]);
      if (selectedProfileId) {
        await loadDetail(selectedProfileId);
      }
    } catch (e: any) {
      setError(e?.message || '加载 Prompt Lab 失败');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void fullReload();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (!selectedProfileId) return;
    setError(null);
    loadDetail(selectedProfileId).catch((e: any) => {
      setError(e?.message || '加载 profile 详情失败');
    });
  }, [selectedProfileId]);

  const handleCreateProfile = async () => {
    if (!newProfileName.trim()) return;
    setSaving(true);
    setError(null);
    try {
      const created = await createPromptLabProfile({
        name: newProfileName.trim(),
        description: newProfileDesc.trim() || undefined,
      });
      setNotice('已创建 profile');
      setNewProfileName('');
      setNewProfileDesc('');
      await loadProfiles();
      setSelectedProfileId(created.profile_id);
    } catch (e: any) {
      setError(e?.message || '创建 profile 失败');
    } finally {
      setSaving(false);
    }
  };

  const handleSaveVersion = async () => {
    if (!selectedProfileId || !newTemplate.trim()) return;
    setSaving(true);
    setError(null);
    try {
      await addPromptLabProfileVersion(selectedProfileId, {
        simple_chat_system_prompt_template: newTemplate,
        extra_goal_hint: newGoalHint || '',
      });
      setNotice('已保存新版本并设为当前生效版本');
      await Promise.all([loadProfiles(), loadDetail(selectedProfileId)]);
    } catch (e: any) {
      setError(e?.message || '保存版本失败');
    } finally {
      setSaving(false);
    }
  };

  const handleActivateVersion = async (versionId: string) => {
    if (!selectedProfileId || !versionId) return;
    setSaving(true);
    setError(null);
    try {
      await activatePromptLabVersion(selectedProfileId, versionId);
      setNotice('已切换生效版本');
      await Promise.all([loadProfiles(), loadDetail(selectedProfileId)]);
    } catch (e: any) {
      setError(e?.message || '切换版本失败');
    } finally {
      setSaving(false);
    }
  };

  const handleBindActivation = async () => {
    if (!selectedProfileId || !bindActivationCode.trim()) return;
    setSaving(true);
    setError(null);
    try {
      await bindPromptLabProfile({
        activation_code: bindActivationCode.trim().toUpperCase(),
        profile_id: selectedProfileId,
      });
      setNotice('绑定成功（仅对该 SBX/ADM 工作区生效）');
      setBindActivationCode('');
      await loadBindings();
    } catch (e: any) {
      setError(e?.message || '绑定失败');
    } finally {
      setSaving(false);
    }
  };

  const handleCopyCurrent = async (mode: 'template' | 'merged') => {
    if (!selectedProfileId) return;
    setSaving(true);
    setError(null);
    try {
      const payload = await exportPromptLabCurrent(selectedProfileId);
      const text =
        mode === 'template'
          ? (payload.template || '')
          : (payload.merged_for_copy || '');
      await navigator.clipboard.writeText(text);
      setLastCopiedMeta({ mode, length: text.length });
      setNotice(
        mode === 'template'
          ? '已复制当前生效版本的纯模板'
          : '已复制当前生效版本（模板+goals）到剪贴板，可回填代码模板文件',
      );
    } catch (e: any) {
      setError(e?.message || '复制失败');
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="max-w-7xl mx-auto space-y-6">
      <header>
        <h1 className="text-xl font-semibold mb-2" style={{ color: 'var(--bd-fg)' }}>
          Prompt Lab（sandbox_only）
        </h1>
        <p className="text-sm text-bd-muted leading-relaxed">
          这里编辑的是沙箱提示词版本，不会直接改代码模板。仅在
          <code className="mx-1">SBX/ADM</code>
          工作区、且管理员调试开关开启时生效。生产用户流程不受影响。
        </p>
        <div className="mt-4 inline-flex rounded-xl border border-bd-border overflow-hidden text-sm">
          <button
            type="button"
            onClick={() => setActiveTab('catalog')}
            className={`px-4 py-2 ${activeTab === 'catalog' ? 'bg-bd-ui-accent text-bd-ui-accent-fg' : 'hover:bg-bd-overlay-sm text-bd-fg'}`}
          >
            Prompt Catalog
          </button>
          <button
            type="button"
            onClick={() => setActiveTab('lab')}
            className={`px-4 py-2 ${activeTab === 'lab' ? 'bg-bd-ui-accent text-bd-ui-accent-fg' : 'hover:bg-bd-overlay-sm text-bd-fg'}`}
          >
            Profile 编辑
          </button>
        </div>
      </header>

      {activeTab === 'catalog' ? (
        <PromptCatalogViewer profileId={selectedProfileId} bindings={bindings} />
      ) : null}

      {activeTab === 'lab' ? (
        <>
      {error && (
        <div className="rounded-xl border border-red-200 bg-red-50 text-red-700 px-4 py-3 text-xs">{error}</div>
      )}
      {notice && (
        <div className="rounded-xl border border-emerald-200 bg-emerald-50 text-emerald-700 px-4 py-3 text-xs">
          {notice}
        </div>
      )}

      <section className="rounded-2xl bg-bd-card border border-bd-border p-5 space-y-3">
        <h2 className="text-sm font-medium text-bd-fg">新建 Profile</h2>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
          <input
            value={newProfileName}
            onChange={(e) => setNewProfileName(e.target.value)}
            placeholder="profile 名称"
            className="rounded-lg border border-bd-border bg-bd-overlay px-3 py-2 text-sm"
          />
          <input
            value={newProfileDesc}
            onChange={(e) => setNewProfileDesc(e.target.value)}
            placeholder="描述（可选）"
            className="rounded-lg border border-bd-border bg-bd-overlay px-3 py-2 text-sm md:col-span-2"
          />
        </div>
        <button
          type="button"
          onClick={handleCreateProfile}
          disabled={saving || !newProfileName.trim()}
          className="px-3 py-2 rounded-lg bg-bd-ui-accent text-bd-ui-accent-fg text-sm disabled:opacity-50"
        >
          创建
        </button>
      </section>

      <section className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="rounded-2xl bg-bd-card border border-bd-border p-4 space-y-3">
          <h3 className="text-sm font-medium text-bd-fg">Profiles</h3>
          {loading ? (
            <p className="text-xs text-bd-subtle">加载中...</p>
          ) : profiles.length === 0 ? (
            <p className="text-xs text-bd-subtle">暂无 profile</p>
          ) : (
            <div className="space-y-2">
              {profiles.map((p) => (
                <button
                  type="button"
                  key={p.profile_id}
                  onClick={() => setSelectedProfileId(p.profile_id)}
                  className={`w-full text-left rounded-lg border px-3 py-2 text-xs ${
                    p.profile_id === selectedProfileId
                      ? 'border-bd-ui-accent bg-bd-overlay-md'
                      : 'border-bd-border hover:bg-bd-overlay-sm'
                  }`}
                >
                  <p className="font-medium text-bd-fg">{p.name}</p>
                  <p className="text-bd-subtle mt-1">{p.description || '—'}</p>
                  <p className="text-bd-subtle mt-1">版本数：{p.version_count}</p>
                </button>
              ))}
            </div>
          )}
        </div>

        <div className="rounded-2xl bg-bd-card border border-bd-border p-4 space-y-3 lg:col-span-2">
          <h3 className="text-sm font-medium text-bd-fg">编辑当前 Profile</h3>
          {!detail ? (
            <p className="text-xs text-bd-subtle">请选择一个 profile。</p>
          ) : (
            <>
              <p className="text-xs text-bd-subtle">
                当前：<span className="text-bd-fg">{detail.name}</span>
                {' · '}
                生效版本：<code>{detail.current_version_id || '无'}</code>
              </p>
              <textarea
                value={newTemplate}
                onChange={(e) => setNewTemplate(e.target.value)}
                placeholder="simple_chat_system 提示词模板（Jinja 变量：phase/question_bank/basic_info/prior_block）"
                rows={14}
                className="w-full rounded-lg border border-bd-border bg-bd-overlay px-3 py-2 text-xs font-mono"
              />
              <textarea
                value={newGoalHint}
                onChange={(e) => setNewGoalHint(e.target.value)}
                placeholder="额外 goals 补充（可选，会附加到系统提示词末尾）"
                rows={4}
                className="w-full rounded-lg border border-bd-border bg-bd-overlay px-3 py-2 text-xs"
              />
              <button
                type="button"
                onClick={handleSaveVersion}
                disabled={saving || !newTemplate.trim()}
                className="px-3 py-2 rounded-lg bg-bd-ui-accent text-bd-ui-accent-fg text-sm disabled:opacity-50"
              >
                保存为新版本并生效
              </button>
              <button
                type="button"
                onClick={() => handleCopyCurrent('template')}
                disabled={saving || !selectedProfileId || !currentVersion}
                className="ml-2 px-3 py-2 rounded-lg border border-bd-border hover:bg-bd-overlay-md text-sm disabled:opacity-50"
              >
                复制纯模板
              </button>
              <button
                type="button"
                onClick={() => handleCopyCurrent('merged')}
                disabled={saving || !selectedProfileId || !currentVersion}
                className="ml-2 px-3 py-2 rounded-lg border border-bd-border hover:bg-bd-overlay-md text-sm disabled:opacity-50"
              >
                复制当前生效版本（回填用）
              </button>
              {lastCopiedMeta && (
                <span className="ml-2 text-xs text-bd-subtle">
                  上次复制：
                  {lastCopiedMeta.mode === 'template' ? '纯模板' : '模板+goals'}
                  {' · '}
                  {lastCopiedMeta.length} 字符
                </span>
              )}

              <div className="pt-3 border-t border-bd-border">
                <p className="text-xs text-bd-subtle mb-2">历史版本</p>
                <div className="space-y-2 max-h-56 overflow-y-auto">
                  {(detail.versions || []).slice().reverse().map((v) => {
                    const isCurrent = v.version_id === detail.current_version_id;
                    return (
                      <div key={v.version_id} className="rounded-lg border border-bd-border p-2 text-xs">
                        <p className="text-bd-fg font-mono">{v.version_id}</p>
                        <p className="text-bd-subtle mt-1">{v.created_at ? formatLocalDateTime(v.created_at) : '—'}</p>
                        <div className="mt-2">
                          {isCurrent ? (
                            <span className="text-emerald-600">当前生效</span>
                          ) : (
                            <button
                              type="button"
                              onClick={() => handleActivateVersion(v.version_id)}
                              disabled={saving}
                              className="px-2 py-1 rounded border border-bd-border hover:bg-bd-overlay-md"
                            >
                              设为生效
                            </button>
                          )}
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>
            </>
          )}
        </div>
      </section>

      <section className="rounded-2xl bg-bd-card border border-bd-border p-5 space-y-3">
        <h3 className="text-sm font-medium text-bd-fg">绑定到 SBX/ADM 激活码</h3>
        <p className="text-xs text-bd-subtle">
          绑定后，该激活码对应工作区的 simple-chat 会使用当前 profile 的生效版本。普通激活码不支持绑定。
        </p>
        <div className="flex flex-wrap gap-2 items-center">
          <input
            value={bindActivationCode}
            onChange={(e) => setBindActivationCode(e.target.value.toUpperCase())}
            placeholder="输入 SBX/ADM 激活码"
            className="rounded-lg border border-bd-border bg-bd-overlay px-3 py-2 text-sm w-64"
          />
          <button
            type="button"
            onClick={handleBindActivation}
            disabled={saving || !selectedProfileId || !bindActivationCode.trim()}
            className="px-3 py-2 rounded-lg bg-bd-ui-accent text-bd-ui-accent-fg text-sm disabled:opacity-50"
          >
            绑定当前 profile
          </button>
        </div>

        <div className="pt-3 border-t border-bd-border">
          <p className="text-xs text-bd-subtle mb-2">已绑定列表</p>
          {bindings.length === 0 ? (
            <p className="text-xs text-bd-subtle">暂无绑定</p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-xs">
                <thead>
                  <tr className="text-left text-bd-subtle border-b border-bd-border">
                    <th className="py-2 pr-2">activation_code</th>
                    <th className="py-2 pr-2">profile_id</th>
                    <th className="py-2 pr-2">updated_at</th>
                  </tr>
                </thead>
                <tbody>
                  {bindings.map((b) => (
                    <tr key={`${b.activation_code}-${b.profile_id}`} className="border-b border-bd-border/50">
                      <td className="py-2 pr-2 font-mono">{b.activation_code}</td>
                      <td className="py-2 pr-2 font-mono">{b.profile_id}</td>
                      <td className="py-2 pr-2">{b.updated_at ? formatLocalDateTime(b.updated_at) : '—'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </section>
        </>
      ) : null}
    </div>
  );
}
