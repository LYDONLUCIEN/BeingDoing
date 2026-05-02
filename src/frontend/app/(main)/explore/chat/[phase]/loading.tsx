export default function ChatLoading() {
  return (
    <div className="flex min-h-[70vh] items-center justify-center">
      <div className="flex flex-col items-center gap-3">
        <div className="h-8 w-8 animate-spin rounded-full border-2 border-primary-400 border-t-transparent" />
        <p className="text-sm text-white/50">正在加载对话…</p>
      </div>
    </div>
  );
}
