export interface NavItem {
  label: string;
  href: string;
  requiresAuth?: boolean;
}

export const NAV_ITEMS: NavItem[] = [
  { label: '首页', href: '/' },
  { label: '理论介绍', href: '/theory' },
  { label: '开始测试', href: '/explore', requiresAuth: true },
  { label: '社区', href: '/community' },
  { label: '关于我们', href: '/about' },
];
