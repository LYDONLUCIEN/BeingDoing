'use client';

/**
 * Admin 复核 Markdown 编辑器（2026-09-14）
 *
 * - 双版本 tab：当前版本（正式缓存）/ 重新生成版（staging，无新稿时置灰）
 * - 按 H2 标题分章查看与编辑（textarea + MarkdownPreview 实时渲染预览，非 PDF）
 * - 编辑仅存前端；「下载 .md」本地导出当前编辑稿；
 * - 「发布此版本」把编辑内容整体提交为正式缓存，未被选择的版本由后端自动清除
 */

import { useCallback, useEffect, useMemo, useState } from 'react';
import MarkdownPreview from '@uiw/react-markdown-preview';
import { Loader2, Download, Send } from 'lucide-react';
import {
  fetchAdminRecheckMarkdown,
  publishAdminRecheckEdited,
  type RecheckMarkdownVersion,
} from '@/lib/api/admin';

interface RecheckMarkdownEditorProps {
  reportId: string;
  hasStaging: boolean;
  /** 重新生成中或面板有其他操作进行时禁用交互 */
  disabled?: boolean;
  /** 发布成功后回调（父组件关闭面板并刷新列表） */
  onPublished: () => void;
}

interface Chapter {
  title: string;
  content: string;
}

/** 按 H2 标题切章；H2 前的内容归为「开头」章 */
function splitChapters(markdown: string): Chapter[] {
  const parts = markdown.split(/(?=^## )/m);
  return parts
    .filter((p) => p.trim().length > 0)
    .map((p, i) => {
      const firstLine = p.split('\n', 1)[0].trim();
      const title = firstLine.startsWith('## ')
        ? firstLine.replace(/^##\s+/, '')
        : i === 0
          ? '开头'
          : `片段 ${i + 1}`;
      return { title, content: p };
    });
}

const VERSION_LABEL: Record<RecheckMarkdownVersion, string> = {
  original: '当前版本',
  staging: '重新生成版',
};

export default function RecheckMarkdownEditor({
  reportId,
  hasStaging,
  disabled = false,
  onPublished,
}: RecheckMarkdownEditorProps) {
  const [version, setVersion] = useState<RecheckMarkdownVersion>('original');
  /** 各版本的章节编辑稿（拉取后缓存，编辑只改这里） */
  const [docs, setDocs] = useState<Partial<Record<RecheckMarkdownVersion, Chapter[]>>>({});
  const [originals, setOriginals] = useState<Partial<Record<RecheckMarkdownVersion, string>>>({});
  const [loading, setLoading] = useState(false);
  const [publishing, setPublishing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [activeChapter, setActiveChapter] = useState(0);
  /** 跟随站点明暗主题（与 chat 页 MessageContent 同方案） */
  const [colorMode, setColorMode] = useState<'dark' | 'light'>('dark');

  useEffect(() => {
    setColorMode(document.documentElement.classList.contains('dark') ? 'dark' : 'light');
  }, []);

  const loadVersion = useCallback(
    async (v: RecheckMarkdownVersion) => {
      if (docs[v]) return;
      setLoading(true);
      setError(null);
      try {
        const md = await fetchAdminRecheckMarkdown(reportId, v);
        setDocs((prev) => ({ ...prev, [v]: splitChapters(md) }));
        setOriginals((prev) => ({ ...prev, [v]: md }));
        setActiveChapter(0);
      } catch (e: any) {
        setError(e?.response?.data?.detail || e?.message || '加载 markdown 失败');
      } finally {
        setLoading(false);
      }
    },
    [docs, reportId],
  );

  useEffect(() => {
    void loadVersion('original');
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [reportId]);

  const chapters = docs[version] ?? null;
  const assembled = useMemo(
    () => (chapters ? chapters.map((c) => c.content).join('') : ''),
    [chapters],
  );
  const dirty = originals[version] != null && assembled !== originals[version];

  const switchVersion = (v: RecheckMarkdownVersion) => {
    setVersion(v);
    setActiveChapter(0);
    void loadVersion(v);
  };

  const updateChapter = (index: number, content: string) => {
    setDocs((prev) => {
      const list = prev[version];
      if (!list) return prev;
      const next = [...list];
      next[index] = { ...next[index], content };
      return { ...prev, [version]: next };
    });
  };

  const handleDownload = () => {
    const blob = new Blob([assembled], { type: 'text/markdown;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `报告_${reportId}_${version}.md`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const handlePublish = async () => {
    if (
      !window.confirm(
        `确认发布「${VERSION_LABEL[version]}」的编辑内容吗？\n` +
          '发布后该内容将覆盖正式报告（旧版自动备份），并通过站内信+邮件通知用户；\n' +
          '未被选择的版本将被自动清除。',
      )
    ) {
      return;
    }
    setPublishing(true);
    setError(null);
    try {
      await publishAdminRecheckEdited(reportId, version, assembled);
      onPublished();
    } catch (e: any) {
      setError(e?.response?.data?.detail || e?.message || '发布失败');
    } finally {
      setPublishing(false);
    }
  };

  return (
    <div className="rounded-xl border border-bd-border bg-bd-overlay p-4 space-y-3">
      {/* 版本 tab */}
      <div className="flex items-center gap-2 text-xs">
        {(['original', 'staging'] as RecheckMarkdownVersion[]).map((v) => (
          <button
            key={v}
            type="button"
            onClick={() => switchVersion(v)}
            disabled={disabled || (v === 'staging' && !hasStaging)}
            className={`px-3 py-1.5 rounded-lg border transition-colors disabled:opacity-50 disabled:cursor-not-allowed ${
              version === v
                ? 'border-[var(--bd-ui-accent)] bg-bd-overlay-md text-bd-fg font-medium'
                : 'border-bd-border text-bd-muted hover:bg-bd-overlay-md'
            }`}
          >
            {VERSION_LABEL[v]}
            {v === 'staging' && !hasStaging && '（未生成）'}
          </button>
        ))}
        {dirty && <span className="text-amber-600">已修改（未发布）</span>}
        <span className="ml-auto flex items-center gap-2">
          <button
            type="button"
            onClick={handleDownload}
            disabled={disabled || !chapters || publishing}
            className="inline-flex items-center gap-1 px-3 py-1.5 rounded-lg border border-bd-border text-bd-fg hover:bg-bd-overlay-md disabled:opacity-60"
          >
            <Download size={12} />
            下载 .md
          </button>
          <button
            type="button"
            onClick={handlePublish}
            disabled={disabled || !chapters || publishing}
            className="inline-flex items-center gap-1 px-3 py-1.5 rounded-lg border border-emerald-300 bg-emerald-50 text-emerald-700 hover:bg-emerald-100 disabled:opacity-60 disabled:cursor-not-allowed"
          >
            {publishing ? <Loader2 size={12} className="animate-spin" /> : <Send size={12} />}
            {publishing ? '发布中...' : '发布此版本'}
          </button>
        </span>
      </div>

      {error && <p className="text-xs text-red-600">{error}</p>}

      {loading ? (
        <p className="text-xs text-bd-subtle flex items-center gap-2 py-6 justify-center">
          <Loader2 size={14} className="animate-spin" /> 加载 markdown...
        </p>
      ) : !chapters ? (
        <p className="text-xs text-bd-subtle py-4 text-center">该版本暂无内容</p>
      ) : (
        <>
          {/* 章节 tab */}
          <div className="flex flex-wrap gap-1.5 text-[11px]">
            {chapters.map((c, i) => (
              <button
                key={i}
                type="button"
                onClick={() => setActiveChapter(i)}
                className={`px-2 py-1 rounded-md border truncate max-w-[160px] ${
                  activeChapter === i
                    ? 'border-[var(--bd-ui-accent)] bg-bd-overlay-md text-bd-fg'
                    : 'border-bd-border text-bd-subtle hover:bg-bd-overlay-md'
                }`}
                title={c.title}
              >
                {c.title}
              </button>
            ))}
          </div>

          {/* 编辑 + 预览 */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            <textarea
              value={chapters[activeChapter]?.content ?? ''}
              onChange={(e) => updateChapter(activeChapter, e.target.value)}
              disabled={disabled || publishing}
              spellCheck={false}
              className="w-full h-72 rounded-lg border border-bd-border bg-bd-card px-3 py-2 text-xs font-mono text-bd-fg focus:outline-none focus:border-[var(--bd-ui-accent)] disabled:opacity-60"
            />
            <div className="h-72 overflow-auto rounded-lg border border-bd-border bg-bd-card px-3 py-2">
              <MarkdownPreview
                source={chapters[activeChapter]?.content ?? ''}
                wrapperElement={{ 'data-color-mode': colorMode }}
                style={{ backgroundColor: 'transparent', fontSize: 12, color: 'inherit' }}
              />
            </div>
          </div>
        </>
      )}
    </div>
  );
}
