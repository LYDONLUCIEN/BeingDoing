'use client';

import { useCallback, useEffect, useState } from 'react';
import { authApi } from '@/lib/api/auth';
import { getApiErrorMessage } from '@/lib/api/client';

/**
 * 注册前置邮箱验证（2026-10-13 起，ADR-0026）共享逻辑：
 * 注册页 (/auth/register) 与 AuthModal 注册 Tab 复用。
 *
 * 流程：email（发码）→ code（验码 / 链接轮询）→ password（凭 ticket 完成注册）。
 * ticket 由调用方在提交注册时携带；本 hook 不管密码表单与最终提交。
 */
export type RegisterStep = 'email' | 'code' | 'password';

export function useRegisterVerification() {
  const [step, setStep] = useState<RegisterStep>('email');
  const [email, setEmail] = useState('');
  const [pendingId, setPendingId] = useState('');
  const [ticket, setTicket] = useState('');
  const [alreadyRegistered, setAlreadyRegistered] = useState(false);
  const [cooldown, setCooldown] = useState(0);
  const [sending, setSending] = useState(false);
  const [verifying, setVerifying] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');

  // 重发冷却倒计时（60 秒，与后端冷却口径一致）
  useEffect(() => {
    if (cooldown <= 0) return;
    const timer = window.setTimeout(() => setCooldown((prev) => Math.max(0, prev - 1)), 1000);
    return () => window.clearTimeout(timer);
  }, [cooldown]);

  /** 第一步：发送验证码（返回是否成功进入验码步骤） */
  const sendCode = useCallback(async (rawEmail: string): Promise<boolean> => {
    const normalized = rawEmail.trim().toLowerCase();
    if (!normalized) {
      setError('请输入邮箱');
      return false;
    }
    setError('');
    setNotice('');
    setAlreadyRegistered(false);
    setSending(true);
    try {
      const res = await authApi.requestRegisterCode({ email: normalized });
      const data = res?.data;
      if (data?.already_registered) {
        // 明确提示口径：页面引导去登录（后端已发通知邮件）
        setAlreadyRegistered(true);
        setNotice('该邮箱已注册，请直接登录；我们已发送一封提醒邮件到该邮箱');
        return false;
      }
      if (data?.pending_id) {
        setEmail(normalized);
        setPendingId(data.pending_id);
        setStep('code');
        setCooldown(60);
        setNotice('验证码已发送，请查收邮件（10 分钟内有效）；也可以直接点击邮件中的链接');
        return true;
      }
      setError('发送失败，请稍后重试');
      return false;
    } catch (err: unknown) {
      setError(getApiErrorMessage(err, '发送验证码失败，请稍后重试'));
      return false;
    } finally {
      setSending(false);
    }
  }, []);

  /** 第二步（验证码形态）：校验 6 位验证码，通过进入密码步骤 */
  const verifyCode = useCallback(
    async (code: string): Promise<boolean> => {
      if (!pendingId || !email) return false;
      setError('');
      setVerifying(true);
      try {
        const res = await authApi.verifyRegisterCode({
          pending_id: pendingId,
          email,
          code: code.trim(),
        });
        const t = res?.data?.ticket;
        if (res?.code === 200 && t) {
          setTicket(t);
          setStep('password');
          setNotice('邮箱验证成功，请设置密码完成注册');
          return true;
        }
        setError('验证失败，请重试');
        return false;
      } catch (err: unknown) {
        setError(getApiErrorMessage(err, '验证码错误或已过期'));
        return false;
      } finally {
        setVerifying(false);
      }
    },
    [pendingId, email]
  );

  // 第二步（链接形态）：停留验码步骤时每 5 秒轮询，用户在任意设备点邮件链接即可推进
  useEffect(() => {
    if (step !== 'code' || !pendingId || !email || ticket) return;
    const timer = window.setInterval(async () => {
      try {
        const res = await authApi.pollRegisterVerification({ pending_id: pendingId, email });
        const data = res?.data;
        if (data?.verified && data?.ticket) {
          setTicket(data.ticket);
          setStep('password');
          setNotice('邮箱验证成功，请设置密码完成注册');
        } else if (data?.expired) {
          setError('验证码已过期，请重新发送');
        }
      } catch {
        // 轮询失败静默，下一轮再试
      }
    }, 5000);
    return () => window.clearInterval(timer);
  }, [step, pendingId, email, ticket]);

  /** 返回第一步换邮箱（作废旧会话） */
  const backToEmail = useCallback(() => {
    setStep('email');
    setPendingId('');
    setTicket('');
    setAlreadyRegistered(false);
    setError('');
    setNotice('');
  }, []);

  return {
    step,
    email,
    ticket,
    alreadyRegistered,
    cooldown,
    sending,
    verifying,
    error,
    notice,
    setError,
    setNotice,
    sendCode,
    verifyCode,
    backToEmail,
  };
}
