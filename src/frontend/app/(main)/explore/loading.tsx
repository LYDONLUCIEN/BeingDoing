export default function ExploreLoading() {
  return (
    <div className="flex min-h-[60vh] items-center justify-center">
      <div className="flex flex-col items-center gap-3">
        <div className="h-8 w-8 animate-spin rounded-full border-2 border-primary-400 border-t-transparent" />
        <p className="text-sm text-white/50">正在准备探索旅程…</p>
      </div>
    </div>
  );
}
