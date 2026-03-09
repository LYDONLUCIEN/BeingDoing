import { ArrowDown, Target } from 'lucide-react';

interface MilestonesGridProps {
  language: 'en' | 'zh';
}

const milestonesData = {
  en: [
    {
      en: 'Step 1',
      title: 'Clarify Your Values',
      desc: 'Identify the core values that matter most to you. Understand the root of past job dissatisfaction and establish the right criteria to evaluate future choices.',
      color: 'blue',
      borderColor: '#4A90E2',
    },
    {
      en: 'Step 2',
      title: 'Discover Your Strengths',
      desc: 'Uncover your unique talents and what you naturally excel at. See the distinct advantages that make you valuable.',
      color: 'green',
      borderColor: '#50E3C2',
    },
    {
      en: 'Step 3',
      title: 'Find Your "Flow"',
      desc: 'Explore the activities and topics that energize you. Identify passions that can sustain long-term motivation.',
      color: 'red',
      borderColor: '#FF5A5F',
    },
    {
      en: 'Step 4',
      title: 'Define Your Purpose',
      desc: 'Connect your future work to a larger mission. Identify the social value or impact your desired work can create.',
      color: 'yellow',
      borderColor: '#F5A623',
    },
  ],
  zh: [
    {
      en: '第一步',
      title: '明确你的价值观',
      desc: '找出对你最重要的核心价值观���了解过去工作不满的根源，建立评估未来选择的正确标准。',
      color: 'blue',
      borderColor: '#4A90E2',
    },
    {
      en: '第二步',
      title: '发现你的优势',
      desc: '揭示你独特的天赋和自然擅长的事情。看到让你有价值的独特优势。',
      color: 'green',
      borderColor: '#50E3C2',
    },
    {
      en: '第三步',
      title: '找到你的"心流"',
      desc: '探索能给你带来活力的活动和话题。找到能够维持长期动力的热情所在。',
      color: 'red',
      borderColor: '#FF5A5F',
    },
    {
      en: '第四步',
      title: '定义你的使命',
      desc: '将未来的工作与更大的使命联系起来。明确你期望的工作能创造的社会价值或影响。',
      color: 'yellow',
      borderColor: '#F5A623',
    },
  ],
};

export function MilestonesGrid({ language }: MilestonesGridProps) {
  const milestones = milestonesData[language];
  const badgeText = language === 'en' ? 'Your Direction' : '你的方向';

  return (
    <div className="relative z-10 max-w-5xl mx-auto px-5 mt-20 mb-20">
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6 relative">
        {milestones.map((milestone, index) => (
          <div key={index} className="relative">
            <div
              className="bg-white/60 backdrop-blur-[24px] border border-white/90 rounded-3xl p-10 px-6 text-left shadow-[0_20px_40px_-10px_rgba(0,0,0,0.03)] transition-all duration-500 hover:-translate-y-2 hover:scale-[1.02] hover:shadow-[0_30px_60px_-15px_rgba(0,0,0,0.08)] hover:bg-white/85 relative overflow-hidden h-full flex flex-col"
            >
              <div
                className="absolute top-0 left-0 right-0 h-1 opacity-90"
                style={{ background: milestone.borderColor }}
              ></div>

              <div className="uppercase tracking-[0.1em] text-xs text-gray-500 mb-2">
                {milestone.en}
              </div>

              <h3 className="text-xl font-medium mb-4">
                {milestone.title}
              </h3>

              <p className="text-sm leading-relaxed text-gray-500 font-light flex-grow">
                {milestone.desc}
              </p>
            </div>
          </div>
        ))}
      </div>

      {/* Path to "Your Direction" */}
      <div className="flex flex-col items-center mt-16">
        {/* Convergence Lines */}
        <div className="relative w-full max-w-3xl h-24 mb-4">
          <svg className="w-full h-full" viewBox="0 0 600 100" preserveAspectRatio="xMidYMid meet">
            {/* Four lines converging to center */}
            <path d="M 75 0 Q 150 50 300 80" stroke="#4A90E2" strokeWidth="2" fill="none" strokeDasharray="5,5" opacity="0.6"/>
            <path d="M 225 0 Q 250 50 300 80" stroke="#50E3C2" strokeWidth="2" fill="none" strokeDasharray="5,5" opacity="0.6"/>
            <path d="M 375 0 Q 350 50 300 80" stroke="#FF5A5F" strokeWidth="2" fill="none" strokeDasharray="5,5" opacity="0.6"/>
            <path d="M 525 0 Q 450 50 300 80" stroke="#F5A623" strokeWidth="2" fill="none" strokeDasharray="5,5" opacity="0.6"/>
          </svg>
        </div>

        {/* Down Arrow */}
        <ArrowDown className="h-8 w-8 text-gray-400 mb-4 animate-bounce" />
        
        {/* Badge */}
        <div className="bg-gradient-to-br from-purple-500 to-blue-600 text-white px-10 py-5 rounded-full shadow-2xl flex items-center gap-3 transform hover:scale-105 transition-transform">
          <Target className="h-6 w-6" />
          <span className="font-semibold text-xl">{badgeText}</span>
        </div>
      </div>
    </div>
  );
}