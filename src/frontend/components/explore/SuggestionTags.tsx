'use client';

interface SuggestionTagsProps {
  suggestions: string[];
  onSelect: (suggestion: string) => void;
  className?: string;
}

export default function SuggestionTags({
  suggestions,
  onSelect,
  className = '',
}: SuggestionTagsProps) {
  if (suggestions.length === 0) return null;

  return (
    <div className={`suggestion-tags flex flex-wrap gap-2 ${className}`}>
      {suggestions.map((s, i) => (
        <button
          key={i}
          type="button"
          onClick={() => onSelect(s)}
          className="suggestion-tags__item px-3 py-1.5 rounded-full text-sm transition-all hover:opacity-90"
          style={{
            background: 'var(--bd-ui-accent-dim, rgba(167,139,250,0.15))',
            border: '1px solid rgba(167,139,250,0.35)',
            color: 'var(--bd-ui-accent, #a78bfa)',
          }}
        >
          {s}
        </button>
      ))}
    </div>
  );
}
