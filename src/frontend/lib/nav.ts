export interface NavItem {
  label: string;
  href: string;
  requiresAuth?: boolean;
}

export const NAV_ITEMS: NavItem[] = [
  { label: '首页', href: '/' },
  { label: '开始探索', href: '/explore/intro' },
  { label: '社区', href: '/community' },
];
