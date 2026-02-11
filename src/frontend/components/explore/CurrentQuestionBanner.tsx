'use client';

interface Question {
  id: number;
  category: string;
  question_number: number;
  content: string;
  is_starred?: boolean;
}

interface CurrentQuestionBannerProps {
  question: Question | null;
}

export default function CurrentQuestionBanner({ question }: CurrentQuestionBannerProps) {
  if (!question) {
    return (
      <div className="rounded-xl border border-white/10 bg-white/5 px-5 py-4 text-white/50 text-center">
        选择或等待当前步骤的一个问题
      </div>
    );
  }

  return (
    <div className="rounded-xl border border-primary-400/50 bg-primary-500/10 px-5 py-4 shadow-lg shadow-primary-500/10">
      <p className="text-primary-200/90 text-xs font-medium uppercase tracking-wider mb-1">
        当前问题
      </p>
      <p className="text-white text-lg font-medium leading-snug">
        {question.content}
      </p>
    </div>
  );
}
