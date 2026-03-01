'use client';

import { useState, useEffect } from 'react';
import { priorContextApi } from '@/lib/api/survey';

interface PriorContextPanelProps {
  activationCode: string;
  phase: string;
  phaseLabel: string;
  previousPhaseLabel: string;
}

/**
 * 允许用户上传或粘贴上一轮咨询结果的面板。
 * 对 strengths 阶段，显示 values 谈话结果上传区。
 * 对 interests_goals 阶段，显示 strengths+values 谈话结果上传区。
 */
export default function PriorContextPanel({
  activationCode,
  phase,
  phaseLabel,
  previousPhaseLabel,
}: PriorContextPanelProps) {
  const [text, setText] = useState('');
  const [loaded, setLoaded] = useState(false);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [expanded, setExpanded] = useState(false);

  // 加载已有内容
  useEffect(() => {
    if (!activationCode) return;
    let cancelled = false;
    (async () => {
      try {
        const res = await priorContextApi.getForActivation(activationCode, phase);
        if (!cancelled && res.data?.context_text) {
          setText(res.data.context_text);
        }
      } catch {
        // 静默失败
      } finally {
        if (!cancelled) setLoaded(true);
      }
    })();
    return () => { cancelled = true; };
  }, [activationCode, phase]);

  const handleSave = async () => {
    setSaving(true);
    setError(null);
    setSaved(false);
    try {
      await priorContextApi.saveForActivation(activationCode, phase, text);
      setSaved(true);
      setTimeout(() => setSaved(false), 3000);
    } catch (e: any) {
      setError(e?.message || '保存失败');
    } finally {
      setSaving(false);
    }
  };

  const handleFileUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = (ev) => {
      setText(ev.target?.result as string ?? '');
    };
    reader.readAsText(file, 'utf-8');
    // Reset input so same file can be re-uploaded
    e.target.value = '';
  };

  return (
    <div className="rounded-lg border border-white/10 bg-white/5 text-sm">
      <button
        type="button"
        onClick={() => setExpanded((v) => !v)}
        className="w-full flex items-center justify-between px-4 py-3 text-left text-white/80 hover:bg-white/5 transition-colors rounded-lg"
      >
        <span className="font-medium">
          {phaseLabel}阶段：上一轮咨询结果（{previousPhaseLabel}）
        </span>
        <span className="text-white/40 text-xs ml-2">
          {text.trim() ? '已有内容' : '未上传'}
          {expanded ? ' ▲' : ' ▼'}
        </span>
      </button>

      {expanded && (
        <div className="px-4 pb-4 space-y-3">
          <p className="text-xs text-white/50">
            将上一轮咨询的谈话总结粘贴到下方，或上传文本文件，AI 将参考这些内容为你提供更连贯的咨询。
          </p>
          <textarea
            rows={8}
            value={text}
            onChange={(e) => setText(e.target.value)}
            placeholder={`请将${previousPhaseLabel}咨询结果粘贴到此处……`}
            className="w-full resize-y rounded-md border border-white/15 bg-slate-900/70 px-3 py-2 text-white/90 placeholder-white/30 outline-none focus:border-primary-400 text-xs leading-relaxed"
          />
          <div className="flex flex-wrap items-center gap-2">
            <button
              type="button"
              onClick={handleSave}
              disabled={saving}
              className="rounded-md bg-primary-500 px-3 py-1.5 text-xs font-medium text-white hover:bg-primary-400 disabled:opacity-50 transition-colors"
            >
              {saving ? '保存中…' : saved ? '已保存 ✓' : '保存'}
            </button>
            <label className="rounded-md border border-white/20 px-3 py-1.5 text-xs font-medium text-white/80 hover:bg-white/5 transition-colors cursor-pointer">
              上传文本文件
              <input type="file" accept=".txt,.md" className="hidden" onChange={handleFileUpload} />
            </label>
            {text.trim() && (
              <button
                type="button"
                onClick={() => { setText(''); setSaved(false); }}
                className="text-xs text-white/40 hover:text-white/70 transition-colors"
              >
                清除
              </button>
            )}
            {error && <span className="text-xs text-rose-400">{error}</span>}
          </div>
        </div>
      )}
    </div>
  );
}
