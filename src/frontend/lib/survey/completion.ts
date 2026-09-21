import type { SurveyData } from './schema';

/**
 * 资料完成度统计：已填字段数 / 总字段数。
 * core_needs_other 是「其他需求」的条件补充框，不计入总字段。
 */
const SURVEY_COMPLETION_KEYS: Array<keyof SurveyData> = [
  'nickname',
  'gender',
  'age',
  'education_school',
  'education_degree',
  'education_major',
  'city',
  'family_status',
  'family_affects_career',
  'career_status',
  'industry',
  'position',
  'work_years_total',
  'work_history',
  'company_types',
  'salary_level',
  'core_needs',
  'past_consultation',
];

export interface SurveyCompletion {
  filled: number;
  total: number;
  percent: number;
}

export function computeSurveyCompletion(data: SurveyData): SurveyCompletion {
  const total = SURVEY_COMPLETION_KEYS.length;
  const filled = SURVEY_COMPLETION_KEYS.reduce((count, key) => {
    const val = data[key];
    if (val === undefined || val === null) return count;
    if (Array.isArray(val)) return val.length > 0 ? count + 1 : count;
    return String(val).trim() ? count + 1 : count;
  }, 0);
  return { filled, total, percent: Math.round((filled / total) * 100) };
}
