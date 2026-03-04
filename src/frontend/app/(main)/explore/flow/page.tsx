'use client';

import { useState, useEffect, useCallback, useRef } from 'react';
import { useRouter } from 'next/navigation';
import { useAuthStore } from '@/stores/authStore';
import { useSessionStore } from '@/stores/sessionStore';
import { useProgressStore } from '@/stores/progressStore';
import { chatApi, type Message, type QuestionProgress, type AnswerCardMeta } from '@/lib/api/chat';
import { surveyApi } from '@/lib/api/survey';
import { useAuthModalStore } from '@/stores/authModalStore';
import { ArrowLeft, ChevronDown } from 'lucide-react';
import SurveyForm from '@/components/survey/SurveyForm';
import type { SurveyData } from '@/lib/survey/schema';

// v2.4: 新组件
import FlowHeader from '@/components/explore/FlowHeader';
import StepTheoryIntro from '@/components/explore/StepTheoryIntro';
import EnhancedAnswerCard from '@/components/explore/EnhancedAnswerCard';
import FlowChatInput from '@/components/explore/FlowChatInput';
import FlowAiMessage from '@/components/explore/FlowAiMessage';
import SuggestionTags from '@/components/explore/SuggestionTags';
import DebugPanel from '@/components/explore/DebugPanel';

// 步骤理论配置（对应后端 step_guidance.py）
const STEP_THEORIES: Record<string, { name: string; purpose: string; theory: string }> = {
  'values_exploration': {
    name: '探索重要的事（价值观）',
    purpose: '探索你内心真正看重的价值观',
    theory: `价值观是指引人生方向的核心信念。通过探索价值观，我们能够：
1. 明确什么对你来说真正重要
2. 理解你做决策时的内在驱动力
3. 找到让你感到有意义的人生方向

价值观探索不是寻找"正确答案"，而是发现你内心真实的声音。`
  },
  'strengths_exploration': {
    name: '探索擅长的事（才能）',
    purpose: '发现你的天赋优势和核心能力',
    theory: `才能是你天生擅长且容易做好的事情。探索才能可以帮助你：
1. 识别你的天赋优势领域
2. 了解你能在哪些方面出类拔萃
3. 找到能发挥优势的职业方向

真正的才能往往表现为：做这件事时感到轻松、自然，且能比他人做得更好。`
  },
  'interests_exploration': {
    name: '探索喜欢的事（热情）',
    purpose: '探索你内心真正感兴趣和充满热情的事物',
    theory: `热情是驱动你持续投入的内在动力。探索热情能够：
1. 发现让你充满活力的事物
2. 识别你愿意长期投入的方向
3. 找到工作与乐趣结合的可能性

热情的标志是：即使遇到困难，你仍然愿意继续，并从中获得满足感。`
  }
};

/** currentStep → flow 阶段类（llmchat: values/strength/interest/purpose） */
function stepToPhaseClass(step: string): 'values' | 'strength' | 'interest' | 'purpose' {
  if (step === 'values_exploration') return 'values';
  if (step === 'strengths_exploration') return 'strength';
  if (step === 'interests_exploration') return 'interest';
  return 'purpose';
}

/** currentStep → 维度名（用于标签） */
function stepToDimensionName(step: string): string {
  if (step === 'values_exploration') return '信念';
  if (step === 'strengths_exploration') return '禀赋';
  if (step === 'interests_exploration') return '热忱';
  return '使命';
}

function stepToPhase(step: string): string {
  if (step === 'values_exploration') return 'values';
  if (step === 'strengths_exploration') return 'strengths';
  if (step === 'interests_exploration') return 'interests';
  if (step === 'combination' || step === 'refinement') return 'purpose';
  return 'default';
}

/** 已完成的题目（折叠显示用） */
interface CompletedQuestion {
  questionId: number;
  questionContent: string;
  messages: Message[];
  answerCard?: AnswerCardMeta;
  isExpanded: boolean;
}

export default function ExploreFlowPageV2() {
  const router = useRouter();
  const { isAuthenticated, user } = useAuthStore();
  const { currentSession } = useSessionStore();
  const { setProgress } = useProgressStore();

  // 基础状态
  const [currentStep, setCurrentStep] = useState<string>('values_exploration');
  const [chatMessages, setChatMessages] = useState<Message[]>([]);

  // v2.4: 题目进度状态
  const [questionProgress, setQuestionProgress] = useState<QuestionProgress | null>(null);
  const [completedQuestions, setCompletedQuestions] = useState<CompletedQuestion[]>([]);

  // UI状态
  const [error, setError] = useState<string>('');
  const [streamingContent, setStreamingContent] = useState('');
  const [streaming, setStreaming] = useState(false);
  const [showStepIntro, setShowStepIntro] = useState(false);
  const [initialLoaded, setInitialLoaded] = useState(false);

  // Answer Card状态
  const [answerCard, setAnswerCard] = useState<AnswerCardMeta | null>(null);

  // 建议标签状态
  const [suggestions, setSuggestions] = useState<string[]>([]);
  const [pendingInputText, setPendingInputText] = useState('');

  // 调试状态
  const [showDebugPanel, setShowDebugPanel] = useState(false);
  const [debugEntries, setDebugEntries] = useState<any[]>([]);

  // 调研问卷：进入 flow 时若尚无数据则先展示
  const [surveyData, setSurveyData] = useState<SurveyData | null | undefined>(undefined);
  const [surveyCompleted, setSurveyCompleted] = useState(false);
  const [surveyLoading, setSurveyLoading] = useState(false);

  const abortControllerRef = useRef<AbortController | null>(null);
  const chatEndRef = useRef<HTMLDivElement | null>(null);
  const chatBodyRef = useRef<HTMLDivElement | null>(null);
  const [showScrollBottom, setShowScrollBottom] = useState(false);

  // 滚动检测（复刻 llmchat）
  const checkScrollPosition = useCallback(() => {
    const el = chatBodyRef.current;
    if (!el) return;
    const distFromBottom = el.scrollHeight - el.scrollTop - el.clientHeight;
    setShowScrollBottom(distFromBottom > 80);
  }, []);

  useEffect(() => {
    const el = chatBodyRef.current;
    if (!el) return;
    el.addEventListener('scroll', checkScrollPosition);
    checkScrollPosition();
    return () => el.removeEventListener('scroll', checkScrollPosition);
  }, [checkScrollPosition, chatMessages, streamingContent]);

  // 内容变化时重新检测滚动位置
  useEffect(() => {
    const t = setTimeout(checkScrollPosition, 50);
    return () => clearTimeout(t);
  }, [chatMessages, streamingContent, checkScrollPosition]);

  const scrollToBottom = useCallback(() => {
    chatBodyRef.current?.scrollTo({ top: chatBodyRef.current.scrollHeight, behavior: 'smooth' });
  }, []);

  // 自动滚动到底部（发送/流式时）
  useEffect(() => {
    const el = chatBodyRef.current;
    if (!el) return;
    const distFromBottom = el.scrollHeight - el.scrollTop - el.clientHeight;
    if (distFromBottom < 120) {
      chatEndRef.current?.scrollIntoView({ behavior: 'smooth' });
    }
  }, [chatMessages, streamingContent]);

  // 认证检查
  useEffect(() => {
    if (!isAuthenticated) {
      useAuthModalStore.getState().openAuthModal('/explore/flow');
      return;
    }
    if (!currentSession) {
      router.push('/explore');
      return;
    }
    const step = currentSession.current_step || 'values_exploration';
    setCurrentStep(step);
  }, [isAuthenticated, currentSession, router]);

  // 加载调研数据
  useEffect(() => {
    if (!currentSession?.session_id) return;
    let cancelled = false;
    (async () => {
      try {
        const res = await surveyApi.getForSession(currentSession.session_id);
        if (!cancelled && res.data?.survey_data) {
          const data = res.data.survey_data;
          const hasData = Object.keys(data).some((k) => {
            const v = (data as Record<string, unknown>)[k];
            return v !== undefined && v !== null && v !== '' && (Array.isArray(v) ? v.length > 0 : true);
          });
          if (hasData) setSurveyCompleted(true);
          setSurveyData(data);
        } else {
          setSurveyData({});
        }
      } catch {
        if (!cancelled) setSurveyData({});
      }
    })();
    return () => { cancelled = true; };
  }, [currentSession?.session_id]);

  // 首次加载对话历史 + 历史答题卡 + 判断是否显示步骤介绍
  useEffect(() => {
    if (!currentSession || initialLoaded) return;
    (async () => {
      try {
        // 并行加载：对话历史 + 历史答题卡
        const [chatRes, cardsRes] = await Promise.all([
          chatApi.getHistory(currentSession.session_id, 'main_flow', 50),
          chatApi.getAnswerCards(currentSession.session_id).catch(() => ({ data: { answer_cards: [] } })),
        ]);

        const messages = chatRes.data?.messages || [];
        setChatMessages(messages);

        // 恢复已完成的答题卡
        const savedCards: AnswerCardMeta[] = cardsRes.data?.answer_cards || [];
        if (savedCards.length > 0) {
          setCompletedQuestions(savedCards.map((card) => ({
            questionId: card.question_id!,
            questionContent: card.question_content || '',
            messages: [], // 历史对话不单独恢复，保持折叠即可
            answerCard: card,
            isExpanded: false,
          })));
        }

        // 如果没有对话历史也没有已完成答题卡，说明是新开始的探索
        if (messages.length === 0 && savedCards.length === 0) {
          setShowStepIntro(true);
        }
      } catch (err) {
        console.error('加载对话失败:', err);
      }
      setInitialLoaded(true);
    })();
  }, [currentSession, initialLoaded]);

  // 加载对话历史（用于刷新，不改变 showStepIntro）
  const loadChatHistory = useCallback(async () => {
    if (!currentSession) return;
    try {
      const chatRes = await chatApi.getHistory(currentSession.session_id, 'main_flow', 50);
      setChatMessages(chatRes.data?.messages || []);
    } catch (err) {
      console.error('加载对话失败:', err);
    }
  }, [currentSession]);

  // 处理对话提交
  const handleChatSubmit = async (content: string, skipAddingUserMessage?: boolean) => {
    if (!currentSession) return;
    setError('');
    setStreaming(true);
    setStreamingContent('');
    setSuggestions([]);

    // 只有非空消息才添加到聊天列表（空消息用于触发AI引导）；重新生成时跳过（已保留）
    if (content.trim() && !skipAddingUserMessage) {
      setChatMessages((prev) => [
        ...prev,
        { id: `temp-user-${Date.now()}`, role: 'user', content, created_at: new Date().toISOString() },
      ]);
    }

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
        onDone: async (_full, meta) => {
          setStreamingContent('');
          setStreaming(false);
          abortControllerRef.current = null;

          // v2.4: 处理 answer_card（从流式响应 meta 中获取）
          if (meta?.answerCard && meta.answerCard.user_answer) {
            setAnswerCard(meta.answerCard);
          }

          // v2.4: 处理 question_progress（从流式响应 meta 中获取）
          if (meta?.questionProgress) {
            setQuestionProgress(meta.questionProgress);
          }

          // v2.6: 处理建议标签
          setSuggestions(meta?.suggestions || []);

          await loadChatHistory();
        },
        onError: (err) => {
          setError(err);
          setStreamingContent('');
          setStreaming(false);
          abortControllerRef.current = null;
          loadChatHistory();
        },
        onStop: async (partialContent) => {
          setStreamingContent('');
          setStreaming(false);
          abortControllerRef.current = null;
          try {
            await chatApi.recordInterrupt(currentSession.session_id, partialContent, currentStep);
          } catch (_) {}
          loadChatHistory();
        },
      },
      controller.signal
    );
  };

  const handleStopStream = () => {
    if (abortControllerRef.current) abortControllerRef.current.abort();
  };

  /** 重新生成：移除该 AI 消息及之后的对话，用上一条用户消息重新发送 */
  const handleRegenerate = useCallback(
    (aiMessageIndex: number) => {
      if (streaming) return;
      const msgs = [...chatMessages];
      const lastUser = msgs
        .slice(0, aiMessageIndex)
        .filter((m) => m.role === 'user')
        .pop();
      if (!lastUser) return;
      setChatMessages(msgs.slice(0, aiMessageIndex));
      setAnswerCard(null);
      handleChatSubmit(lastUser.content, true);
    },
    [chatMessages, streaming]
  );

  const handleOpenDebug = async () => {
    if (!currentSession) return;
    try {
      const res = await chatApi.getDebugLogs(currentSession.session_id);
      const entries = res.data?.entries ?? [];
      setDebugEntries(entries.length === 0 ? [{ _hint: '暂无日志' }] : entries);
      setShowDebugPanel(true);
    } catch (err: any) {
      setDebugEntries([{ error: '无权限或暂无日志' }]);
      setShowDebugPanel(true);
    }
  };

  // v2.4: 确认answer_card并移动到下一题
  const handleConfirmAnswer = () => {
    if (!answerCard) return;

    // 将当前题目的对话记录和答题卡添加到已完成列表
    setCompletedQuestions(prev => [
      ...prev,
      {
        questionId: answerCard.question_id!,
        questionContent: answerCard.question_content!,
        messages: [...chatMessages],
        answerCard: answerCard,
        isExpanded: false,
      }
    ]);

    // 清空answer_card和当前对话
    setAnswerCard(null);
    setChatMessages([]);

    // 发送空消息触发下一题引导
    handleChatSubmit('');
  };

  // v2.4: 继续讨论（不移动到下一题）
  const handleDiscussMore = () => {
    setAnswerCard(null);
  };

  // v2.4: 编辑答案
  const handleEditAnswer = async (newAnswer: string) => {
    // TODO: 调用API更新答案
    console.log('编辑答案:', newAnswer);
  };

  // v2.4: 开始步骤（关闭理论介绍，发送空消息触发后端生成介绍+第一题引导）
  const handleStartStep = () => {
    setShowStepIntro(false);
    handleChatSubmit('');
  };

  const phase = stepToPhase(currentStep);

  // Loading状态
  if (!isAuthenticated || !currentSession) {
    return (
      <div className="flow-light min-h-screen flex items-center justify-center" data-phase={phase}>
        <div className="animate-spin rounded-full h-12 w-12 border-2 border-[var(--bd-ui-accent)] border-t-transparent" />
      </div>
    );
  }

  // 调研问卷加载中
  if (surveyData === undefined) {
    return (
      <div className="flow-light min-h-screen flex flex-col items-center justify-center text-neutral-600" data-phase={phase}>
        <div className="animate-spin rounded-full h-12 w-12 border-2 border-[var(--bd-ui-accent)] border-t-transparent mb-4" />
        <p className="text-sm">加载调研问卷…</p>
      </div>
    );
  }

  const stepTheory = STEP_THEORIES[currentStep];
  const progressByStep = {}; // TODO: 从store获取

  // 调研问卷未完成时展示问卷
  if (surveyData !== undefined && !surveyCompleted) {
    return (
      <div className="flow-light min-h-screen flex flex-col" data-phase={phase}>
        <FlowHeader
          currentStep={currentStep}
          progressByStep={progressByStep}
          isSuperAdmin={user?.is_super_admin || false}
          onStepChange={setCurrentStep}
          onOpenDebug={handleOpenDebug}
          variant="light"
        />
        <main className="flex-1 max-w-2xl mx-auto w-full px-4 py-8 overflow-y-auto">
          <h2 className="text-xl font-semibold text-neutral-900 mb-2">调研问卷</h2>
          <p className="text-sm text-neutral-600 mb-6">
            请填写以下基本信息（选填），便于我们更好地为你提供咨询服务。填写后可跳过直接开始探索。
          </p>
          <SurveyForm
            initialData={surveyData || {}}
            loading={surveyLoading}
            submitLabel="提交并开始探索"
            showSkip
            onSubmit={async (data: SurveyData) => {
              if (!currentSession) return;
              setSurveyLoading(true);
              try {
                await surveyApi.saveForSession(currentSession.session_id, data);
                setSurveyCompleted(true);
              } catch (e) {
                setError((e as Error)?.message || '保存失败');
              } finally {
                setSurveyLoading(false);
              }
            }}
            onSkip={async () => {
              if (!currentSession) return;
              setSurveyLoading(true);
              try {
                await surveyApi.saveForSession(currentSession.session_id, {});
                setSurveyCompleted(true);
              } catch {
                setSurveyCompleted(true);
              } finally {
                setSurveyLoading(false);
              }
            }}
          />
        </main>
      </div>
    );
  }

  return (
    <div
      className="flow-light min-h-screen flex flex-col"
      data-phase={phase}
    >
      <FlowHeader
        currentStep={currentStep}
        progressByStep={progressByStep}
        isSuperAdmin={user?.is_super_admin || false}
        onStepChange={setCurrentStep}
        onOpenDebug={handleOpenDebug}
        variant="light"
      />

      <main className="flex-1 flex flex-col max-w-[720px] mx-auto w-full px-4 py-4 overflow-hidden">
        {/* v2.4: 步骤理论介绍 */}
        {showStepIntro && stepTheory && (
          <StepTheoryIntro
            stepName={stepTheory.name}
            purpose={stepTheory.purpose}
            theory={stepTheory.theory}
            onStart={handleStartStep}
            variant="light"
          />
        )}

        {!showStepIntro && (
          <>
            {/* v2.4: 已完成的题目（折叠答题卡） */}
            {completedQuestions.map((q, idx) => (
              <EnhancedAnswerCard
                key={q.questionId}
                questionContent={q.questionContent}
                userAnswer={q.answerCard?.user_answer || ''}
                aiSummary={q.answerCard?.ai_summary}
                aiAnalysis={q.answerCard?.ai_analysis}
                keyInsights={q.answerCard?.key_insights}
                onConfirm={() => {}}
                onDiscussMore={() => {}}
                isCollapsed={!q.isExpanded}
                onToggleExpand={() => {
                  setCompletedQuestions(prev => prev.map((item, i) =>
                    i === idx ? { ...item, isExpanded: !item.isExpanded } : item
                  ));
                }}
              />
            ))}

            {/* 对话区 - 严格按图片：维度标签 + 消息 + 输入 */}
            <div className="flex-1 min-h-0 flex flex-col relative max-w-[720px] mx-auto w-full">
              <div ref={chatBodyRef} className="flow-chat-body flex-1 min-h-0 overflow-y-auto">
                {/* 维度标签：● 正在探索 · 信念维度 */}
                <div className="flow-dimension-label">
                  <span className="flow-dimension-dot" />
                  正在探索 · {stepToDimensionName(currentStep)}维度
                </div>

                {questionProgress && questionProgress.total_questions > 1 && (
                  <div className="flow-progress-text text-center py-1 text-[11px]">
                    第 {questionProgress.current_index + 1} / {questionProgress.total_questions} 题
                    {questionProgress.completed_count > 0 && ` · 已完成 ${questionProgress.completed_count} 题`}
                  </div>
                )}

                {chatMessages.map((msg, idx) => (
                  <div key={msg.id || idx} className={msg.role === 'user' ? 'flow-msg-user' : ''}>
                    {msg.role === 'user' ? (
                      <div className="flow-msg-user-content">
                        <span className="whitespace-pre-wrap">{msg.content}</span>
                      </div>
                    ) : (
                      <FlowAiMessage
                        content={msg.content}
                        phase={stepToPhaseClass(currentStep)}
                        onRegenerate={() => handleRegenerate(idx)}
                      />
                    )}
                  </div>
                ))}

                {streamingContent && (
                  <FlowAiMessage
                    content={streamingContent}
                    phase={stepToPhaseClass(currentStep)}
                    streaming
                  />
                )}

                {error && (
                  <div className="flow-msg-error">
                    <div className="font-semibold text-sm mb-1">⚠ 生成失败</div>
                    {error}
                    <button
                      type="button"
                      className="flow-retry-btn"
                      onClick={() => {
                        setError('');
                        const lastUser = [...chatMessages].filter((m) => m.role === 'user').pop();
                        if (lastUser) handleChatSubmit(lastUser.content);
                      }}
                    >
                      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                        <path d="M1 4v6h6" />
                        <path d="M3.51 15a9 9 0 1 0 .49-4.11" />
                      </svg>
                      重新生成
                    </button>
                  </div>
                )}
                <div ref={chatEndRef} />
              </div>

              {/* 向下箭头：不在最底部时显示，点击滚动到底部 */}
              <button
                type="button"
                aria-label="滚动到底部"
                className={`flow-scroll-bottom-btn ${showScrollBottom ? 'visible' : ''}`}
                onClick={scrollToBottom}
                title="滚动到底部"
              >
                <ChevronDown size={20} strokeWidth={2.5} />
              </button>
            </div>

            {/* v2.4: Answer Card */}
            {answerCard && answerCard.user_answer && (
              <EnhancedAnswerCard
                questionContent={answerCard.question_content || '当前问题'}
                userAnswer={answerCard.user_answer}
                aiSummary={answerCard.ai_summary}
                aiAnalysis={answerCard.ai_analysis}
                keyInsights={answerCard.key_insights}
                onConfirm={handleConfirmAnswer}
                onDiscussMore={handleDiscussMore}
                onEdit={handleEditAnswer}
              />
            )}

            {/* v2.6: 建议标签 */}
            {!streaming && !answerCard && (
              <SuggestionTags
                suggestions={suggestions}
                onSelect={(s) => {
                  setPendingInputText(s);
                  setSuggestions([]);
                }}
                className="mb-3"
              />
            )}

            {/* 输入框 - 复刻 llmchat */}
            <div className="flex-shrink-0">
              <FlowChatInput
                onSubmit={handleChatSubmit}
                streaming={streaming}
                onStopStream={handleStopStream}
                placeholder="说说你的想法..."
                externalText={pendingInputText}
                onExternalTextConsumed={() => setPendingInputText('')}
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
