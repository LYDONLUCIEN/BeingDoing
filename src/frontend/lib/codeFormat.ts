/**
 * 码格式归一化（与后端 app/utils/code_format.py 同规则，2026-10-06）
 *
 * 作用：输入框即刻容错——大小写/折行空白/全角横杠（富文本复制变体）清理，
 * 裸码 body 按输入上下文自动补前缀（严格长度触发，与存量 10/12 位裸码不冲突）。
 * 后端 validate/activate 已兜底归一化，此处仅为提升输入体验与展示一致性。
 */

const COUPON_PREFIX = 'Q-';
const COUPON_BODY_LENGTH = 8;
const ACTIVATION_PREFIX = 'OPENLIFE-';
const ACTIVATION_BODY_LENGTH = 12;
const ACTIVATION_GROUP_SIZE = 4;

// 全角/异体横杠 → 半角连字符
const DASH_MAP: Record<string, string> = {
  '－': '-',
  '—': '-',
  '–': '-',
  '−': '-',
  _: '-',
};

function baseNormalize(raw: string): string {
  const translated = (raw || '')
    .split('')
    .map((ch) => DASH_MAP[ch] ?? ch)
    .join('');
  return translated.replace(/\s+/g, '').toUpperCase();
}

function formatActivationBody(body: string): string {
  const groups: string[] = [];
  for (let i = 0; i < body.length; i += ACTIVATION_GROUP_SIZE) {
    groups.push(body.slice(i, i + ACTIVATION_GROUP_SIZE));
  }
  return groups.join('-');
}

/** 券码输入归一化：裸 8 位自动补 Q-；存量 12 位裸码原样（精确匹配兼容） */
export function normalizeCouponCode(raw: string): string {
  const s = baseNormalize(raw);
  if (!s) return '';
  if (s.startsWith(ACTIVATION_PREFIX)) return s; // 输错框保护：券码不可能带激活码前缀
  if (!s.includes('-') && s.length === COUPON_BODY_LENGTH) return COUPON_PREFIX + s;
  return s;
}

/** 激活码输入归一化：裸 12 位补 OPENLIFE- 并 4-4-4 分组；存量 10 位裸码原样 */
export function normalizeActivationCode(raw: string): string {
  const s = baseNormalize(raw);
  if (!s) return '';
  if (s.startsWith(ACTIVATION_PREFIX)) {
    const rest = s.slice(ACTIVATION_PREFIX.length);
    if (!rest.includes('-') && rest.length === ACTIVATION_BODY_LENGTH) {
      return ACTIVATION_PREFIX + formatActivationBody(rest);
    }
    return s;
  }
  if (!s.includes('-') && s.length === ACTIVATION_BODY_LENGTH) {
    return ACTIVATION_PREFIX + formatActivationBody(s);
  }
  return s;
}
