import { useState } from 'react';
import { ChevronDown } from 'lucide-react';

interface TopMenuProps {
  language: 'en' | 'zh';
  onLanguageChange: (lang: 'en' | 'zh') => void;
}

export function TopMenu({ language, onLanguageChange }: TopMenuProps) {
  const [isLangOpen, setIsLangOpen] = useState(false);
  const [currentPage] = useState('home');

  const text = {
    en: {
      home: 'Home',
      explore: 'Start Exploring',
      community: 'Community',
      login: 'Login / Register',
    },
    zh: {
      home: '首页',
      explore: '开始探索',
      community: '社区',
      login: '登录 / 注册',
    },
  };

  const t = text[language];

  return (
    <nav className="fixed top-0 left-0 right-0 bg-[#F2F5F8] z-50 border-b border-gray-200/50">
      <div className="max-w-7xl mx-auto px-6 py-4 flex items-center justify-between">
        {/* Left: Logo */}
        <div className="font-bold text-black text-xl cursor-pointer">
          Careering
        </div>

        {/* Center: Navigation */}
        <div className="hidden md:flex items-center gap-8">
          <button
            className={`transition-colors cursor-pointer ${
              currentPage === 'home' ? 'text-black font-medium' : 'text-gray-700 hover:text-black'
            }`}
          >
            {t.home}
          </button>
          <button className="text-gray-700 hover:text-black transition-colors cursor-pointer">
            {t.explore}
          </button>
          <button className="text-gray-700 hover:text-black transition-colors cursor-pointer">
            {t.community}
          </button>
        </div>

        {/* Right: Language + Login */}
        <div className="flex items-center gap-4">
          {/* Language Dropdown */}
          <div className="relative">
            <button
              onClick={() => setIsLangOpen(!isLangOpen)}
              className="px-4 py-2 bg-white rounded-lg text-sm border border-gray-200 hover:border-gray-300 transition-colors flex items-center gap-2"
            >
              {language === 'en' ? 'English' : '中文'}
              <ChevronDown className="w-4 h-4" />
            </button>

            {isLangOpen && (
              <div className="absolute right-0 mt-2 w-32 bg-white rounded-lg shadow-lg border border-gray-200 overflow-hidden">
                <button
                  onClick={() => {
                    onLanguageChange('en');
                    setIsLangOpen(false);
                  }}
                  className="w-full px-4 py-2 text-left text-sm hover:bg-gray-50 transition-colors"
                >
                  English
                </button>
                <button
                  onClick={() => {
                    onLanguageChange('zh');
                    setIsLangOpen(false);
                  }}
                  className="w-full px-4 py-2 text-left text-sm hover:bg-gray-50 transition-colors"
                >
                  中文
                </button>
              </div>
            )}
          </div>

          {/* Login/Register Button */}
          <button className="px-6 py-2 bg-black text-white rounded-lg text-sm hover:bg-gray-800 transition-colors">
            {t.login}
          </button>
        </div>
      </div>
    </nav>
  );
}
