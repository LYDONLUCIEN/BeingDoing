import { Outlet } from 'react-router';
import { TopMenu } from '../../imports/TopMenu';
import { AnimatedBackground } from './AnimatedBackground';

interface AppLayoutProps {
  language: 'en' | 'zh';
  onLanguageChange: (lang: 'en' | 'zh') => void;
  isLoggedIn: boolean;
  user: {
    name: string;
    initials: string;
    avatar: string;
  };
  onLogout: () => void;
}

export function AppLayout({ language, onLanguageChange, isLoggedIn, user, onLogout }: AppLayoutProps) {
  return (
    <div className="min-h-screen bg-[#faf9f8]">
      <AnimatedBackground />
      <TopMenu 
        language={language} 
        onLanguageChange={onLanguageChange}
        isLoggedIn={isLoggedIn}
        user={user}
        onLogout={onLogout}
      />
      <Outlet />
    </div>
  );
}
