import { apiClient } from './client';

// ---------- 类型 ----------

export type FeedbackType = 'bug' | 'idea';
export type FeedbackStatus = 'received' | 'in_progress' | 'done';
export type NotificationType =
  | 'feedback_auto_ack'
  | 'feedback_new'
  | 'feedback_status_changed'
  | 'announcement';

export interface Feedback {
  id: string;
  type: FeedbackType;
  content: string;
  status: FeedbackStatus;
  created_at: string;
}

export interface AttachmentUploadResult {
  id: string;
  preview_url: string;
  size_bytes: number;
  content_type: string;
}

export interface Notification {
  id: string;
  type: NotificationType;
  title: string;
  content: string;
  read_at: string | null;
  related_feedback_id: string | null;
  created_at: string;
}

export interface NotificationList {
  items: Notification[];
  total: number;
  page: number;
  page_size: number;
  unread_count: number;
}

// ---------- 反馈 ----------

export async function createFeedback(payload: {
  type: FeedbackType;
  content: string;
  attachment_ids?: string[];
}): Promise<Feedback> {
  const res = await apiClient.post('/feedbacks', {
    type: payload.type,
    content: payload.content,
    attachment_ids: payload.attachment_ids ?? [],
  });
  return res.data;
}

export async function uploadAttachment(file: File): Promise<AttachmentUploadResult> {
  const form = new FormData();
  form.append('file', file);
  const res = await apiClient.post('/feedbacks/attachments', form, {
    headers: { 'Content-Type': 'multipart/form-data' },
  });
  return res.data;
}

export async function deleteAttachment(id: string): Promise<void> {
  await apiClient.delete(`/feedbacks/attachments/${id}`);
}

// ---------- 通知 ----------

export async function getUnreadCount(): Promise<number> {
  const res = await apiClient.get('/notifications/unread_count');
  return res.data.count;
}

export async function listNotifications(params?: {
  page?: number;
  page_size?: number;
  unread_only?: boolean;
}): Promise<NotificationList> {
  const res = await apiClient.get('/notifications', { params });
  return res.data;
}

export async function markNotificationRead(id: string): Promise<void> {
  await apiClient.post(`/notifications/${id}/read`);
}

export async function markAllNotificationsRead(): Promise<void> {
  await apiClient.post('/notifications/read_all');
}
