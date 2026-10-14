'use client';

import { useEffect, useRef, type ReactNode } from 'react';
import { Menu, X } from 'lucide-react';
import { useMobileLayout } from '@/hooks/useMobileLayout';

/** 同一份侧栏在桌面常驻、手机进入原生模态抽屉；原生 dialog 负责焦点与背景隔离。 */
export default function ResponsiveSidebar({ children, label, open, onOpen, onClose }: {
  children: ReactNode;
  label: string;
  open: boolean;
  onOpen: () => void;
  onClose: () => void;
}) {
  const mobile = useMobileLayout();
  const dialogRef = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const dialog = dialogRef.current;
    if (!dialog) return;
    if (open && !dialog.open) dialog.showModal();
    if (!open && dialog.open) dialog.close();
  }, [open, mobile]);
  useEffect(() => {
    if (!mobile) onClose();
  }, [mobile, onClose]);

  if (!mobile) return <div className="workspace-sidebar-desktop">{children}</div>;
  return (
    <>
      <button type="button" className="workspace-sidebar-toggle" aria-label={`打开${label}`}
        aria-expanded={open} onClick={onOpen}><Menu size={20} /></button>
      <dialog ref={dialogRef} className="workspace-sidebar-dialog" aria-label={label}
        onCancel={onClose} onClose={onClose}
        onClick={(event) => { if (event.target === event.currentTarget) onClose(); }}>
        <div className="workspace-sidebar-panel">
          <div className="workspace-sidebar-heading"><span>{label}</span>
            <button type="button" aria-label={`关闭${label}`} onClick={onClose}><X size={20} /></button>
          </div>
          {children}
        </div>
      </dialog>
    </>
  );
}
