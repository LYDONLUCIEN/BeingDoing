/**
 * 调研问卷数据结构与校验
 * 供 simple（激活码）和 complex（session）两种模式复用
 */

export const GENDER_OPTIONS = ['男', '女', '不愿意透露'] as const;
export const AGE_OPTIONS = ['18-24', '25-30', '31-36', '37-42', '42+'] as const;
export const FAMILY_AFFECTS_OPTIONS = ['会', '不会', '不确定'] as const;
export const CAREER_STATUS_OPTIONS = ['在职', '离职待业', '应届生', '创业初期'] as const;
export const COMPANY_TYPE_OPTIONS = ['国企', '外企', '民企', '初创', '事业单位'] as const;
export const PAST_CONSULTATION_OPTIONS = ['有', '无'] as const;

export const FAMILY_STATUS_OPTIONS = [
  '未婚',
  '已婚',
  '有子女',
  '需兼顾家人照料',
] as const;

/** 核心诉求：5个可多选的选项 + 其他（可补充） */
export const CORE_NEEDS_OPTIONS = [
  '职业方向不清晰',
  '想转型但不知道如何开始',
  '工作与生活平衡',
  '薪资与晋升',
  '职业倦怠',
  '其他',
] as const;

export interface SurveyData {
  nickname?: string;
  gender?: string;
  age?: string;
  education_school?: string;
  education_degree?: string;
  education_major?: string;
  city?: string;
  family_status?: string[];
  family_affects_career?: string;
  career_status?: string;
  industry?: string;
  position?: string;
  work_years_total?: string;
  work_history?: string;
  company_types?: string[];
  salary_level?: string;
  core_needs?: string[];
  core_needs_other?: string;
  past_consultation?: string;
}
