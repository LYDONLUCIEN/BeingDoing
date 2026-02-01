'use client';

interface Progress {
  step: string;
  completed_count: number;
  total_count: number;
  percentage: number;
}

interface ProgressDisplayProps {
  progresses: Record<string, Progress>;
  currentStep: string;
}

const STEP_NAMES: Record<string, string> = {
  values_exploration: '价值观探索',
  strengths_exploration: '才能探索',
  interests_exploration: '兴趣探索',
  combination: '组合分析',
  refinement: '精炼结果',
};

export default function ProgressDisplay({ progresses, currentStep }: ProgressDisplayProps) {
  const currentProgress = progresses[currentStep];

  // 计算总体进度
  const totalSteps = Object.keys(progresses).length;
  const completedSteps = Object.values(progresses).filter(p => p.percentage === 100).length;
  const overallPercentage = totalSteps > 0 ? Math.round((completedSteps / totalSteps) * 100) : 0;

  return (
    <div className="bg-white rounded-lg shadow-lg p-6">
      <h2 className="text-xl font-semibold text-gray-700 mb-4">探索进度</h2>

      {/* 总体进度 */}
      <div className="mb-6">
        <div className="flex justify-between items-center mb-2">
          <span className="text-sm font-medium text-gray-700">总体进度</span>
          <span className="text-sm text-gray-600">{overallPercentage}%</span>
        </div>
        <div className="w-full bg-gray-200 rounded-full h-2">
          <div
            className="bg-primary-600 h-2 rounded-full transition-all"
            style={{ width: `${overallPercentage}%` }}
          ></div>
        </div>
      </div>

      {/* 当前步骤进度 */}
      {currentProgress && (
        <div>
          <div className="flex justify-between items-center mb-2">
            <span className="text-sm font-medium text-gray-700">
              {STEP_NAMES[currentStep] || currentStep}
            </span>
            <span className="text-sm text-gray-600">
              {currentProgress.completed_count} / {currentProgress.total_count}
            </span>
          </div>
          <div className="w-full bg-gray-200 rounded-full h-2">
            <div
              className="bg-green-500 h-2 rounded-full transition-all"
              style={{ width: `${currentProgress.percentage}%` }}
            ></div>
          </div>
        </div>
      )}

      {/* 所有步骤进度 */}
      <div className="mt-6 space-y-3">
        {Object.entries(progresses).map(([step, progress]) => (
          <div key={step} className="text-sm">
            <div className="flex justify-between items-center mb-1">
              <span className="text-gray-600">{STEP_NAMES[step] || step}</span>
              <span className="text-gray-500">{progress.percentage}%</span>
            </div>
            <div className="w-full bg-gray-200 rounded-full h-1">
              <div
                className={`h-1 rounded-full transition-all ${
                  progress.percentage === 100 ? 'bg-green-500' : 'bg-primary-400'
                }`}
                style={{ width: `${progress.percentage}%` }}
              ></div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
