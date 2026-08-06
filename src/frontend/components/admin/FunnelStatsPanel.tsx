'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import { format, startOfMonth, subDays } from 'date-fns';
import { fetchAdminFunnelStats, type AdminFunnelStats } from '@/lib/api/admin';

/**
 * 漏斗级统计看板（ADR-0013，事件时间口径）。
 * 环节定义见 CONTEXT.md「统计看板」节。
 * 注意：PV 与日活自埋点上线起统计，更早时段无数据。
 */

type Preset = 'today' | '7d' | '30d' | 'month' | 'custom';

const PRESET_LABELS: Array<{ key: Preset; label: string }> = [
  { key: 'today', label: '今日' },
  { key: '7d', label: '近 7 天' },
  { key: '30d', label: '近 30 天' },
  { key: 'month', label: '本月' },
  { key: 'custom', label: '自定义' },
];

function resolveRange(preset: Preset): { start: string; end: string } {
  const today = new Date();
  const end = format(today, 'yyyy-MM-dd');
  switch (preset) {
    case 'today':
      return { start: end, end };
    case '7d':
      return { start: format(subDays(today, 6), 'yyyy-MM-dd'), end };
    case 'month':
      return { start: format(startOfMonth(today), 'yyyy-MM-dd'), end };
    case '30d':
    default:
      return { start: format(subDays(today, 29), 'yyyy-MM-dd'), end };
  }
}

function fenToYuan(cents: number): string {
  return `¥${(cents / 100).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

function pct(part: number, whole: number): string {
  if (!whole) return '—';
  return `${((part / whole) * 100).toFixed(1)}%`;
}

export default function FunnelStatsPanel() {
  const [preset, setPreset] = useState<Preset>('30d');
  const [customStart, setCustomStart] = useState('');
  const [customEnd, setCustomEnd] = useState('');
  const [granularity, setGranularity] = useState<'day' | 'month'>('day');
  const [data, setData] = useState<AdminFunnelStats | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const range = useMemo(() => {
    if (preset === 'custom') {
      return customStart && customEnd ? { start: customStart, end: customEnd } : null;
    }
    return resolveRange(preset);
  }, [preset, customStart, customEnd]);

  const load = useCallback(async () => {
    if (!range) return;
    setLoading(true);
    setError(null);
    try {
      const res = await fetchAdminFunnelStats({ ...range, granularity });
      setData(res);
    } catch (e: any) {
      setError(e?.message || '加载漏斗统计失败');
    } finally {
      setLoading(false);
    }
  }, [range, granularity]);

  useEffect(() => {
    load();
  }, [load]);

  const stages = useMemo(() => {
    if (!data?.funnel) return [];
    const f = data.funnel;
    const list = [
      { key: 'pv', label: '浏览（PV）', value: f.pv },
      { key: 'registrations', label: '注册', value: f.registrations },
      { key: 'trial_started', label: '试用开聊', value: f.trial_started },
      { key: 'values_10_completed', label: '完成 10 轮', value: f.values_10_completed },
      { key: 'paid_users', label: '付费', value: f.paid_users },
      { key: 'report_approved_users', label: '得到报告', value: f.report_approved_users },
    ];
    const base = Math.max(f.pv, 1);
    return list.map((s, i) => ({
      ...s,
      widthPct: Math.max((s.value / base) * 100, s.value > 0 ? 2 : 0),
      conv: i > 0 ? pct(s.value, list[i - 1].value) : null,
    }));
  }, [data]);

  return (
    <section className="rounded-2xl bg-bd-card border border-bd-border px-6 py-5 shadow-sm space-y-5">
      <div className="flex flex-wrap items-end gap-3">
        <div className="space-y-1">
          <h2 className="text-sm font-medium">转化漏斗与经营统计</h2>
          <p className="text-[11px] text-bd-subtle">
            事件时间口径：各环节独立统计「事件发生在选定时段内」的人/次数；PV 与日活自埋点上线起统计
          </p>
        </div>
        <div className="flex-1" />
        <div className="flex rounded-lg border border-bd-border overflow-hidden">
          {PRESET_LABELS.map((p) => (
            <button
              key={p.key}
              type="button"
              onClick={() => setPreset(p.key)}
              className={`px-3 py-1.5 text-xs ${
                preset === p.key
                  ? 'bg-bd-ui-accent text-bd-ui-accent-fg'
                  : 'hover:bg-bd-overlay-md'
              }`}
            >
              {p.label}
            </button>
          ))}
        </div>
        {preset === 'custom' && (
          <div className="flex items-center gap-2">
            <input
              type="date"
              value={customStart}
              onChange={(e) => setCustomStart(e.target.value)}
              className="rounded-lg border border-bd-border bg-bd-overlay px-2 py-1.5 text-xs"
            />
            <span className="text-xs text-bd-subtle">至</span>
            <input
              type="date"
              value={customEnd}
              onChange={(e) => setCustomEnd(e.target.value)}
              className="rounded-lg border border-bd-border bg-bd-overlay px-2 py-1.5 text-xs"
            />
          </div>
        )}
        <div className="flex rounded-lg border border-bd-border overflow-hidden">
          {(['day', 'month'] as const).map((g) => (
            <button
              key={g}
              type="button"
              onClick={() => setGranularity(g)}
              className={`px-3 py-1.5 text-xs ${
                granularity === g
                  ? 'bg-bd-ui-accent text-bd-ui-accent-fg'
                  : 'hover:bg-bd-overlay-md'
              }`}
            >
              {g === 'day' ? '按天' : '按月'}
            </button>
          ))}
        </div>
        <button
          type="button"
          onClick={load}
          disabled={loading || !range}
          className="px-3 py-1.5 rounded-lg border border-bd-border text-xs hover:bg-bd-overlay-md disabled:opacity-60"
        >
          {loading ? '加载中...' : '刷新'}
        </button>
      </div>

      {error && (
        <div className="rounded-xl border border-red-200 bg-red-50 text-red-700 px-4 py-3 text-xs">
          {error}
        </div>
      )}

      {data && (
        <>
          {/* 漏斗 */}
          <div className="space-y-1.5">
            {stages.map((s) => (
              <div key={s.key} className="flex items-center gap-3">
                <span className="w-24 shrink-0 text-xs text-right text-bd-subtle">{s.label}</span>
                <div className="flex-1 h-6 rounded-md bg-bd-overlay-md overflow-hidden">
                  <div
                    className="h-full rounded-md bg-bd-ui-accent/70 transition-all"
                    style={{ width: `${s.widthPct}%` }}
                  />
                </div>
                <span className="w-16 shrink-0 text-xs font-semibold">{s.value}</span>
                <span className="w-16 shrink-0 text-[11px] text-bd-subtle">
                  {s.conv ? `转化 ${s.conv}` : ''}
                </span>
              </div>
            ))}
          </div>

          {/* 指标卡 */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <div className="rounded-xl border border-bd-border bg-bd-overlay-md px-3 py-2">
              <p className="text-[11px] text-bd-subtle">访客数（UV）</p>
              <p className="text-base font-semibold">{data.funnel.uv}</p>
            </div>
            <div className="rounded-xl border border-bd-border bg-bd-overlay-md px-3 py-2">
              <p className="text-[11px] text-bd-subtle">日活（次数 / 人数）</p>
              <p className="text-base font-semibold">
                {data.daily_active.total_events} / {data.daily_active.unique_users}
              </p>
            </div>
            <div className="rounded-xl border border-bd-border bg-bd-overlay-md px-3 py-2">
              <p className="text-[11px] text-bd-subtle">
                激活码（累计 试用/完整 / 时段新增）
              </p>
              <p className="text-base font-semibold">
                {data.activation_codes.total}
                <span className="text-xs font-normal text-bd-subtle">
                  {' '}
                  {data.activation_codes.trial}/{data.activation_codes.full} / +
                  {data.activation_codes.new_in_range}
                </span>
              </p>
            </div>
            <div className="rounded-xl border border-bd-border bg-bd-overlay-md px-3 py-2">
              <p className="text-[11px] text-bd-subtle">购买咨询人数</p>
              <p className="text-base font-semibold">{data.consultation_users}</p>
            </div>
            <div className="rounded-xl border border-bd-border bg-bd-overlay-md px-3 py-2">
              <p className="text-[11px] text-bd-subtle">实收（纯利润，已扣折扣/剔退款）</p>
              <p className="text-base font-semibold">{fenToYuan(data.revenue.actual_cents)}</p>
            </div>
            <div className="rounded-xl border border-bd-border bg-bd-overlay-md px-3 py-2">
              <p className="text-[11px] text-bd-subtle">理论收益（原价）</p>
              <p className="text-base font-semibold">{fenToYuan(data.revenue.theoretical_cents)}</p>
            </div>
            <div className="rounded-xl border border-bd-border bg-bd-overlay-md px-3 py-2">
              <p className="text-[11px] text-bd-subtle">折扣让利（理论 − 实收）</p>
              <p className="text-base font-semibold">
                {fenToYuan(data.revenue.theoretical_cents - data.revenue.actual_cents)}
              </p>
            </div>
          </div>

          {/* 商品拆分 */}
          {Object.keys(data.revenue.by_product || {}).length > 0 && (
            <div className="text-[11px] text-bd-subtle">
              收益拆分：
              {Object.entries(data.revenue.by_product)
                .map(
                  ([k, v]) =>
                    `${k} ${v.orders} 单（实收 ${fenToYuan(v.actual_cents)} / 原价 ${fenToYuan(v.theoretical_cents)}）`
                )
                .join('；')}
            </div>
          )}

          {/* 趋势 */}
          <div>
            <h3 className="text-xs font-medium mb-2 text-bd-subtle">
              分{granularity === 'day' ? '天' : '月'}趋势
            </h3>
            <div className="max-h-72 overflow-auto rounded-xl border border-bd-border">
              <table className="w-full text-[11px]">
                <thead className="sticky top-0 bg-bd-card">
                  <tr className="text-bd-subtle border-b border-bd-border">
                    <th className="px-2 py-1.5 text-left font-normal">日期</th>
                    <th className="px-2 py-1.5 text-right font-normal">PV</th>
                    <th className="px-2 py-1.5 text-right font-normal">UV</th>
                    <th className="px-2 py-1.5 text-right font-normal">注册</th>
                    <th className="px-2 py-1.5 text-right font-normal">日活人数</th>
                    <th className="px-2 py-1.5 text-right font-normal">试用开聊</th>
                    <th className="px-2 py-1.5 text-right font-normal">10 轮</th>
                    <th className="px-2 py-1.5 text-right font-normal">付费</th>
                    <th className="px-2 py-1.5 text-right font-normal">报告</th>
                    <th className="px-2 py-1.5 text-right font-normal">实收</th>
                    <th className="px-2 py-1.5 text-right font-normal">理论收益</th>
                  </tr>
                </thead>
                <tbody>
                  {data.trends.map((row) => (
                    <tr key={row.date} className="border-b border-bd-border/50 last:border-0">
                      <td className="px-2 py-1">{row.date}</td>
                      <td className="px-2 py-1 text-right">{row.pv}</td>
                      <td className="px-2 py-1 text-right">{row.uv}</td>
                      <td className="px-2 py-1 text-right">{row.registrations}</td>
                      <td className="px-2 py-1 text-right">{row.active_users}</td>
                      <td className="px-2 py-1 text-right">{row.trial_started}</td>
                      <td className="px-2 py-1 text-right">{row.values_10_completed}</td>
                      <td className="px-2 py-1 text-right">{row.paid_users}</td>
                      <td className="px-2 py-1 text-right">{row.report_approved_users}</td>
                      <td className="px-2 py-1 text-right">{fenToYuan(row.actual_cents)}</td>
                      <td className="px-2 py-1 text-right">{fenToYuan(row.theoretical_cents)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </>
      )}
    </section>
  );
}
