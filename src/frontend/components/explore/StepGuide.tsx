'use client';

import { motion } from 'framer-motion';

interface Step {
  id: string;
  name: string;
  order: number;
}

interface StepGuideProps {
  steps: Step[];
  currentStep: string;
  onStepChange: (step: string) => void;
}

export default function StepGuide({ steps, currentStep, onStepChange }: StepGuideProps) {
  return (
    <div className="bg-white rounded-lg shadow-lg p-6">
      <h2 className="text-xl font-semibold text-gray-700 mb-4">探索步骤</h2>
      <div className="space-y-3">
        {steps.map((step, index) => {
          const isActive = step.id === currentStep;
          const isCompleted = steps.findIndex(s => s.id === currentStep) > index;

          return (
            <motion.div
              key={step.id}
              onClick={() => onStepChange(step.id)}
              className={`
                p-4 rounded-lg cursor-pointer transition-all
                ${isActive 
                  ? 'bg-primary-100 border-2 border-primary-500' 
                  : isCompleted
                  ? 'bg-green-50 border-2 border-green-300'
                  : 'bg-gray-50 border-2 border-gray-200'
                }
              `}
              whileHover={{ scale: 1.02 }}
              whileTap={{ scale: 0.98 }}
            >
              <div className="flex items-center space-x-3">
                <div className={`
                  w-8 h-8 rounded-full flex items-center justify-center font-bold
                  ${isActive 
                    ? 'bg-primary-600 text-white' 
                    : isCompleted
                    ? 'bg-green-500 text-white'
                    : 'bg-gray-300 text-gray-600'
                  }
                `}>
                  {isCompleted ? '✓' : step.order}
                </div>
                <div className="flex-1">
                  <p className={`font-medium ${isActive ? 'text-primary-700' : 'text-gray-700'}`}>
                    {step.name}
                  </p>
                </div>
              </div>
            </motion.div>
          );
        })}
      </div>
    </div>
  );
}
