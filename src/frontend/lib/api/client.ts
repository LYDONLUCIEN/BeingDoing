import axios, { AxiosInstance, AxiosError } from 'axios';
import { useAuthStore } from '@/stores/authStore';

const API_URL = (process.env.NEXT_PUBLIC_API_URL || '').trim();

function isLoopbackUrl(url: string): boolean {
  return /^https?:\/\/(localhost|127\.0\.0\.1)(:\d+)?$/i.test(url);
}

function resolveApiBase(): string {
  if (!API_URL) return '/api/v1';
  // 外网访问时若仍注入了 localhost 地址，强制回退同域，避免 CORS/network error
  if (typeof window !== 'undefined' && isLoopbackUrl(API_URL)) {
    const host = window.location.hostname;
    const isLocalPage = host === 'localhost' || host === '127.0.0.1';
    if (!isLocalPage) return '/api/v1';
  }
  return `${API_URL.replace(/\/+$/, '')}/api/v1`;
}

const API_BASE = resolveApiBase();

export interface ApiResponse<T = any> {
  code: number;
  message: string;
  data: T;
}

export function getApiErrorMessage(error: unknown, fallback = '请求失败，请稍后重试'): string {
  const err = error as AxiosError<{ detail?: string; message?: string }>;
  const detail = err?.response?.data?.detail;
  const message = err?.response?.data?.message;
  if (detail) return detail;
  if (message) return message;
  if (err?.code === 'ERR_NETWORK') {
    return '网络连接失败，请检查服务是否可用（或 NEXT_PUBLIC_API_URL 配置是否正确）';
  }
  if (err?.message) return err.message;
  return fallback;
}

/** 401 事件：供全局 AuthModal 监听 */
const AUTH_REQUIRED_EVENT = 'auth:required';

export function onAuthRequired(callback: (redirectTo: string) => void): () => void {
  const handler = (e: Event) => callback((e as CustomEvent).detail?.redirectTo || '/explore/intro');
  window.addEventListener(AUTH_REQUIRED_EVENT, handler);
  return () => window.removeEventListener(AUTH_REQUIRED_EVENT, handler);
}

function emitAuthRequired(redirectTo: string) {
  if (typeof window !== 'undefined') {
    window.dispatchEvent(new CustomEvent(AUTH_REQUIRED_EVENT, { detail: { redirectTo } }));
  }
}

class ApiClient {
  private client: AxiosInstance;

  constructor() {
    this.client = axios.create({
      baseURL: API_BASE,
      headers: {
        'Content-Type': 'application/json',
      },
    });

    // 请求拦截器：添加Token
    this.client.interceptors.request.use(
      (config) => {
        const token = this.getToken();
        if (token) {
          config.headers.Authorization = `Bearer ${token}`;
        }
        return config;
      },
      (error) => {
        return Promise.reject(error);
      }
    );

    // 响应拦截器：处理错误
    this.client.interceptors.response.use(
      (response) => response,
      (error: AxiosError) => {
        if (error.response?.status === 401) {
          const requestUrl = error.config?.url ?? '';
          const isAuthRequest =
            typeof requestUrl === 'string' &&
            (requestUrl.includes('/auth/login') || requestUrl.includes('/auth/register'));
          // 登录/注册接口返回 401 时不跳转，让页面显示错误、用户可重试；其他接口 401 弹登录弹窗
          if (!isAuthRequest && typeof window !== 'undefined') {
            this.clearToken();
            useAuthStore.getState().logout();
            const currentPath = window.location.pathname;
            emitAuthRequired(currentPath);
          }
        }
        return Promise.reject(error);
      }
    );
  }

  private getToken(): string | null {
    if (typeof window === 'undefined') return null;
    return localStorage.getItem('token');
  }

  private clearToken(): void {
    if (typeof window === 'undefined') return;
    localStorage.removeItem('token');
  }

  setToken(token: string): void {
    if (typeof window === 'undefined') return;
    localStorage.setItem('token', token);
  }

  async get<T = any>(url: string, config?: any): Promise<ApiResponse<T>> {
    const response = await this.client.get<ApiResponse<T>>(url, config);
    return response.data;
  }

  async post<T = any>(url: string, data?: any, config?: any): Promise<ApiResponse<T>> {
    const response = await this.client.post<ApiResponse<T>>(url, data, config);
    return response.data;
  }

  async patch<T = any>(url: string, data?: any, config?: any): Promise<ApiResponse<T>> {
    const response = await this.client.patch<ApiResponse<T>>(url, data, config);
    return response.data;
  }

  async delete<T = any>(url: string, config?: any): Promise<ApiResponse<T>> {
    const response = await this.client.delete<ApiResponse<T>>(url, config);
    return response.data;
  }
}

export const apiClient = new ApiClient();
