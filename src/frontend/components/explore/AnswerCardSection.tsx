'use client';

import AnswerCard from './AnswerCard';
import { type AnswerCardMeta } from '@/lib/api/chat';
import { type Answer } from '@/lib/api/answers';
import { FLOW_STEPS } from '@/lib/constants';

interface AnswerCardSectionProps {
  answerCard: AnswerCardMeta | null;
  currentQuestion: any;
  currentStep: string;
  answers: Answer[];
  currentSessionId: string;
  onNext: (answerId: string, questionTitle: string, userAnswer: string, aiAnalysis?: string) => void;
  onDiscussMore: () => void;
  onSubmitEdit: (newText: string) => Promise<void>;
}

export default function AnswerCardSection({
  answerCard,
  currentQuestion,
  currentStep,
  answers,
  currentSessionId,
  onNext,
  onDiscussMore,
  onSubmitEdit,
}: AnswerCardSectionProps) {
  if (!answerCard?.user_answer) return null;

  const questionTitle =
    currentQuestion?.content ||
    FLOW_STEPS.find((s) => s.id === currentStep)?.name ||
    '当前问题';

  const handleNext = () => {
    const latestAnswer = [...answers].sort(
      (a, b) =>
        new Date(b.updated_at || b.created_at).getTime() -
        new Date(a.updated_at || a.created_at).getTime()
    )[0];

    if (latestAnswer) {
      onNext(
        latestAnswer.id,
        questionTitle,
        answerCard.user_answer || '',
        answerCard.ai_analysis
      );
    }
  };

  return (
    <div className="mt-3">
      <AnswerCard
        questionTitle={questionTitle}
        aiAnalysis={answerCard.ai_analysis}
        userAnswer={answerCard.user_answer}
        onNext={handleNext}
        onDiscussMore={onDiscussMore}
        onSubmitEdit={onSubmitEdit}
        canDiscuss={true}
      />
    </div>
  );
}
