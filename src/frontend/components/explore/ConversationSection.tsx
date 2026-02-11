'use client';

import ConversationThread, { type ConversationItem } from './ConversationThread';
import { type AnswerChangeType } from '@/lib/api/answers';

interface ConversationSectionProps {
  conversationItems: ConversationItem[];
  streamingContent: string;
  editingAnswerId: string | null;
  editContent: string;
  editChangeType: AnswerChangeType;
  savingEdit: boolean;
  onStartEdit: (answerId: string) => void;
  onCancelEdit: () => void;
  onSaveEdit: (answerId: string, content: string, changeType: AnswerChangeType) => Promise<void>;
  onEditContentChange: (content: string) => void;
  onEditChangeTypeChange: (type: AnswerChangeType) => void;
}

export default function ConversationSection({
  conversationItems,
  streamingContent,
  editingAnswerId,
  editContent,
  editChangeType,
  savingEdit,
  onStartEdit,
  onCancelEdit,
  onSaveEdit,
  onEditContentChange,
  onEditChangeTypeChange,
}: ConversationSectionProps) {
  return (
    <div className="flex-1 min-h-0 flex flex-col rounded-xl border border-white/10 bg-slate-800/30 overflow-hidden">
      <div className="flex h-full gap-4">
        <div className="flex-1 flex flex-col">
          <ConversationThread
            items={conversationItems}
            streamingContent={streamingContent}
            editingAnswerId={editingAnswerId}
            onStartEdit={onStartEdit}
            onCancelEdit={onCancelEdit}
            onSaveEdit={onSaveEdit}
            editContent={editContent}
            editChangeType={editChangeType}
            onEditContentChange={onEditContentChange}
            onEditChangeTypeChange={onEditChangeTypeChange}
            savingEdit={savingEdit}
          />
        </div>
      </div>
    </div>
  );
}
