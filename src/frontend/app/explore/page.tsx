'use client';

import { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { useAuthStore } from '@/stores/authStore';
import { useSessionStore } from '@/stores/sessionStore';
import { useProgressStore } from '@/stores/progressStore';
import { sessionsApi } from '@/lib/api/sessions';
import { questionsApi } from '@/lib/api/questions';
import { answersApi } from '@/lib/api/answers';
import { chatApi } from '@/lib/api/chat';
import { formulaApi } from '@/lib/api/formula';
import StepGuide from '@/components/explore/StepGuide';
import QuestionDisplay from '@/components/explore/QuestionDisplay';
import AnswerInput from '@/components/explore/AnswerInput';
import ChatAssistant from '@/components/explore/ChatAssistant';
import ProgressDisplay from '@/components/explore/ProgressDisplay';

const EXPLORATION_STEPS = [
  { id: 'values_exploration', name: '探索重要的事（价值观）', order: 1 },
  { id: 'strengths_exploration', name: '探索擅长的事（才能）', order: 2 },
  { id: 'interests_exploration', name: '探索喜欢的事（热情）', order: 3 },
  { id: 'combination', name: '组合分析', order: 4 },
  { id: 'refinement', name: '精炼结果', order: 5 },
];

export default function ExplorePage() {
  const router = useRouter();
  const { isAuthenticated, user } = useAuthStore();
  const { currentSession, setCurrentSession } = useSessionStore();
  const { progresses, setProgress } = useProgressStore();
  
  const [currentStep, setCurrentStep] = useState<string>('values_exploration');
  const [currentQuestion, setCurrentQuestion] = useState<any>(null);
  const [guideQuestions, setGuideQuestions] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string>('');

  useEffect(() => {
    if (!isAuthenticated) {
      router.push('/auth/login');
      return;
    }

    initializeSession();
  }, [isAuthenticated]);

  const initializeSession = async () => {
    try {
      let session = currentSession;
      
      if (!session) {
        const response = await sessionsApi.create({
          current_step: currentStep,
        });
        session = response.data;
        setCurrentSession(session);
      } else {
        setCurrentStep(session.current_step);
      }

      await loadGuideQuestions(session.current_step);
    } catch (err: any) {
      setError(err.response?.data?.detail || '初始化失败');
    }
  };

  const loadGuideQuestions = async (step: string) => {
    try {
      const response = await questionsApi.getGuideQuestions(step, 5);
      setGuideQuestions(response.data.questions);
    } catch (err: any) {
      console.error('加载引导问题失败:', err);
    }
  };

  const handleQuestionSelect = (question: any) => {
    setCurrentQuestion(question);
  };

  const handleAnswerSubmit = async (content: string, questionId?: number) => {
    if (!currentSession) return;

    setLoading(true);
    setError('');

    try {
      // 保存回答
      await answersApi.submit({
        session_id: currentSession.session_id,
        category: currentStep.split('_')[0], // values, strengths, interests
        content,
        question_id: questionId,
      });

      // 更新进度
      const progressResponse = await sessionsApi.updateProgress(
        currentSession.session_id,
        currentStep,
        1, // completed_count 增量
        undefined // total_count 保持不变
      );

      if (progressResponse.data) {
        setProgress(currentStep, {
          step: currentStep,
          completed_count: progressResponse.data.completed_count,
          total_count: progressResponse.data.total_count,
          percentage: progressResponse.data.percentage,
        });
      }

      // 清空当前问题
      setCurrentQuestion(null);
    } catch (err: any) {
      setError(err.response?.data?.detail || '提交失败');
    } finally {
      setLoading(false);
    }
  };

  const handleStepChange = async (step: string) => {
    setCurrentStep(step);
    if (currentSession) {
      await loadGuideQuestions(step);
    }
  };

  if (!isAuthenticated || !currentSession) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-primary-600"></div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-primary-50 to-primary-100">
      <div className="container mx-auto px-4 py-8">
        {/* 头部 */}
        <div className="mb-8">
          <h1 className="text-3xl font-bold text-primary-700 mb-2">
            找到想做的事
          </h1>
          <p className="text-gray-600">
            通过探索你的价值观、才能和兴趣，找到真正想做的事
          </p>
        </div>

        {error && (
          <div className="mb-6 p-4 bg-red-100 border border-red-400 text-red-700 rounded">
            {error}
          </div>
        )}

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* 左侧：步骤引导和进度 */}
          <div className="lg:col-span-1 space-y-6">
            <StepGuide
              steps={EXPLORATION_STEPS}
              currentStep={currentStep}
              onStepChange={handleStepChange}
            />
            <ProgressDisplay
              progresses={progresses}
              currentStep={currentStep}
            />
          </div>

          {/* 中间：问题和回答 */}
          <div className="lg:col-span-1 space-y-6">
            <QuestionDisplay
              currentQuestion={currentQuestion}
              guideQuestions={guideQuestions}
              onQuestionSelect={handleQuestionSelect}
              currentStep={currentStep}
            />
            <AnswerInput
              currentQuestion={currentQuestion}
              onSubmit={handleAnswerSubmit}
              loading={loading}
            />
          </div>

          {/* 右侧：对话助手 */}
          <div className="lg:col-span-1">
            <ChatAssistant
              sessionId={currentSession.session_id}
              currentStep={currentStep}
            />
          </div>
        </div>
      </div>
    </div>
  );
}
