'use client';

interface DebugPanelProps {
  isOpen: boolean;
  debugEntries: any[];
  onClose: () => void;
}

export default function DebugPanel({ isOpen, debugEntries, onClose }: DebugPanelProps) {
  if (!isOpen) return null;

  return (
    <div className="fixed bottom-4 right-4 w-[460px] max-h-[60vh] z-30 bg-slate-900/95 flex flex-col border border-white/20 rounded-xl shadow-xl">
      <div className="flex items-center justify-between px-3 py-2 border-b border-white/10">
        <h2 className="text-sm font-semibold text-white/90">调试日志（智能体判断与调用链）</h2>
        <button
          type="button"
          onClick={onClose}
          className="px-3 py-1 rounded-lg bg-white/10 hover:bg-white/20 text-xs"
        >
          关闭
        </button>
      </div>
      <pre className="flex-1 overflow-auto p-3 text-xs text-white/90 whitespace-pre-wrap font-mono">
        {debugEntries.length === 0
          ? '暂无日志'
          : JSON.stringify(debugEntries, null, 2)}
      </pre>
    </div>
  );
}
