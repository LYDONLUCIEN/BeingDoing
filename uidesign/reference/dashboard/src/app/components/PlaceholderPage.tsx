import { LucideIcon } from 'lucide-react';

interface PlaceholderPageProps {
  title: string;
  description: string;
  icon: LucideIcon;
}

export function PlaceholderPage({ title, description, icon: Icon }: PlaceholderPageProps) {
  return (
    <div className="max-w-4xl">
      <div className="bg-white/60 backdrop-blur-lg border border-gray-200/50 rounded-3xl p-12 shadow-sm text-center">
        <div className="w-20 h-20 mx-auto mb-6 rounded-full bg-gradient-to-br from-[#A2C2E8] to-[#B5D8C6] flex items-center justify-center">
          <Icon className="w-10 h-10 text-white" />
        </div>
        <h1 className="text-3xl font-semibold text-[#1d1d1f] mb-4">{title}</h1>
        <p className="text-gray-600 text-lg">{description}</p>
      </div>
    </div>
  );
}
