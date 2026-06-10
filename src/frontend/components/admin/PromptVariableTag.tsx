'use client';

interface PromptVariableTagProps {
  name: string;
  sample?: string;
}

export function PromptVariableTag({ name, sample }: PromptVariableTagProps) {
  return (
    <span className="relative group inline-flex align-baseline">
      <code className="mx-0.5 px-1.5 py-0.5 rounded-md text-[11px] font-mono bg-sky-100 text-sky-800 border border-sky-200 cursor-help">
        {'{{ '}
        {name}
        {' }}'}
      </code>
      {sample ? (
        <span
          role="tooltip"
          className="pointer-events-none absolute left-0 bottom-full z-20 mb-1 hidden w-72 max-w-[90vw] rounded-lg border border-bd-border bg-bd-card px-2.5 py-2 text-[10px] leading-relaxed text-bd-fg shadow-lg group-hover:block"
        >
          <span className="block text-bd-subtle mb-1">示例值</span>
          <pre className="whitespace-pre-wrap font-mono text-[10px] text-bd-muted">{sample}</pre>
        </span>
      ) : null}
    </span>
  );
}
