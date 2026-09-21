'use client';

import { useEffect, useMemo, useState } from 'react';
import { useRouter } from 'next/navigation';
import DashboardPageHeader from '@/components/dashboard/DashboardPageHeader';
import SurveyFormBd from '@/components/survey/SurveyFormBd';
import { surveyApi } from '@/lib/api/survey';
import { getLastActivationCode } from '@/lib/explore/session';
import { useAuthStore } from '@/stores/authStore';
import { computeSurveyCompletion } from '@/lib/survey/completion';
import type { SurveyData } from '@/lib/survey/schema';

/**
 * 编辑个人资料（独立页面，对齐 HTML 当前进度「01 个人信息」卡）：
 * 顶部资料完成度进度条 + 完整问卷表单；保存接口与 /dashboard/settings 同源。
 */
export default function ProfileEditPage() {
  const router = useRouter();
  const { isAuthenticated } = useAuthStore();
  const [data, setData] = useState<SurveyData>({});
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [toast, setToast] = useState<string | null>(null);

  const isLocalUiPreview =
    process.env.NODE_ENV === 'development' &&
    typeof window !== 'undefined' &&
    new URLSearchParams(window.location.search).get('ui_preview') === '1';

  useEffect(() => {
    if (!isAuthenticated) return;
    if (isLocalUiPreview) {
      setData({ nickname: '预览用户', gender: '女', age: '25-30' });
      setLoading(false);
      return;
    }
    surveyApi
      .getUserSurveyStatus()
      .then((r) => setData(r.data?.survey_data || {}))
      .catch(() => setData({}))
      .finally(() => setLoading(false));
  }, [isAuthenticated, isLocalUiPreview]);

  useEffect(() => {
    if (!toast) return;
    const id = setTimeout(() => setToast(null), 2500);
    return () => clearTimeout(id);
  }, [toast]);

  const completion = useMemo(() => computeSurveyCompletion(data), [data]);

  const handleSubmit = async (next: SurveyData) => {
    setSaving(true);
    setError(null);
    try {
      const code = getLastActivationCode();
      if (code) {
        await surveyApi.saveForActivation(code, next);
      } else {
        await surveyApi.saveForUser(next);
      }
      setData(next);
      setToast('保存成功');
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : '保存失败';
      setError(msg);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="ol-profile-content">
      <DashboardPageHeader
        kicker="PROFILE"
        title="编辑个人资料"
        description="这些信息会成为 AI 了解你的起点，只对你和当前旅程可见。"
        action={
          <button
            type="button"
            onClick={() => router.push('/dashboard')}
            className="ol-profile-edit-link"
          >
            ← 返回当前进度
          </button>
        }
      />

      {/* 资料完成度（HTML 同款渐变进度条） */}
      <section className="ol-profile-surface p-6 mb-6">
        <div className="ol-profile-progress-meta">
          <span>资料完成度</span>
          <strong>
            {completion.filled}/{completion.total} · {completion.percent}%
          </strong>
        </div>
        <div
          className="ol-profile-progress-track"
          role="progressbar"
          aria-valuenow={completion.percent}
          aria-valuemin={0}
          aria-valuemax={100}
          aria-label="资料完成度"
        >
          <div className="ol-profile-progress-fill" style={{ width: `${completion.percent}%` }} />
        </div>
      </section>

      <section className="ol-profile-surface p-8">
        {error && <p className="text-sm text-bd-err mb-4">{error}</p>}
        <SurveyFormBd
          initialData={data}
          loading={loading}
          saving={saving}
          submitLabel="保存修改"
          showSkip={false}
          onSubmit={handleSubmit}
        />
      </section>

      {toast && (
        <div
          role="alert"
          className="fixed bottom-8 left-1/2 -translate-x-1/2 px-5 py-3 rounded-xl text-sm font-medium shadow-lg z-[100] bg-emerald-600/95 text-white"
          style={{ animation: 'toast-in 0.25s ease-out' }}
        >
          {toast}
        </div>
      )}
    </div>
  );
}
