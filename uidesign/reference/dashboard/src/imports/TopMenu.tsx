import { useState, useRef, useEffect } from 'react';
import { useNavigate } from 'react-router';

interface TopMenuProps {
  language: 'en' | 'zh';
  onLanguageChange: (lang: 'en' | 'zh') => void;
  isLoggedIn?: boolean;
  user?: {
    name: string;
    initials: string;
    avatar?: string;
  };
  onLogout?: () => void;
}

export function TopMenu({ language, onLanguageChange, isLoggedIn = true, user, onLogout }: TopMenuProps) {
  const [isOpen, setIsOpen] = useState(false);
  const [isUserMenuOpen, setIsUserMenuOpen] = useState(false);
  const userMenuRef = useRef<HTMLDivElement>(null);
  const navigate = useNavigate();

  // Default user if not provided
  const currentUser = user || {
    name: 'John Doe',
    initials: 'JD',
    avatar: '',
  };

  // Close dropdown when clicking outside
  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (userMenuRef.current && !userMenuRef.current.contains(event.target as Node)) {
        setIsUserMenuOpen(false);
      }
    }

    if (isUserMenuOpen) {
      document.addEventListener('mousedown', handleClickOutside);
    }
    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
    };
  }, [isUserMenuOpen]);

  const text = {
    en: {
      home: 'Home',
      explore: 'Start Exploring',
      community: 'Community',
      login: 'Login / Register',
      personalHomepage: 'Personal Homepage',
      logout: 'Log out',
    },
    zh: {
      home: '首页',
      explore: '开始探索',
      community: '社区',
      login: '登录 / 注册',
      personalHomepage: '个人主页',
      logout: '退出登录',
    },
  };

  const t = text[language];

  const handlePersonalHomepage = () => {
    navigate('/dashboard');
    setIsUserMenuOpen(false);
  };

  const handleLogout = () => {
    if (onLogout) {
      onLogout();
    }
    setIsUserMenuOpen(false);
    navigate('/');
  };

  return (
    <nav className="fixed top-0 left-0 right-0 bg-[#F2F5F8] z-50 border-b border-gray-200/50">
      <div className="max-w-7xl mx-auto px-6 py-4 flex items-center justify-between">
        {/* Left: Logo */}
        <div className="font-bold text-black text-xl">
          Careering
        </div>

        {/* Center: Navigation */}
        <div className="hidden md:flex items-center gap-8">
          <a href="#home" className="text-gray-700 hover:text-black transition-colors cursor-pointer">
            {t.home}
          </a>
          <a href="#explore" className="text-gray-700 hover:text-black transition-colors cursor-pointer">
            {t.explore}
          </a>
          <a href="#community" className="text-gray-700 hover:text-black transition-colors cursor-pointer">
            {t.community}
          </a>
        </div>

        {/* Right: Language + Login/User Avatar */}
        <div className="flex items-center gap-4">
          {/* Language Dropdown */}
          <div className="relative">
            <button
              onClick={() => setIsOpen(!isOpen)}
              className="px-4 py-2 bg-white rounded-lg text-sm border border-gray-200 hover:border-gray-300 transition-colors flex items-center gap-2"
            >
              {language === 'en' ? 'English' : '中文'}
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
              </svg>
            </button>

            {isOpen && (
              <div className="absolute right-0 mt-2 w-32 bg-white rounded-lg shadow-lg border border-gray-200 overflow-hidden">
                <button
                  onClick={() => {
                    onLanguageChange('en');
                    setIsOpen(false);
                  }}
                  className="w-full px-4 py-2 text-left text-sm hover:bg-gray-50 transition-colors"
                >
                  English
                </button>
                <button
                  onClick={() => {
                    onLanguageChange('zh');
                    setIsOpen(false);
                  }}
                  className="w-full px-4 py-2 text-left text-sm hover:bg-gray-50 transition-colors"
                >
                  中文
                </button>
              </div>
            )}
          </div>

          {/* Login/Register Button or User Avatar */}
          {isLoggedIn ? (
            <div className="relative" ref={userMenuRef}>
              <button
                onClick={() => setIsUserMenuOpen(!isUserMenuOpen)}
                className="w-10 h-10 rounded-full bg-gradient-to-br from-[#A2C2E8] to-[#B5D8C6] flex items-center justify-center text-white text-sm font-semibold hover:shadow-lg transition-all hover:scale-105"
                title={currentUser.name}
              >
                {currentUser.avatar ? (
                  <img src={currentUser.avatar} alt={currentUser.name} className="w-full h-full rounded-full object-cover" />
                ) : (
                  currentUser.initials
                )}
              </button>

              {isUserMenuOpen && (
                <div className="absolute right-0 mt-2 w-48 bg-white rounded-lg shadow-lg border border-gray-200 overflow-hidden">
                  <button
                    onClick={handlePersonalHomepage}
                    className="w-full px-4 py-3 text-left text-sm hover:bg-gray-50 transition-colors border-b border-gray-100"
                  >
                    {t.personalHomepage}
                  </button>
                  <button
                    onClick={handleLogout}
                    className="w-full px-4 py-3 text-left text-sm hover:bg-red-50 text-red-600 transition-colors"
                  >
                    {t.logout}
                  </button>
                </div>
              )}
            </div>
          ) : (
            <button className="px-6 py-2 bg-black text-white rounded-lg text-sm hover:bg-gray-800 transition-colors">
              {t.login}
            </button>
          )}
        </div>
      </div>
    </nav>
  );
}