import { QrCode } from 'lucide-react';

interface FooterProps {
  language: 'en' | 'zh';
}

export function Footer({ language }: FooterProps) {
  const text = {
    en: {
      about: 'About Us',
      contact: 'Contact',
      qrcode: 'QR Code',
      privacy: 'Privacy Policy',
      terms: 'Terms of Service',
      copyright: '© 2026 Careering. All rights reserved.',
    },
    zh: {
      about: '关于我们',
      contact: '联系我们',
      qrcode: '二维码',
      privacy: '隐私政策',
      terms: '服务条款',
      copyright: '© 2026 职引. 保留所有权利。',
    },
  };

  const t = text[language];

  return (
    <footer className="relative z-10 bg-white/60 backdrop-blur-xl border-t border-gray-200 py-12 mt-20">
      <div className="max-w-6xl mx-auto px-5">
        <div className="grid grid-cols-2 md:grid-cols-5 gap-8 mb-8">
          <a href="#about" className="text-gray-700 hover:text-black transition-colors text-center md:text-left">
            {t.about}
          </a>
          <a href="#contact" className="text-gray-700 hover:text-black transition-colors text-center md:text-left">
            {t.contact}
          </a>
          <button className="text-gray-700 hover:text-black transition-colors flex items-center gap-2 justify-center md:justify-start">
            <QrCode className="h-4 w-4" />
            {t.qrcode}
          </button>
          <a href="#privacy" className="text-gray-700 hover:text-black transition-colors text-center md:text-left">
            {t.privacy}
          </a>
          <a href="#terms" className="text-gray-700 hover:text-black transition-colors text-center md:text-left">
            {t.terms}
          </a>
        </div>

        <div className="text-center text-sm text-gray-500 border-t border-gray-200 pt-8">
          <p>{t.copyright}</p>
        </div>
      </div>
    </footer>
  );
}
