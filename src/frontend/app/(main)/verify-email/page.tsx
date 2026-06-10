'use client';

import { useState, useEffect, Suspense, useCallback } from 'react';
import { useSearchParams, useRouter } from 'next/navigation';
import Link from 'next/link';
import { CheckCircle, XCircle, Mail } from 'lucide-react';
import { apiClient, getApiErrorMessage } from '@/lib/api/client';
import { useAuthStore } from '@/stores/authStore';
import { useLocale } from '@/hooks/useLocale';

type VerifyState = 'loading' | 'success' | 'expired' | 'error';

function VerifyEmailContent() {
  const searchParams = useSearchParams();
  const router = useRouter();
  const { t } = useLocale();
  const { user, setUser } = useAuthStore();
  const token = searchParams.get('token') || '';
  const [state, setState] = useState<VerifyState>('loading');
  const [errorMsg, setErrorMsg] = useState('');
  const [resending, setResending] = useState(false);
  const [resendMsg, setResendMsg] = useState('');

  const doVerify = useCallback(async (tkn: string) => {
    setState('loading');
    setErrorMsg('');
    try {
      const res = await apiClient.get(`/auth/email-verify?token=${encodeURIComponent(tkn)}`);
      const data = res.data?.data;
      setState('success');
      // Update auth store with verified status
      if (user && data) {
        setUser({ ...user, email_verified: true });
      }
    } catch (err: unknown) {
      const msg = getApiErrorMessage(err, t('auth.verifyFailed'));
      setErrorMsg(msg);
      // Detect expired vs other errors
      if (msg.includes('过期') || msg.includes('expired') || msg.includes('无效') || msg.includes('invalid')) {
        setState('expired');
      } else {
        setState('error');
      }
    }
  }, [t, user, setUser]);

  useEffect(() => {
    if (token) doVerify(token);
    else setState('error');
  }, [token, doVerify]);

  const handleResend = async () => {
    if (!user?.email || resending) return;
    setResending(true);
    setResendMsg('');
    try {
      await apiClient.post('/auth/email-verify/request', { email: user.email });
      setResendMsg(t('auth.verifyEmailSent'));
    } catch (err: unknown) {
      setResendMsg(getApiErrorMessage(err, t('auth.verifyFailed')));
    } finally {
      setResending(false);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center px-4" style={{ background: 'var(--bg, #fff)' }}>
      <div className="w-full max-w-sm space-y-6 text-center">
        {state === 'loading' && (
          <>
            <div className="animate-spin rounded-full h-10 w-10 border-2 mx-auto" style={{ borderColor: 'var(--bd-border)', borderTopColor: 'var(--bd-fg)' }} />
            <p className="text-sm" style={{ color: 'var(--bd-fg-muted)' }}>{t('auth.loggingIn')}</p>
          </>
        )}

        {state === 'success' && (
          <>
            <CheckCircle className="mx-auto h-12 w-12 text-emerald-500" />
            <h1 className="text-xl font-semibold" style={{ color: 'var(--bd-fg)' }}>{t('auth.verifySuccess')}</h1>
            <p className="text-sm" style={{ color: 'var(--bd-fg-muted)' }}>{t('auth.verifyEmailDesc')}</p>
            <Link
              href="/explore/activate"
              className="inline-block rounded-xl px-6 py-3 text-sm font-medium text-white transition-all bd-btn-black"
            >
              {t('explore.activate.submit')}
            </Link>
          </>
        )}

        {(state === 'expired' || state === 'error') && (
          <>
            <XCircle className="mx-auto h-12 w-12 text-red-400" />
            <h1 className="text-xl font-semibold" style={{ color: 'var(--bd-fg)' }}>{state === 'expired' ? t('auth.linkExpired') : t('auth.verifyFailed')}</h1>
            <p className="text-sm" style={{ color: 'var(--bd-fg-muted)' }}>{errorMsg}</p>
            {user?.email && (
              <div className="space-y-3">
                <button
                  type="button"
                  onClick={handleResend}
                  disabled={resending}
                  className="inline-flex items-center gap-2 rounded-xl px-5 py-2.5 text-sm font-medium text-white transition-all bd-btn-black disabled:opacity-50"
                >
                  <Mail className="h-4 w-4" />
                  {t('auth.resendVerifyEmail')}
                </button>
                {resendMsg && <p className="text-xs" style={{ color: 'var(--bd-fg-muted)' }}>{resendMsg}</p>}
              </div>
            )}
            <Link href="/" className="text-sm hover:underline" style={{ color: 'var(--bd-fg-muted)' }}>
              ← {t('explore.intro.back')}
            </Link>
          </>
        )}
      </div>
    </div>
  );
}

export default function VerifyEmailPage() {
  return (
    <Suspense fallback={null}>
      <VerifyEmailContent />
    </Suspense>
  );
}
