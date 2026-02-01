'use client';

import { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { useForm, useFieldArray } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { usersApi, WorkHistoryRequest, ProjectExperienceRequest } from '@/lib/api/users';
import { useAuthStore } from '@/stores/authStore';

const profileSchema = z.object({
  gender: z.string().optional(),
  age: z.number().min(1).max(120).optional(),
  workHistories: z.array(
    z.object({
      company: z.string().optional(),
      position: z.string().optional(),
      start_date: z.string().optional(),
      end_date: z.string().optional(),
      evaluation: z.string().optional(),
      projects: z.array(
        z.object({
          name: z.string().min(1, '项目名称不能为空'),
          description: z.string().optional(),
          role: z.string().optional(),
          achievements: z.string().optional(),
        })
      ).optional(),
    })
  ).optional(),
});

type ProfileFormData = z.infer<typeof profileSchema>;

export default function ProfileSetupPage() {
  const router = useRouter();
  const { user } = useAuthStore();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string>('');

  const {
    register,
    control,
    handleSubmit,
    formState: { errors },
  } = useForm<ProfileFormData>({
    resolver: zodResolver(profileSchema),
    defaultValues: {
      workHistories: [],
    },
  });

  const { fields: workHistoryFields, append: appendWorkHistory, remove: removeWorkHistory } = useFieldArray({
    control,
    name: 'workHistories',
  });

  const onSubmit = async (data: ProfileFormData) => {
    setError('');
    setLoading(true);

    try {
      // 保存基本信息
      if (data.gender || data.age) {
        await usersApi.submitProfile({
          gender: data.gender,
          age: data.age,
        });
      }

      // 保存工作履历
      if (data.workHistories && data.workHistories.length > 0) {
        for (const workHistory of data.workHistories) {
          const workHistoryData: WorkHistoryRequest = {
            company: workHistory.company,
            position: workHistory.position,
            start_date: workHistory.start_date,
            end_date: workHistory.end_date,
            evaluation: workHistory.evaluation,
          };

          const workHistoryResponse = await usersApi.submitWorkHistory(workHistoryData);
          const workHistoryId = workHistoryResponse.data.id;

          // 保存项目经历
          if (workHistory.projects && workHistory.projects.length > 0) {
            for (const project of workHistory.projects) {
              const projectData: ProjectExperienceRequest = {
                name: project.name,
                description: project.description,
                role: project.role,
                achievements: project.achievements,
              };
              await usersApi.submitProjectExperience(workHistoryId, projectData);
            }
          }
        }
      }

      // 标记完成
      await usersApi.markProfileComplete();
      router.push('/explore');
    } catch (err: any) {
      setError(err.response?.data?.detail || '保存失败，请重试');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-primary-50 to-primary-100 py-12 px-4">
      <div className="max-w-4xl mx-auto">
        <h1 className="text-3xl font-bold text-center mb-8 text-primary-700">
          完善个人信息
        </h1>

        {error && (
          <div className="mb-6 p-4 bg-red-100 border border-red-400 text-red-700 rounded">
            {error}
          </div>
        )}

        <form onSubmit={handleSubmit(onSubmit)} className="bg-white rounded-lg shadow-lg p-8 space-y-6">
          {/* 基本信息 */}
          <div className="space-y-4">
            <h2 className="text-xl font-semibold text-gray-700">基本信息</h2>
            
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label htmlFor="gender" className="block text-sm font-medium text-gray-700 mb-1">
                  性别
                </label>
                <select
                  {...register('gender')}
                  id="gender"
                  className="w-full px-4 py-2 border border-gray-300 rounded-md focus:ring-primary-500 focus:border-primary-500"
                >
                  <option value="">请选择</option>
                  <option value="male">男</option>
                  <option value="female">女</option>
                  <option value="other">其他</option>
                </select>
              </div>

              <div>
                <label htmlFor="age" className="block text-sm font-medium text-gray-700 mb-1">
                  年龄
                </label>
                <input
                  {...register('age', { valueAsNumber: true })}
                  type="number"
                  id="age"
                  min="1"
                  max="120"
                  className="w-full px-4 py-2 border border-gray-300 rounded-md focus:ring-primary-500 focus:border-primary-500"
                />
                {errors.age && (
                  <p className="mt-1 text-sm text-red-600">{errors.age.message}</p>
                )}
              </div>
            </div>
          </div>

          {/* 工作履历 */}
          <div className="space-y-4">
            <div className="flex justify-between items-center">
              <h2 className="text-xl font-semibold text-gray-700">工作履历</h2>
              <button
                type="button"
                onClick={() => appendWorkHistory({})}
                className="px-4 py-2 bg-primary-600 text-white rounded-md hover:bg-primary-700"
              >
                添加工作经历
              </button>
            </div>

            {workHistoryFields.map((field, index) => (
              <div key={field.id} className="border border-gray-200 rounded-lg p-4 space-y-4">
                <div className="flex justify-between items-center">
                  <h3 className="font-medium text-gray-700">工作经历 {index + 1}</h3>
                  <button
                    type="button"
                    onClick={() => removeWorkHistory(index)}
                    className="text-red-600 hover:text-red-700"
                  >
                    删除
                  </button>
                </div>

                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1">
                      公司名称
                    </label>
                    <input
                      {...register(`workHistories.${index}.company`)}
                      className="w-full px-4 py-2 border border-gray-300 rounded-md focus:ring-primary-500 focus:border-primary-500"
                    />
                  </div>

                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1">
                      职位
                    </label>
                    <input
                      {...register(`workHistories.${index}.position`)}
                      className="w-full px-4 py-2 border border-gray-300 rounded-md focus:ring-primary-500 focus:border-primary-500"
                    />
                  </div>
                </div>

                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1">
                      开始日期
                    </label>
                    <input
                      {...register(`workHistories.${index}.start_date`)}
                      type="date"
                      className="w-full px-4 py-2 border border-gray-300 rounded-md focus:ring-primary-500 focus:border-primary-500"
                    />
                  </div>

                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1">
                      结束日期（留空表示当前工作）
                    </label>
                    <input
                      {...register(`workHistories.${index}.end_date`)}
                      type="date"
                      className="w-full px-4 py-2 border border-gray-300 rounded-md focus:ring-primary-500 focus:border-primary-500"
                    />
                  </div>
                </div>

                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">
                    工作评价
                  </label>
                  <textarea
                    {...register(`workHistories.${index}.evaluation`)}
                    rows={3}
                    className="w-full px-4 py-2 border border-gray-300 rounded-md focus:ring-primary-500 focus:border-primary-500"
                    placeholder="请描述您在这份工作中的感受、成就、挑战等..."
                  />
                </div>
              </div>
            ))}
          </div>

          <div className="flex justify-end space-x-4">
            <button
              type="button"
              onClick={() => router.push('/explore')}
              className="px-6 py-2 border border-gray-300 rounded-md text-gray-700 hover:bg-gray-50"
            >
              跳过
            </button>
            <button
              type="submit"
              disabled={loading}
              className="px-6 py-2 bg-primary-600 text-white rounded-md hover:bg-primary-700 focus:outline-none focus:ring-2 focus:ring-primary-500 focus:ring-offset-2 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {loading ? '保存中...' : '保存并继续'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
