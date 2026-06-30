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
  private refreshClient: AxiosInstance;
  private refreshPromise: Promise<string | null> | null = null;

  /**
   * 暴露底层 axios 实例，用于需要原始响应的场景（如 blob/文件下载，
   * 需要 Content-Disposition 头取文件名，post/get 包装方法会解包 response.data）。
   * 调用方需自行处理 responseType、headers 读取与 Blob 下载。
   */
  get raw(): AxiosInstance {
    return this.client;
  }

  constructor() {
    this.client = axios.create({
      baseURL: API_BASE,
      withCredentials: true,
      headers: {
        'Content-Type': 'application/json',
      },
    });
    this.refreshClient = axios.create({
      baseURL: API_BASE,
      withCredentials: true,
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
      async (error: AxiosError) => {
        if (error.response?.status === 401) {
          const requestUrl = error.config?.url ?? '';
          const isAuthRequest =
            typeof requestUrl === 'string' &&
            (
              requestUrl.includes('/auth/login') ||
              requestUrl.includes('/auth/register') ||
              requestUrl.includes('/auth/refresh')
            );
          const originalConfig = (error.config || {}) as any;
          if (!isAuthRequest && !originalConfig._retry) {
            originalConfig._retry = true;
            const nextAccessToken = await this.refreshAccessTokenSingleFlight();
            if (nextAccessToken) {
              originalConfig.headers = originalConfig.headers || {};
              originalConfig.headers.Authorization = `Bearer ${nextAccessToken}`;
              return this.client.request(originalConfig);
            }
          }
          if (!isAuthRequest && typeof window !== 'undefined') {
            this.clearTokens();
            useAuthStore.getState().logout();
            // 会话失效后重新登录：回到当前页面
            emitAuthRequired(window.location.pathname || '/');
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

  private clearTokens(): void {
    if (typeof window === 'undefined') return;
    localStorage.removeItem('token');
  }

  setToken(token: string): void {
    if (typeof window === 'undefined') return;
    localStorage.setItem('token', token);
  }

  setTokens(accessToken: string): void {
    if (typeof window === 'undefined') return;
    localStorage.setItem('token', accessToken);
  }

  private async refreshAccessTokenSingleFlight(): Promise<string | null> {
    if (this.refreshPromise) {
      return this.refreshPromise;
    }

    this.refreshPromise = (async () => {
      try {
        const response = await this.refreshClient.post<ApiResponse<{
          token: string;
          expires_in: number;
        }>>('/auth/refresh', {});
        const data = response.data?.data;
        if (!data?.token) {
          return null;
        }
        this.setToken(data.token);
        const authStore = useAuthStore.getState();
        authStore.setTokens(data.token);
        return data.token;
      } catch {
        return null;
      } finally {
        this.refreshPromise = null;
      }
    })();

    return this.refreshPromise;
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
