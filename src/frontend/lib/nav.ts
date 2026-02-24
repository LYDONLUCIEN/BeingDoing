export interface NavItem {
  label: string;
  href: string;
  requiresAuth?: boolean;
}

export const NAV_ITEMS: NavItem[] = [
  { label: '首页', href: '/' },
  { label: '理论介绍', href: '/theory' },
  // 将「开始测试」指向轻量版激活码入口，避免直接暴露复杂版路径
  { label: '开始测试', href: '/light-explore' },
  { label: '社区', href: '/community' },
  { label: '关于我们', href: '/about' },
];
