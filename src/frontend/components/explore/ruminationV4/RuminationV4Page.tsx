'use client';

/**
 * Rumination v4 页壳
 *
 * 一个大容器内：顶栏（居中「05 沉淀」+ 右上「完成并继续」）
 * → 组合 tabs +「新建组合」
 * → 左选择器/结论 + 右对话（内部分区）
 */

import { useEffect, useRef, useState } from 'react';
import dynamic from 'next/dynamic';
import { useRouter } from 'next/navigation';
import { ChevronsLeft, ChevronsRight, FileText, Lock } from 'lucide-react';
import { useRuminationV4Store } from '@/stores/ruminationV4Store';
import { markV4IntroShown } from '@/lib/explore/ruminationV4Api';
import { useChatAppearanceAttrs } from '@/lib/explore/useChatAppearanceAttrs';
import { useChatAppearanceStore } from '@/stores/chatAppearanceStore';
import ChatAppearancePopover from '@/components/explore/ChatAppearancePopover';
import V4ChatPanel from './V4ChatPanel';
import V4ComboSidebar, { enterComboDraft } from './V4ComboSidebar';
import TopComboBar from './TopComboBar';
import V4FinalSelectionModal from './V4FinalSelectionModal';
import V4IntroModal from './V4IntroModal';

const V4MatrixLeftPanel = dynamic(() => import('./V4MatrixLeftPanel'), { ssr: false });

interface Props {
  activationCode: string;
  onCompleteAndContinue?: () => void;
  canContinue?: boolean;
  continueDisabledHint?: string;
}

export default function RuminationV4Page({
  activationCode,
  onCompleteAndContinue,
  canContinue = true,
  continueDisabledHint = '',
}: Props) {
  const { state, init } = useRuminationV4Store();
  // Chat 外观配置 → 根节点 data-* 属性（背景/气泡/布局/皮肤/矩阵等）
  const { dataAttrs: chatAppearanceAttrs, style: chatAppearanceStyle } = useChatAppearanceAttrs();
  /** 页面布局（外观面板）：guided = 左组合列表 / 中对话 / 右选择器（stacked 时回退 classic 堆叠） */
  const ruminationLayout = useChatAppearanceStore((s) => s.ruminationLayout);
  const [finalModalOpen, setFinalModalOpen] = useState(false);
  const [introOpen, setIntroOpen] = useState(false);
  const introCheckedRef = useRef(false);
  const router = useRouter();

  /**
   * 自适应堆叠模式（2026-08-24）：
   * 工作台过窄（< 视口 2/3，对齐 v3 口径）或视口过低（< 760px，常见于系统缩放
   * 150% 的笔记本 100% 缩放场景）时，左右双栏改为上下堆叠 + 页面纵向滚动，
   * 避免固定视口高 + overflow-hidden 把左栏选择器/结论卡裁掉。
   * （阈值可调：125% 缩放等效 864px 高，走双栏 + 选择器内部滚动 + 小高度压缩）
   */
  const workbenchRef = useRef<HTMLDivElement>(null);
  const [stacked, setStacked] = useState(false);
  useEffect(() => {
    const el = workbenchRef.current;
    if (!el) return;
    const update = () => {
      const vw = window.innerWidth;
      const vh = window.innerHeight;
      const w = el.getBoundingClientRect().width;
      setStacked(w < (vw * 2) / 3 || vh < 760);
    };
    update();
    const ro = new ResizeObserver(update);
    ro.observe(el);
    window.addEventListener('resize', update);
    return () => {
      ro.disconnect();
      window.removeEventListener('resize', update);
    };
    // state 加载完成后 workbench 才渲染，依赖 state 确保 ref 已挂载
  }, [state]);

  /** 终选已提交：顶栏按钮变为「查看报告」直达报告页（报告下载页除个人空间外的另一入口） */
  const finalSubmitted = !!state?.final_selection?.submitted;
  /** guided 布局（外观面板「组合解锁」）：左组合列表 / 中对话 / 右选择器；stacked 窄屏回退 classic 堆叠 */
  const isGuided = ruminationLayout === 'guided' && !stacked;
  const activeComboId = state?.active_combo_id ?? null;
  /**
   * guided 选择器收拢（2026-09-22）：确认组合（开始探索）后自动收拢，对话区/输入框自动伸展；
   * 回到草稿态（新建组合、无激活组合）强制展开。收拢后右缘留 « 边条可手动展开/收拢。
   */
  const [selectorCollapsed, setSelectorCollapsed] = useState(false);
  useEffect(() => {
    if (!isGuided) return;
    setSelectorCollapsed(!!activeComboId);
  }, [isGuided, activeComboId]);
  const gotoReport = () => {
    router.push(`/explore/report?code=${encodeURIComponent(activationCode)}`);
  };

  useEffect(() => {
    if (activationCode) {
      init(activationCode);
    }
  }, [activationCode, init]);

  useEffect(() => {
    if (state?.active_combo_id) {
      useRuminationV4Store.getState().loadCombo(state.active_combo_id);
    }
  }, [state?.active_combo_id]);

  // 开场弹窗：每个激活码的 report 首次进入 v4 页面时弹一次（后端 intro_shown 持久化）
  useEffect(() => {
    if (!state || introCheckedRef.current) return;
    introCheckedRef.current = true;
    if (!state.intro_shown) setIntroOpen(true);
  }, [state]);

  const handleIntroConfirm = () => {
    setIntroOpen(false);
    // 本地先落标记，避免同一会话内因 state 刷新重弹；后端标记失败也静默
    const s = useRuminationV4Store.getState().state;
    if (s) {
      useRuminationV4Store.setState({ state: { ...s, intro_shown: true } });
    }
    markV4IntroShown(activationCode).catch(() => { /* 静默忽略 */ });
  };

  const v4CanContinue =
    canContinue ||
    !!state?.final_selection?.submitted ||
    (state?.combo_sessions || []).some(
      (c) => !!c.conclusion_card || c.status === 'concluded'
    );

  /**
   * 点击「完成并继续」：已提交 → 直达报告页；否则始终开终选弹窗。
   * 判定未完成的卡点不再在页级拦截，改由弹窗内模糊浮层处理（含 failed 引导重试）。
   */
  const handleCompleteClick = () => {
    if (finalSubmitted) {
      gotoReport();
      return;
    }
    setFinalModalOpen(true);
  };

  if (!state) {
    return (
      <div className="flex flex-1 items-center justify-center text-sm text-[#9ca3af]">
        加载中…
      </div>
    );
  }

  return (
    <div
      className={`rumination-beautiful-root rumination-v4-root flow-light relative min-h-0 flex-1 ${
        stacked ? 'block overflow-y-auto' : 'flex overflow-hidden'
      }`}
      data-phase="rumination"
      {...chatAppearanceAttrs}
      style={chatAppearanceStyle}
    >
      <div className="rumination-journey-backdrop" aria-hidden>
        <div className="rumination-journey-ribbon" />
        <img src="/assets/openlife-journey/sticker-rumination.webp" alt="" />
      </div>

      <div className="relative z-10 flex min-h-0 w-full flex-col px-3 pb-3 pt-1 sm:px-4">
        <div
          className={`v4-outer-shell flex w-full flex-col ${stacked ? 'flex-none' : 'min-h-0 flex-1 overflow-hidden'}`}
        >
          {/* 顶栏：居中标题 + 右上完成并继续 */}
          <header className="hero journey-rumination-header mb-2.5 grid shrink-0 grid-cols-[1fr_auto_1fr] items-center border-b border-[rgba(80,94,145,0.08)] pb-3 pt-1 text-center">
            <div />
            <div className="px-4 sm:px-8">
              {/* 标题字体与前四阶段顶栏一致：衬线栈 + SemiBold 600（避免合成加粗）+ 中文正字距 */}
              <h1
                className="m-0 text-[24px] font-semibold leading-tight tracking-[0.02em] text-[#282331] sm:text-[32px]"
                style={{ fontFamily: 'var(--font-serif-cn)' }}
              >
                05 沉淀
                <span className="ml-2 inline-block text-[#8f78d8]" style={{ fontSize: '0.72em' }}>
                  ✦
                </span>
              </h1>
              <p className="mx-auto mt-2 max-w-[520px] text-[13px] font-[500] leading-relaxed text-[#657198] sm:text-[16px]">
                把热爱与优势组成方向，和我深入聊一聊，留下你的假设结论
              </p>
            </div>
            <div className="flex items-center justify-end gap-2 pr-1">
              {/* 外观弹层：沉淀页无会话侧栏，隐藏「对话排版」组 */}
              <ChatAppearancePopover hideSidebarOptions />
              {onCompleteAndContinue && (
                <button
                  type="button"
                  onClick={handleCompleteClick}
                  disabled={!finalSubmitted && !v4CanContinue}
                  title={finalSubmitted ? '查看我的报告' : continueDisabledHint || undefined}
                  className="complete-btn flex items-center gap-2 rounded-full px-4 py-2.5 text-sm font-bold text-white transition-all hover:-translate-y-0.5 disabled:cursor-not-allowed disabled:opacity-40 sm:px-5 sm:py-3 sm:text-base"
                  style={{
                    background: 'linear-gradient(180deg,#121f3f,#07132f)',
                    boxShadow: '0 10px 22px rgba(4,19,52,0.22)',
                  }}
                >
                  <FileText size={18} strokeWidth={2} className="hidden shrink-0 sm:inline" />
                  <span className="max-w-[7.5rem] truncate sm:max-w-none">
                    {finalSubmitted ? '查看报告' : '完成并继续'}
                  </span>
                </button>
              )}
            </div>
          </header>

          {/* 组合 tabs + 新建组合（guided 布局下组合管理移到左侧 V4ComboSidebar） */}
          {!isGuided && (
            <div className="rumination-toolbar-wrap mb-2.5 min-w-0 shrink-0">
              <TopComboBar />
            </div>
          )}

          {/* 提交后回看模式：轻量锁定说明条 */}
          {finalSubmitted && (
            <div
              className="mb-2.5 flex shrink-0 items-center gap-2 rounded-[14px] px-4 py-2 text-[12px] font-[650] text-[#5d5a8f]"
              style={{
                background: 'rgba(244,240,255,0.72)',
                border: '1px solid rgba(122,100,255,0.16)',
              }}
              role="status"
            >
              <Lock size={13} strokeWidth={2.2} className="shrink-0" />
              最终选择已提交，内容已锁定，仅供回看
            </div>
          )}

          {/* classic/studio：左选择器 / 右对话；guided：左组合列表 / 中对话（未确认组合时锁定） / 右选择器 */}
          <div
            ref={workbenchRef}
            className={`rumination-workbench flex gap-3 ${
              stacked ? 'w-full flex-none flex-col' : 'min-h-0 flex-1 overflow-hidden'
            }`}
          >
            {isGuided && <V4ComboSidebar />}
            {/* guided 选择器可收拢；展开宽度上限 min(430px, 50% - 侧栏220px - 间距24px)，保证对话区至少占半页 */}
            {(!isGuided || !selectorCollapsed) && (
              <div
                className={`v4-inner-pane flex min-w-0 flex-col ${
                  stacked ? 'w-full flex-none' : 'min-h-0 overflow-hidden'
                } ${isGuided ? 'order-3 flex-none' : 'flex-[1.05]'}`}
                style={
                  isGuided && !stacked
                    ? { width: 'max(280px, min(430px, calc(50% - 244px)))' }
                    : undefined
                }
              >
                <V4MatrixLeftPanel stacked={stacked} />
              </div>
            )}
            {/* guided 收拢/展开边条（仅已有激活组合时可收拢；草稿态强制展开） */}
            {isGuided && !stacked && !!activeComboId && (
              <button
                type="button"
                onClick={() => setSelectorCollapsed((v) => !v)}
                className="order-4 flex h-[96px] w-[22px] shrink-0 items-center justify-center self-center rounded-full text-[#8b84a8] transition-colors hover:text-[#6f52c7]"
                style={{
                  background: 'rgba(255,255,255,0.6)',
                  border: '1px solid rgba(100,91,122,0.12)',
                  boxShadow: '0 6px 16px rgba(49,43,65,0.08)',
                }}
                aria-expanded={!selectorCollapsed}
                aria-label={selectorCollapsed ? '展开组合选择器' : '收拢组合选择器'}
                title={selectorCollapsed ? '展开组合选择器' : '收拢组合选择器'}
              >
                {selectorCollapsed ? (
                  <ChevronsLeft size={13} strokeWidth={2.2} />
                ) : (
                  <ChevronsRight size={13} strokeWidth={2.2} />
                )}
              </button>
            )}
            <div
              className={`relative flex min-w-0 flex-col overflow-hidden ${
                stacked ? 'h-[min(58vh,560px)] w-full flex-none' : 'min-h-0 flex-1'
              }`}
            >
              <V4ChatPanel comboId={state.active_combo_id} hideDraftHint={isGuided} />
              {/* guided 锁屏：未确认组合时对话区锁定（对齐 HTML .guided-chat-lock） */}
              {isGuided && !state.active_combo_id && !finalSubmitted && (
                <div
                  className="absolute inset-0 z-20 flex items-center justify-center rounded-[20px] border border-white/60 bg-white/55 p-6"
                  style={{
                    backdropFilter: 'blur(14px) saturate(1.05)',
                    WebkitBackdropFilter: 'blur(14px) saturate(1.05)',
                  }}
                  role="status"
                >
                  <div className="flex max-w-[340px] flex-col items-center gap-3 rounded-2xl border border-[rgba(100,91,122,0.12)] bg-white/90 px-8 py-7 text-center shadow-[0_18px_46px_rgba(49,43,65,0.12)]">
                    <span className="text-[22px] leading-none text-[#886ddc]" aria-hidden>
                      ⌁
                    </span>
                    <h3 className="m-0 text-[16px] font-bold text-[#282331]">先创建一个新的组合</h3>
                    <p className="m-0 text-[12.5px] leading-relaxed text-[#657198]">
                      从左侧新建组合，再在右侧选择一项热爱与至少一项优势。确认组合后，对话会自动解锁。
                    </p>
                    <button
                      type="button"
                      onClick={enterComboDraft}
                      className="mt-1 rounded-full bg-[#202832] px-5 py-2 text-[13px] font-semibold text-white transition-transform hover:-translate-y-0.5"
                    >
                      ＋ 新建组合
                    </button>
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>
      </div>

      <V4IntroModal open={introOpen} onConfirm={handleIntroConfirm} />

      <V4FinalSelectionModal
        open={finalModalOpen}
        onClose={() => setFinalModalOpen(false)}
        onConfirm={() => {
          setFinalModalOpen(false);
          onCompleteAndContinue?.();
        }}
      />
    </div>
  );
}
