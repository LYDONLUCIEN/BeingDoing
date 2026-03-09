import { useState } from 'react';
import { Outlet, NavLink } from 'react-router';
import { User, BarChart3, BookOpen, HelpCircle, Trash2, Settings } from 'lucide-react';

interface DashboardLayoutProps {
  language: 'en' | 'zh';
}

export function DashboardLayout({ language }: DashboardLayoutProps) {
  const text = {
    en: {
      currentProgress: 'Current Progress',
      report: 'Report',
      usageGuide: 'Usage Guide',
      helpCenter: 'Help Center',
      recycleBin: 'Recycle Bin',
      setting: 'Setting',
    },
    zh: {
      currentProgress: '当前进度',
      report: '报告',
      usageGuide: '使用指南',
      helpCenter: '帮助中心',
      recycleBin: '回收站',
      setting: '设置',
    },
  };

  const t = text[language];

  const navItems = [
    { path: '/dashboard', icon: User, label: t.currentProgress },
    { path: '/dashboard/report', icon: BarChart3, label: t.report },
    { path: '/dashboard/guide', icon: BookOpen, label: t.usageGuide },
    { path: '/dashboard/help', icon: HelpCircle, label: t.helpCenter },
    { path: '/dashboard/recycle', icon: Trash2, label: t.recycleBin },
    { path: '/dashboard/settings', icon: Settings, label: t.setting },
  ];

  return (
    <div className="flex min-h-screen bg-[#faf9f8] pt-20">
      {/* Left Sidebar */}
      <aside className="w-64 bg-white/60 backdrop-blur-lg border-r border-gray-200/50 fixed left-0 top-20 bottom-0 flex flex-col items-center pt-8 px-4">
        {/* User Avatar */}
        <div className="w-20 h-20 rounded-full bg-gradient-to-br from-[#A2C2E8] to-[#B5D8C6] flex items-center justify-center text-white text-2xl font-semibold mb-3">
          JD
        </div>
        
        {/* User Nickname */}
        <h3 className="font-medium text-[#1d1d1f] mb-8">John Doe</h3>

        {/* Navigation Items */}
        <nav className="w-full space-y-2">
          {navItems.map((item) => {
            const Icon = item.icon;
            return (
              <NavLink
                key={item.path}
                to={item.path}
                end={item.path === '/dashboard'}
                className={({ isActive }) =>
                  `flex items-center gap-3 px-4 py-3 rounded-lg transition-all ${
                    isActive
                      ? 'bg-[#1d1d1f] text-white'
                      : 'text-gray-700 hover:bg-gray-100'
                  }`
                }
              >
                <Icon className="w-5 h-5" />
                <span className="text-sm">{item.label}</span>
              </NavLink>
            );
          })}
        </nav>
      </aside>

      {/* Main Content Area */}
      <main className="ml-64 flex-1 p-8">
        <Outlet />
      </main>
    </div>
  );
}
