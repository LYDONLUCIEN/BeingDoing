'use client';

import { forwardRef, useImperativeHandle, useRef, useState } from 'react';
import { ImagePlus, Trash2, Loader2 } from 'lucide-react';
import { uploadAttachment, deleteAttachment, type AttachmentUploadResult } from '@/lib/api/feedback';
import { getApiErrorMessage } from '@/lib/api/client';

const MAX_SIZE = 2 * 1024 * 1024; // 2MB
const MAX_COUNT = 3;
const ACCEPT = 'image/jpeg,image/png,image/webp';

export interface AttachmentUploaderHandle {
  /** 供外部（如粘贴事件）直接添加图片文件 */
  addFiles: (files: File[]) => void;
}

interface Props {
  attachmentIds: string[];
  onChange: (ids: string[]) => void;
}

interface Item {
  id: string;
  preview_url: string;
  status: 'uploading' | 'done' | 'error';
  error?: string;
}

const AttachmentUploader = forwardRef<AttachmentUploaderHandle, Props>(
  function AttachmentUploader({ attachmentIds, onChange }, ref) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [items, setItems] = useState<Item[]>([]);

  const handlePick = () => {
    if (items.filter((i) => i.status !== 'error').length >= MAX_COUNT) return;
    inputRef.current?.click();
  };

  const handleFile = async (file: File) => {
    // 前端校验
    if (!['image/jpeg', 'image/png', 'image/webp'].includes(file.type)) {
      alert('仅支持 jpg/png/webp 格式');
      return;
    }
    if (file.size > MAX_SIZE) {
      alert('图片大小不能超过 2MB');
      return;
    }
    if (items.filter((i) => i.status !== 'error').length >= MAX_COUNT) {
      alert(`最多 ${MAX_COUNT} 张截图`);
      return;
    }

    // 占位
    const placeholderId = `temp-${Date.now()}`;
    setItems((arr) => [
      ...arr,
      { id: placeholderId, preview_url: '', status: 'uploading' },
    ]);

    try {
      const result: AttachmentUploadResult = await uploadAttachment(file);
      setItems((arr) =>
        arr
          .map((it) =>
            it.id === placeholderId
              ? {
                  id: result.id,
                  preview_url: result.preview_url,
                  status: 'done' as const,
                }
              : it
          )
      );
      onChange([...attachmentIds.filter((id) => id), result.id]);
    } catch (e) {
      const msg = getApiErrorMessage(e, '上传失败');
      setItems((arr) =>
        arr.map((it) =>
          it.id === placeholderId ? { ...it, status: 'error', error: msg } : it
        )
      );
    }
  };

  const handleRemove = async (item: Item) => {
    // 乐观删除
    setItems((arr) => arr.filter((it) => it.id !== item.id));
    onChange(attachmentIds.filter((id) => id !== item.id));
    // 后端清理（已上传的删除 OSS 文件）
    if (item.status === 'done' && !item.id.startsWith('temp-')) {
      try {
        await deleteAttachment(item.id);
      } catch {
        // 静默：孤儿清理任务会兜底
      }
    }
  };

  const handleInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(e.target.files || []);
    files.forEach(handleFile);
    // 清空 input，允许重复选同一文件
    e.target.value = '';
  };

  // 暴露给父组件：粘贴图片时直接走同一套上传流程
  useImperativeHandle(ref, () => ({
    addFiles: (files: File[]) => {
      files.forEach(handleFile);
    },
  }));

  const validCount = items.filter((i) => i.status !== 'error').length;
  const canAdd = validCount < MAX_COUNT;

  return (
    <div>
      <div className="flex flex-wrap gap-2">
        {items.map((item) => (
          <div
            key={item.id}
            className="relative w-16 h-16 rounded-xl border border-bd-border overflow-hidden bg-bd-overlay-md"
          >
            {item.status === 'uploading' ? (
              <div className="w-full h-full flex items-center justify-center">
                <Loader2 className="w-4 h-4 animate-spin text-bd-muted" />
              </div>
            ) : item.status === 'error' ? (
              <div
                className="w-full h-full flex items-center justify-center text-[9px] text-center px-1"
                style={{ color: 'var(--bd-error)' }}
                title={item.error}
              >
                失败
              </div>
            ) : (
              // eslint-disable-next-line @next/next/no-img-element
              <img
                src={item.preview_url}
                alt="截图"
                className="w-full h-full object-cover"
              />
            )}
            {item.status !== 'uploading' && (
              <button
                type="button"
                onClick={() => handleRemove(item)}
                className="absolute top-0.5 right-0.5 w-5 h-5 rounded-full bg-black/60 text-white flex items-center justify-center hover:bg-black/80"
                aria-label="删除"
              >
                <Trash2 className="w-3 h-3" />
              </button>
            )}
          </div>
        ))}

        {canAdd && (
          <button
            type="button"
            onClick={handlePick}
            className="w-16 h-16 rounded-xl border-2 border-dashed border-bd-border hover:border-bd-ui-accent hover:bg-bd-overlay-md transition-colors flex flex-col items-center justify-center"
            style={{ color: 'var(--bd-fg-muted)' }}
          >
            <ImagePlus className="w-4 h-4 mb-0.5" />
            <span className="text-[9px]">添加截图</span>
          </button>
        )}
      </div>
      <p className="text-[10px] mt-1.5 text-bd-subtle">
        可选，最多 {MAX_COUNT} 张，单张 ≤ 2MB（jpg/png/webp），也可在下方输入框直接粘贴截图
      </p>

      <input
        ref={inputRef}
        type="file"
        accept={ACCEPT}
        multiple
        className="hidden"
        onChange={handleInputChange}
      />
    </div>
  );
  }
);

export default AttachmentUploader;
