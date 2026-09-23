'use client';

/**
 * Rumination v4 页壳
 *
 * guided（默认，0923 结构对齐前四阶段 / HTML .workspace.rumination）：
 *   根级横向 flex = 左 V4ComboSidebar（全高组合栏，同前四阶段会话侧栏）
 *   + 内容列（header「05 沉淀」+ 对话卡（画面主体）+ 右选择器）。
 *   不再有 .v4-outer-shell 整页玻璃罩（设计系统：禁止整页大磨砂玻璃），
 *   选择器壳 .v4-inner-pane 同样不渲染，元素直接落在流光背景上。
 * classic/studio（备选）：保留 outer-shell + inner-pane 原结构（mist 等皮肤依赖）。
 */

import { useEffect, useRef, useState } from 'react';
import dynamic from 'next/dynamic';
import { useRouter } from 'next/navigation';
import { ChevronRight, ChevronsLeft, ChevronsRight, FileText, Lock } from 'lucide-react';
import { useRuminationV4Store } from '@/stores/ruminationV4Store';
import { markV4IntroShown } from '@/lib/explore/ruminationV4Api';
import { useChatAppearanceAttrs } from '@/lib/explore/useChatAppearanceAttrs';
import { useChatAppearanceStore } from '@/stores/chatAppearanceStore';
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
    // state 加载完成后 workbench 才渲染；isGuided/stacked 切换会换挂 workbench 节点，需重挂观察
  }, [state, ruminationLayout]);

  /** 终选已提交：顶栏按钮变为「查看报告」直达报告页（报告下载页除个人空间外的另一入口） */
  const finalSubmitted = !!state?.final_selection?.submitted;
  /** guided 布局（外观面板「组合解锁」）：左组合列表 / 中对话 / 右选择器；stacked 窄屏回退 classic 堆叠 */
  const isGuided = ruminationLayout === 'guided' && !stacked;
  const activeComboId = state?.active_combo_id ?? null;
  /**
   * guided 选择器收拢策略：
   * - 确认新组合（草稿 null → id）后自动收拢，对话区伸展（2026-09-22 拍板）
   * - 组合间切换（id → 另一 id）改为**展开**选择器，方便对照结论/选择（2026-09-23 拍板）
   * - 回到草稿态（id → null）强制展开
   * 收拢条在选择器左侧——展开时随选择器左移，收拢后滑回右缘。
   */
  const [selectorCollapsed, setSelectorCollapsed] = useState(false);
  const prevComboIdRef = useRef<string | null>(null);
  useEffect(() => {
    const prev = prevComboIdRef.current;
    prevComboIdRef.current = activeComboId ?? null;
    if (!isGuided || prev === (activeComboId ?? null)) return;
    setSelectorCollapsed(prev ? false : !!activeComboId);
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

  /* ── 共享节点（guided / classic 两分支复用，避免 JSX 重复） ─────────── */

  const headerNode = (
    /* 顶栏：居中标题 + 右上完成并继续（guided 下仅横跨对话列，同 HTML conversation-top）。
       relative z-30：毛玻璃 backdrop-filter 会建立层叠上下文把外观弹层困在 header 层级之下，
       显式置顶保证弹层永远盖住对话/选择器（0923 拍板） */
    <header className="hero journey-rumination-header relative z-30 mb-2.5 grid shrink-0 grid-cols-[1fr_auto_1fr] items-center border-b border-[rgba(80,94,145,0.08)] pb-3 pt-1 text-center">
      <div />
      <div className="px-4 sm:px-8">
        {/* 标题与前四阶段 .careering-chat-phase-title 同口径：19px 衬线 + SemiBold 600
            （避免合成加粗）+ 中文正字距 + journey-ink（0923 拍板：副标题移除；外观配置迁至 admin） */}
        <h1
          className="m-0 text-[19px] font-semibold leading-tight tracking-[0.02em] text-[var(--journey-ink,#17212d)]"
          style={{ fontFamily: 'var(--font-serif-cn)' }}
        >
          05 沉淀
          <span className="ml-2 inline-block text-[#8f78d8]" style={{ fontSize: '0.72em' }}>
            ✦
          </span>
        </h1>
      </div>
      <div className="flex items-center justify-end gap-2 pr-1">
        {onCompleteAndContinue && (
          <button
            type="button"
            onClick={handleCompleteClick}
            disabled={!finalSubmitted && !v4CanContinue}
            title={finalSubmitted ? '查看我的报告' : continueDisabledHint || undefined}
            className="complete-btn bd-btn-black inline-flex items-center gap-2 rounded-full px-4 py-2.5 text-sm font-semibold text-white transition-all sm:px-5 disabled:cursor-not-allowed disabled:opacity-40"
          >
            <FileText size={15} strokeWidth={2} className="hidden shrink-0 sm:inline" />
            <span className="max-w-[7.5rem] truncate sm:max-w-none">
              {finalSubmitted ? '查看报告' : '完成并继续'}
            </span>
            <ChevronRight size={16} strokeWidth={2} className="shrink-0" aria-hidden />
          </button>
        )}
      </div>
    </header>
  );

  /* 提交后回看模式：轻量锁定说明条 */
  const lockBannerNode = finalSubmitted ? (
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
  ) : null;

  /* 选择器列：guided 无 v4-inner-pane 壳（透出背景流光），classic 保留（皮肤依赖）。
     guided 展开宽度上限 min(430px, 50% - 侧栏238px - 间距24px)，保证对话区至少占半页；
     开合带 0.4s 精简动画（宽度/透明度，收起时负 margin 抵消 gap，0923 拍板） */
  const selectorNode = (
    <div
      className={`flex min-h-0 min-w-0 flex-col overflow-hidden ${
        stacked ? 'w-full flex-none' : ''
      } ${
        isGuided
          ? `flex-none transition-[width,opacity,margin] duration-[400ms] ease-[cubic-bezier(0.2,0.8,0.2,1)] motion-reduce:transition-none ${
              selectorCollapsed ? 'pointer-events-none' : ''
            }`
          : 'v4-inner-pane flex-[1.05]'
      }`}
      style={
        isGuided && !stacked
          ? selectorCollapsed
            ? { width: 0, opacity: 0, marginLeft: '-12px' }
            : { width: 'max(280px, min(430px, calc(50% - 262px)))', opacity: 1, marginLeft: 0 }
          : undefined
      }
      aria-hidden={isGuided && !stacked && selectorCollapsed ? true : undefined}
    >
      <V4MatrixLeftPanel stacked={stacked} />
    </div>
  );

  /* guided 收拢/展开边条（仅已有激活组合时可收拢；草稿态强制展开）。
     hover 有浅紫底+描边的「被选中」反馈（0923 拍板） */
  const collapseNode =
    isGuided && !stacked && !!activeComboId ? (
      <button
        type="button"
        onClick={() => setSelectorCollapsed((v) => !v)}
        className="flex h-[96px] w-[22px] shrink-0 items-center justify-center self-center rounded-full border border-[rgba(100,91,122,0.12)] bg-white/60 text-[#8b84a8] shadow-[0_6px_16px_rgba(49,43,65,0.08)] transition-all duration-200 hover:border-[#b9a6ec] hover:bg-[#f3f0fc] hover:text-[#6f52c7] hover:shadow-[0_6px_16px_rgba(111,82,199,0.15)]"
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
    ) : null;

  /* 对话列：guided 下为画面主体（flex-1），classic 为右栏 */
  const chatNode = (
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
              className="mt-1 rounded-full bg-[var(--journey-ink,#17212d)] px-5 py-2 text-[13px] font-semibold text-white transition-transform hover:-translate-y-0.5"
            >
              ＋ 新建组合
            </button>
          </div>
        </div>
      )}
    </div>
  );

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
        {/* HTML .rumination-flow：前四阶段色的极淡回声（柔和淡彩 blob 慢速漂移），紫色仍是交互锚点。
            0923：删除整页照片纹理 ribbon（0.55 不透明度闷死色彩，HTML 背景只有流光 + 贴纸） */}
        <div className="rumination-flow">
          <div className="rumination-flow-blob rumination-flow-blue" />
          <div className="rumination-flow-blob rumination-flow-green" />
          <div className="rumination-flow-blob rumination-flow-coral" />
          <div className="rumination-flow-blob rumination-flow-gold" />
        </div>
        <img src="/assets/openlife-journey/sticker-rumination.webp" alt="" />
      </div>

      {isGuided ? (
        <>
          {/* guided（默认）：组合栏直接挂根级、全高左栏（同前四阶段会话侧栏 / HTML .sidebar），
              不再包进 outer-shell；header/对话/选择器落在内容列，流光背景直接可见 */}
          <V4ComboSidebar onExpandSelector={() => setSelectorCollapsed(false)} />
          <div className="relative z-10 flex min-h-0 min-w-0 flex-1 flex-col py-2 pr-3 sm:pr-4">
            {headerNode}
            {lockBannerNode}
            <div
              ref={workbenchRef}
              className="rumination-workbench flex min-h-0 flex-1 gap-3 overflow-hidden"
            >
              {chatNode}
              {/* 0923 拍板：收拢条放在选择器左侧——展开时跟随选择器往左移动，点击收起滑回右缘 */}
              {collapseNode}
              {selectorNode}
            </div>
          </div>
        </>
      ) : (
        <div className="relative z-10 flex min-h-0 w-full flex-col px-3 pb-3 pt-1 sm:px-4">
          <div
            className={`v4-outer-shell flex w-full flex-col ${stacked ? 'flex-none' : 'min-h-0 flex-1 overflow-hidden'}`}
          >
            {headerNode}
            {/* 组合 tabs + 新建组合（classic 布局横向条；guided 移到左侧 V4ComboSidebar） */}
            <div className="rumination-toolbar-wrap mb-2.5 min-w-0 shrink-0">
              <TopComboBar />
            </div>
            {lockBannerNode}
            {/* classic/studio：左选择器 / 右对话 */}
            <div
              ref={workbenchRef}
              className={`rumination-workbench flex gap-3 ${
                stacked ? 'w-full flex-none flex-col' : 'min-h-0 flex-1 overflow-hidden'
              }`}
            >
              {selectorNode}
              {chatNode}
            </div>
          </div>
        </div>
      )}

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
