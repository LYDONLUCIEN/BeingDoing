/**
 * 报告解读咨询 API（P-D）
 *
 * 用户侧：
 * - GET  /consultation/my-reports               我的已完成报告（问卷选报告）
 * - GET  /consultation/bookings                 我的预约单列表
 * - GET  /consultation/bookings/{id}            预约单详情
 * - POST /consultation/bookings/{id}/survey     提交预约问卷
 *
 * Admin 侧（超管）：
 * - GET  /admin/consultations                   预约单列表
 * - GET  /admin/consultations/{id}              详情
 * - POST /admin/consultations/{id}/schedule     标记已预约
 * - POST /admin/consultations/{id}/complete     标记已完成
 */

import { apiClient } from './client';

// ─── 类型 ────────────────────────────────────────────────────

export type ConsultationStatus =
  | 'pending_survey'
  | 'submitted'
  | 'scheduled'
  | 'completed'
  | 'cancelled';

export interface ConsultationBooking {
  id: string;
  order_id: string;
  user_id: string;
  report_id: string | null;
  topics: string | null;
  time_slots: string[];
  contact: string | null;
  note: string | null;
  status: ConsultationStatus;
  scheduled_at: string | null;
  admin_note: string | null;
  created_at: string | null;
  updated_at: string | null;
  user_email?: string;
}

export interface MyReportItem {
  report_id: string;
  activation_code: string;
  created_at: string | null;
}

export interface SurveyPayload {
  report_id: string;
  topics: string;
  time_slots: string[];
  contact: string;
  note?: string;
}

interface ListResponse<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
}

// ─── 用户侧 ──────────────────────────────────────────────────

export async function fetchMyReports(): Promise<MyReportItem[]> {
  const res = await apiClient.get<{ items: MyReportItem[] }>('/consultation/my-reports');
  return res.data?.items ?? [];
}

export async function fetchMyBookings(
  page = 1,
  pageSize = 20
): Promise<ListResponse<ConsultationBooking>> {
  const res = await apiClient.get<ListResponse<ConsultationBooking>>('/consultation/bookings', {
    params: { page, page_size: pageSize },
  });
  return (res.data ?? { items: [], total: 0, page: 1, page_size: pageSize }) as ListResponse<ConsultationBooking>;
}

export async function fetchBooking(bookingId: string): Promise<ConsultationBooking> {
  const res = await apiClient.get<{ booking: ConsultationBooking }>(
    `/consultation/bookings/${bookingId}`
  );
  return res.data.booking;
}

export async function submitSurvey(
  bookingId: string,
  payload: SurveyPayload
): Promise<ConsultationBooking> {
  const res = await apiClient.post<{ booking: ConsultationBooking }>(
    `/consultation/bookings/${bookingId}/survey`,
    payload
  );
  return res.data.booking;
}

// ─── Admin 侧 ────────────────────────────────────────────────

export async function adminListConsultations(params: {
  status?: string;
  page?: number;
  page_size?: number;
}): Promise<ListResponse<ConsultationBooking>> {
  const res = await apiClient.get<ListResponse<ConsultationBooking>>('/admin/consultations', {
    params,
  });
  return (res.data ?? { items: [], total: 0, page: 1, page_size: 20 }) as ListResponse<ConsultationBooking>;
}

export async function adminScheduleConsultation(
  bookingId: string,
  payload: { scheduled_at: string; admin_note?: string }
): Promise<ConsultationBooking> {
  const res = await apiClient.post<{ booking: ConsultationBooking }>(
    `/admin/consultations/${bookingId}/schedule`,
    payload
  );
  return res.data.booking;
}

export async function adminCompleteConsultation(bookingId: string): Promise<ConsultationBooking> {
  const res = await apiClient.post<{ booking: ConsultationBooking }>(
    `/admin/consultations/${bookingId}/complete`
  );
  return res.data.booking;
}
