import { redirect } from 'next/navigation';

/** 订单记录已并入「我的激活码」页订单 tab，保留路由避免死链 */
export default function DashboardOrdersRedirectPage() {
  redirect('/dashboard/codes?tab=orders');
}
