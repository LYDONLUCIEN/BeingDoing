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
          className="suggestion-tags__item px-3 py-1.5 rounded-full text-sm
                     bg-primary-500/15 border border-primary-500/30 text-primary-200
                     hover:bg-primary-500/25 transition-all"
        >
          {s}
        </button>
      ))}
    </div>
  );
}
