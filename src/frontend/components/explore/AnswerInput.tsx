'use client';

import { useState } from 'react';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';

const answerSchema = z.object({
  content: z.string().min(10, '回答至少需要10个字符'),
});

type AnswerFormData = z.infer<typeof answerSchema>;

interface AnswerInputProps {
  currentQuestion: any;
  onSubmit: (content: string, questionId?: number) => void;
  loading: boolean;
}

export default function AnswerInput({ currentQuestion, onSubmit, loading }: AnswerInputProps) {
  const {
    register,
    handleSubmit,
    reset,
    formState: { errors },
  } = useForm<AnswerFormData>({
    resolver: zodResolver(answerSchema),
  });

  const onFormSubmit = (data: AnswerFormData) => {
    onSubmit(data.content, currentQuestion?.id);
    reset();
  };

  return (
    <div className="bg-white rounded-lg shadow-lg p-6">
      <h2 className="text-xl font-semibold text-gray-700 mb-4">回答</h2>

      {currentQuestion ? (
        <form onSubmit={handleSubmit(onFormSubmit)} className="space-y-4">
          <div>
            <label htmlFor="content" className="block text-sm font-medium text-gray-700 mb-2">
              请回答以下问题：
            </label>
            <p className="text-sm text-gray-600 mb-3">{currentQuestion.content}</p>
            <textarea
              {...register('content')}
              id="content"
              rows={6}
              className="w-full px-4 py-2 border border-gray-300 rounded-md focus:ring-primary-500 focus:border-primary-500"
              placeholder="请详细描述你的想法..."
            />
            {errors.content && (
              <p className="mt-1 text-sm text-red-600">{errors.content.message}</p>
            )}
          </div>

          <button
            type="submit"
            disabled={loading}
            className="w-full py-2 px-4 bg-primary-600 text-white rounded-md hover:bg-primary-700 focus:outline-none focus:ring-2 focus:ring-primary-500 focus:ring-offset-2 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {loading ? '提交中...' : '提交回答'}
          </button>
        </form>
      ) : (
        <div className="text-center py-8 text-gray-500">
          <p>请先选择一个问题</p>
        </div>
      )}
    </div>
  );
}
