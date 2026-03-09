import { useState, useMemo, useCallback } from 'react';
import { RouterProvider } from 'react-router';
import { createRouter } from './routes.tsx';
import { UserProvider } from './contexts/UserContext';

export default function App() {
  const [language, setLanguage] = useState<'en' | 'zh'>('zh');
  const [isLoggedIn, setIsLoggedIn] = useState(true);
  const [user] = useState({
    name: 'John Doe',
    initials: 'JD',
    avatar: '',
  });

  const handleLogout = useCallback(() => {
    setIsLoggedIn(false);
    console.log('User logged out');
  }, []);

  // Create router based on current language and auth state
  const router = useMemo(() => createRouter({
    language,
    onLanguageChange: setLanguage,
    isLoggedIn,
    user,
    onLogout: handleLogout,
  }), [language, isLoggedIn, user, handleLogout]);

  return (
    <UserProvider>
      <RouterProvider router={router} />
    </UserProvider>
  );
}