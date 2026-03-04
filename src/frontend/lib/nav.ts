export interface NavItem {
  labelKey: string; // i18n key e.g. 'nav.home'
  href: string;
  requiresAuth?: boolean;
}

export const NAV_ITEMS: NavItem[] = [
  { labelKey: 'nav.home', href: '/' },
  { labelKey: 'nav.explore', href: '/explore/intro' },
  { labelKey: 'nav.community', href: '/community' },
];
