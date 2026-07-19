import { create } from 'zustand';
import {
  getUnreadCount,
  listNotifications,
  markAllNotificationsRead,
  markNotificationRead,
  type Notification,
} from '@/lib/api/feedback';

interface NotificationState {
  unreadCount: number;
  items: Notification[];
  total: number;
  page: number;
  pageSize: number;
  isLoading: boolean;
  isOpen: boolean;

  // 动作
  refreshUnreadCount: () => Promise<void>;
  fetchFirstPage: () => Promise<void>;
  openWidget: () => Promise<void>;
  closeWidget: () => void;
  markRead: (id: string) => Promise<void>;
  markAllRead: () => Promise<void>;
}

export const useNotificationStore = create<NotificationState>((set, get) => ({
  unreadCount: 0,
  items: [],
  total: 0,
  page: 1,
  pageSize: 20,
  isLoading: false,
  isOpen: false,

  refreshUnreadCount: async () => {
    try {
      const count = await getUnreadCount();
      set({ unreadCount: count });
    } catch (e) {
      // 未登录或网络错误，静默
    }
  },

  fetchFirstPage: async () => {
    set({ isLoading: true });
    try {
      const data = await listNotifications({ page: 1, page_size: 20 });
      set({
        items: data.items,
        total: data.total,
        unreadCount: data.unread_count,
        page: 1,
        pageSize: data.page_size,
        isLoading: false,
      });
    } catch (e) {
      set({ isLoading: false });
    }
  },

  openWidget: async () => {
    set({ isOpen: true });
    await get().fetchFirstPage();
  },

  closeWidget: () => set({ isOpen: false }),

  markRead: async (id: string) => {
    // 乐观更新
    set((s) => ({
      items: s.items.map((n) =>
        n.id === id && n.read_at === null ? { ...n, read_at: new Date().toISOString() } : n
      ),
      unreadCount: Math.max(0, s.unreadCount - 1),
    }));
    try {
      await markNotificationRead(id);
    } catch (e) {
      // 回滚由下次 fetchFirstPage 修正
    }
  },

  markAllRead: async () => {
    set((s) => ({
      items: s.items.map((n) =>
        n.read_at === null ? { ...n, read_at: new Date().toISOString() } : n
      ),
      unreadCount: 0,
    }));
    try {
      await markAllNotificationsRead();
    } catch (e) {
      // 静默
    }
  },
}));
