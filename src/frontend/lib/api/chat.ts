import { apiClient, ApiResponse } from './client';

export interface SendMessageRequest {
  session_id: string;
  message: string;
  current_step: string;
  category?: string;
}

export interface Message {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  context?: any;
  created_at: string;
}

export interface GuideRequest {
  session_id: string;
  current_step: string;
}

export interface GuidePreferenceRequest {
  session_id: string;
  preference: 'normal' | 'quiet';
}

export interface AnswerCardMeta {
  /** 当前步骤（如 values_exploration），前端可结合自身映射展示 */
  question_step?: string;
  /** AI 对当前题目的分析/反馈（只读，Markdown 展示） */
  ai_analysis?: string;
  /** 用户针对当前题目的回答文本（可编辑，Markdown 展示） */
  user_answer?: string;
}

export const chatApi = {
  sendMessage: async (data: SendMessageRequest): Promise<ApiResponse<{ response: string; session_id: string; tools_used: string[] }>> => {
    return apiClient.post('/chat/messages', data);
  },

  getHistory: async (sessionId: string, category?: string, limit?: number): Promise<ApiResponse<{ messages: Message[]; count: number }>> => {
    return apiClient.get('/chat/history', {
      params: { session_id: sessionId, category, limit },
    });
  },

  triggerGuide: async (data: GuideRequest): Promise<ApiResponse<{ message: string }>> => {
    return apiClient.post('/chat/guide', data);
  },

  setGuidePreference: async (data: GuidePreferenceRequest): Promise<ApiResponse<any>> => {
    return apiClient.post('/chat/guide-preference', data);
  },

  /** 用户修改回答后触发后台重新梳理总结 */
  resummarize: async (sessionId: string, currentStep?: string): Promise<ApiResponse<{ triggered: boolean }>> => {
    return apiClient.post('/chat/resummarize', { session_id: sessionId, current_step: currentStep });
  },

  /**
   * 流式发送消息：通过 SSE 逐块接收助手回复。
   * 服务端会先发 started，再跑智能体，再发 chunk / done。
   * signal: 用于终止请求（点击停止时 abort）。
   * onStarted() 收到 started 时调用（可显示「思考中…」），onChunk/onDone/onError/onStop 同上。
   */
  sendMessageStream: async (
    data: SendMessageRequest,
    callbacks: {
      onStarted?: () => void;
      onChunk: (chunk: string) => void;
      onDone: (fullResponse: string, meta?: { answerCard?: AnswerCardMeta }) => void;
      onError: (err: string) => void;
      onStop?: (partialContent: string) => void;
    },
    signal?: AbortSignal
  ): Promise<void> => {
    const baseURL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
    const url = `${baseURL}/api/v1/chat/messages/stream`;
    const token = typeof window !== 'undefined' ? localStorage.getItem('token') : null;
    const res = await fetch(url, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      body: JSON.stringify(data),
      signal,
    });
    if (!res.ok) {
      callbacks.onError(res.statusText || '请求失败');
      return;
    }
    const reader = res.body?.getReader();
    if (!reader) {
      callbacks.onError('无法读取流');
      return;
    }
    const decoder = new TextDecoder();
    let buffer = '';
    let fullResponse = '';
    try {
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() || '';
        for (const line of lines) {
          if (line.startsWith('data: ')) {
            try {
              const payload = JSON.parse(line.slice(6));
              if (payload.error) {
                callbacks.onError(payload.error);
                return;
              }
              if (payload.started) {
                callbacks.onStarted?.();
                continue;
              }
              if (payload.chunk) {
                fullResponse += payload.chunk;
                callbacks.onChunk(payload.chunk);
              }
              if (payload.done && payload.response != null) {
                fullResponse = payload.response;
                callbacks.onDone(fullResponse, { answerCard: payload.answer_card });
                return;
              }
            } catch (_) {}
          }
        }
      }
      if (fullResponse) callbacks.onDone(fullResponse);
    } catch (e: unknown) {
      if (e instanceof Error && e.name === 'AbortError') {
        callbacks.onStop?.(fullResponse);
        return;
      }
      callbacks.onError(e instanceof Error ? e.message : '流式读取失败');
    }
  },

  /** 用户点击终止时记录打断与截至内容 */
  recordInterrupt: async (sessionId: string, partialContent: string, currentStep?: string): Promise<ApiResponse<{ recorded: boolean }>> => {
    return apiClient.post('/chat/record-interrupt', {
      session_id: sessionId,
      partial_content: partialContent,
      current_step: currentStep,
    });
  },

  /** 超级管理员：获取某会话的智能体调试日志 */
  getDebugLogs: async (sessionId: string): Promise<ApiResponse<{ entries: any[] }>> => {
    return apiClient.get('/chat/debug-logs', { params: { session_id: sessionId } });
  },
};
