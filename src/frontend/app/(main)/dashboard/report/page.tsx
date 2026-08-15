import { redirect } from 'next/navigation';

/** 报告列表页已下线：报告入口并入「当前进度」旅程卡，保留路由避免死链 */
export default function DashboardReportRedirectPage() {
  redirect('/dashboard');
}
