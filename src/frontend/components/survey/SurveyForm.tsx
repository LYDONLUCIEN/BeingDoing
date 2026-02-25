'use client';

import { useState } from 'react';
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

interface SurveyFormProps {
  initialData?: Partial<SurveyData>;
  onSubmit: (data: SurveyData) => void | Promise<void>;
  onSkip?: () => void;
  loading?: boolean;
  submitLabel?: string;
  showSkip?: boolean;
}

export default function SurveyForm({
  initialData = {},
  onSubmit,
  onSkip,
  loading = false,
  submitLabel = '提交并开始',
  showSkip = true,
}: SurveyFormProps) {
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
    await onSubmit(formData);
  };

  const hasOther = formData.core_needs?.includes('其他') ?? false;

  return (
    <form onSubmit={handleSubmit} className="space-y-6">
      {/* 昵称 */}
      <div>
        <label className="block text-sm text-white/80 mb-1.5">昵称</label>
        <input
          type="text"
          value={formData.nickname}
          onChange={(e) => setFormData({ ...formData, nickname: e.target.value })}
          placeholder="请输入昵称（选填）"
          className="w-full rounded-md border border-white/20 bg-white/5 px-3 py-2 text-sm text-white placeholder-white/40 outline-none focus:border-primary-400"
        />
      </div>

      {/* 性别 - 单选 */}
      <div>
        <label className="block text-sm text-white/80 mb-1.5">性别</label>
        <div className="flex flex-wrap gap-2">
          {GENDER_OPTIONS.map((opt) => (
            <label key={opt} className="flex items-center gap-2 cursor-pointer">
              <input
                type="radio"
                name="gender"
                checked={formData.gender === opt}
                onChange={() => setFormData({ ...formData, gender: opt })}
                className="accent-primary-500"
              />
              <span className="text-sm text-white/90">{opt}</span>
            </label>
          ))}
        </div>
      </div>

      {/* 年龄 - 单选 */}
      <div>
        <label className="block text-sm text-white/80 mb-1.5">年龄</label>
        <div className="flex flex-wrap gap-2">
          {AGE_OPTIONS.map((opt) => (
            <label key={opt} className="flex items-center gap-2 cursor-pointer">
              <input
                type="radio"
                name="age"
                checked={formData.age === opt}
                onChange={() => setFormData({ ...formData, age: opt })}
                className="accent-primary-500"
              />
              <span className="text-sm text-white/90">{opt}</span>
            </label>
          ))}
        </div>
      </div>

      {/* 教育背景 */}
      <div className="space-y-2">
        <label className="block text-sm text-white/80">教育背景</label>
        <div className="grid gap-2 sm:grid-cols-3">
          <input
            type="text"
            value={formData.education_school}
            onChange={(e) => setFormData({ ...formData, education_school: e.target.value })}
            placeholder="院校（选填）"
            className="rounded-md border border-white/20 bg-white/5 px-3 py-2 text-sm text-white placeholder-white/40 outline-none focus:border-primary-400"
          />
          <input
            type="text"
            value={formData.education_degree}
            onChange={(e) => setFormData({ ...formData, education_degree: e.target.value })}
            placeholder="学历（选填）"
            className="rounded-md border border-white/20 bg-white/5 px-3 py-2 text-sm text-white placeholder-white/40 outline-none focus:border-primary-400"
          />
          <input
            type="text"
            value={formData.education_major}
            onChange={(e) => setFormData({ ...formData, education_major: e.target.value })}
            placeholder="专业（选填）"
            className="rounded-md border border-white/20 bg-white/5 px-3 py-2 text-sm text-white placeholder-white/40 outline-none focus:border-primary-400"
          />
        </div>
      </div>

      {/* 长期生活的城市 */}
      <div>
        <label className="block text-sm text-white/80 mb-1.5">长期生活的城市</label>
        <input
          type="text"
          value={formData.city}
          onChange={(e) => setFormData({ ...formData, city: e.target.value })}
          placeholder="如北京、上海等（选填）"
          className="w-full rounded-md border border-white/20 bg-white/5 px-3 py-2 text-sm text-white placeholder-white/40 outline-none focus:border-primary-400"
        />
      </div>

      {/* 家庭生活状态 - 多选 */}
      <div>
        <label className="block text-sm text-white/80 mb-1.5">当下的家庭生活状态</label>
        <div className="flex flex-wrap gap-2">
          {FAMILY_STATUS_OPTIONS.map((opt) => (
            <label key={opt} className="flex items-center gap-2 cursor-pointer">
              <input
                type="checkbox"
                checked={formData.family_status?.includes(opt) ?? false}
                onChange={() => toggleArray('family_status', opt)}
                className="accent-primary-500 rounded"
              />
              <span className="text-sm text-white/90">{opt}</span>
            </label>
          ))}
        </div>
      </div>

      {/* 家庭状态是否影响职业选择 - 单选 */}
      <div>
        <label className="block text-sm text-white/80 mb-1.5">家庭生活状态是否会影响你的职业选择</label>
        <div className="flex flex-wrap gap-2">
          {FAMILY_AFFECTS_OPTIONS.map((opt) => (
            <label key={opt} className="flex items-center gap-2 cursor-pointer">
              <input
                type="radio"
                name="family_affects_career"
                checked={formData.family_affects_career === opt}
                onChange={() => setFormData({ ...formData, family_affects_career: opt })}
                className="accent-primary-500"
              />
              <span className="text-sm text-white/90">{opt}</span>
            </label>
          ))}
        </div>
      </div>

      {/* 职业状态 - 单选 */}
      <div>
        <label className="block text-sm text-white/80 mb-1.5">目前你处于怎样的职业状态</label>
        <div className="flex flex-wrap gap-2">
          {CAREER_STATUS_OPTIONS.map((opt) => (
            <label key={opt} className="flex items-center gap-2 cursor-pointer">
              <input
                type="radio"
                name="career_status"
                checked={formData.career_status === opt}
                onChange={() => setFormData({ ...formData, career_status: opt })}
                className="accent-primary-500"
              />
              <span className="text-sm text-white/90">{opt}</span>
            </label>
          ))}
        </div>
      </div>

      {/* 行业 / 岗位 / 工作年限 */}
      <div className="grid gap-2 sm:grid-cols-3">
        <div>
          <label className="block text-sm text-white/80 mb-1.5">行业</label>
          <input
            type="text"
            value={formData.industry}
            onChange={(e) => setFormData({ ...formData, industry: e.target.value })}
            placeholder="选填"
            className="w-full rounded-md border border-white/20 bg-white/5 px-3 py-2 text-sm text-white placeholder-white/40 outline-none focus:border-primary-400"
          />
        </div>
        <div>
          <label className="block text-sm text-white/80 mb-1.5">岗位</label>
          <input
            type="text"
            value={formData.position}
            onChange={(e) => setFormData({ ...formData, position: e.target.value })}
            placeholder="选填"
            className="w-full rounded-md border border-white/20 bg-white/5 px-3 py-2 text-sm text-white placeholder-white/40 outline-none focus:border-primary-400"
          />
        </div>
        <div>
          <label className="block text-sm text-white/80 mb-1.5">累计工作年限</label>
          <input
            type="text"
            value={formData.work_years_total}
            onChange={(e) => setFormData({ ...formData, work_years_total: e.target.value })}
            placeholder="如 3年、5-8年（选填）"
            className="w-full rounded-md border border-white/20 bg-white/5 px-3 py-2 text-sm text-white placeholder-white/40 outline-none focus:border-primary-400"
          />
        </div>
      </div>

      {/* 分别在哪儿工作 */}
      <div>
        <label className="block text-sm text-white/80 mb-1.5">分别在哪儿工作</label>
        <input
          type="text"
          value={formData.work_history}
          onChange={(e) => setFormData({ ...formData, work_history: e.target.value })}
          placeholder="简述工作经历或公司名称（选填）"
          className="w-full rounded-md border border-white/20 bg-white/5 px-3 py-2 text-sm text-white placeholder-white/40 outline-none focus:border-primary-400"
        />
      </div>

      {/* 企业类型 - 多选 */}
      <div>
        <label className="block text-sm text-white/80 mb-1.5">企业类型</label>
        <div className="flex flex-wrap gap-2">
          {COMPANY_TYPE_OPTIONS.map((opt) => (
            <label key={opt} className="flex items-center gap-2 cursor-pointer">
              <input
                type="checkbox"
                checked={formData.company_types?.includes(opt) ?? false}
                onChange={() => toggleArray('company_types', opt)}
                className="accent-primary-500 rounded"
              />
              <span className="text-sm text-white/90">{opt}</span>
            </label>
          ))}
        </div>
      </div>

      {/* 薪资待遇水平 */}
      <div>
        <label className="block text-sm text-white/80 mb-1.5">目前的薪资待遇水平</label>
        <input
          type="text"
          value={formData.salary_level}
          onChange={(e) => setFormData({ ...formData, salary_level: e.target.value })}
          placeholder="可说区间或核心构成（选填）"
          className="w-full rounded-md border border-white/20 bg-white/5 px-3 py-2 text-sm text-white placeholder-white/40 outline-none focus:border-primary-400"
        />
      </div>

      {/* 核心诉求 - 5个多选 + 其他补充 */}
      <div>
        <label className="block text-sm text-white/80 mb-1.5">核心诉求/困扰/目标（可多选）</label>
        <div className="flex flex-wrap gap-2">
          {CORE_NEEDS_OPTIONS.map((opt) => (
            <label key={opt} className="flex items-center gap-2 cursor-pointer">
              <input
                type="checkbox"
                checked={formData.core_needs?.includes(opt) ?? false}
                onChange={() => toggleArray('core_needs', opt)}
                className="accent-primary-500 rounded"
              />
              <span className="text-sm text-white/90">{opt}</span>
            </label>
          ))}
        </div>
        {hasOther && (
          <div className="mt-2">
            <input
              type="text"
              value={formData.core_needs_other}
              onChange={(e) => setFormData({ ...formData, core_needs_other: e.target.value })}
              placeholder="请补充其他诉求"
              className="w-full rounded-md border border-white/20 bg-white/5 px-3 py-2 text-sm text-white placeholder-white/40 outline-none focus:border-primary-400"
            />
          </div>
        )}
      </div>

      {/* 过往咨询经历 - 单选 */}
      <div>
        <label className="block text-sm text-white/80 mb-1.5">有无过往咨询经历</label>
        <div className="flex flex-wrap gap-2">
          {PAST_CONSULTATION_OPTIONS.map((opt) => (
            <label key={opt} className="flex items-center gap-2 cursor-pointer">
              <input
                type="radio"
                name="past_consultation"
                checked={formData.past_consultation === opt}
                onChange={() => setFormData({ ...formData, past_consultation: opt })}
                className="accent-primary-500"
              />
              <span className="text-sm text-white/90">{opt}</span>
            </label>
          ))}
        </div>
      </div>

      {/* 提交按钮 */}
      <div className="flex gap-3 pt-4">
        <button
          type="submit"
          disabled={loading}
          className="rounded-md bg-primary-500 px-4 py-2.5 text-sm font-medium text-white hover:bg-primary-400 disabled:opacity-50 transition-colors"
        >
          {loading ? '提交中…' : submitLabel}
        </button>
        {showSkip && onSkip && (
          <button
            type="button"
            onClick={onSkip}
            disabled={loading}
            className="rounded-md border border-white/30 px-4 py-2.5 text-sm font-medium text-white/80 hover:bg-white/5 transition-colors"
          >
            暂时跳过
          </button>
        )}
      </div>
    </form>
  );
}
