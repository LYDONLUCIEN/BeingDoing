import { ArrowRight } from 'lucide-react';

interface HeroSectionProps {
  language: 'en' | 'zh';
}

export function HeroSection({ language }: HeroSectionProps) {
  const text = {
    en: {
      title: 'Careering',
      slogan: 'All passions deserve to be careers.',
      button: 'Start Exploring',
    },
    zh: {
      title: '职引',
      slogan: '所有热爱都值得成为事业。',
      button: '开始探索',
    },
  };

  const t = text[language];

  return (
    <section className="relative z-10 max-w-4xl mx-auto px-5 pt-[20vh] pb-20 flex flex-col items-center text-center">
      <h1 className="text-[64px] font-semibold mb-6 tracking-[0.05em] leading-none">
        {t.title}
      </h1>

      <h2 className="text-2xl text-gray-500 mb-[60px] font-light tracking-[0.05em]">
        {t.slogan}
      </h2>

      <button className="bg-[#1d1d1f] text-white border-none px-12 py-[18px] text-base rounded-full cursor-pointer shadow-[0_20px_40px_-10px_rgba(0,0,0,0.2)] transition-all duration-[400ms] hover:scale-95 hover:translate-y-[2px] hover:shadow-[0_10px_20px_-5px_rgba(0,0,0,0.15)] hover:bg-[#333] flex items-center gap-2 group">
        {t.button}
        <ArrowRight className="h-5 w-5 group-hover:translate-x-1 transition-transform" />
      </button>
    </section>
  );
}
