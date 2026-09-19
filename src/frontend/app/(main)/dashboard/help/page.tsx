'use client';

import { useEffect, useMemo, useState } from 'react';
import { Bell, HelpCircle, MessageSquare, Search } from 'lucide-react';
import DashboardPageHeader from '@/components/dashboard/DashboardPageHeader';
import FeedbackForm from '@/components/feedback/FeedbackForm';
import NotificationList from '@/components/feedback/NotificationList';
import { FAQ_ITEMS } from '@/lib/content/faq';
import { useNotificationStore } from '@/stores/notificationStore';

export default function DashboardHelpPage() {
  const [showFeedback, setShowFeedback] = useState(false);
  const [messageQuery, setMessageQuery] = useState('');
  const [faqQuery, setFaqQuery] = useState('');
  const [unreadOnly, setUnreadOnly] = useState(false);
  const { fetchFirstPage, unreadCount } = useNotificationStore();

  useEffect(() => {
    const isUiPreview =
      process.env.NODE_ENV === 'development' &&
      typeof window !== 'undefined' &&
      new URLSearchParams(window.location.search).get('ui_preview') === '1';
    if (isUiPreview) {
      useNotificationStore.setState({
        unreadCount: 2,
        total: 3,
        isLoading: false,
        items: [
          {
            id: 'preview-report',
            type: 'announcement',
            title: '你的职业探索报告已完成审核',
            content: '报告已经可以查看。你可以从“当前进度”进入对应旅程，回看报告内容。',
            read_at: null,
            related_feedback_id: null,
            created_at: new Date().toISOString(),
          },
          {
            id: 'preview-progress',
            type: 'announcement',
            title: '继续你的 OpenLife 探索',
            content: '上次的对话已经自动保存，可以随时回到个人空间继续。',
            read_at: null,
            related_feedback_id: null,
            created_at: new Date(Date.now() - 86400000).toISOString(),
          },
          {
            id: 'preview-feedback',
            type: 'feedback_status_changed',
            title: '反馈处理进度更新',
            content: '你提交的问题已经进入处理流程，我们会通过站内信和邮箱同步结果。',
            read_at: new Date().toISOString(),
            related_feedback_id: 'preview',
            created_at: new Date(Date.now() - 172800000).toISOString(),
          },
        ],
      });
      return;
    }
    void fetchFirstPage();
  }, [fetchFirstPage]);

  const visibleFaqs = useMemo(() => {
    const query = faqQuery.trim().toLocaleLowerCase();
    if (!query) return FAQ_ITEMS;
    return FAQ_ITEMS.filter((item) => `${item.q}\n${item.a}`.toLocaleLowerCase().includes(query));
  }, [faqQuery]);

  return (
    <div className="ol-profile-content">
      <DashboardPageHeader
        kicker="MESSAGE & SUPPORT"
        title="消息与帮助"
        description="查看与你的探索相关的通知，也可以从常见问题中找到答案。"
        action={<span className="ol-support-count"><b>{unreadCount}</b>&nbsp;条未读</span>}
      />

      <section className="ol-support-root ol-profile-surface">
        <header className="ol-support-intro">
          <div>
            <span className="ol-support-intro-icon"><MessageSquare aria-hidden="true" /></span>
            <div>
              <strong>属于你的消息中心</strong>
              <small>阅读通知、查找答案，或把遇到的问题告诉我们。</small>
            </div>
          </div>
          <button type="button" className="ol-profile-primary" onClick={() => setShowFeedback((value) => !value)}>
            {showFeedback ? '返回消息与帮助' : '提交反馈'} <span aria-hidden="true">→</span>
          </button>
        </header>

        {showFeedback ? (
          <section className="ol-support-feedback" aria-label="提交反馈">
            <FeedbackForm onSubmitted={() => setShowFeedback(false)} />
          </section>
        ) : (
          <div className="ol-support-grid">
            <section className="ol-support-card" aria-labelledby="dashboard-inbox-title">
              <header className="ol-support-card-head">
                <span><Bell aria-hidden="true" /></span>
                <div>
                  <h3 id="dashboard-inbox-title">我的站内信</h3>
                  <p>探索进度、报告与账户通知</p>
                </div>
                <span className="ol-support-count"><b>{unreadCount}</b>&nbsp;条未读</span>
              </header>
              <div className="ol-support-toolbar">
                <label className="ol-support-search">
                  <Search aria-hidden="true" />
                  <span className="sr-only">搜索站内信</span>
                  <input
                    type="search"
                    value={messageQuery}
                    onChange={(event) => setMessageQuery(event.target.value)}
                    placeholder="搜索标题或内容"
                  />
                </label>
                <div className="ol-support-filters" role="group" aria-label="站内信筛选">
                  <button type="button" aria-pressed={!unreadOnly} onClick={() => setUnreadOnly(false)}>全部</button>
                  <button type="button" aria-pressed={unreadOnly} onClick={() => setUnreadOnly(true)}>未读</button>
                </div>
              </div>
              <div className="ol-support-message-list">
                <NotificationList query={messageQuery} unreadOnly={unreadOnly} />
              </div>
            </section>

            <section className="ol-support-card" aria-labelledby="dashboard-faq-title">
              <header className="ol-support-card-head">
                <span><HelpCircle aria-hidden="true" /></span>
                <div>
                  <h3 id="dashboard-faq-title">常见问题</h3>
                  <p>与首页保持一致，随时查阅</p>
                </div>
              </header>
              <label className="ol-support-search">
                <Search aria-hidden="true" />
                <span className="sr-only">搜索常见问题</span>
                <input
                  type="search"
                  value={faqQuery}
                  onChange={(event) => setFaqQuery(event.target.value)}
                  placeholder="搜索一个问题"
                />
              </label>
              <div className="ol-support-faq-list">
                {visibleFaqs.map((item) => (
                  <details key={item.q}>
                    <summary>{item.q}<span aria-hidden="true">＋</span></summary>
                    <p>{item.a}</p>
                  </details>
                ))}
                {visibleFaqs.length === 0 && <p className="ol-support-empty">没有找到相关问题</p>}
              </div>
            </section>
          </div>
        )}
      </section>
    </div>
  );
}
