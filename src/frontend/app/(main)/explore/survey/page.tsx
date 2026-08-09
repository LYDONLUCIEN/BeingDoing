'use client';

import { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { motion } from 'framer-motion';
import SurveyFormBd from '@/components/survey/SurveyFormBd';
import { surveyApi } from '@/lib/api/survey';
import { apiClient, getApiErrorMessage } from '@/lib/api/client';
import { loadSession, saveSession, getLastActivationCode, setUserSurveyCompleted, getUserPrivacyAck, setUserPrivacyAck } from '@/lib/explore/session';
import { applyExploreResumeToSession } from '@/lib/explore/session';
import { fetchExploreResumeFromJourneys } from '@/lib/explore/journeyResume';
import type { SurveyData } from '@/lib/survey/schema';
import { useAuthStore } from '@/stores/authStore';
import { useLocale } from '@/hooks/useLocale';
import PhaseCompleteWarmModal from '@/components/explore/PhaseCompleteWarmModal';

export default function SurveyPage() {
  const router = useRouter();
  const [activationCode, setActivationCode] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [initialData, setInitialData] = useState<SurveyData>({});
  const [preloadDone, setPreloadDone] = useState(false);
  const { user } = useAuthStore();
  const { t } = useLocale();
  const [privacyOpen, setPrivacyOpen] = useState(false);
  const [resending, setResending] = useState(false);
  const [resendMsg, setResendMsg] = useState('');

  // 邮箱未验证：禁止进入探索（问卷是探索流程的第一个写操作，在此拦截并引导验证）
  const emailUnverified = !!(user?.email && user.email_verified === false);

  const handleResendVerify = async () => {
    if (!user?.email || resending) return;
    setResending(true);
    setResendMsg('');
    try {
      await apiClient.post('/auth/email-verify/request', { email: user.email });
      setResendMsg('验证邮件已发送，请查收（如未收到请检查垃圾邮件）');
    } catch (e: unknown) {
      setResendMsg(getApiErrorMessage(e, '发送失败，请稍后重试'));
    } finally {
      setResending(false);
    }
  };

  useEffect(() => {
    const code = getLastActivationCode();
    if (!code) {
      router.replace('/explore/activate');
      return;
    }
    setActivationCode(code);

    // 用户级直读：通过 user-survey-status 加载已保存的问卷数据用于回填
    surveyApi.getUserSurveyStatus().then((res) => {
      if (res.data?.survey_data && Object.keys(res.data.survey_data).length > 0) {
        setInitialData(res.data.survey_data);
      }
    }).catch(() => {
      // 回退到激活码维度
      if (code) {
        surveyApi.getForActivation(code).then((sv) => {
          if (sv.data?.survey_data && Object.keys(sv.data.survey_data).length > 0) {
            setInitialData(sv.data.survey_data);
          }
        }).catch(() => {});
      }
    }).finally(() => setPreloadDone(true));
  }, [router]);

  // 隐私声明弹窗：等激活码与预加载完成后，若用户未勾选"不再提醒"则弹出
  useEffect(() => {
    if (activationCode && preloadDone && !emailUnverified) {
      if (!getUserPrivacyAck(user?.user_id)) {
        setPrivacyOpen(true);
      }
    }
  }, [activationCode, preloadDone, user?.user_id, emailUnverified]);

  const handlePrivacyContinue = (dontRemind?: boolean) => {
    if (dontRemind) setUserPrivacyAck(user?.user_id ?? '', true);
    setPrivacyOpen(false);
  };

  /** 提交/跳过后跳到「最新一步」：merge 后端 resume，避免硬编码回 values（回访用户应续上进度） */
  const gotoLatestPhase = async (code: string) => {
    let session = { ...loadSession(code), surveyCompleted: true };
    saveSession(session);
    try {
      const resume = await fetchExploreResumeFromJourneys(code);
      if (resume) {
        session = applyExploreResumeToSession(session, resume);
        saveSession(session);
      }
    } catch {
      /* resume 拉取失败则用本地 session 进度 */
    }
    router.push(`/explore/chat/${session.currentPhase}`);
  };

  const handleSubmit = async (data: SurveyData) => {
    if (!activationCode) return;
    setLoading(true);
    setError(null);
    try {
      await surveyApi.saveForActivation(activationCode, data);
      // 用户维度持久化：切换激活码或清缓存后仍可恢复
      setUserSurveyCompleted(user?.user_id ?? '', true);
      await gotoLatestPhase(activationCode);
    } catch (e: unknown) {
      const msg = getApiErrorMessage(e, '保存失败，请重试');
      if (msg.includes('激活码已过期')) {
        setError(`${msg}，请返回激活页更换激活码`);
        return;
      }
      setError(msg);
    } finally {
      setLoading(false);
    }
  };

  const handleSkip = async (data: SurveyData) => {
    if (!activationCode) return;
    setLoading(true);
    setError(null);
    let saved = false;
    try {
      // 跳过时仍保存昵称（最终报告署名必填，前端已校验非空）
      await surveyApi.saveForActivation(activationCode, { nickname: (data.nickname ?? '').trim() });
      // 用户维度持久化
      setUserSurveyCompleted(user?.user_id ?? '', true);
      saved = true;
    } catch (e: unknown) {
      const msg = getApiErrorMessage(e, '暂时跳过失败，请重试');
      if (msg.includes('激活码已过期')) {
        setError(`${msg}，请返回激活页更换激活码`);
      } else {
        setError(msg);
      }
    } finally {
      setLoading(false);
    }
    if (saved) {
      await gotoLatestPhase(activationCode);
    }
  };

  if (!activationCode || !preloadDone) return null;

  // 问卷昵称默认与注册昵称（users.username）同源：已保存的问卷昵称优先，否则回填注册昵称
  const mergedInitialData: SurveyData = { ...initialData };
  if (!(typeof mergedInitialData.nickname === 'string' && mergedInitialData.nickname.trim()) && user?.username?.trim()) {
    mergedInitialData.nickname = user.username.trim();
  }

  return (
    <div className="min-h-screen bg-bd-gradient text-bd-fg">
      <div className="max-w-2xl mx-auto px-4 pt-24 pb-20">
        <PhaseCompleteWarmModal
          open={privacyOpen}
          title={t('explore.survey.privacyTitle')}
          body={t('explore.survey.privacyBody')}
          continueLabel={t('explore.survey.privacyContinue')}
          dontRemindLabel={t('explore.survey.privacyDontRemind')}
          onContinue={handlePrivacyContinue}
        />
        <motion.div
          initial={{ opacity: 0, y: 24 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5, ease: [0.22, 1, 0.36, 1] }}
          className="space-y-8"
        >
          <button
            type="button"
            onClick={() => router.push('/explore/activate')}
            className="text-sm text-bd-subtle hover:text-bd-fg transition-colors flex items-center gap-1"
          >
            <span aria-hidden>←</span> 返回
          </button>

          <header className="space-y-3">
            <p className="text-xs tracking-[0.25em] uppercase text-bd-primary font-medium">在正式开始之前</p>
            <h1 className="text-3xl sm:text-4xl font-semibold text-bd-fg tracking-tight">了解你</h1>
            <p className="text-bd-muted text-sm sm:text-base leading-relaxed max-w-lg">
              这份问卷帮助我们更了解你的背景，让对话更有针对性。
              <span className="text-bd-fg font-medium">昵称为必填项</span>
              —— 最后生成的报告需要署名，不填写无法跳过；其余问题均为选填。
            </p>
          </header>

          {error && (
            <div className="rounded-xl border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-400">
              {error}
            </div>
          )}

          {emailUnverified ? (
            <div className="rounded-2xl border border-amber-500/30 bg-amber-500/10 p-6 sm:p-8 space-y-4">
              <h2 className="text-lg font-semibold text-bd-fg">请先验证邮箱</h2>
              <p className="text-sm text-bd-muted leading-relaxed">
                开始探索前需要先验证邮箱（{user?.email}）。点击下方按钮发送验证邮件（链接 24 小时有效），
                如未收到请留意垃圾邮件文件夹。
              </p>
              <div className="flex items-center gap-3">
                <button
                  type="button"
                  onClick={handleResendVerify}
                  disabled={resending}
                  className="rounded-xl px-5 py-2.5 text-sm font-medium text-white transition-all bd-btn-black disabled:opacity-50"
                >
                  {resending ? '发送中…' : '发送验证邮件'}
                </button>
              </div>
              {resendMsg && <p className="text-xs text-bd-muted">{resendMsg}</p>}
            </div>
          ) : (
          <div className="rounded-2xl border border-bd-border bg-bd-card/80 backdrop-blur-lg p-6 sm:p-8 shadow-[0_4px_24px_rgba(0,0,0,0.06)]">
            <SurveyFormBd
              initialData={mergedInitialData}
              loading={loading}
              saving={loading}
              submitLabel="提交并开始第一步 →"
              showSkip
              nicknameRequired
              onSubmit={handleSubmit}
              onSkip={handleSkip}
            />
          </div>
          )}
        </motion.div>
      </div>
    </div>
  );
}
