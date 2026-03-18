import { apiClient } from '@/lib/api/client';

export interface AdminActivationItem {
  activation_code: string;
  session_id: string;
  mode: string;
  created_at: string;
  expires_at: string;
  last_activity_at: string;
  status: string;
}

export async function fetchAdminActivations(params?: {
  status?: string;
  mode?: string;
  q?: string;
}): Promise<AdminActivationItem[]> {
  const res = await apiClient.get('/admin/activations', { params });
  const items = res.data?.data?.items ?? [];
  return items as AdminActivationItem[];
}

