import { LandingPage } from './components/LandingPage';
import { useState } from 'react';

export default function Root() {
  const [language] = useState<'en' | 'zh'>('zh');

  return <LandingPage language={language} />;
}