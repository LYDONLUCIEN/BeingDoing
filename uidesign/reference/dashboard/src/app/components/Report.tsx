import { useState } from 'react';
import { Download, Share2, Trash2 } from 'lucide-react';

interface ReportProps {
  language: 'en' | 'zh';
}

interface SubReport {
  id: string;
  type: 'values' | 'strengths' | 'passion' | 'purpose';
  label: { en: string; zh: string };
  generatedDate: string;
  lastEditedTime: number;
  content: string;
}

interface MasterReport {
  id: string;
  title: { en: string; zh: string };
  generatedDate: string;
  lastEditedTime: number;
  subReports: SubReport[];
  content: string;
}

export function Report({ language }: ReportProps) {
  const text = {
    en: {
      title: 'Reports',
      masterReport: 'Comprehensive Career Development Plan',
      download: 'Download',
      share: 'Share',
      delete: 'Delete',
      generated: 'Generated',
      lastEdited: 'Last edited',
      subReportsTitle: 'Topic Reports',
      viewDetails: 'View Details',
      previousReports: 'Previous Reports',
      masterReportBadge: 'Master Report',
      subReportBadge: 'Sub Report',
    },
    zh: {
      title: '报告',
      masterReport: '综合职业发展计划',
      download: '下载',
      share: '分享',
      delete: '删除',
      generated: '生成时间',
      lastEdited: '最后编辑',
      subReportsTitle: '主题报告',
      viewDetails: '查看详情',
      previousReports: '之前的报告',
      masterReportBadge: '主报告',
      subReportBadge: '子报告',
    },
  };

  const t = text[language];

  // Mock data - multiple master reports with sub-reports
  const [masterReports] = useState<MasterReport[]>([
    {
      id: 'm1',
      title: { en: 'Comprehensive Career Development Plan', zh: '综合职业发展计划' },
      generatedDate: 'March 7, 2026',
      lastEditedTime: Date.now(),
      content: 'This is the latest comprehensive report...',
      subReports: [
        {
          id: 's1-1',
          type: 'values',
          label: { en: 'Values Report', zh: '底色报告' },
          generatedDate: 'March 2, 2026',
          lastEditedTime: Date.now() - 1 * 24 * 60 * 60 * 1000,
          content: 'Values analysis...',
        },
        {
          id: 's1-2',
          type: 'strengths',
          label: { en: 'Strengths Report', zh: '天赋报告' },
          generatedDate: 'March 3, 2026',
          lastEditedTime: Date.now() - 2 * 24 * 60 * 60 * 1000,
          content: 'Strengths analysis...',
        },
        {
          id: 's1-3',
          type: 'passion',
          label: { en: 'Passion Report', zh: '热忱报告' },
          generatedDate: 'March 5, 2026',
          lastEditedTime: Date.now() - 3 * 24 * 60 * 60 * 1000,
          content: 'Passion analysis...',
        },
        {
          id: 's1-4',
          type: 'purpose',
          label: { en: 'Purpose Report', zh: '航向报告' },
          generatedDate: 'March 6, 2026',
          lastEditedTime: Date.now() - 4 * 24 * 60 * 60 * 1000,
          content: 'Purpose analysis...',
        },
      ],
    },
    {
      id: 'm2',
      title: { en: 'Career Development Plan Q1', zh: 'Q1职业发展计划' },
      generatedDate: 'March 1, 2026',
      lastEditedTime: Date.now() - 6 * 24 * 60 * 60 * 1000,
      content: 'This is the Q1 report...',
      subReports: [
        {
          id: 's2-1',
          type: 'values',
          label: { en: 'Values Report', zh: '底色报告' },
          generatedDate: 'February 28, 2026',
          lastEditedTime: Date.now() - 7 * 24 * 60 * 60 * 1000,
          content: 'Values analysis Q1...',
        },
        {
          id: 's2-2',
          type: 'strengths',
          label: { en: 'Strengths Report', zh: '天赋报告' },
          generatedDate: 'February 29, 2026',
          lastEditedTime: Date.now() - 8 * 24 * 60 * 60 * 1000,
          content: 'Strengths analysis Q1...',
        },
      ],
    },
  ]);

  // Create a flat list of all reports (master + sub) for sorting
  const allReports: Array<{ type: 'master' | 'sub'; data: MasterReport | SubReport; parentId?: string }> = [];
  
  masterReports.forEach((master) => {
    allReports.push({ type: 'master', data: master });
    master.subReports.forEach((sub) => {
      allReports.push({ type: 'sub', data: sub, parentId: master.id });
    });
  });

  // Sort all reports by lastEditedTime
  const sortedReports = allReports.sort((a, b) => b.data.lastEditedTime - a.data.lastEditedTime);
  const mostRecentReport = sortedReports[0];
  const olderReports = sortedReports.slice(1);

  const [selectedReportId, setSelectedReportId] = useState<string>(mostRecentReport.data.id);

  const getTypeColor = (type: string) => {
    const colors = {
      values: '#A2C2E8',
      strengths: '#B5D8C6',
      passion: '#F4B3B3',
      purpose: '#FDE093',
    };
    return colors[type as keyof typeof colors] || '#A2C2E8';
  };

  const handleDownload = (reportId: string) => {
    console.log('Download report:', reportId);
  };

  const handleShare = (reportId: string) => {
    console.log('Share report:', reportId);
  };

  const handleDelete = (reportId: string) => {
    console.log('Delete report:', reportId);
  };

  const formatDate = (timestamp: number) => {
    const date = new Date(timestamp);
    return language === 'en'
      ? date.toLocaleDateString('en-US', { month: 'long', day: 'numeric', year: 'numeric' })
      : date.toLocaleDateString('zh-CN', { year: 'numeric', month: 'long', day: 'numeric' });
  };

  const renderFullMasterReport = (report: MasterReport) => (
    <div className="space-y-4">
      {/* Master Report */}
      <div className="bg-white/60 backdrop-blur-lg border border-gray-200/50 rounded-2xl p-6 shadow-sm">
        <div className="flex items-start justify-between">
          <div className="flex-1">
            <div className="flex items-center gap-3 mb-2">
              <div className="px-3 py-1 bg-gradient-to-r from-[#A2C2E8] to-[#B5D8C6] text-white text-xs font-medium rounded-full">
                {t.masterReportBadge}
              </div>
            </div>
            <h2 className="text-2xl font-medium text-[#1d1d1f] mb-2">
              {report.title[language]}
            </h2>
            <div className="flex items-center gap-3 text-sm text-gray-500">
              <span>{t.generated}: {report.generatedDate}</span>
              <span>•</span>
              <span>{t.lastEdited}: {formatDate(report.lastEditedTime)}</span>
            </div>
          </div>

          {/* Actions */}
          <div className="flex items-center gap-2">
            <button
              onClick={() => handleDownload(report.id)}
              className="p-2 hover:bg-gray-100 rounded-lg transition-colors"
              title={t.download}
            >
              <Download className="w-5 h-5 text-gray-700" />
            </button>
            <button
              onClick={() => handleShare(report.id)}
              className="p-2 hover:bg-gray-100 rounded-lg transition-colors"
              title={t.share}
            >
              <Share2 className="w-5 h-5 text-gray-700" />
            </button>
            <button
              onClick={() => handleDelete(report.id)}
              className="p-2 hover:bg-red-50 rounded-lg transition-colors"
              title={t.delete}
            >
              <Trash2 className="w-5 h-5 text-red-500" />
            </button>
          </div>
        </div>
      </div>

      {/* Sub-reports */}
      <div className="pl-6">
        <h3 className="text-sm font-medium text-gray-600 mb-3">{t.subReportsTitle}</h3>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
          {report.subReports.map((subReport) => (
            <div
              key={subReport.id}
              className="bg-white/60 backdrop-blur-lg border border-gray-200/50 rounded-xl p-4 shadow-sm hover:shadow-md transition-all"
            >
              <div className="mb-3">
                <div
                  className="w-12 h-1 rounded-full mb-3"
                  style={{ backgroundColor: getTypeColor(subReport.type) }}
                />
                <h4 className="font-medium text-[#1d1d1f] mb-1">
                  {subReport.label[language]}
                </h4>
                <p className="text-xs text-gray-500">
                  {t.lastEdited}: {formatDate(subReport.lastEditedTime)}
                </p>
              </div>

              {/* Actions */}
              <div className="flex items-center gap-1 pt-3 border-t border-gray-200">
                <button
                  onClick={() => handleDownload(subReport.id)}
                  className="p-1.5 hover:bg-gray-100 rounded-lg transition-colors"
                  title={t.download}
                >
                  <Download className="w-4 h-4 text-gray-600" />
                </button>
                <button
                  onClick={() => handleShare(subReport.id)}
                  className="p-1.5 hover:bg-gray-100 rounded-lg transition-colors"
                  title={t.share}
                >
                  <Share2 className="w-4 h-4 text-gray-600" />
                </button>
                <button
                  onClick={() => handleDelete(subReport.id)}
                  className="p-1.5 hover:bg-red-50 rounded-lg transition-colors"
                  title={t.delete}
                >
                  <Trash2 className="w-4 h-4 text-red-500" />
                </button>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );

  const renderFullSubReport = (report: SubReport, parentReport: MasterReport) => (
    <div className="bg-white/60 backdrop-blur-lg border border-gray-200/50 rounded-2xl p-6 shadow-sm">
      <div className="flex items-start justify-between">
        <div className="flex-1">
          <div className="flex items-center gap-3 mb-2">
            <div
              className="px-3 py-1 text-white text-xs font-medium rounded-full"
              style={{ backgroundColor: getTypeColor(report.type) }}
            >
              {t.subReportBadge}
            </div>
            <span className="text-xs text-gray-500">
              From: {parentReport.title[language]}
            </span>
          </div>
          <h2 className="text-2xl font-medium text-[#1d1d1f] mb-2">
            {report.label[language]}
          </h2>
          <div className="flex items-center gap-3 text-sm text-gray-500">
            <span>{t.generated}: {report.generatedDate}</span>
            <span>•</span>
            <span>{t.lastEdited}: {formatDate(report.lastEditedTime)}</span>
          </div>
        </div>

        {/* Actions */}
        <div className="flex items-center gap-2">
          <button
            onClick={() => handleDownload(report.id)}
            className="p-2 hover:bg-gray-100 rounded-lg transition-colors"
            title={t.download}
          >
            <Download className="w-5 h-5 text-gray-700" />
          </button>
          <button
            onClick={() => handleShare(report.id)}
            className="p-2 hover:bg-gray-100 rounded-lg transition-colors"
            title={t.share}
          >
            <Share2 className="w-5 h-5 text-gray-700" />
          </button>
          <button
            onClick={() => handleDelete(report.id)}
            className="p-2 hover:bg-red-50 rounded-lg transition-colors"
            title={t.delete}
          >
            <Trash2 className="w-5 h-5 text-red-500" />
          </button>
        </div>
      </div>
    </div>
  );

  const renderThumbnail = (item: { type: 'master' | 'sub'; data: MasterReport | SubReport; parentId?: string }) => {
    const isMaster = item.type === 'master';
    const data = item.data;

    return (
      <div
        key={data.id}
        onClick={() => setSelectedReportId(data.id)}
        className="bg-white/60 backdrop-blur-lg border border-gray-200/50 rounded-xl p-4 shadow-sm hover:shadow-md transition-all cursor-pointer hover:scale-[1.02]"
      >
        <div className="mb-3">
          <div className="flex items-center gap-2 mb-2">
            {isMaster ? (
              <div className="px-2 py-0.5 bg-gradient-to-r from-[#A2C2E8] to-[#B5D8C6] text-white text-xs font-medium rounded-full">
                {t.masterReportBadge}
              </div>
            ) : (
              <div
                className="px-2 py-0.5 text-white text-xs font-medium rounded-full"
                style={{ backgroundColor: getTypeColor((data as SubReport).type) }}
              >
                {t.subReportBadge}
              </div>
            )}
          </div>
          <h3 className="font-medium text-[#1d1d1f] mb-1 text-sm">
            {isMaster ? (data as MasterReport).title[language] : (data as SubReport).label[language]}
          </h3>
          <p className="text-xs text-gray-500">
            {t.lastEdited}: {formatDate(data.lastEditedTime)}
          </p>
        </div>

        <button className="text-xs text-blue-600 hover:text-blue-700 font-medium">
          {t.viewDetails} →
        </button>
      </div>
    );
  };

  // Find the selected report to display
  const selectedReport = sortedReports.find(r => r.data.id === selectedReportId) || mostRecentReport;

  return (
    <div className="max-w-7xl">
      <h1 className="text-4xl font-semibold text-[#1d1d1f] mb-8">{t.title}</h1>

      {/* Most Recent Report - Full View */}
      <div className="mb-8">
        {selectedReport.type === 'master' ? (
          renderFullMasterReport(selectedReport.data as MasterReport)
        ) : (
          renderFullSubReport(
            selectedReport.data as SubReport,
            masterReports.find(m => m.id === selectedReport.parentId)!
          )
        )}
      </div>

      {/* Older Reports - Thumbnail List */}
      {olderReports.length > 0 && (
        <div>
          <h2 className="text-lg font-medium text-[#1d1d1f] mb-4">{t.previousReports}</h2>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
            {olderReports.map((report) => renderThumbnail(report))}
          </div>
        </div>
      )}
    </div>
  );
}