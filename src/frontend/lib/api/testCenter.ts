import { apiClient } from './client';

export type TestStatus = 'queued' | 'running' | 'pass' | 'fail' | 'error' | 'incomplete' | 'cancelled' | 'needs_review';
export interface TestDefinition {
  purpose?: string; sources?: { path: string; rule: string }[]; conversation_mode?: 'independent' | 'sequence' | 'workflow';
  id?: string; title: string; module: string; kind: 'api' | 'ui' | 'ai'; inputs: string[]; assertions: string[]; targets: string[]; timeout: number;
  origin?: 'authored'; template_id?: string; template_revision?: string; context_id?: string; repeats?: number;
}
export interface TestCase {
  id: string; revision: string; core: boolean; archived: boolean; available: boolean; version: boolean;
  definition: TestDefinition; attempts?: AiAttempt[]; upstream?: { revision: string; definition: TestDefinition };
  status?: TestStatus; duration_ms?: number; error?: string;
  artifacts?: string[]; counts?: { tests?: number; failures?: number; errors?: number; skipped?: number; assertions?: number; planned?: number; passed?: number; needs_review?: number };
}
export interface TestBuild { sha: string; tag: string; base_tag: string; label: string; dirty: boolean; source_digest?: string }
export interface TestCatalog {
  cases: TestCase[]; build: TestBuild; coverage_gaps: string[]; unknown_cases: string[];
  storage?: { free_bytes: number; used_bytes: number };
  changes: { id: string; summary: string; cases: string[] }[]; worker: { ready: boolean };
}
export interface TestRun { id: string; status: TestStatus; mode: 'diagnostic' | 'release'; created: number; finished?: number; build: TestBuild; required: string[]; cases: TestCase[]; error?: string;
  ai?: { planned_calls: number; budget: TestBudget; config: AiCapability['config']; contexts?: Record<string, TestContext> };
  reviews?: TestReview[]; calls?: { id: string; purpose: string; status: string; charged_tokens: number }[];
  usage?: { calls: number; total_tokens: number; charged_tokens: number; unknown_calls: number; cost: number | null; currency?: string };
}
const base = '/admin/test-center';
export const testCenterApi = {
  catalog: async () => (await apiClient.get<TestCatalog>(`${base}/catalog`)).data,
  runs: async () => (await apiClient.get<TestRun[]>(`${base}/runs`)).data,
  run: async (id: string) => (await apiClient.get<TestRun>(`${base}/runs/${id}`)).data,
  start: async (caseIds: string[], mode: 'diagnostic' | 'release' = 'diagnostic', budget?: TestBudget) =>
    (await apiClient.post<TestRun>(`${base}/runs`, { case_ids: caseIds, mode, budget })).data,
  cancel: async (id: string) => (await apiClient.post<TestRun>(`${base}/runs/${id}/cancel`)).data,
  update: async (test: TestCase, core: boolean, archived: boolean) =>
    apiClient.put(`${base}/cases/${test.id}`, { core, archived }),
  download: async (runId: string, caseId: string, name: string) => {
    const response = await apiClient.raw.get<Blob>(`${base}/runs/${runId}/artifacts/${caseId}/${encodeURIComponent(name)}`, { responseType: 'blob' });
    const url = URL.createObjectURL(response.data);
    const link = document.createElement('a'); link.href = url; link.download = name; link.click();
    window.setTimeout(() => URL.revokeObjectURL(url), 1000);
  },
};

export interface DraftRequest {
  purpose?: string; conversation_mode?: 'independent' | 'sequence' | 'workflow';
  title: string; kind: 'api' | 'ui' | 'ai'; template_id?: string; case_id?: string; base_revision?: string;
  inputs: string[]; assertions: string[]; context_id?: string; repeats?: number;
}
export interface TestDraft { id: string; created: number; state: 'ready' | 'needs_clarification'; issues: string[]; definition: TestDefinition; base_revision?: string; }
export interface ContextMessage { role: 'user' | 'assistant' | 'system'; content: string; }
export interface ContextSpec {
  name: string; phase: 'values' | 'strengths' | 'interests' | 'purpose' | 'rumination'; thread_id: string;
  messages?: ContextMessage[]; question_bank?: string; basic_info?: string; prior_context?: string; values_info?: string;
  purpose_progress_injection?: string; conclusion_state_injection?: string; anchor_text?: string;
  user_context?: string; values_keywords?: string[]; source?: 'manual' | 'debug_workspace';
  workflow_seed?: { completed_phases?: string[]; basic_info?: Record<string, unknown>; conclusions?: Record<string, Record<string, unknown>>; thread_metadata?: Record<string, unknown>; anchor?: Record<string, unknown> } | null;
  combo?: { combo_id: string; passion: string; strengths: string[]; messages?: ContextMessage[]; summary?: string; summary_last_round?: number; conclusion_card?: { hypothesis: string }; reopen_feedback?: string; status?: 'discussing' } | null;
}
export interface TestContext { id: string; created: number; spec: ContextSpec; version: number; }
export interface TestBudget { max_calls: number; max_tokens: number; }
export interface ModelProfile { model: string; thinking: boolean; }
export interface AiCapability { configured: boolean; reason?: string; worker_key_ready: boolean; config?: { provider: string; base_url: string; chat: ModelProfile; rumination: ModelProfile; conclusion?: ModelProfile; report?: ModelProfile; unknown?: ModelProfile; input_price?: number; output_price?: number; currency?: string }; }
export interface AiAttempt {
  index: number; input_index: number; repeat: number; input: string; reply?: string; raw_reply?: string; status: TestStatus;
  context_id: string; prompt_digest?: string; actual_model?: string; judge_reply?: string;
  messages?: ContextMessage[]; checks: { index?: number; status: TestStatus; reason: string }[];
  http_status?: number; request?: { method: string; path: string; body: Record<string, unknown> }; response?: string;
  before_state?: Record<string, unknown>; state?: Record<string, unknown>;
  model_calls?: { id: string; messages: ContextMessage[]; raw_reply: string; config: Record<string, unknown> }[];
}
export interface TestReview { id: string; case_id: string; attempt: number; created: number; verdict: 'pass' | 'fail' | 'needs_review'; reason: string; reviewer: string; automated_status: TestStatus; }
export const testAuthorApi = {
  drafts: async () => (await apiClient.get<TestDraft[]>(`${base}/drafts`)).data,
  compile: async (body: DraftRequest) => (await apiClient.post<TestDraft>(`${base}/drafts`, body)).data,
  save: async (draftId: string) => (await apiClient.post<{ id: string; revision: string }>(`${base}/cases`, { draft_id: draftId })).data,
  revisions: async (id: string) => (await apiClient.get<{ revision: string; definition: TestDefinition }[]>(`${base}/cases/${id}/revisions`)).data,
  contexts: async () => (await apiClient.get<TestContext[]>(`${base}/contexts`)).data,
  context: async (spec: ContextSpec) => (await apiClient.post<TestContext>(`${base}/contexts`, spec)).data,
  capture: async (body: { activation_code: string; phase: string; thread_id: string; name: string }) => (await apiClient.post<ContextSpec>(`${base}/contexts/preview`, body)).data,
  capabilities: async () => (await apiClient.get<AiCapability>(`${base}/capabilities`)).data,
  review: async (runId: string, body: { case_id: string; attempt: number; verdict: TestReview['verdict']; reason: string }) => (await apiClient.post<TestReview>(`${base}/runs/${runId}/reviews`, body)).data,
};
