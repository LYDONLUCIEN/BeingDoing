import { useState } from 'react';
import { Check, Clock, Lock } from 'lucide-react';

interface CurrentProgressProps {
  language: 'en' | 'zh';
}

interface PathNode {
  id: string;
  label: { en: string; zh: string };
  status: 'completed' | 'in-progress' | 'incomplete';
}

interface ProgressEntry {
  id: string;
  title: { en: string; zh: string };
  startDate: string;
  lastEditedTime: number; // timestamp for sorting
  nodes: PathNode[];
}

export function CurrentProgress({ language }: CurrentProgressProps) {
  const text = {
    en: {
      title: 'Current Progress',
      journeyTitle: 'My Career Journey',
      startDate: 'Started',
      lastEdited: 'Last edited',
      viewDetails: 'View Details',
      previousEntries: 'Previous Progress Entries',
    },
    zh: {
      title: '当前进度',
      journeyTitle: '我的职业旅程',
      startDate: '开始时间',
      lastEdited: '最后编辑',
      viewDetails: '查看详情',
      previousEntries: '之前的进度记录',
    },
  };

  const t = text[language];

  // Mock data - multiple progress entries with different statuses
  const [progressEntries] = useState<ProgressEntry[]>([
    {
      id: '3',
      title: { en: 'My Career Journey', zh: '我的职业旅程' },
      startDate: 'March 7, 2026',
      lastEditedTime: Date.now(),
      nodes: [
        { id: 'value', label: { en: 'Value', zh: '底色' }, status: 'completed' },
        { id: 'strengths', label: { en: 'Strengths', zh: '天赋' }, status: 'completed' },
        { id: 'passion', label: { en: 'Passion', zh: '热忱' }, status: 'in-progress' },
        { id: 'purpose', label: { en: 'Purpose', zh: '航向' }, status: 'incomplete' },
        { id: 'exploration', label: { en: 'Exploration', zh: '探索' }, status: 'incomplete' },
      ],
    },
    {
      id: '2',
      title: { en: 'Career Development Plan 2', zh: '职业发展计划 2' },
      startDate: 'March 3, 2026',
      lastEditedTime: Date.now() - 3 * 24 * 60 * 60 * 1000,
      nodes: [
        { id: 'value', label: { en: 'Value', zh: '底色' }, status: 'completed' },
        { id: 'strengths', label: { en: 'Strengths', zh: '天赋' }, status: 'completed' },
        { id: 'passion', label: { en: 'Passion', zh: '热忱' }, status: 'completed' },
        { id: 'purpose', label: { en: 'Purpose', zh: '航向' }, status: 'completed' },
        { id: 'exploration', label: { en: 'Exploration', zh: '探索' }, status: 'in-progress' },
      ],
    },
    {
      id: '1',
      title: { en: 'Initial Career Exploration', zh: '初始职业探索' },
      startDate: 'March 1, 2026',
      lastEditedTime: Date.now() - 6 * 24 * 60 * 60 * 1000,
      nodes: [
        { id: 'value', label: { en: 'Value', zh: '底色' }, status: 'completed' },
        { id: 'strengths', label: { en: 'Strengths', zh: '天赋' }, status: 'completed' },
        { id: 'passion', label: { en: 'Passion', zh: '热忱' }, status: 'incomplete' },
        { id: 'purpose', label: { en: 'Purpose', zh: '航向' }, status: 'incomplete' },
        { id: 'exploration', label: { en: 'Exploration', zh: '探索' }, status: 'incomplete' },
      ],
    },
  ]);

  // Sort by lastEditedTime and get most recent
  const sortedEntries = [...progressEntries].sort((a, b) => b.lastEditedTime - a.lastEditedTime);
  const mostRecentEntry = sortedEntries[0];
  const olderEntries = sortedEntries.slice(1);

  const [selectedEntry, setSelectedEntry] = useState<string>(mostRecentEntry.id);

  const handleNodeClick = (node: PathNode) => {
    if (node.status === 'incomplete') {
      return; // Prevent navigation for incomplete nodes
    }
    // Navigate to chat page (to be implemented)
    console.log(`Navigate to ${node.id} chat`);
  };

  const getNodeColor = (index: number) => {
    const colors = ['#A2C2E8', '#B5D8C6', '#F4B3B3', '#FDE093', '#A2C2E8'];
    return colors[index];
  };

  const getNodeIcon = (status: string) => {
    if (status === 'completed') return <Check className="w-4 h-4 text-white" />;
    if (status === 'in-progress') return <Clock className="w-4 h-4 text-white" />;
    return <Lock className="w-3 h-3 text-white" />;
  };

  const formatDate = (timestamp: number) => {
    const date = new Date(timestamp);
    return language === 'en'
      ? date.toLocaleDateString('en-US', { month: 'long', day: 'numeric', year: 'numeric' })
      : date.toLocaleDateString('zh-CN', { year: 'numeric', month: 'long', day: 'numeric' });
  };

  const renderFullProgressView = (entry: ProgressEntry) => (
    <div className="bg-white/60 backdrop-blur-lg border border-gray-200/50 rounded-3xl p-8 shadow-sm">
      <div className="mb-8">
        <h2 className="text-2xl font-medium text-[#1d1d1f] mb-2">{entry.title[language]}</h2>
        <div className="flex items-center gap-4 text-sm text-gray-500">
          <span>{t.startDate}: {entry.startDate}</span>
          <span>•</span>
          <span>{t.lastEdited}: {formatDate(entry.lastEditedTime)}</span>
        </div>
      </div>

      {/* Full Path Diagram */}
      <div className="relative">
        <div className="flex items-center justify-between gap-4">
          {entry.nodes.map((node, index) => (
            <div key={node.id} className="flex-1 flex flex-col items-center">
              {/* Node */}
              <button
                onClick={() => handleNodeClick(node)}
                disabled={node.status === 'incomplete'}
                className={`relative w-24 h-24 rounded-full flex flex-col items-center justify-center transition-all ${
                  node.status !== 'incomplete'
                    ? 'cursor-pointer hover:scale-110 hover:shadow-xl'
                    : 'cursor-not-allowed opacity-40'
                }`}
                style={{
                  backgroundColor: getNodeColor(index),
                  filter: node.status === 'incomplete' ? 'grayscale(100%)' : 'none',
                }}
              >
                {node.status !== 'incomplete' && (
                  <div
                    className={`absolute -top-1 -right-1 w-6 h-6 rounded-full flex items-center justify-center border-2 border-white ${
                      node.status === 'completed' ? 'bg-green-500' : 'bg-blue-500'
                    }`}
                  >
                    {getNodeIcon(node.status)}
                  </div>
                )}
                <span className="text-white font-medium text-sm text-center px-2">
                  {node.label[language]}
                </span>
              </button>
            </div>
          ))}
        </div>

        {/* Connection Lines */}
        <div className="absolute top-12 left-0 right-0 flex items-center justify-between px-12 -z-10">
          {entry.nodes.slice(0, -1).map((_, index) => (
            <div
              key={index}
              className="flex-1 h-0.5 bg-gradient-to-r from-gray-300 to-gray-300 mx-2"
            />
          ))}
        </div>
      </div>
    </div>
  );

  const renderThumbnailView = (entry: ProgressEntry) => (
    <div
      key={entry.id}
      onClick={() => setSelectedEntry(entry.id)}
      className="bg-white/60 backdrop-blur-lg border border-gray-200/50 rounded-xl p-4 shadow-sm hover:shadow-md transition-all cursor-pointer hover:scale-[1.02]"
    >
      <div className="mb-3">
        <h3 className="font-medium text-[#1d1d1f] mb-1 text-sm">{entry.title[language]}</h3>
        <p className="text-xs text-gray-500">{t.lastEdited}: {formatDate(entry.lastEditedTime)}</p>
      </div>

      {/* Compact Path Diagram */}
      <div className="flex items-center gap-2 mb-3">
        {entry.nodes.map((node, index) => (
          <div key={node.id} className="flex items-center gap-1">
            <div
              className="w-8 h-8 rounded-full flex items-center justify-center"
              style={{
                backgroundColor: getNodeColor(index),
                opacity: node.status === 'incomplete' ? 0.4 : 1,
              }}
            >
              {node.status !== 'incomplete' && (
                <div
                  className={`w-4 h-4 rounded-full flex items-center justify-center ${
                    node.status === 'completed' ? 'bg-green-500' : 'bg-blue-500'
                  }`}
                >
                  {node.status === 'completed' ? (
                    <Check className="w-2 h-2 text-white" />
                  ) : (
                    <Clock className="w-2 h-2 text-white" />
                  )}
                </div>
              )}
            </div>
            {index < entry.nodes.length - 1 && (
              <div className="w-2 h-0.5 bg-gray-300" />
            )}
          </div>
        ))}
      </div>

      <button className="text-xs text-blue-600 hover:text-blue-700 font-medium">
        {t.viewDetails} →
      </button>
    </div>
  );

  // Find currently selected entry to display
  const displayEntry = sortedEntries.find(e => e.id === selectedEntry) || mostRecentEntry;

  return (
    <div className="max-w-6xl">
      <h1 className="text-4xl font-semibold text-[#1d1d1f] mb-8">{t.title}</h1>

      {/* Most Recent Entry - Full View */}
      <div className="mb-8">
        {renderFullProgressView(displayEntry)}
      </div>

      {/* Older Entries - Thumbnail List */}
      {olderEntries.length > 0 && (
        <div>
          <h2 className="text-lg font-medium text-[#1d1d1f] mb-4">{t.previousEntries}</h2>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {olderEntries.map((entry) => renderThumbnailView(entry))}
          </div>
        </div>
      )}
    </div>
  );
}