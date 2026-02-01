'use client';

import { useEffect, useState } from 'react';
import { questionsApi } from '@/lib/api/questions';

interface Question {
  id: number;
  category: string;
  question_number: number;
  content: string;
  is_starred: boolean;
}

interface QuestionDisplayProps {
  currentQuestion: Question | null;
  guideQuestions: Question[];
  onQuestionSelect: (question: Question) => void;
  currentStep: string;
}

export default function QuestionDisplay({
  currentQuestion,
  guideQuestions,
  onQuestionSelect,
  currentStep,
}: QuestionDisplayProps) {
  const [allQuestions, setAllQuestions] = useState<Question[]>([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    loadQuestions();
  }, [currentStep]);

  const loadQuestions = async () => {
    setLoading(true);
    try {
      const category = currentStep.split('_')[0]; // values, strengths, interests
      const response = await questionsApi.getQuestions(category);
      setAllQuestions(response.data.questions);
    } catch (err) {
      console.error('加载问题失败:', err);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="bg-white rounded-lg shadow-lg p-6 space-y-4">
      <h2 className="text-xl font-semibold text-gray-700">问题</h2>

      {/* 当前问题 */}
      {currentQuestion && (
        <div className="p-4 bg-primary-50 border-2 border-primary-300 rounded-lg">
          <div className="flex items-start space-x-2">
            <span className="text-primary-600 font-bold">Q{currentQuestion.question_number}</span>
            <p className="flex-1 text-gray-800">{currentQuestion.content}</p>
          </div>
        </div>
      )}

      {/* 引导问题 */}
      <div>
        <h3 className="text-sm font-medium text-gray-600 mb-2">推荐问题</h3>
        <div className="space-y-2">
          {guideQuestions.map((question) => (
            <button
              key={question.id}
              onClick={() => onQuestionSelect(question)}
              className={`
                w-full text-left p-3 rounded-lg border-2 transition-all
                ${currentQuestion?.id === question.id
                  ? 'border-primary-500 bg-primary-50'
                  : 'border-gray-200 bg-gray-50 hover:border-primary-300 hover:bg-primary-50'
                }
              `}
            >
              <div className="flex items-start space-x-2">
                {question.is_starred && (
                  <span className="text-yellow-500">⭐</span>
                )}
                <span className="text-sm text-gray-700">{question.content}</span>
              </div>
            </button>
          ))}
        </div>
      </div>

      {/* 所有问题列表 */}
      {allQuestions.length > 0 && (
        <div>
          <h3 className="text-sm font-medium text-gray-600 mb-2">所有问题</h3>
          <div className="max-h-64 overflow-y-auto space-y-2">
            {allQuestions.map((question) => (
              <button
                key={question.id}
                onClick={() => onQuestionSelect(question)}
                className={`
                  w-full text-left p-2 rounded border transition-all text-sm
                  ${currentQuestion?.id === question.id
                    ? 'border-primary-500 bg-primary-50'
                    : 'border-gray-200 bg-white hover:border-primary-300'
                  }
                `}
              >
                <span className="text-gray-700">
                  {question.is_starred && '⭐ '}
                  Q{question.question_number}: {question.content}
                </span>
              </button>
            ))}
          </div>
        </div>
      )}

      {loading && (
        <div className="text-center py-4">
          <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-primary-600 mx-auto"></div>
        </div>
      )}
    </div>
  );
}
