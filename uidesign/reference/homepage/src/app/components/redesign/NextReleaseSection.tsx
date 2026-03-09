import { Sparkles } from 'lucide-react';

interface NextReleaseSectionProps {
  language: 'en' | 'zh';
}

const featuresData = {
  en: {
    badge: 'Coming Soon',
    title: 'Next Release',
    subtitle: 'Exciting new features to enhance your journey',
    features: [
      {
        title: 'AI Career Coach',
        desc: 'Get personalized advice and guidance from our AI-powered career assistant',
      },
      {
        title: 'Mentor Matching',
        desc: 'Connect with industry professionals who can guide your career journey',
      },
      {
        title: 'Skills Analytics',
        desc: 'Advanced analytics to track your skill development and market demand',
      },
    ],
  },
  zh: {
    badge: '即将推出',
    title: '下一版本',
    subtitle: '激动人心的新功能，助力你的职业之旅',
    features: [
      {
        title: 'AI 职业导师',
        desc: '从我们的 AI 驱动的职业助手获得个性化建议和指导',
      },
      {
        title: '导师匹配',
        desc: '与能够指导你职业旅程的行业专业人士建立联系',
      },
      {
        title: '技能分析',
        desc: '高级分析，追踪你的技能发展和市场需求',
      },
    ],
  },
};

export function NextReleaseSection({ language }: NextReleaseSectionProps) {
  const content = featuresData[language];

  return (
    <div className="relative z-10 max-w-4xl mx-auto px-5 py-20">
      <div className="text-center mb-16">
        <div className="inline-flex items-center gap-2 bg-purple-100/60 backdrop-blur-md text-purple-700 px-5 py-2 rounded-full mb-6">
          <Sparkles className="h-4 w-4" />
          <span className="text-sm">{content.badge}</span>
        </div>

        <h2 className="text-5xl font-semibold mb-4 tracking-[0.05em]">
          {content.title}
        </h2>

        <p className="text-xl text-gray-500 font-light">
          {content.subtitle}
        </p>
      </div>

      <div className="grid md:grid-cols-3 gap-6">
        {content.features.map((feature, index) => (
          <div
            key={index}
            className="bg-white/60 backdrop-blur-[24px] border border-white/90 rounded-3xl p-8 shadow-[0_20px_40px_-10px_rgba(0,0,0,0.03)] transition-all duration-500 hover:-translate-y-2 hover:shadow-[0_30px_60px_-15px_rgba(0,0,0,0.08)] hover:bg-white/85"
          >
            <h3 className="text-xl font-medium mb-3">{feature.title}</h3>
            <p className="text-sm leading-relaxed text-gray-500 font-light">
              {feature.desc}
            </p>
          </div>
        ))}
      </div>
    </div>
  );
}
