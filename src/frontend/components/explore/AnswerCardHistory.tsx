'use client';

import AnswerCard from './AnswerCard';

interface HistoryCard {
  id: string;
  questionTitle: string;
  userAnswer: string;
  aiAnalysis?: string;
}

interface AnswerCardHistoryProps {
  history: HistoryCard[];
  onSubmitEdit: (cardId: string, newText: string) => Promise<void>;
}

export default function AnswerCardHistory({ history, onSubmitEdit }: AnswerCardHistoryProps) {
  if (history.length === 0) return null;

  return (
    <aside className="w-72 flex-shrink-0 overflow-y-auto space-y-2 border-l border-white/10 pl-3">
      {history.map((card) => (
        <AnswerCard
          key={card.id}
          questionTitle={card.questionTitle}
          aiAnalysis={card.aiAnalysis}
          userAnswer={card.userAnswer}
          onNext={() => {}}
          onDiscussMore={() => {}}
          onSubmitEdit={async (newText: string) => {
            await onSubmitEdit(card.id, newText);
          }}
          canDiscuss={false}
          defaultCollapsed
          showNext={false}
        />
      ))}
    </aside>
  );
}
