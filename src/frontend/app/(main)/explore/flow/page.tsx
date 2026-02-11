'use client';

import { useState, useEffect, useCallback, useRef } from 'react';
import { useRouter } from 'next/navigation';
import { useAuthStore } from '@/stores/authStore';
import { useSessionStore } from '@/stores/sessionStore';
import { useProgressStore } from '@/stores/progressStore';
import { sessionsApi } from '@/lib/api/sessions';
import { questionsApi } from '@/lib/api/questions';
import { answersApi, type Answer, type AnswerChangeType } from '@/lib/api/answers';
import { chatApi, type Message, type AnswerCardMeta } from '@/lib/api/chat';
import { FLOW_STEPS, mergeConversationItems } from '@/lib/constants';

// 子组件导入
import FlowHeader from '@/components/explore/FlowHeader';
import StepIntroSection from '@/components/explore/StepIntroSection';
import CurrentQuestionBanner from '@/components/explore/CurrentQuestionBanner';
import ConversationSection from '@/components/explore/ConversationSection';
import AnswerCardHistory from '@/components/explore/AnswerCardHistory';
import AnswerCardSection from '@/components/explore/AnswerCardSection';
import ConversationInput from '@/components/explore/ConversationInput';
import DebugPanel from '@/components/explore/DebugPanel';

export default function ExploreFlowPage() {
  const router = useRouter();
  const { isAuthenticated, user } = useAuthStore();
  const { currentSession, setCurrentSession } = useSessionStore();
  const { progresses, setProgress } = useProgressStore();

  // 基础状态
  const [currentStep, setCurrentStep] = useState<string>('values_exploration');
  const [currentQuestion, setCurrentQuestion] = useState<any>(null);
  const [guideQuestions, setGuideQuestions] = useState<any[]>([]);
  const [answers, setAnswers] = useState<Answer[]>([]);
  const [chatMessages, setChatMessages] = useState<Message[]>([]);
  const [questionMap, setQuestionMap] = useState<Record<number, string>>({});

  // UI状态
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string>('');
  const [streamingContent, setStreamingContent] = useState('');
  const [streaming, setStreaming] = useState(false);
  const [stepIntroSeen, setStepIntroSeen] = useState<Record<string, boolean>>({});

  // 编辑状态
  const [editingAnswerId, setEditingAnswerId] = useState<string | null>(null);
  const [editContent, setEditContent] = useState('');
  const [editChangeType, setEditChangeType] = useState<AnswerChangeType>('unrelated');
  const [savingEdit, setSavingEdit] = useState(false);

  // Answer Card状态
  const [answerCard, setAnswerCard] = useState<AnswerCardMeta | null>(null);
  const [answerCardHistory, setAnswerCardHistory] = useState<
    { id: string; questionTitle: string; userAnswer: string; aiAnalysis?: string }[]
  >([]);

  // 调试状态
  const [showDebugPanel, setShowDebugPanel] = useState(false);
  const [debugEntries, setDebugEntries] = useState<any[]>([]);

  const abortControllerRef = useRef<AbortController | null>(null);

  // 认证检查
  useEffect(() => {
    if (!isAuthenticated) {
      router.push('/auth/login?redirect=/explore');
      return;
    }
    if (!currentSession) {
      router.push('/explore');
      return;
    }
    const step = currentSession.current_step || 'values_exploration';
    setCurrentStep(step);
    setStepIntroSeen((prev) => ({ ...prev, [step]: true }));
  }, [isAuthenticated, currentSession, router]);

  // 数据加载函数
  const loadGuideQuestions = async (step: string) => {
    try {
      const response = await questionsApi.getGuideQuestions(step, 5);
      const list = response.data?.questions || [];
      setGuideQuestions(list);
      if (list.length > 0 && !currentQuestion) setCurrentQuestion(list[0]);
    } catch (err) {
      console.error('加载引导问题失败:', err);
    }
  };

  const loadAnswersAndChat = useCallback(async () => {
    if (!currentSession) return;
    try {
      const [ansRes, chatRes] = await Promise.all([
        answersApi.getAnswers(currentSession.session_id),
        chatApi.getHistory(currentSession.session_id, 'main_flow', 10), // 减少到10条，开发期间更快
      ]);
      setAnswers(ansRes.data?.answers || []);
      setChatMessages(chatRes.data?.messages || []);
    } catch (err) {
      console.error('加载回答/对话失败:', err);
    }
  }, [currentSession]);

  const loadQuestionMap = useCallback(async () => {
    const categories = ['values', 'strengths', 'interests'];
    const map: Record<number, string> = {};
    for (const cat of categories) {
      try {
        const res = await questionsApi.getQuestions(cat);
        const list = res.data?.questions || [];
        list.forEach((q: any) => { map[q.id] = q.content; });
      } catch (_) {}
    }
    setQuestionMap(map);
  }, []);

  useEffect(() => {
    if (currentSession && !streaming) {
      loadAnswersAndChat();
      loadQuestionMap();
      if (!stepIntroSeen[currentStep]) return;
      loadGuideQuestions(currentStep);
    }
  }, [currentSession, currentStep, loadAnswersAndChat, loadQuestionMap, streaming, stepIntroSeen]);

  // 事件处理函数
  const handleStepChange = async (step: string) => {
    setCurrentStep(step);
    if (currentSession) await loadGuideQuestions(step);
  };

  const handleChatSubmit = async (content: string) => {
    if (!currentSession) return;
    setError('');
    setStreaming(true);
    setStreamingContent('');
    setChatMessages((prev) => [
      ...prev,
      { id: `temp-user-${Date.now()}`, role: 'user', content, created_at: new Date().toISOString() },
    ]);
    const controller = new AbortController();
    abortControllerRef.current = controller;
    await chatApi.sendMessageStream(
      {
        session_id: currentSession.session_id,
        message: content,
        current_step: currentStep,
        category: 'main_flow',
      },
      {
        onStarted: () => setStreamingContent('思考中…'),
        onChunk: (chunk) => setStreamingContent((prev) => (prev === '思考中…' ? chunk : prev + chunk)),
        onDone: (_full, meta) => {
          setStreamingContent('');
          setStreaming(false);
          abortControllerRef.current = null;
          if (meta?.answerCard && meta.answerCard.user_answer) {
            setAnswerCard(meta.answerCard);
          } else {
            setAnswerCard(null);
          }
          loadAnswersAndChat();
        },
        onError: (err) => {
          setError(err);
          setStreamingContent('');
          setStreaming(false);
          abortControllerRef.current = null;
          loadAnswersAndChat();
        },
        onStop: async (partialContent) => {
          setStreamingContent('');
          setStreaming(false);
          abortControllerRef.current = null;
          try {
            await chatApi.recordInterrupt(currentSession.session_id, partialContent, currentStep);
          } catch (_) {}
          loadAnswersAndChat();
        },
      },
      controller.signal
    );
  };

  const handleStopStream = () => {
    if (abortControllerRef.current) abortControllerRef.current.abort();
  };

  const handleOpenDebug = async () => {
    if (!currentSession) return;
    try {
      const res = await chatApi.getDebugLogs(currentSession.session_id);
      const entries = res.data?.entries ?? [];
      if (entries.length === 0) {
        setDebugEntries([{ _hint: '暂无日志。请先使用「向咨询师提问」完成一次对话后，再打开调试查看智能体判断与调用链。' }]);
      } else {
        setDebugEntries(entries);
      }
      setShowDebugPanel(true);
    } catch (err: any) {
      const status = err.response?.status;
      const msg = status === 403
        ? '无权限。请在 .env 中配置 SUPER_ADMIN_EMAILS=你的邮箱 或 SUPER_ADMIN_USER_IDS=你的用户ID，仅超级管理员可查看调试日志。'
        : (err.response?.data?.detail || err.message || '无权限或暂无日志');
      setDebugEntries([{ error: msg }]);
      setShowDebugPanel(true);
    }
  };

  const handleStartEdit = (answerId: string) => {
    const a = answers.find((x) => x.id === answerId);
    if (a) {
      setEditingAnswerId(answerId);
      setEditContent(a.content);
      setEditChangeType('unrelated');
    }
  };

  const handleSaveEdit = async (answerId: string, content: string, changeType: AnswerChangeType) => {
    setSavingEdit(true);
    try {
      await answersApi.update(answerId, { content, change_type: changeType });
      await chatApi.resummarize(currentSession!.session_id, currentStep);
      await loadAnswersAndChat();
      setEditingAnswerId(null);
    } catch (err: any) {
      setError(err.response?.data?.detail || '保存失败');
    } finally {
      setSavingEdit(false);
    }
  };

  const handleAnswerCardNext = (answerId: string, questionTitle: string, userAnswer: string, aiAnalysis?: string) => {
    if (currentSession) {
      sessionsApi
        .updateProgress(currentSession.session_id, currentStep, 1, undefined)
        .then((res) => {
          if (res.data) {
            setProgress(currentStep, {
              step: currentStep,
              completed_count: res.data.completed_count,
              total_count: res.data.total_count,
              percentage: res.data.percentage,
            });
          }
        })
        .catch(() => {});

      const idx = FLOW_STEPS.findIndex((s) => s.id === currentStep);
      const nextStep = idx >= 0 && idx + 1 < FLOW_STEPS.length ? FLOW_STEPS[idx + 1].id : null;
      if (nextStep) {
        setCurrentStep(nextStep);
        setStepIntroSeen((prev) => ({ ...prev, [nextStep]: false }));
      }
    }

    setAnswerCardHistory((prev) => [
      ...prev,
      { id: answerId, questionTitle, userAnswer, aiAnalysis },
    ]);
    setAnswerCard(null);
  };

  const handleAnswerCardEdit = async (newText: string) => {
    const latestAnswer = [...answers].sort(
      (a, b) =>
        new Date(b.updated_at || b.created_at).getTime() -
        new Date(a.updated_at || a.created_at).getTime()
    )[0];
    try {
      if (latestAnswer) {
        await answersApi.update(latestAnswer.id, {
          content: newText,
          change_type: 'same_direction',
        });
        if (currentSession) {
          await chatApi.resummarize(currentSession.session_id, currentStep);
        }
        await loadAnswersAndChat();
      }
      setAnswerCard((prev) => (prev ? { ...prev, user_answer: newText } : prev));
    } catch {
      // silently ignore
    }
  };

  const handleHistoryCardEdit = async (cardId: string, newText: string) => {
    try {
      await answersApi.update(cardId, {
        content: newText,
        change_type: 'same_direction',
      });
      if (currentSession) {
        await chatApi.resummarize(currentSession.session_id, currentStep);
      }
      await loadAnswersAndChat();
      setAnswerCardHistory((prev) =>
        prev.map((h) => (h.id === cardId ? { ...h, userAnswer: newText } : h))
      );
    } catch {
      // silently ignore
    }
  };

  const handleStepIntroStart = () => {
    setStepIntroSeen((prev) => ({ ...prev, [currentStep]: true }));
    if (currentSession) {
      loadGuideQuestions(currentStep);
    }
  };

  // Loading状态
  if (!isAuthenticated || !currentSession) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-slate-900">
        <div className="animate-spin rounded-full h-12 w-12 border-2 border-primary-500 border-t-transparent" />
      </div>
    );
  }

  const conversationItems = mergeConversationItems(answers, chatMessages, questionMap);
  const progressByStep = Object.fromEntries(
    Object.entries(progresses).map(([k, v]) => [k, { percentage: v?.percentage ?? 0 }])
  );
  const showStepIntro = !stepIntroSeen[currentStep];

  return (
    <div className="min-h-screen bg-gradient-to-b from-slate-900 via-slate-900 to-slate-800 text-white flex flex-col">
      <FlowHeader
        currentStep={currentStep}
        progressByStep={progressByStep}
        isSuperAdmin={user?.is_super_admin || false}
        onStepChange={handleStepChange}
        onOpenDebug={handleOpenDebug}
      />

      <main className="flex-1 flex flex-col max-w-4xl mx-auto w-full px-4 py-6 overflow-hidden">
        {showStepIntro ? (
          <StepIntroSection currentStep={currentStep} onStart={handleStepIntroStart} />
        ) : (
          <>
            <div className="flex-shrink-0 mb-4">
              <CurrentQuestionBanner question={currentQuestion} />
            </div>

            <div className="flex-1 min-h-0 flex gap-4">
              <ConversationSection
                conversationItems={conversationItems}
                streamingContent={streamingContent}
                editingAnswerId={editingAnswerId}
                editContent={editContent}
                editChangeType={editChangeType}
                savingEdit={savingEdit}
                onStartEdit={handleStartEdit}
                onCancelEdit={() => setEditingAnswerId(null)}
                onSaveEdit={handleSaveEdit}
                onEditContentChange={setEditContent}
                onEditChangeTypeChange={setEditChangeType}
              />

              <AnswerCardHistory
                history={answerCardHistory}
                onSubmitEdit={handleHistoryCardEdit}
              />
            </div>

            <AnswerCardSection
              answerCard={answerCard}
              currentQuestion={currentQuestion}
              currentStep={currentStep}
              answers={answers}
              currentSessionId={currentSession.session_id}
              onNext={handleAnswerCardNext}
              onDiscussMore={() => {}}
              onSubmitEdit={handleAnswerCardEdit}
            />

            <div className="flex-shrink-0 mt-4 space-y-2">
              {error && (
                <div
                  className="p-3 rounded-lg bg-red-500/20 border border-red-400/40 text-red-200 text-sm"
                  role="alert"
                >
                  {error}
                </div>
              )}
              <ConversationInput
                onSubmit={handleChatSubmit}
                loading={loading || streaming}
                streaming={streaming}
                onStopStream={handleStopStream}
              />
            </div>
          </>
        )}
      </main>

      <DebugPanel
        isOpen={showDebugPanel}
        debugEntries={debugEntries}
        onClose={() => setShowDebugPanel(false)}
      />
    </div>
  );
}
