import { apiClient } from '@/lib/api/client';

/** 公开接口：当前生效公告 */
export interface SiteNoticeChannel {
  type: string; // wechat | blog | xiaohongshu | other
  url?: string;
  qr_url?: string;
  label?: string;
}

export interface SiteNoticeItem {
  id: string;
  type: string;
  title: string;
  content_md: string;
  severity: 'info' | 'warn' | 'urgent';
  start_at: string | null;
  end_at: string | null;
  dismissible: boolean;
  is_active: boolean;
  channels: SiteNoticeChannel[];
  created_at: string | null;
  updated_at: string | null;
}

/** 拉取当前生效的 banner（公开接口）。失败返回 null，不抛错（banner 不应阻断主流程） */
export async function fetchActiveNotice(type = 'banner'): Promise<SiteNoticeItem | null> {
  try {
    // 直接用裸 fetch，绕过 apiClient（拦截器/鉴权可能干扰公开接口）
    const url = `/api/v1/site-notices/active?type=${encodeURIComponent(type)}&limit=1`;
    const resp = await fetch(url);
    if (!resp.ok) {
      console.warn('[fetchActiveNotice] HTTP', resp.status, await resp.text());
      return null;
    }
    const items = (await resp.json()) as SiteNoticeItem[];
    console.log('[fetchActiveNotice] items=', items);
    return items.length > 0 ? items[0] : null;
  } catch (e) {
    console.error('[fetchActiveNotice] error:', e);
    return null;
  }
}

// ── Admin 接口 ────────────────────────────────────────
export interface SiteNoticeListResp {
  items: SiteNoticeItem[];
  total: number;
  page: number;
  page_size: number;
}

export interface SiteNoticePayload {
  type?: string;
  title: string;
  content_md?: string;
  severity?: 'info' | 'warn' | 'urgent';
  start_at?: string;
  end_at?: string;
  dismissible?: boolean;
  is_active?: boolean;
  channels?: SiteNoticeChannel[];
}

export async function adminListSiteNotices(params: {
  type?: string;
  is_active?: boolean;
  page?: number;
  page_size?: number;
} = {}): Promise<SiteNoticeListResp> {
  const res = await apiClient.get<SiteNoticeListResp>('/admin/site-notices', { params });
  return (
    res.data ?? {
      items: [],
      total: 0,
      page: 1,
      page_size: 20,
    }
  );
}

export async function adminGetSiteNotice(id: string): Promise<SiteNoticeItem> {
  const res = await apiClient.get<SiteNoticeItem>(`/admin/site-notices/${id}`);
  return res.data as SiteNoticeItem;
}

export async function adminCreateSiteNotice(payload: SiteNoticePayload): Promise<SiteNoticeItem> {
  const res = await apiClient.post<SiteNoticeItem>('/admin/site-notices', payload);
  return res.data as SiteNoticeItem;
}

export async function adminUpdateSiteNotice(
  id: string,
  payload: Partial<SiteNoticePayload>
): Promise<SiteNoticeItem> {
  const res = await apiClient.patch<SiteNoticeItem>(`/admin/site-notices/${id}`, payload);
  return res.data as SiteNoticeItem;
}

export async function adminDeleteSiteNotice(id: string): Promise<{ ok: boolean }> {
  const res = await apiClient.delete<{ ok: boolean }>(`/admin/site-notices/${id}`);
  return res.data as { ok: boolean };
}

export async function adminToggleSiteNotice(id: string): Promise<SiteNoticeItem> {
  const res = await apiClient.post<SiteNoticeItem>(`/admin/site-notices/${id}/toggle`);
  return res.data as SiteNoticeItem;
}

// ── 维护模式 ──────────────────────────────────────────
export interface MaintenanceStatus {
  is_on: boolean;
  flag_path: string;
  meta?: { raw?: string };
}

export async function getMaintenanceStatus(): Promise<MaintenanceStatus> {
  const res = await apiClient.get<MaintenanceStatus>('/admin/maintenance/status');
  return res.data as MaintenanceStatus;
}

export async function setMaintenanceMode(payload: {
  action: 'on' | 'off';
  end_at?: string;
  reason?: string;
  env?: string;
}): Promise<{ ok: boolean; stdout?: string }> {
  const res = await apiClient.post<{ ok: boolean; stdout?: string }>(
    '/admin/maintenance',
    { env: 'prod', ...payload }
  );
  return res.data as { ok: boolean; stdout?: string };
}
