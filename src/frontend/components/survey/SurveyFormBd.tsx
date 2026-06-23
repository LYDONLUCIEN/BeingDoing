'use client';

import { useState, useEffect } from 'react';
import {
  GENDER_OPTIONS,
  AGE_OPTIONS,
  FAMILY_STATUS_OPTIONS,
  FAMILY_AFFECTS_OPTIONS,
  CAREER_STATUS_OPTIONS,
  COMPANY_TYPE_OPTIONS,
  CORE_NEEDS_OPTIONS,
  PAST_CONSULTATION_OPTIONS,
  type SurveyData,
} from '@/lib/survey/schema';

const inputCls =
  'w-full rounded-xl border border-bd-border bg-bd-overlay px-3 py-2.5 text-sm text-bd-fg placeholder:text-bd-subtle focus:border-bd-ui-accent focus:ring-2 focus:ring-bd-ui-accent/20 outline-none transition-colors';
const inputReadOnlyCls =
  'w-full rounded-xl border border-bd-border/50 bg-bd-overlay/40 px-3 py-2.5 text-sm text-bd-fg cursor-default outline-none';
const labelCls = 'block text-sm font-medium text-bd-muted mb-1.5';
const optionCls = 'text-sm text-bd-fg';

// 只读模式下数组字段的 chip 样式
const chipCls =
  'inline-block rounded-full text-xs px-2.5 py-0.5 mr-1.5 mb-1.5';
const chipStyle = {
  background: 'rgba(59,130,246,0.12)',
  color: '#2563eb',
  border: '1px solid rgba(59,130,246,0.2)',
};

interface SurveyFormBdProps {
  initialData?: Partial<SurveyData>;
  /** 编辑模式下提交回调;readOnly=true 时可不传 */
  onSubmit?: (data: SurveyData) => void | Promise<void>;
  onSkip?: () => void;
  loading?: boolean;
  saving?: boolean;
  submitLabel?: string;
  showSkip?: boolean;
  /** 只读模式:字段以纯展示形态呈现,空值字段不渲染,数组字段以 chip 排列 */
  readOnly?: boolean;
}

export default function SurveyFormBd({
  initialData = {},
  onSubmit,
  onSkip,
  loading = false,
  saving = false,
  submitLabel = '保存',
  showSkip = false,
  readOnly = false,
}: SurveyFormBdProps) {
  const [formData, setFormData] = useState<SurveyData>({
    nickname: initialData.nickname ?? '',
    gender: initialData.gender ?? '',
    age: initialData.age ?? '',
    education_school: initialData.education_school ?? '',
    education_degree: initialData.education_degree ?? '',
    education_major: initialData.education_major ?? '',
    city: initialData.city ?? '',
    family_status: initialData.family_status ?? [],
    family_affects_career: initialData.family_affects_career ?? '',
    career_status: initialData.career_status ?? '',
    industry: initialData.industry ?? '',
    position: initialData.position ?? '',
    work_years_total: initialData.work_years_total ?? '',
    work_history: initialData.work_history ?? '',
    company_types: initialData.company_types ?? [],
    salary_level: initialData.salary_level ?? '',
    core_needs: initialData.core_needs ?? [],
    core_needs_other: initialData.core_needs_other ?? '',
    past_consultation: initialData.past_consultation ?? '',
  });

  useEffect(() => {
    setFormData({
      nickname: initialData.nickname ?? '',
      gender: initialData.gender ?? '',
      age: initialData.age ?? '',
      education_school: initialData.education_school ?? '',
      education_degree: initialData.education_degree ?? '',
      education_major: initialData.education_major ?? '',
      city: initialData.city ?? '',
      family_status: initialData.family_status ?? [],
      family_affects_career: initialData.family_affects_career ?? '',
      career_status: initialData.career_status ?? '',
      industry: initialData.industry ?? '',
      position: initialData.position ?? '',
      work_years_total: initialData.work_years_total ?? '',
      work_history: initialData.work_history ?? '',
      company_types: initialData.company_types ?? [],
      salary_level: initialData.salary_level ?? '',
      core_needs: initialData.core_needs ?? [],
      core_needs_other: initialData.core_needs_other ?? '',
      past_consultation: initialData.past_consultation ?? '',
    });
  }, [initialData]);

  const toggleArray = (key: 'family_status' | 'company_types' | 'core_needs', value: string) => {
    const arr = formData[key] ?? [];
    if (arr.includes(value)) {
      setFormData({ ...formData, [key]: arr.filter((v) => v !== value) });
    } else {
      setFormData({ ...formData, [key]: [...arr, value] });
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (readOnly || !onSubmit) return;
    await onSubmit(formData);
  };

  const hasOther = formData.core_needs?.includes('其他') ?? false;
  const disabled = loading || saving;

  // ─── 只读模式辅助函数 ─────────────────────────────────────────
  const hasText = (v?: string) => !!v && v.trim() !== '';
  const hasArray = (v?: string[]) => !!v && v.length > 0;
  const hasAnyEducation = hasText(formData.education_school) || hasText(formData.education_degree) || hasText(formData.education_major);
  const hasAnyCareer = hasText(formData.industry) || hasText(formData.position) || hasText(formData.work_years_total);

  // 渲染字符串字段:有值才返回 input readOnly
  const renderReadOnlyText = (label: string, value?: string) => {
    if (!hasText(value)) return null;
    return (
      <div>
        <label className={labelCls}>{label}</label>
        <input readOnly value={value as string} className={inputReadOnlyCls} />
      </div>
    );
  };

  // 渲染 chip 字段:数组用标签排列
  const renderReadOnlyChips = (label: string, values?: string[]) => {
    if (!hasArray(values)) return null;
    return (
      <div>
        <label className={labelCls}>{label}</label>
        <div className="flex flex-wrap items-center">
          {(values as string[]).map((v) => (
            <span key={v} className={chipCls} style={chipStyle}>
              {v}
            </span>
          ))}
        </div>
      </div>
    );
  };

  // ─── 只读模式布局 ─────────────────────────────────────────────
  if (readOnly) {
    const hasNickname = hasText(formData.nickname);
    const hasGender = hasText(formData.gender);
    const hasAge = hasText(formData.age);
    const hasCity = hasText(formData.city);
    const hasFamily = hasArray(formData.family_status);
    const hasFamilyAffects = hasText(formData.family_affects_career);
    const hasCareerStatus = hasText(formData.career_status);
    const hasWorkHistory = hasText(formData.work_history);
    const hasSalary = hasText(formData.salary_level);
    const hasCoreNeeds = hasArray(formData.core_needs) || hasText(formData.core_needs_other);
    const hasPastConsultation = hasText(formData.past_consultation);

    const hasBasic = hasNickname || hasGender || hasAge || hasCity;
    const hasEducationBlock = hasAnyEducation;
    const hasFamilyBlock = hasFamily || hasFamilyAffects;
    const hasCareerBlock = hasCareerStatus || hasAnyCareer || hasWorkHistory || hasSalary;
    const hasNeedsBlock = hasCoreNeeds || hasPastConsultation;

    const nothingToShow =
      !hasBasic && !hasEducationBlock && !hasFamilyBlock && !hasCareerBlock && !hasNeedsBlock;

    if (nothingToShow) {
      return (
        <p className="text-sm" style={{ color: 'var(--bd-fg-muted)' }}>
          该用户尚未填写调研问卷
        </p>
      );
    }

    return (
      <div className="space-y-6">
        {/* 基本信息 */}
        {hasBasic && (
          <section className="space-y-4">
            <h3 className="text-sm font-semibold text-bd-fg">基本信息</h3>
            <div className="grid gap-3 sm:grid-cols-2">
              {renderReadOnlyText('昵称', formData.nickname)}
              {renderReadOnlyText('性别', formData.gender)}
              {renderReadOnlyText('年龄', formData.age)}
              {renderReadOnlyText('长期生活的城市', formData.city)}
            </div>
          </section>
        )}

        {/* 教育背景 */}
        {hasEducationBlock && (
          <section className="space-y-4">
            <h3 className="text-sm font-semibold text-bd-fg">教育背景</h3>
            <div className="grid gap-3 sm:grid-cols-3">
              {renderReadOnlyText('院校', formData.education_school)}
              {renderReadOnlyText('学历', formData.education_degree)}
              {renderReadOnlyText('专业', formData.education_major)}
            </div>
          </section>
        )}

        {/* 家庭情况 */}
        {hasFamilyBlock && (
          <section className="space-y-4">
            <h3 className="text-sm font-semibold text-bd-fg">家庭情况</h3>
            {renderReadOnlyChips('家庭生活状态', formData.family_status)}
            {renderReadOnlyText('家庭是否影响职业选择', formData.family_affects_career)}
          </section>
        )}

        {/* 职业信息 */}
        {hasCareerBlock && (
          <section className="space-y-4">
            <h3 className="text-sm font-semibold text-bd-fg">职业信息</h3>
            {renderReadOnlyText('职业状态', formData.career_status)}
            <div className="grid gap-3 sm:grid-cols-3">
              {renderReadOnlyText('行业', formData.industry)}
              {renderReadOnlyText('岗位', formData.position)}
              {renderReadOnlyText('工作年限', formData.work_years_total)}
            </div>
            {renderReadOnlyText('工作经历', formData.work_history)}
            {renderReadOnlyChips('企业类型', formData.company_types)}
            {renderReadOnlyText('薪资水平', formData.salary_level)}
          </section>
        )}

        {/* 核心诉求 */}
        {hasNeedsBlock && (
          <section className="space-y-4">
            <h3 className="text-sm font-semibold text-bd-fg">核心诉求</h3>
            {renderReadOnlyChips('核心诉求/困扰/目标', formData.core_needs)}
            {renderReadOnlyText('核心诉求（其他补充）', formData.core_needs_other)}
            {renderReadOnlyText('过往咨询经历', formData.past_consultation)}
          </section>
        )}
      </div>
    );
  }

  // ─── 编辑模式(原样) ───────────────────────────────────────────
  return (
    <form onSubmit={handleSubmit} className="space-y-6">
      <div>
        <label className={labelCls}>昵称</label>
        <input type="text" value={formData.nickname} onChange={(e) => setFormData({ ...formData, nickname: e.target.value })} placeholder="选填" className={inputCls} />
      </div>
      <div>
        <label className={labelCls}>性别</label>
        <div className="flex flex-wrap gap-3">
          {GENDER_OPTIONS.map((opt) => (
            <label key={opt} className="flex items-center gap-2 cursor-pointer">
              <input type="radio" name="gender" checked={formData.gender === opt} onChange={() => setFormData({ ...formData, gender: opt })} className="accent-bd-ui-accent" />
              <span className={optionCls}>{opt}</span>
            </label>
          ))}
        </div>
      </div>
      <div>
        <label className={labelCls}>年龄</label>
        <div className="flex flex-wrap gap-3">
          {AGE_OPTIONS.map((opt) => (
            <label key={opt} className="flex items-center gap-2 cursor-pointer">
              <input type="radio" name="age" checked={formData.age === opt} onChange={() => setFormData({ ...formData, age: opt })} className="accent-bd-ui-accent" />
              <span className={optionCls}>{opt}</span>
            </label>
          ))}
        </div>
      </div>
      <div className="grid gap-3 sm:grid-cols-3">
        <div>
          <label className={labelCls}>院校</label>
          <input type="text" value={formData.education_school} onChange={(e) => setFormData({ ...formData, education_school: e.target.value })} placeholder="选填" className={inputCls} />
        </div>
        <div>
          <label className={labelCls}>学历</label>
          <input type="text" value={formData.education_degree} onChange={(e) => setFormData({ ...formData, education_degree: e.target.value })} placeholder="选填" className={inputCls} />
        </div>
        <div>
          <label className={labelCls}>专业</label>
          <input type="text" value={formData.education_major} onChange={(e) => setFormData({ ...formData, education_major: e.target.value })} placeholder="选填" className={inputCls} />
        </div>
      </div>
      <div>
        <label className={labelCls}>长期生活的城市</label>
        <input type="text" value={formData.city} onChange={(e) => setFormData({ ...formData, city: e.target.value })} placeholder="如北京、上海等" className={inputCls} />
      </div>
      <div>
        <label className={labelCls}>家庭生活状态</label>
        <div className="flex flex-wrap gap-3">
          {FAMILY_STATUS_OPTIONS.map((opt) => (
            <label key={opt} className="flex items-center gap-2 cursor-pointer">
              <input type="checkbox" checked={formData.family_status?.includes(opt) ?? false} onChange={() => toggleArray('family_status', opt)} className="accent-bd-ui-accent rounded" />
              <span className={optionCls}>{opt}</span>
            </label>
          ))}
        </div>
      </div>
      <div>
        <label className={labelCls}>家庭是否影响职业选择</label>
        <div className="flex flex-wrap gap-3">
          {FAMILY_AFFECTS_OPTIONS.map((opt) => (
            <label key={opt} className="flex items-center gap-2 cursor-pointer">
              <input type="radio" name="family_affects" checked={formData.family_affects_career === opt} onChange={() => setFormData({ ...formData, family_affects_career: opt })} className="accent-bd-ui-accent" />
              <span className={optionCls}>{opt}</span>
            </label>
          ))}
        </div>
      </div>
      <div>
        <label className={labelCls}>职业状态</label>
        <div className="flex flex-wrap gap-3">
          {CAREER_STATUS_OPTIONS.map((opt) => (
            <label key={opt} className="flex items-center gap-2 cursor-pointer">
              <input type="radio" name="career" checked={formData.career_status === opt} onChange={() => setFormData({ ...formData, career_status: opt })} className="accent-bd-ui-accent" />
              <span className={optionCls}>{opt}</span>
            </label>
          ))}
        </div>
      </div>
      <div className="grid gap-3 sm:grid-cols-3">
        <div>
          <label className={labelCls}>行业</label>
          <input type="text" value={formData.industry} onChange={(e) => setFormData({ ...formData, industry: e.target.value })} placeholder="选填" className={inputCls} />
        </div>
        <div>
          <label className={labelCls}>岗位</label>
          <input type="text" value={formData.position} onChange={(e) => setFormData({ ...formData, position: e.target.value })} placeholder="选填" className={inputCls} />
        </div>
        <div>
          <label className={labelCls}>工作年限</label>
          <input type="text" value={formData.work_years_total} onChange={(e) => setFormData({ ...formData, work_years_total: e.target.value })} placeholder="如 3年、5-8年" className={inputCls} />
        </div>
      </div>
      <div>
        <label className={labelCls}>工作经历</label>
        <input type="text" value={formData.work_history} onChange={(e) => setFormData({ ...formData, work_history: e.target.value })} placeholder="简述工作经历或公司名称" className={inputCls} />
      </div>
      <div>
        <label className={labelCls}>企业类型</label>
        <div className="flex flex-wrap gap-3">
          {COMPANY_TYPE_OPTIONS.map((opt) => (
            <label key={opt} className="flex items-center gap-2 cursor-pointer">
              <input type="checkbox" checked={formData.company_types?.includes(opt) ?? false} onChange={() => toggleArray('company_types', opt)} className="accent-bd-ui-accent rounded" />
              <span className={optionCls}>{opt}</span>
            </label>
          ))}
        </div>
      </div>
      <div>
        <label className={labelCls}>薪资水平</label>
        <input type="text" value={formData.salary_level} onChange={(e) => setFormData({ ...formData, salary_level: e.target.value })} placeholder="选填" className={inputCls} />
      </div>
      <div>
        <label className={labelCls}>核心诉求/困扰/目标</label>
        <div className="flex flex-wrap gap-3">
          {CORE_NEEDS_OPTIONS.map((opt) => (
            <label key={opt} className="flex items-center gap-2 cursor-pointer">
              <input type="checkbox" checked={formData.core_needs?.includes(opt) ?? false} onChange={() => toggleArray('core_needs', opt)} className="accent-bd-ui-accent rounded" />
              <span className={optionCls}>{opt}</span>
            </label>
          ))}
        </div>
        {hasOther && (
          <input type="text" value={formData.core_needs_other} onChange={(e) => setFormData({ ...formData, core_needs_other: e.target.value })} placeholder="请补充" className={`${inputCls} mt-2`} />
        )}
      </div>
      <div>
        <label className={labelCls}>过往咨询经历</label>
        <div className="flex flex-wrap gap-3">
          {PAST_CONSULTATION_OPTIONS.map((opt) => (
            <label key={opt} className="flex items-center gap-2 cursor-pointer">
              <input type="radio" name="past" checked={formData.past_consultation === opt} onChange={() => setFormData({ ...formData, past_consultation: opt })} className="accent-bd-ui-accent" />
              <span className={optionCls}>{opt}</span>
            </label>
          ))}
        </div>
      </div>
      <div className="pt-4 flex gap-3">
        <button type="submit" disabled={disabled} className="rounded-xl px-6 py-2.5 text-sm font-medium text-white transition-colors disabled:opacity-50" style={{ background: 'var(--bd-ui-accent)' }}>
          {loading ? '提交中…' : saving ? '保存中…' : submitLabel}
        </button>
        {showSkip && onSkip && (
          <button type="button" onClick={onSkip} disabled={disabled} className="rounded-xl border border-bd-border px-6 py-2.5 text-sm font-medium text-bd-muted hover:bg-bd-overlay transition-colors">
            暂时跳过
          </button>
        )}
      </div>
    </form>
  );
}
