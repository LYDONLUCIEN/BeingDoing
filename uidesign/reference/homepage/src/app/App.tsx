import { useState } from 'react';
import { TopMenu } from './components/redesign/TopMenu';
import { BackgroundLayers } from './components/BackgroundLayers';
import { HeroSection } from './components/redesign/HeroSection';
import { MilestonesGrid } from './components/redesign/MilestonesGrid';
import { NextReleaseSection } from './components/redesign/NextReleaseSection';
import { TestimonialsSection } from './components/redesign/TestimonialsSection';
import { Footer } from './components/redesign/Footer';

export default function App() {
  const [language, setLanguage] = useState<'en' | 'zh'>('en');

  return (
    <div className="min-h-screen bg-[#faf9f8] text-[#1d1d1f] overflow-x-hidden">
      <TopMenu language={language} onLanguageChange={setLanguage} />
      <BackgroundLayers language={language} />
      
      <div className="relative z-10">
        <HeroSection language={language} />
        <MilestonesGrid language={language} />
        <NextReleaseSection language={language} />
        <TestimonialsSection language={language} />
        <Footer language={language} />
      </div>
    </div>
  );
}
