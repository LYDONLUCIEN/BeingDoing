/**
 * 时区转换工具（T2 层3）
 *
 * 后端统一返回 tz-aware ISO 字符串（带 +00:00），前端需要转成浏览器本地时区显示。
 * 本文件提供三个常用粒度的格式化函数，底层走 `Intl.DateTimeFormat`，
 * 默认使用浏览器本地时区，可通过 locale 参数定制输出语言。
 */

/** 后端返回的合法时间值；可能是 ISO 字符串、Date 实例或时间戳，空值统一返回占位符。 */
export type TimeInput = string | number | Date | null | undefined;

const FALLBACK = '-';

/**
 * 兜底把后端传来的 ISO 字符串规整成 `Date` 可解析的形式。
 *
 * 历史数据若未跑 fix 脚本，可能返回 naive 字符串（无时区后缀），
 * 此处统一按 UTC 处理（追加 'Z'），避免被浏览器当本地时间解析造成偏差。
 */
export function toDate(input: TimeInput): Date | null {
  if (input == null) return null;

  if (input instanceof Date) return Number.isNaN(input.getTime()) ? null : input;

  if (typeof input === 'number') return Number.isFinite(input) ? new Date(input) : null;

  const str = String(input).trim();
  if (!str) return null;

  // 不带时区后缀的 ISO 串：补 'Z' 视作 UTC
  // 检测末尾的 [+-]HH:MM 或 'Z'
  const hasTz = /([Zz]|[+-]\d{2}:\d{2})\s*$/.test(str);
  const normalized = hasTz ? str : `${str}Z`;
  const d = new Date(normalized);
  return Number.isNaN(d.getTime()) ? null : d;
}

/**
 * 把后端 UTC ISO 字符串格式化为浏览器本地时区的完整时间。
 *
 * @param input  后端返回的 ISO 字符串、Date 或时间戳
 * @param locale 输出语言，默认浏览器语言（如 'zh-CN'）
 * @returns      形如 `2026/6/29 14:30:00` 的本地时间字符串；空值返回 '-'
 */
export function formatUTC(input: TimeInput, locale?: string): string {
  const d = toDate(input);
  if (!d) return FALLBACK;

  const fmt = new Intl.DateTimeFormat(locale, {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false,
  });
  return fmt.format(d);
}

/**
 * 本地时区的 "YYYY-MM-DD HH:mm" 格式（与项目历史 UI 风格一致）。
 *
 * 主要供原有 `formatTime` / `formatAdminTime` 等辅助函数收敛复用，
 * 新代码建议直接使用 `formatUTC`。
 */
export function formatLocalDateTime(input: TimeInput): string {
  const d = toDate(input);
  if (!d) return FALLBACK;

  const pad = (n: number) => String(n).padStart(2, '0');
  return (
    `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ` +
    `${pad(d.getHours())}:${pad(d.getMinutes())}`
  );
}

/**
 * 仅日期（不含时间），用于表格的"注册日期"等场景。
 */
export function formatDate(input: TimeInput, locale?: string): string {
  const d = toDate(input);
  if (!d) return FALLBACK;

  const fmt = new Intl.DateTimeFormat(locale, {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  });
  return fmt.format(d);
}

/**
 * 相对时间，例如 "3 分钟前"。用于评论/消息列表。
 *
 * 注意：相对时间不需要时区转换（基于时间差），但输入仍需正确解析为 UTC。
 */
export function formatRelative(input: TimeInput, locale?: string): string {
  const d = toDate(input);
  if (!d) return FALLBACK;

  const diff = Date.now() - d.getTime();
  const sec = Math.round(diff / 1000);
  const min = Math.round(sec / 60);
  const hour = Math.round(min / 60);
  const day = Math.round(hour / 24);

  const rtf = new Intl.RelativeTimeFormat(locale, { numeric: 'auto' });
  if (Math.abs(sec) < 60) return rtf.format(-sec, 'second');
  if (Math.abs(min) < 60) return rtf.format(-min, 'minute');
  if (Math.abs(hour) < 24) return rtf.format(-hour, 'hour');
  return rtf.format(-day, 'day');
}
