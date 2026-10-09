'use client';

import { useEffect, useState, useCallback } from 'react';
import {
  fetchAdminUsers,
  fetchFilterSchema,
  exportUsersFullData,
  type AdminUserItem,
  type FilterSchemaEntry,
  type FilterValues,
} from '@/lib/api/admin';
import { FilterBar } from '@/components/admin/FilterBar';
import { toDate } from '@/lib/utils/formatTime';

/** 用户类型 tag 样式（与用户管理页同口径：真实=绿 / 内测=蓝 / 测试=灰 / 管理员=橙） */
const USER_TYPE_TAG: Record<string, { label: string; bg: string; color: string }> = {
  real: { label: '真实用户', bg: 'rgba(34,197,94,0.12)', color: '#16a34a' },
  beta: { label: '内测用户', bg: 'rgba(59,130,246,0.12)', color: '#2563eb' },
  test: { label: '测试账号', bg: 'rgba(148,163,184,0.18)', color: '#64748b' },
  admin: { label: '管理员', bg: 'rgba(245,158,11,0.14)', color: '#d97706' },
};

// 后端单次导出用户数上限（users/export MAX_EXPORT_USERS）
const MAX_EXPORT_USERS = 50;

export default function AdminDataExportPage() {
  const [items, setItems] = useState<AdminUserItem[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [pageSize] = useState(50);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  /** 筛选 schema（ADR-0023）；拉取失败时为空数组，降级为仅关键词搜索框 */
  const [schema, setSchema] = useState<FilterSchemaEntry[]>([]);
  /** 通用筛选值（注册表 key → 值，空 key 已剔除）；同时作用于列表与「按筛选全量导出」 */
  const [filters, setFilters] = useState<FilterValues>({});

  /** 跨页勾选的 user_id 集合 */
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [exporting, setExporting] = useState(false);

  const loadList = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetchAdminUsers({
        page,
        page_size: pageSize,
        filters,
      });
      setItems(res.items);
      setTotal(res.total);
    } catch (e: any) {
      setError(e?.message || '加载用户列表失败');
    } finally {
      setLoading(false);
    }
  }, [page, pageSize, filters]);

  // 拉取筛选 schema（失败降级：FilterBar 不渲染，仅保留关键词搜索框）
  useEffect(() => {
    (async () => {
      try {
        setSchema(await fetchFilterSchema());
      } catch {
        setSchema([]);
      }
    })();
  }, []);

  useEffect(() => {
    loadList();
  }, [loadList]);

  const toggleSelect = (userId: string) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(userId)) {
        next.delete(userId);
      } else {
        next.add(userId);
      }
      return next;
    });
  };

  /** 当前页全选 / 取消全选 */
  const toggleSelectPage = () => {
    setSelected((prev) => {
      const next = new Set(prev);
      const allOnPage = items.every((u) => next.has(u.user_id));
      if (allOnPage) {
        items.forEach((u) => next.delete(u.user_id));
      } else {
        items.forEach((u) => next.add(u.user_id));
      }
      return next;
    });
  };

  /** 组装导出 payload：导出入口再剔一次空 key（保险；FilterBar onChange 时已剔除） */
  const buildFilterPayload = () => {
    const cleaned: FilterValues = {};
    for (const [key, value] of Object.entries(filters)) {
      if (value === undefined) continue;
      if (Array.isArray(value) && value.length === 0) continue;
      if (typeof value === 'string' && !value.trim()) continue;
      if (
        typeof value === 'object' &&
        !Array.isArray(value) &&
        !(value.after || '').trim() &&
        !(value.before || '').trim()
      ) {
        continue;
      }
      cleaned[key] = value;
    }
    return { filters: cleaned };
  };

  const hasActiveFilter = Object.keys(filters).length > 0;

  /** 导出勾选的用户（显式 user_ids） */
  const exportSelected = async () => {
    if (selected.size === 0) return;
    setExporting(true);
    setError(null);
    try {
      await exportUsersFullData({ user_ids: Array.from(selected) });
    } catch (e: any) {
      // blob 响应的错误体需要手动解析
      setError(e?.response?.data instanceof Blob ? '导出失败，请检查所选用户数（≤50）' : e?.message || '导出失败');
    } finally {
      setExporting(false);
    }
  };

  /** 按当前筛选条件服务端全量导出（不依赖勾选，覆盖所有分页） */
  const exportByFilter = async () => {
    if (!hasActiveFilter) return;
    setExporting(true);
    setError(null);
    try {
      await exportUsersFullData(buildFilterPayload());
    } catch (e: any) {
      setError(e?.response?.data instanceof Blob ? '导出失败：匹配用户数可能超过 50，请缩小筛选范围' : e?.message || '导出失败');
    } finally {
      setExporting(false);
    }
  };

  const totalPages = Math.ceil(total / pageSize);

  const fmtDate = (iso: string | null | undefined) => {
    if (!iso) return '-';
    try {
      const d = toDate(iso);
      return d
        ? d.toLocaleString('zh-CN', {
            month: '2-digit',
            day: '2-digit',
            hour: '2-digit',
            minute: '2-digit',
          })
        : iso;
    } catch {
      return iso;
    }
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-xl font-semibold" style={{ color: 'var(--bd-fg)' }}>
          数据导出
        </h1>
        <p className="text-sm mt-1" style={{ color: 'var(--bd-fg-muted)' }}>
          按用户全量导出：注册邮箱、激活码、profile、工作履历、备注 + 名下全部报告
          （五轮对话全线程、rumination 表格、报告全文 markdown）。跨激活码的旅程完整打包在一个用户目录里。
        </p>
      </div>

      {/* Filters（ADR-0023 通用筛选条） */}
      <div
        className="rounded-2xl border p-4 space-y-3"
        style={{
          background: 'var(--bd-card, rgba(255,255,255,0.6))',
          borderColor: 'var(--bd-border)',
        }}
      >
        {schema.length > 0 ? (
          <FilterBar
            schema={schema}
            values={filters}
            onChange={(v) => {
              setFilters(v);
              setPage(1);
            }}
          />
        ) : (
          // schema 拉取失败降级：仅保留关键词搜索框（写入 filters.q，同走新筛选链路）
          <div className="flex flex-wrap gap-3 items-center">
            <input
              type="text"
              placeholder="搜索 email / username"
              value={typeof filters.q === 'string' ? filters.q : ''}
              onChange={(e) => {
                const v = e.target.value;
                setFilters((prev) => {
                  const next = { ...prev };
                  if (v.trim()) {
                    next.q = v;
                  } else {
                    delete next.q;
                  }
                  return next;
                });
                setPage(1);
              }}
              className="px-3 py-2 rounded-lg text-sm border outline-none"
              style={{
                background: 'var(--bd-overlay-md, #fff)',
                borderColor: 'var(--bd-border)',
                color: 'var(--bd-fg)',
              }}
            />
          </div>
        )}
      </div>

      {/* Export actions */}
      <div
        className="rounded-2xl border p-4 flex flex-wrap items-center gap-3"
        style={{ borderColor: 'var(--bd-border)' }}
      >
        <button
          onClick={exportSelected}
          disabled={exporting || selected.size === 0 || selected.size > MAX_EXPORT_USERS}
          className="px-4 py-2 rounded-lg text-sm font-medium border hover:opacity-80 transition-opacity disabled:opacity-40"
          style={{ borderColor: '#7c3aed', color: '#7c3aed' }}
        >
          {exporting ? '导出中...' : `导出选中（${selected.size}）`}
        </button>
        <button
          onClick={exportByFilter}
          disabled={exporting || !hasActiveFilter || total > MAX_EXPORT_USERS}
          className="px-4 py-2 rounded-lg text-sm font-medium border hover:opacity-80 transition-opacity disabled:opacity-40"
          style={{ borderColor: '#2563eb', color: '#2563eb' }}
        >
          按筛选全量导出（匹配 {total} 人）
        </button>
        {selected.size > 0 && (
          <button
            onClick={() => setSelected(new Set())}
            className="px-3 py-1.5 rounded-lg text-xs border hover:opacity-80 transition-opacity"
            style={{ borderColor: 'var(--bd-border)', color: 'var(--bd-fg-muted)' }}
          >
            清空勾选
          </button>
        )}
        <span className="text-xs" style={{ color: 'var(--bd-fg-muted)' }}>
          单次最多 {MAX_EXPORT_USERS} 个用户；勾选跨分页保留
          {total > MAX_EXPORT_USERS && '；当前筛选匹配数超限，请缩小范围'}
        </span>
      </div>

      {error && (
        <div
          className="rounded-xl border p-3 text-sm"
          style={{ color: '#ef4444', borderColor: 'var(--bd-border)' }}
        >
          {error}
        </div>
      )}

      {/* Table */}
      {loading ? (
        <div className="text-sm py-12 text-center" style={{ color: 'var(--bd-fg-muted)' }}>
          加载中...
        </div>
      ) : items.length === 0 ? (
        <div className="text-sm py-12 text-center" style={{ color: 'var(--bd-fg-muted)' }}>
          暂无匹配用户
        </div>
      ) : (
        <div
          className="overflow-x-auto rounded-2xl border"
          style={{ borderColor: 'var(--bd-border)' }}
        >
          <table className="w-full text-sm">
            <thead>
              <tr
                className="border-b text-left"
                style={{
                  background: 'var(--bd-overlay-md, rgba(0,0,0,0.03))',
                  borderColor: 'var(--bd-border)',
                }}
              >
                <th className="px-4 py-3 w-10">
                  <input
                    type="checkbox"
                    checked={items.length > 0 && items.every((u) => selected.has(u.user_id))}
                    onChange={toggleSelectPage}
                  />
                </th>
                <th className="px-4 py-3 font-medium" style={{ color: 'var(--bd-fg-muted)' }}>
                  用户
                </th>
                <th className="px-4 py-3 font-medium" style={{ color: 'var(--bd-fg-muted)' }}>
                  用户 ID
                </th>
                <th className="px-4 py-3 font-medium" style={{ color: 'var(--bd-fg-muted)' }}>
                  用户类型
                </th>
                <th className="px-4 py-3 font-medium" style={{ color: 'var(--bd-fg-muted)' }}>
                  备注
                </th>
                <th className="px-4 py-3 font-medium" style={{ color: 'var(--bd-fg-muted)' }}>
                  激活码数
                </th>
                <th className="px-4 py-3 font-medium" style={{ color: 'var(--bd-fg-muted)' }}>
                  注册时间
                </th>
              </tr>
            </thead>
            <tbody>
              {items.map((u) => {
                const tag = USER_TYPE_TAG[u.user_type || 'real'] || USER_TYPE_TAG.real;
                const isChecked = selected.has(u.user_id);
                return (
                  <tr
                    key={u.user_id}
                    className="border-b cursor-pointer hover:opacity-80 transition-opacity"
                    style={{
                      borderColor: 'var(--bd-border)',
                      background: isChecked ? 'var(--bd-overlay-md, rgba(0,0,0,0.03))' : undefined,
                    }}
                    onClick={() => toggleSelect(u.user_id)}
                  >
                    <td className="px-4 py-3" onClick={(e) => e.stopPropagation()}>
                      <input
                        type="checkbox"
                        checked={isChecked}
                        onChange={() => toggleSelect(u.user_id)}
                      />
                    </td>
                    {/* 用户：昵称优先（加粗）+ 邮箱次行——运营识别第一视角（2026-10-09） */}
                    <td className="px-4 py-3">
                      <div className="font-medium leading-tight" style={{ color: 'var(--bd-fg)' }}>
                        {u.username || u.email || '-'}
                      </div>
                      {u.username && u.email ? (
                        <div
                          className="text-xs leading-tight mt-0.5"
                          style={{ color: 'var(--bd-fg-muted)' }}
                        >
                          {u.email}
                        </div>
                      ) : null}
                    </td>
                    <td
                      className="px-4 py-3 font-mono text-xs"
                      style={{ color: 'var(--bd-fg)' }}
                    >
                      {u.user_id.slice(0, 8)}...
                    </td>
                    <td className="px-4 py-3">
                      <span
                        className="inline-block px-2 py-0.5 rounded-full text-xs font-medium"
                        style={{ background: tag.bg, color: tag.color }}
                      >
                        {tag.label}
                      </span>
                    </td>
                    <td
                      className="px-4 py-3 text-xs max-w-[16rem] truncate"
                      style={{ color: 'var(--bd-fg-muted)' }}
                      title={u.admin_note || undefined}
                    >
                      {u.admin_note || '-'}
                    </td>
                    <td className="px-4 py-3 text-center" style={{ color: 'var(--bd-fg)' }}>
                      {u.activation_count}
                    </td>
                    <td className="px-4 py-3 text-xs" style={{ color: 'var(--bd-fg-muted)' }}>
                      {fmtDate(u.created_at)}
                    </td>
                  </tr>
                );
              })}
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
          <span className="text-xs" style={{ color: 'var(--bd-fg-muted)' }}>
            第 {page} / {totalPages} 页 · 共 {total} 人
          </span>
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
    </div>
  );
}
