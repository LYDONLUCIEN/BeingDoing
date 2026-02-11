import type { StepItem } from '@/components/explore/StepProgressBar';
import type { Answer } from '@/lib/api/answers';
import type { Message } from '@/lib/api/chat';
import type { ConversationItem } from '@/components/explore/ConversationThread';

export const FLOW_STEPS: StepItem[] = [
  { id: 'values_exploration', name: '探索重要的事（价值观）', description: '了解你认为重要的事', order: 1 },
  { id: 'strengths_exploration', name: '探索擅长的事（才能）', description: '了解你的优势和才能', order: 2 },
  { id: 'interests_exploration', name: '探索喜欢的事（热情）', description: '了解你的兴趣和热情', order: 3 },
  { id: 'combination', name: '组合分析', description: '将三个要素进行组合分析', order: 4 },
  { id: 'refinement', name: '精炼结果', description: '精炼和验证最终结果', order: 5 },
];

export function mergeConversationItems(
  answers: Answer[],
  messages: Message[],
  questionMap: Record<number, string>
): ConversationItem[] {
  const answerItems: ConversationItem[] = answers.map((a) => ({
    type: 'answer',
    answer: a,
    questionContent: a.question_id ? questionMap[a.question_id] : undefined,
  }));
  const chatItems: ConversationItem[] = messages.map((m) => ({ type: 'chat', message: m }));
  const all: ConversationItem[] = [...answerItems, ...chatItems];
  all.sort((a, b) => {
    const timeA = a.type === 'answer' ? a.answer.created_at : a.message.created_at;
    const timeB = b.type === 'answer' ? b.answer.created_at : b.message.created_at;
    return new Date(timeA).getTime() - new Date(timeB).getTime();
  });
  return all;
}
