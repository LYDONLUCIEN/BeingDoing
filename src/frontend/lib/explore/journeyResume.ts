/**
 * 从「我的旅程」列表解析某激活码的 explore_resume（与 /simple-auth/activate 返回结构一致）。
 */
import { apiClient } from '@/lib/api/client';
import type { ExploreResumePayload } from '@/lib/explore/session';

type JourneyRow = { activation_code?: string; explore_resume?: ExploreResumePayload };

export async function fetchExploreResumeFromJourneys(
  activationCode: string
): Promise<ExploreResumePayload | null> {
  if (!activationCode.trim()) return null;
  try {
    const res = await apiClient.get<{ journeys: JourneyRow[] }>('/simple-auth/journeys');
    const list = res.data?.journeys ?? [];
    const row = list.find((j) => (j.activation_code || '').trim() === activationCode.trim());
    return row?.explore_resume ?? null;
  } catch {
    return null;
  }
}
