import { createBrowserRouter } from 'react-router';
import { LandingPage } from './components/LandingPage';
import { DashboardLayout } from './components/DashboardLayout';
import { CurrentProgress } from './components/CurrentProgress';
import { Report } from './components/Report';
import { PlaceholderPage } from './components/PlaceholderPage';
import { AppLayout } from './components/AppLayout';
import { BookOpen, HelpCircle, Trash2, Settings } from 'lucide-react';

interface RouterConfig {
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

export const createRouter = ({ language, onLanguageChange, isLoggedIn, user, onLogout }: RouterConfig) => {
  const text = {
    en: {
      usageGuide: 'Usage Guide',
      usageGuideDesc: 'Learn how to use Careering effectively',
      helpCenter: 'Help Center',
      helpCenterDesc: 'Get help and support',
      recycleBin: 'Recycle Bin',
      recycleBinDesc: 'View and restore deleted items',
      settings: 'Settings',
      settingsDesc: 'Manage your account and preferences',
    },
    zh: {
      usageGuide: '使用指南',
      usageGuideDesc: '了解如何有效使用职引',
      helpCenter: '帮助中心',
      helpCenterDesc: '获取帮助和支持',
      recycleBin: '回收站',
      recycleBinDesc: '查看和恢复已删除的项目',
      settings: '设置',
      settingsDesc: '管理您的账户和偏好设置',
    },
  };

  const t = text[language];

  return createBrowserRouter([
    {
      path: '/',
      element: <AppLayout language={language} onLanguageChange={onLanguageChange} isLoggedIn={isLoggedIn} user={user} onLogout={onLogout} />,
      children: [
        {
          index: true,
          element: <LandingPage language={language} />,
        },
        {
          path: 'dashboard',
          element: <DashboardLayout language={language} />,
          children: [
            {
              index: true,
              element: <CurrentProgress language={language} />,
            },
            {
              path: 'report',
              element: <Report language={language} />,
            },
            {
              path: 'guide',
              element: (
                <PlaceholderPage
                  title={t.usageGuide}
                  description={t.usageGuideDesc}
                  icon={BookOpen}
                />
              ),
            },
            {
              path: 'help',
              element: (
                <PlaceholderPage
                  title={t.helpCenter}
                  description={t.helpCenterDesc}
                  icon={HelpCircle}
                />
              ),
            },
            {
              path: 'recycle',
              element: (
                <PlaceholderPage
                  title={t.recycleBin}
                  description={t.recycleBinDesc}
                  icon={Trash2}
                />
              ),
            },
            {
              path: 'settings',
              element: (
                <PlaceholderPage title={t.settings} description={t.settingsDesc} icon={Settings} />
              ),
            },
          ],
        },
      ],
    },
  ]);
};