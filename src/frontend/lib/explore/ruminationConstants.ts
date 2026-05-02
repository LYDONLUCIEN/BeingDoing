/** 反刍表格常量和工具函数 */

export const HYP_CONFIRM_KEY = '用户确认的假设';
export const OTHER_SELECT_VALUE = '__RUMINATION_OTHER__';

/** 历史值兼容映射：旧文案 → 新文案 */
export const LEGACY_VALUE_MAP: Record<string, string> = {
  '其他': '自定义',
  '暂未选定': '无',
  '待定': '无',
};

/** 将旧历史值映射为当前文案（若匹配），否则原样返回 */
export function normalizeRuminationValue(raw: string): string {
  return LEGACY_VALUE_MAP[raw] ?? raw;
}
