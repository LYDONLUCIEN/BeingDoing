'use client';

import { useEffect, useState, useCallback } from 'react';
import { useRouter } from 'next/navigation';
import {
  fetchAdminUsers,
  fetchAdminUserDetail,
  patchAdminUserStatus,
  adminVerifyUserEmail,
  type AdminUserItem,
  type AdminUserDetail,
} from '@/lib/api/admin';

type ActiveFilter = 'all' | 'active' | 'inactive';
type ProfileFilter = 'all' | 'completed' | 'incomplete';

export default function AdminUsersPage() {
  const router = useRouter();
  const [items, setItems] = useState<AdminUserItem[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [pageSize] = useState(50);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [query, setQuery] = useState('');
  const [activeFilter, setActiveFilter] = useState<ActiveFilter>('all');
  const [profileFilter, setProfileFilter] = useState<ProfileFilter>('all');
  const [createdAfter, setCreatedAfter] = useState('');
  const [createdBefore, setCreatedBefore] = useState('');

  // Detail drawer
  const [drawerUser, setDrawerUser] = useState<AdminUserDetail | null>(null);
  const [drawerLoading, setDrawerLoading] = useState(false);

  const loadList = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetchAdminUsers({
        page,
        page_size: pageSize,
        q: query || undefined,
        is_active: activeFilter === 'all' ? null : activeFilter === 'active',
        profile_completed: profileFilter === 'all' ? null : profileFilter === 'completed',
        created_after: createdAfter || undefined,
        created_before: createdBefore || undefined,
      });
      setItems(res.items);
      setTotal(res.total);
    } catch (e: any) {
      setError(e?.message || '加载用户列表失败');
    } finally {
      setLoading(false);
    }
  }, [page, pageSize, query, activeFilter, profileFilter, createdAfter, createdBefore]);

  useEffect(() => {
    loadList();
  }, [loadList]);

  const openDrawer = async (userId: string) => {
    setDrawerLoading(true);
    setDrawerUser(null);
    try {
      const detail = await fetchAdminUserDetail(userId);
      setDrawerUser(detail);
    } catch (e: any) {
      setDrawerUser(null);
    } finally {
      setDrawerLoading(false);
    }
  };

  const closeDrawer = () => {
    setDrawerUser(null);
  };

  const toggleUserStatus = async (userId: string, currentActive: boolean) => {
    const action = currentActive ? '禁用' : '启用';
    if (!confirm(`确定要${action}该用户吗？`)) return;
    try {
      await patchAdminUserStatus(userId, !currentActive);
      await loadList();
      // 如果 drawer 正在显示该用户，刷新详情
      if (drawerUser?.user_id === userId) {
        await openDrawer(userId);
      }
    } catch (e: any) {
      alert(e?.message || `操作失败`);
    }
  };

  const verifyUserEmail = async (userId: string) => {
    try {
      await adminVerifyUserEmail(userId);
      await loadList();
      if (drawerUser?.user_id === userId) {
        await openDrawer(userId);
      }
    } catch (e: any) {
      alert(e?.message || '操作失败');
    }
  };

  const jumpToActivation = (code: string) => {
    closeDrawer();
    router.push(`/admin/activations?q=${encodeURIComponent(code)}`);
  };

  const resetFilters = () => {
    setQuery('');
    setActiveFilter('all');
    setProfileFilter('all');
    setCreatedAfter('');
    setCreatedBefore('');
    setPage(1);
  };

  const totalPages = Math.ceil(total / pageSize);

  const fmtDate = (iso: string | null | undefined) => {
    if (!iso) return '-';
    try {
      return new Date(iso).toLocaleString('zh-CN', {
        month: '2-digit',
        day: '2-digit',
        hour: '2-digit',
        minute: '2-digit',
      });
    } catch {
      return iso;
    }
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-xl font-semibold" style={{ color: 'var(--bd-fg)' }}>
          用户管理
        </h1>
        <p className="text-sm mt-1" style={{ color: 'var(--bd-fg-muted)' }}>
          查看所有注册用户、绑定激活码关系和 profile 详情
        </p>
      </div>

      {/* Filters */}
      <div
        className="rounded-2xl border p-4 space-y-3"
        style={{
          background: 'var(--bd-card, rgba(255,255,255,0.6))',
          borderColor: 'var(--bd-border)',
        }}
      >
        <div className="flex flex-wrap gap-3 items-center">
          <input
            type="text"
            placeholder="搜索 email / username"
            value={query}
            onChange={(e) => {
              setQuery(e.target.value);
              setPage(1);
            }}
            className="px-3 py-2 rounded-lg text-sm border outline-none focus:ring-2 focus:ring-bd-ui-accent/30"
            style={{
              background: 'var(--bd-overlay-md, #fff)',
              borderColor: 'var(--bd-border)',
              color: 'var(--bd-fg)',
            }}
          />
          <select
            value={activeFilter}
            onChange={(e) => {
              setActiveFilter(e.target.value as ActiveFilter);
              setPage(1);
            }}
            className="px-3 py-2 rounded-lg text-sm border outline-none"
            style={{
              background: 'var(--bd-overlay-md, #fff)',
              borderColor: 'var(--bd-border)',
              color: 'var(--bd-fg)',
            }}
          >
            <option value="all">全部状态</option>
            <option value="active">活跃</option>
            <option value="inactive">已禁用</option>
          </select>
          <select
            value={profileFilter}
            onChange={(e) => {
              setProfileFilter(e.target.value as ProfileFilter);
              setPage(1);
            }}
            className="px-3 py-2 rounded-lg text-sm border outline-none"
            style={{
              background: 'var(--bd-overlay-md, #fff)',
              borderColor: 'var(--bd-border)',
              color: 'var(--bd-fg)',
            }}
          >
            <option value="all">Profile 全部</option>
            <option value="completed">已填写</option>
            <option value="incomplete">未填写</option>
          </select>
          <input
            type="date"
            placeholder="注册起始日期"
            value={createdAfter}
            onChange={(e) => {
              setCreatedAfter(e.target.value);
              setPage(1);
            }}
            className="px-3 py-2 rounded-lg text-sm border outline-none"
            style={{
              background: 'var(--bd-overlay-md, #fff)',
              borderColor: 'var(--bd-border)',
              color: 'var(--bd-fg)',
            }}
          />
          <input
            type="date"
            placeholder="注册截止日期"
            value={createdBefore}
            onChange={(e) => {
              setCreatedBefore(e.target.value);
              setPage(1);
            }}
            className="px-3 py-2 rounded-lg text-sm border outline-none"
            style={{
              background: 'var(--bd-overlay-md, #fff)',
              borderColor: 'var(--bd-border)',
              color: 'var(--bd-fg)',
            }}
          />
          <button
            onClick={resetFilters}
            className="px-3 py-2 rounded-lg text-sm border hover:opacity-80 transition-opacity"
            style={{
              borderColor: 'var(--bd-border)',
              color: 'var(--bd-fg-muted)',
            }}
          >
            重置
          </button>
        </div>
      </div>

      {/* Stats bar */}
      <div className="flex items-center gap-4 text-xs" style={{ color: 'var(--bd-fg-muted)' }}>
        <span>共 {total} 位用户</span>
        <span>第 {page} / {totalPages || 1} 页</span>
      </div>

      {/* Table */}
      {error && (
        <div className="rounded-xl border p-3 text-sm" style={{ color: '#ef4444', borderColor: 'var(--bd-border)' }}>
          {error}
        </div>
      )}

      {loading ? (
        <div className="text-sm py-12 text-center" style={{ color: 'var(--bd-fg-muted)' }}>
          加载中...
        </div>
      ) : items.length === 0 ? (
        <div className="text-sm py-12 text-center" style={{ color: 'var(--bd-fg-muted)' }}>
          暂无用户数据
        </div>
      ) : (
        <div className="overflow-x-auto rounded-2xl border" style={{ borderColor: 'var(--bd-border)' }}>
          <table className="w-full text-sm">
            <thead>
              <tr
                className="border-b text-left"
                style={{ background: 'var(--bd-overlay-md, rgba(0,0,0,0.03))', borderColor: 'var(--bd-border)' }}
              >
                <th className="px-4 py-3 font-medium" style={{ color: 'var(--bd-fg-muted)' }}>用户 ID</th>
                <th className="px-4 py-3 font-medium" style={{ color: 'var(--bd-fg-muted)' }}>Email</th>
                <th className="px-4 py-3 font-medium" style={{ color: 'var(--bd-fg-muted)' }}>用户名</th>
                <th className="px-4 py-3 font-medium" style={{ color: 'var(--bd-fg-muted)' }}>状态</th>
                <th className="px-4 py-3 font-medium" style={{ color: 'var(--bd-fg-muted)' }}>邮箱验证</th>
                <th className="px-4 py-3 font-medium" style={{ color: 'var(--bd-fg-muted)' }}>激活码数</th>
                <th className="px-4 py-3 font-medium" style={{ color: 'var(--bd-fg-muted)' }}>Profile</th>
                <th className="px-4 py-3 font-medium" style={{ color: 'var(--bd-fg-muted)' }}>最后登录</th>
                <th className="px-4 py-3 font-medium" style={{ color: 'var(--bd-fg-muted)' }}>注册时间</th>
                <th className="px-4 py-3 font-medium" style={{ color: 'var(--bd-fg-muted)' }}>操作</th>
              </tr>
            </thead>
            <tbody>
              {items.map((u) => (
                <tr
                  key={u.user_id}
                  className="border-b cursor-pointer hover:opacity-80 transition-opacity"
                  style={{ borderColor: 'var(--bd-border)' }}
                  onClick={() => openDrawer(u.user_id)}
                >
                  <td className="px-4 py-3 font-mono text-xs" style={{ color: 'var(--bd-fg)' }}>
                    {u.user_id.slice(0, 8)}...
                  </td>
                  <td className="px-4 py-3" style={{ color: 'var(--bd-fg)' }}>{u.email || '-'}</td>
                  <td className="px-4 py-3" style={{ color: 'var(--bd-fg)' }}>{u.username || '-'}</td>
                  <td className="px-4 py-3">
                    <span
                      className="inline-block px-2 py-0.5 rounded-full text-xs font-medium"
                      style={{
                        background: u.is_active ? 'rgba(34,197,94,0.12)' : 'rgba(239,68,68,0.12)',
                        color: u.is_active ? '#16a34a' : '#dc2626',
                      }}
                    >
                      {u.is_active ? '活跃' : '已禁用'}
                    </span>
                  </td>
                  <td className="px-4 py-3">
                    <span
                      className="inline-block px-2 py-0.5 rounded-full text-xs font-medium"
                      style={{
                        background: u.email_verified !== false ? 'rgba(34,197,94,0.12)' : 'rgba(245,158,11,0.12)',
                        color: u.email_verified !== false ? '#16a34a' : '#d97706',
                      }}
                    >
                      {u.email_verified !== false ? '已验证' : '未验证'}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-center" style={{ color: 'var(--bd-fg)' }}>
                    {u.activation_count}
                  </td>
                  <td className="px-4 py-3">
                    <span
                      className="inline-block px-2 py-0.5 rounded-full text-xs font-medium"
                      style={{
                        background: u.profile_completed ? 'rgba(59,130,246,0.12)' : 'rgba(148,163,184,0.12)',
                        color: u.profile_completed ? '#2563eb' : '#94a3b8',
                      }}
                    >
                      {u.profile_completed ? '已填写' : '未填写'}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-xs" style={{ color: 'var(--bd-fg-muted)' }}>
                    {fmtDate(u.last_login_at)}
                  </td>
                  <td className="px-4 py-3 text-xs" style={{ color: 'var(--bd-fg-muted)' }}>
                    {fmtDate(u.created_at)}
                  </td>
                  <td className="px-4 py-3 flex gap-1">
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        toggleUserStatus(u.user_id, u.is_active);
                      }}
                      className="px-2 py-1 rounded-lg text-xs border hover:opacity-80 transition-opacity"
                      style={{
                        borderColor: 'var(--bd-border)',
                        color: u.is_active ? '#dc2626' : '#16a34a',
                      }}
                    >
                      {u.is_active ? '禁用' : '启用'}
                    </button>
                    {u.email_verified === false && (
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          verifyUserEmail(u.user_id);
                        }}
                        className="px-2 py-1 rounded-lg text-xs border hover:opacity-80 transition-opacity"
                        style={{
                          borderColor: 'var(--bd-border)',
                          color: '#2563eb',
                        }}
                      >
                        验证邮箱
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Pagination */}
      {totalPages > 1 && (
        <div className="flex items-center gap-2 justify-center">
          <button
            disabled={page <= 1}
            onClick={() => setPage(page - 1)}
            className="px-3 py-1.5 rounded-lg text-sm border disabled:opacity-40 hover:opacity-80 transition-opacity"
            style={{ borderColor: 'var(--bd-border)', color: 'var(--bd-fg)' }}
          >
            上一页
          </button>
          {Array.from({ length: Math.min(totalPages, 7) }, (_, i) => {
            const p = page <= 4 ? i + 1 : page - 3 + i;
            if (p > totalPages) return null;
            return (
              <button
                key={p}
                onClick={() => setPage(p)}
                className="px-3 py-1.5 rounded-lg text-sm border hover:opacity-80 transition-opacity"
                style={{
                  borderColor: p === page ? 'var(--bd-ui-accent)' : 'var(--bd-border)',
                  background: p === page ? 'var(--bd-ui-accent)' : 'transparent',
                  color: p === page ? 'var(--bd-ui-accent-fg)' : 'var(--bd-fg)',
                }}
              >
                {p}
              </button>
            );
          })}
          <button
            disabled={page >= totalPages}
            onClick={() => setPage(page + 1)}
            className="px-3 py-1.5 rounded-lg text-sm border disabled:opacity-40 hover:opacity-80 transition-opacity"
            style={{ borderColor: 'var(--bd-border)', color: 'var(--bd-fg)' }}
          >
            下一页
          </button>
        </div>
      )}

      {/* Drawer overlay */}
      {(drawerUser !== null || drawerLoading) && (
        <div
          className="fixed inset-0 z-50 flex justify-end"
          onClick={closeDrawer}
        >
          <div className="absolute inset-0 bg-black/30" />
          <div
            className="relative w-full max-w-lg bg-bd-bg border-l overflow-y-auto shadow-2xl"
            style={{ borderColor: 'var(--bd-border)' }}
            onClick={(e) => e.stopPropagation()}
          >
            <div className="p-6 space-y-6">
              {/* Drawer header */}
              <div className="flex items-center justify-between">
                <h2 className="text-lg font-semibold" style={{ color: 'var(--bd-fg)' }}>用户详情</h2>
                <button
                  onClick={closeDrawer}
                  className="text-bd-muted hover:text-bd-fg text-xl leading-none"
                >
                  &times;
                </button>
              </div>

              {drawerLoading ? (
                <div className="text-sm py-8 text-center" style={{ color: 'var(--bd-fg-muted)' }}>
                  加载中...
                </div>
              ) : drawerUser ? (
                <>
                  {/* Basic info */}
                  <section>
                    <h3 className="text-sm font-medium mb-3" style={{ color: 'var(--bd-fg-muted)' }}>
                      基本信息
                    </h3>
                    <div className="space-y-2 text-sm">
                      <Row label="用户 ID" value={drawerUser.user_id} mono />
                      <Row label="Email" value={drawerUser.email || '-'} />
                      <Row label="手机" value={drawerUser.phone || '-'} />
                      <Row label="用户名" value={drawerUser.username || '-'} />
                      <Row label="性别" value={drawerUser.profile.gender || '-'} />
                      <Row label="年龄" value={drawerUser.profile.age != null ? String(drawerUser.profile.age) : '-'} />
                      <Row label="状态">
                        <span
                          className="inline-block px-2 py-0.5 rounded-full text-xs font-medium"
                          style={{
                            background: drawerUser.is_active ? 'rgba(34,197,94,0.12)' : 'rgba(239,68,68,0.12)',
                            color: drawerUser.is_active ? '#16a34a' : '#dc2626',
                          }}
                        >
                          {drawerUser.is_active ? '活跃' : '已禁用'}
                        </span>
                      </Row>
                      <Row label="Profile" value={drawerUser.profile.profile_completed ? '已填写' : '未填写'} />
                      <Row label="注册时间" value={fmtDate(drawerUser.created_at)} />
                      <Row label="最后登录" value={fmtDate(drawerUser.last_login_at)} />
                    </div>
                  </section>

                  {/* Actions */}
                  <section>
                    <button
                      onClick={() => toggleUserStatus(drawerUser.user_id, drawerUser.is_active)}
                      className="px-4 py-2 rounded-lg text-sm font-medium border hover:opacity-80 transition-opacity"
                      style={{
                        borderColor: drawerUser.is_active ? '#dc2626' : '#16a34a',
                        color: drawerUser.is_active ? '#dc2626' : '#16a34a',
                      }}
                    >
                      {drawerUser.is_active ? '禁用该用户' : '启用该用户'}
                    </button>
                  </section>

                  {/* Activations */}
                  <section>
                    <h3 className="text-sm font-medium mb-3" style={{ color: 'var(--bd-fg-muted)' }}>
                      绑定激活码 ({drawerUser.activations.length})
                    </h3>
                    {drawerUser.activations.length === 0 ? (
                      <p className="text-sm" style={{ color: 'var(--bd-fg-muted)' }}>无绑定激活码</p>
                    ) : (
                      <div className="space-y-2">
                        {drawerUser.activations.map((ac) => (
                          <div
                            key={ac.activation_code}
                            className="rounded-lg border p-3 text-sm space-y-1"
                            style={{
                              borderColor: 'var(--bd-border)',
                              background: 'var(--bd-overlay-md, rgba(0,0,0,0.02))',
                            }}
                          >
                            <div className="flex items-center justify-between">
                              <span className="font-mono font-medium cursor-pointer hover:underline" style={{ color: 'var(--bd-fg)' }} onClick={() => jumpToActivation(ac.activation_code)}>
                                {ac.activation_code}
                              </span>
                              <span
                                className="inline-block px-2 py-0.5 rounded-full text-xs"
                                style={{
                                  background: ac.status === 'active' ? 'rgba(34,197,94,0.12)' : 'rgba(239,68,68,0.12)',
                                  color: ac.status === 'active' ? '#16a34a' : '#dc2626',
                                }}
                              >
                                {ac.status}
                              </span>
                            </div>
                            <div className="text-xs" style={{ color: 'var(--bd-fg-muted)' }}>
                              <span>创建: {fmtDate(ac.created_at)}</span>
                              {ac.expires_at && <span> · 过期: {fmtDate(ac.expires_at)}</span>}
                              {ac.claimed_at && <span> · 绑定: {fmtDate(ac.claimed_at)}</span>}
                              {ac.is_sandbox && <span> · 沙箱</span>}
                            </div>
                          </div>
                        ))}
                      </div>
                    )}
                  </section>

                  {/* Work history */}
                  <section>
                    <h3 className="text-sm font-medium mb-3" style={{ color: 'var(--bd-fg-muted)' }}>
                      工作履历 ({drawerUser.work_histories.length})
                    </h3>
                    {drawerUser.work_histories.length === 0 ? (
                      <p className="text-sm" style={{ color: 'var(--bd-fg-muted)' }}>无工作履历</p>
                    ) : (
                      <div className="space-y-3">
                        {drawerUser.work_histories.map((wh) => (
                          <div
                            key={wh.id}
                            className="rounded-lg border p-3 text-sm space-y-1"
                            style={{
                              borderColor: 'var(--bd-border)',
                              background: 'var(--bd-overlay-md, rgba(0,0,0,0.02))',
                            }}
                          >
                            <div className="font-medium" style={{ color: 'var(--bd-fg)' }}>
                              {wh.position || '-'} @ {wh.company || '-'}
                            </div>
                            <div className="text-xs" style={{ color: 'var(--bd-fg-muted)' }}>
                              {wh.start_date || '?'} ~ {wh.end_date || '至今'}
                            </div>
                            {wh.skills_used && (
                              <div className="text-xs" style={{ color: 'var(--bd-fg-muted)' }}>
                                技能: {wh.skills_used}
                              </div>
                            )}
                            {wh.evaluation && (
                              <div className="text-xs mt-1" style={{ color: 'var(--bd-fg-muted)' }}>
                                {wh.evaluation}
                              </div>
                            )}
                            {wh.projects.length > 0 && (
                              <div className="mt-2 space-y-1">
                                <span className="text-xs font-medium" style={{ color: 'var(--bd-fg-muted)' }}>
                                  项目经历:
                                </span>
                                {wh.projects.map((p) => (
                                  <div key={p.id} className="ml-3 text-xs" style={{ color: 'var(--bd-fg-muted)' }}>
                                    <span className="font-medium" style={{ color: 'var(--bd-fg)' }}>{p.name}</span>
                                    {p.role && <span> ({p.role})</span>}
                                    {p.achievements && <span> - {p.achievements}</span>}
                                  </div>
                                ))}
                              </div>
                            )}
                          </div>
                        ))}
                      </div>
                    )}
                  </section>
                </>
              ) : (
                <div className="text-sm py-8 text-center" style={{ color: 'var(--bd-fg-muted)' }}>
                  未找到用户信息
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function Row({ label, value, mono, children }: { label: string; value?: React.ReactNode; mono?: boolean; children?: React.ReactNode }) {
  return (
    <div className="flex items-baseline gap-2">
      <span className="w-20 flex-shrink-0 text-xs" style={{ color: 'var(--bd-fg-muted)' }}>
        {label}
      </span>
      {children ? (
        children
      ) : (
        <span
          className={mono ? 'font-mono text-xs' : 'text-sm'}
          style={{ color: 'var(--bd-fg)', wordBreak: 'break-all' }}
        >
          {value ?? '-'}
        </span>
      )}
    </div>
  );
}
