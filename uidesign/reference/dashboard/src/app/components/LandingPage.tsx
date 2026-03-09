interface LandingPageProps {
  language: 'en' | 'zh';
}

export function LandingPage({ language }: LandingPageProps) {
  const text = {
    en: {
      welcome: 'Welcome to Careering',
      subtitle: 'Your personal career development companion',
      description: 'Discover your values, strengths, passion, and purpose. Build a comprehensive career development plan tailored to your unique journey.',
      features: {
        feature1: 'Guided Career Exploration',
        feature1Desc: 'Step-by-step journey through self-discovery',
        feature2: 'Comprehensive Reports',
        feature2Desc: 'Detailed insights and actionable plans',
        feature3: 'Track Your Progress',
        feature3Desc: 'Visual path to monitor your growth',
      },
      cta: 'Get Started',
    },
    zh: {
      welcome: '欢迎来到职引',
      subtitle: '您的个人职业发展伙伴',
      description: '发现您的底色、天赋、热忱和航向。为您的独特旅程量身定制全面的职业发展计划。',
      features: {
        feature1: '引导式职业探索',
        feature1Desc: '通过自我发现的逐步旅程',
        feature2: '全面的报告',
        feature2Desc: '详细的见解和可行的计划',
        feature3: '追踪您的进度',
        feature3Desc: '可视化路径来监控您的成长',
      },
      cta: '开始探索',
    },
  };

  const t = text[language];

  return (
    <div className="min-h-screen flex items-center justify-center px-6">
      <div className="max-w-4xl w-full text-center">
        <h1 className="text-6xl font-bold text-[#1d1d1f] mb-4">{t.welcome}</h1>
        <p className="text-xl text-gray-600 mb-3">{t.subtitle}</p>
        <p className="text-lg text-gray-500 mb-12 max-w-2xl mx-auto">{t.description}</p>

        {/* Features */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-12">
          <div className="bg-white/60 backdrop-blur-lg border border-gray-200/50 rounded-2xl p-6">
            <div className="w-12 h-12 rounded-full bg-gradient-to-br from-[#A2C2E8] to-[#B5D8C6] mx-auto mb-4" />
            <h3 className="font-medium text-[#1d1d1f] mb-2">{t.features.feature1}</h3>
            <p className="text-sm text-gray-600">{t.features.feature1Desc}</p>
          </div>
          <div className="bg-white/60 backdrop-blur-lg border border-gray-200/50 rounded-2xl p-6">
            <div className="w-12 h-12 rounded-full bg-gradient-to-br from-[#F4B3B3] to-[#FDE093] mx-auto mb-4" />
            <h3 className="font-medium text-[#1d1d1f] mb-2">{t.features.feature2}</h3>
            <p className="text-sm text-gray-600">{t.features.feature2Desc}</p>
          </div>
          <div className="bg-white/60 backdrop-blur-lg border border-gray-200/50 rounded-2xl p-6">
            <div className="w-12 h-12 rounded-full bg-gradient-to-br from-[#B5D8C6] to-[#A2C2E8] mx-auto mb-4" />
            <h3 className="font-medium text-[#1d1d1f] mb-2">{t.features.feature3}</h3>
            <p className="text-sm text-gray-600">{t.features.feature3Desc}</p>
          </div>
        </div>

        {/* CTA Button */}
        <button className="px-8 py-4 bg-black text-white rounded-xl text-lg font-medium hover:bg-gray-800 transition-colors shadow-lg hover:shadow-xl">
          {t.cta}
        </button>
      </div>
    </div>
  );
}
