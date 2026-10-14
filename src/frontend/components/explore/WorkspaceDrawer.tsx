'use client';

import { useEffect, useRef, type ReactNode } from 'react';

/** 窄桌面辅助面板：只有用户打开时覆盖工作区，原生 dialog 管理焦点与 Escape。 */
export default function WorkspaceDrawer({ label, open, onClose, children }: {
  label: string; open: boolean; onClose: () => void; children: ReactNode;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const dialog = ref.current;
    if (!dialog) return;
    if (open && !dialog.open) dialog.showModal();
    else if (!open && dialog.open) dialog.close();
  }, [open]);
  return <dialog ref={ref} aria-label={label} onCancel={onClose} onClose={onClose}
    onClick={e => { if (e.target === e.currentTarget) onClose(); }}
    className="m-auto h-[min(90vh,850px)] max-h-[90vh] w-[min(440px,92vw)] max-w-none rounded-2xl border border-bd-border bg-white p-0 text-bd-text shadow-xl backdrop:bg-black/25">
    <div className="flex h-full min-h-0 flex-col">
      <div className="flex shrink-0 items-center justify-between border-b border-bd-border px-4 py-2"><b>{label}</b><button className="min-h-11 rounded-lg px-3" type="button" onClick={onClose} aria-label={`关闭${label}`}>完成并收起</button></div>
      <div className="flex min-h-0 flex-1 flex-col overflow-auto">{children}</div>
    </div>
  </dialog>;
}
