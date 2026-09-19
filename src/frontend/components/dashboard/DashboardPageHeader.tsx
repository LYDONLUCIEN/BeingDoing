import type { ReactNode } from 'react';

interface DashboardPageHeaderProps {
  kicker: string;
  title: string;
  description: string;
  action?: ReactNode;
}

/** 个人空间各页面共用的编辑式标题区。 */
export default function DashboardPageHeader({
  kicker,
  title,
  description,
  action,
}: DashboardPageHeaderProps) {
  return (
    <header className="ol-profile-panel-heading">
      <div>
        <p className="ol-profile-kicker">{kicker}</p>
        <h2>{title}</h2>
        <p>{description}</p>
      </div>
      {action ? <div className="ol-profile-heading-action">{action}</div> : null}
    </header>
  );
}
