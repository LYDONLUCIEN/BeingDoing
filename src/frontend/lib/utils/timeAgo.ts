/**
 * 相对时间格式化（"3 分钟前"、"2 天前"）
 *
 * 用于站内信列表等不要求精确时间的场景。
 * 若需要精确时间，使用 formatTime.ts 的 formatDateTime。
 */
import type { TimeInput } from './formatTime';
import { toDate } from './formatTime';

export function timeAgo(input: TimeInput): string {
  const d = toDate(input);
  if (!d) return '';

  const now = Date.now();
  const diff = Math.max(0, now - d.getTime());
  const sec = Math.floor(diff / 1000);
  const min = Math.floor(sec / 60);
  const hour = Math.floor(min / 60);
  const day = Math.floor(hour / 24);

  if (sec < 30) return '刚刚';
  if (min < 1) return `${sec} 秒前`;
  if (hour < 1) return `${min} 分钟前`;
  if (day < 1) return `${hour} 小时前`;
  if (day < 30) return `${day} 天前`;

  // 超过 30 天，回退到日期
  const yyyy = d.getFullYear();
  const mm = String(d.getMonth() + 1).padStart(2, '0');
  const dd = String(d.getDate()).padStart(2, '0');
  return `${yyyy}-${mm}-${dd}`;
}
