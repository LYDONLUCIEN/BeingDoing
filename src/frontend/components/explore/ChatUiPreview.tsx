'use client';

import { useMemo, useState } from 'react';
import { useRouter } from 'next/navigation';
import { ArrowUp, FileText, FlaskConical, RotateCcw, Square } from 'lucide-react';
import ChatPhaseBackground from '@/components/explore/ChatPhaseBackground';
import ChatPhaseSidebar from '@/components/explore/ChatPhaseSidebar';
import DimensionConclusionCard, {
  type DimensionConclusionData,
} from '@/components/explore/DimensionConclusionCard';
import ExploreLandingMeshLayers from '@/components/explore/ExploreLandingMeshLayers';
import ChatAppearancePopover from '@/components/explore/ChatAppearancePopover';
import { useChatAppearanceStore } from '@/stores/chatAppearanceStore';
import FlowAiMessage from '@/components/explore/FlowAiMessage';
import RuminationTableWidget, {
  type RuminationTablePayload,
} from '@/components/explore/RuminationTableWidget';
import type { ChatThread, ThreadMessage } from '@/lib/explore/threads';
import type { PhaseKey } from '@/lib/explore/session';

type PreviewState = 'conversation' | 'streaming' | 'conclusion' | 'loading' | 'empty' | 'error';

const PREVIEW_STATES: Array<{ value: PreviewState; label: string }> = [
  { value: 'conversation', label: '正常对话' },
  { value: 'streaming', label: 'AI 回复中' },
  { value: 'conclusion', label: '结论卡' },
  { value: 'loading', label: '加载状态' },
  { value: 'empty', label: '空会话' },
  { value: 'error', label: '错误状态' },
];

const PHASE_COPY: Record<
  PhaseKey,
  {
    num: string;
    label: string;
    question: string;
    answer: string;
    reflection: string;
    keywords: string[];
    notes?: string[];
  }
> = {
  values: {
    num: '01',
    label: '价值观',
    question: '我们先从最近一次让你感到“这件事做得很值得”的经历聊起。那件事具体发生了什么？',
    answer: '上个月我帮助团队把一个混乱的项目重新理顺。看到大家终于知道下一步该做什么，我特别有成就感。',
    reflection: '我听见的不只是“把项目做完”，而是你很在意让复杂的事情重新变得清晰，也愿意让身边的人因此更安心。你觉得其中更打动你的是解决难题，还是帮助团队重新找到秩序？',
    keywords: ['清晰', '可靠', '共同成长'],
    notes: ['把复杂问题转化为可行动的方向', '成为值得信任、能承担责任的人', '让个人成果转化为团队进步'],
  },
  strengths: {
    num: '02',
    label: '优势',
    question: '回想一次别人主动来找你帮忙的经历，他们为什么会想到你？',
    answer: '大家遇到信息很多、意见不一致的时候经常会找我。我通常能先听懂每个人在担心什么，再整理成几条清楚的选择。',
    reflection: '这段描述里同时出现了倾听、提炼和推动决策三种能力，而且它们似乎已经形成了你很自然的工作方式。我们可以再找一个完全不同的场景，看看这种模式是否仍然存在。',
    keywords: ['结构化思考', '共情沟通', '推动共识'],
  },
  interests: {
    num: '03',
    label: '热爱',
    question: '有哪些事情，即使没人要求你做，你也会忍不住继续了解或反复尝试？',
    answer: '我会一直研究人为什么会做出某种选择，也喜欢把零散的信息整理成图或文章，分享给需要的人。',
    reflection: '你的兴趣似乎不只停留在“知道更多”，而是包含理解人、建立连接，以及把理解转化成别人能使用的表达。哪一部分最容易让你忘记时间？',
    keywords: ['理解人', '知识整理', '表达与分享'],
  },
  purpose: {
    num: '04',
    label: '使命',
    question: '如果你的工作真的能为一类人带来改变，你最希望他们因此少经历什么，又多获得什么？',
    answer: '我希望那些正在做重要选择的人，不必因为信息混乱和自我怀疑反复内耗，而是能更踏实地走出下一步。',
    reflection: '这里已经出现了很清楚的使命线索：你想帮助处在选择关口的人，把混乱转化为理解，把自我怀疑转化为可执行的下一步。接下来我们可以把“谁、什么情境、怎样帮助”说得更具体。',
    keywords: ['减少内耗', '支持选择', '促成行动'],
  },
  rumination: {
    num: '05',
    label: '沉淀',
    question: '把这些方向放回真实生活中看，你最想先验证哪一个？',
    answer: '我想先验证“职业内容与工具设计”这个方向，因为它同时用到了我的分析、表达和助人动机。',
    reflection: '很好。我们暂时不要求它成为最终答案，只把它看作一个值得验证的假设。左侧列出了三个方向，请先为每个方向补充一个成本足够低、两周内可以完成的验证行动。',
    keywords: ['小步验证', '真实反馈', '持续迭代'],
  },
};

const PHASE_ORDER: PhaseKey[] = ['values', 'strengths', 'interests', 'purpose', 'rumination'];

function normalizePreviewState(value: string): PreviewState {
  return PREVIEW_STATES.some((item) => item.value === value)
    ? (value as PreviewState)
    : 'conversation';
}

function phaseClass(phase: PhaseKey): 'values' | 'strength' | 'interest' | 'purpose' | 'rumination' {
  if (phase === 'strengths') return 'strength';
  if (phase === 'interests') return 'interest';
  return phase;
}

function buildConclusion(phase: PhaseKey): DimensionConclusionData {
  const copy = PHASE_COPY[phase];
  if (phase === 'purpose') {
    return {
      summary: '你希望通过清晰、可靠的支持，帮助处在选择关口的人减少内耗，并形成能够真正开始行动的方向。',
      keywords: copy.keywords,
      mission_core: '让重要的职业选择变得更清晰、更有依据。',
      mission_detail: '服务正在经历转型、迷茫或关键选择的人，把复杂信息与内在感受整理为可理解、可执行的路径。',
      mission_aim: '让人们不再因为混乱而停滞，而是更有把握地迈出下一步。',
    };
  }
  return {
    summary: `从这段探索中，我们看见了你在“${copy.keywords.join('、')}”上的稳定倾向。这不是一次仓促的定论，而是一组值得带到真实生活中继续验证的线索。`,
    keywords: copy.keywords,
    keyword_notes: phase === 'values' ? copy.notes : undefined,
    strength_markers: phase === 'strengths' ? ['a', 'a', 'b'] : undefined,
    interest_reasons:
      phase === 'interests'
        ? ['你会主动观察他人的选择与动机', '整理信息时容易进入专注状态', '分享成果会带来明显满足感']
        : undefined,
  };
}

function buildMessages(phase: PhaseKey, state: PreviewState, now: number): ThreadMessage[] {
  if (state === 'empty' || state === 'loading') return [];
  const copy = PHASE_COPY[phase];
  const messages: ThreadMessage[] = [
    {
      id: `${phase}-ai-1`,
      role: 'assistant',
      content: copy.question,
      createdAt: now - 9 * 60_000,
    },
    {
      id: `${phase}-user-1`,
      role: 'user',
      content: copy.answer,
      createdAt: now - 7 * 60_000,
    },
    {
      id: `${phase}-ai-2`,
      role: 'assistant',
      content: copy.reflection,
      createdAt: now - 6 * 60_000,
    },
  ];

  if (state === 'streaming') {
    messages.push({
      id: `${phase}-ai-streaming`,
      role: 'assistant',
      content: '',
      thinkStreaming: true,
      thinkChunkContent: '正在把你刚才提到的经历与前面的线索联系起来…',
      createdAt: now,
    });
  }

  if (state === 'conclusion') {
    messages.push({
      id: `${phase}-conclusion`,
      role: 'assistant',
      content: '',
      type: 'dimension_conclusion',
      conclusionData: buildConclusion(phase),
      createdAt: now,
    });
  }

  return messages;
}

function buildThreads(phase: PhaseKey, state: PreviewState): ChatThread[] {
  if (state === 'empty') return [];
  const now = Date.now();
  const copy = PHASE_COPY[phase];
  return [
    {
      id: `preview-${phase}-main`,
      title: '正在探索的对话',
      status: state === 'conclusion' ? 'completed' : 'in-progress',
      messages: buildMessages(phase, state, now),
      createdAt: now - 16 * 60_000,
      dimensionConclusion: state === 'conclusion' ? buildConclusion(phase) : undefined,
    },
    {
      id: `preview-${phase}-second`,
      title: '另一种可能性',
      status: 'completed',
      messages: [
        {
          id: `${phase}-old-user`,
          role: 'user',
          content: '我也想看看，如果不沿用过去的职业标签，还会有哪些可能。',
          createdAt: now - 26 * 60_000,
        },
        {
          id: `${phase}-old-ai`,
          role: 'assistant',
          content: `可以。我们先暂时放下职位名称，只观察“${copy.keywords[0]}”这条线索在不同场景里怎样出现。`,
          createdAt: now - 25 * 60_000,
        },
      ],
      createdAt: now - 31 * 60_000,
    },
    {
      id: `preview-${phase}-third`,
      title: '较早的探索',
      status: 'in-progress',
      messages: [
        {
          id: `${phase}-early-ai`,
          role: 'assistant',
          content: '这是一段较早的示例会话，用来检查侧栏在多条记录时的视觉层级。',
          createdAt: now - 2 * 24 * 60 * 60_000,
        },
      ],
      createdAt: now - 2 * 24 * 60 * 60_000,
    },
  ];
}

const RUMINATION_TABLE: RuminationTablePayload = {
  step: 2,
  guideText: '为每个方向补充一个最小验证行动。这里的内容只存在于当前预览页面。',
  columns: [
    { key: 'direction', label: '候选方向' },
    { key: 'evidence', label: '已有依据' },
    { key: 'action', label: '两周验证行动' },
  ],
  rows: [
    { id: '01', direction: '职业内容与工具设计', evidence: '分析、表达、助人动机', action: '访谈 3 位目标用户并完成一份内容原型' },
    { id: '02', direction: '用户研究与策略', evidence: '倾听、提炼、推动共识', action: '拆解一个真实项目并邀请同行反馈' },
    { id: '03', direction: '成长型社群运营', evidence: '连接他人、营造安全感', action: '组织一次 6 人主题讨论并记录能量变化' },
  ],
  editableCols: ['action'],
};

function formatTime(ms?: number): string {
  if (!ms) return '';
  const date = new Date(ms);
  return `${String(date.getHours()).padStart(2, '0')}:${String(date.getMinutes()).padStart(2, '0')}`;
}

function PreviewMessages({
  phase,
  messages,
  state,
  streaming,
  conclusionConfirmed,
  onConfirmConclusion,
}: {
  phase: PhaseKey;
  messages: ThreadMessage[];
  state: PreviewState;
  streaming: boolean;
  conclusionConfirmed: boolean;
  onConfirmConclusion: () => void;
}) {
  const copy = PHASE_COPY[phase];
  const theme = phaseClass(phase);

  if (state === 'loading') {
    return (
      <div className="ol-chat-preview-loading" role="status" aria-label="正在加载示例会话">
        <span />
        <span />
        <span />
      </div>
    );
  }

  if (messages.length === 0) {
    return (
      <div className="ol-chat-preview-empty">
        <span>从一段真实经历开始</span>
        <p>当前没有消息。你可以在下方输入一段文字，检查新会话的空状态和第一条消息。</p>
      </div>
    );
  }

  return (
    <>
      {messages.map((message, index) => {
        if (message.type === 'dimension_conclusion' && message.conclusionData) {
          return (
            <div className="flow-msg-conclusion-wrap" key={message.id}>
              <DimensionConclusionCard
                phase={theme}
                data={message.conclusionData}
                inline
                isCompleted={conclusionConfirmed}
                showActions={!conclusionConfirmed}
                onConfirm={onConfirmConclusion}
                onContinueChat={() => {}}
              />
            </div>
          );
        }

        if (message.role === 'user') {
          return (
            <div className="flow-msg-user" key={message.id}>
              <div className="flow-msg-user-wrap">
                <div className="flow-msg-careering-meta flow-msg-careering-meta--user">
                  <div className="flow-msg-careering-avatar flow-msg-careering-avatar--user ol-chat-preview-user-avatar" aria-hidden>
                    你
                  </div>
                  <span>你 · {formatTime(message.createdAt)}</span>
                </div>
                <div className="flow-msg-user-anchor">
                  <div className="flow-msg-user-content">
                    <span className="flow-msg-user-text flow-msg-user-text--careering-plain">
                      {message.content}
                    </span>
                  </div>
                </div>
              </div>
            </div>
          );
        }

        return (
          <FlowAiMessage
            key={message.id}
            content={message.content}
            phase={theme}
            variant={phase === 'rumination' ? 'ruminationWorkbench' : 'careeringMatte'}
            careeringAiRoleLabel="AI 职业教练"
            streaming={streaming && index === messages.length - 1}
            thinkStreaming={message.thinkStreaming}
            thinkChunkContent={message.thinkChunkContent}
            timestamp={message.createdAt}
            messageId={message.id}
            phaseKey={phase}
            hideToolbar={streaming && index === messages.length - 1}
          />
        );
      })}
      {state === 'error' && (
        <div className="flow-msg-error" role="alert">
          <div className="flow-msg-error-text">示例：网络连接暂时中断，请稍后重试。</div>
          <button type="button" className="flow-retry-btn">重新尝试</button>
        </div>
      )}
      <span className="sr-only">当前预览阶段：{copy.label}</span>
    </>
  );
}

export default function ChatUiPreview({
  phase,
  previewState: rawPreviewState,
}: {
  phase: PhaseKey;
  previewState: string;
}) {
  const router = useRouter();
  const chatAppearance = useChatAppearanceStore();
  const previewState = normalizePreviewState(rawPreviewState);
  const copy = PHASE_COPY[phase];
  const [threads, setThreads] = useState<ChatThread[]>(() => buildThreads(phase, previewState));
  const [activeThreadId, setActiveThreadId] = useState<string | null>(() =>
    buildThreads(phase, previewState)[0]?.id ?? null
  );
  const [input, setInput] = useState('');
  const [streaming, setStreaming] = useState(previewState === 'streaming');
  const [conclusionConfirmed, setConclusionConfirmed] = useState(false);

  const activeThread = useMemo(
    () => threads.find((thread) => thread.id === activeThreadId) ?? null,
    [activeThreadId, threads]
  );
  const messages = activeThread?.messages ?? [];

  const navigatePreview = (nextPhase: PhaseKey, nextState: PreviewState) => {
    router.replace(
      `/explore/chat/${nextPhase}?ui_preview=1&preview_state=${nextState}`
    );
  };

  const resetPreview = () => {
    const next = buildThreads(phase, previewState);
    setThreads(next);
    setActiveThreadId(next[0]?.id ?? null);
    setInput('');
    setStreaming(previewState === 'streaming');
    setConclusionConfirmed(false);
  };

  const updateActiveMessages = (updater: (items: ThreadMessage[]) => ThreadMessage[]) => {
    if (!activeThreadId) return;
    setThreads((current) =>
      current.map((thread) =>
        thread.id === activeThreadId
          ? { ...thread, messages: updater(thread.messages) }
          : thread
      )
    );
  };

  const handleSend = () => {
    const text = input.trim();
    if (!text || streaming) return;
    if (!activeThreadId) {
      const now = Date.now();
      const newThread: ChatThread = {
        id: `preview-${phase}-${now}`,
        title: '新预览对话',
        status: 'in-progress',
        createdAt: now,
        messages: [{ id: `preview-user-${now}`, role: 'user', content: text, createdAt: now }],
      };
      setThreads([newThread]);
      setActiveThreadId(newThread.id);
      setInput('');
      return;
    }

    const now = Date.now();
    updateActiveMessages((items) => [
      ...items,
      { id: `preview-user-${now}`, role: 'user', content: text, createdAt: now },
    ]);
    setInput('');
    setStreaming(true);
    window.setTimeout(() => {
      updateActiveMessages((items) => [
        ...items,
        {
          id: `preview-ai-${Date.now()}`,
          role: 'assistant',
          content: '这是本地 UI 预览中的模拟回复，不会发送给服务器。你可以继续输入内容来检查气泡长度、滚动和输入框状态。',
          createdAt: Date.now(),
        },
      ]);
      setStreaming(false);
    }, 420);
  };

  const handleNewThread = () => {
    const now = Date.now();
    const thread: ChatThread = {
      id: `preview-${phase}-new-${now}`,
      title: '新的预览会话',
      status: 'in-progress',
      messages: [],
      createdAt: now,
    };
    setThreads((items) => [thread, ...items]);
    setActiveThreadId(thread.id);
  };

  const handleDeleteThread = (target: ChatThread) => {
    setThreads((items) => {
      const next = items.filter((item) => item.id !== target.id);
      if (target.id === activeThreadId) setActiveThreadId(next[0]?.id ?? null);
      return next;
    });
  };

  const toolbar = (
    <div className="ol-chat-preview-bar" role="region" aria-label="Chat UI 预览控制台">
      <div className="ol-chat-preview-badge">
        <FlaskConical size={15} aria-hidden />
        <strong>UI PREVIEW</strong>
        <span>仅本地 · 不保存</span>
      </div>
      <label>
        <span>阶段</span>
        <select
          aria-label="预览阶段"
          value={phase}
          onChange={(event) => navigatePreview(event.target.value as PhaseKey, previewState)}
        >
          {PHASE_ORDER.map((item) => (
            <option key={item} value={item}>
              {PHASE_COPY[item].num} {PHASE_COPY[item].label}
            </option>
          ))}
        </select>
      </label>
      <label>
        <span>场景</span>
        <select
          aria-label="预览场景"
          value={previewState}
          onChange={(event) => navigatePreview(phase, event.target.value as PreviewState)}
        >
          {PREVIEW_STATES.map((item) => (
            <option key={item.value} value={item.value}>{item.label}</option>
          ))}
        </select>
      </label>
      <button type="button" onClick={resetPreview} title="恢复当前预览数据">
        <RotateCcw size={14} aria-hidden />
        <span>重置</span>
      </button>
    </div>
  );

  const messagePane = (
    <div className="flow-chat-box relative flex min-h-0 min-w-0 flex-1 flex-col w-full max-w-none">
      <div className="flow-chat-body min-h-0 min-w-0 flex-1 overflow-y-auto w-full">
        <div className="careering-chat-messages-inner min-w-0 w-full max-w-none px-4 sm:px-6 lg:px-12">
          <PreviewMessages
            phase={phase}
            messages={messages}
            state={previewState}
            streaming={streaming}
            conclusionConfirmed={conclusionConfirmed}
            onConfirmConclusion={() => setConclusionConfirmed(true)}
          />
        </div>
      </div>
    </div>
  );

  const inputDock = (
    <div className="careering-input-dock w-full flex-shrink-0">
      <div className="flow-input-area">
        <form
          className="w-full"
          onSubmit={(event) => {
            event.preventDefault();
            handleSend();
          }}
        >
          <div className="flow-input-box">
            <textarea
              value={input}
              onChange={(event) => setInput(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === 'Enter' && !event.shiftKey) {
                  event.preventDefault();
                  handleSend();
                }
              }}
              rows={1}
              disabled={streaming}
              className="flow-input-field"
              placeholder="输入任意内容，测试消息气泡与输入状态…"
            />
            <div className="flow-send-btn-wrap">
              {streaming && <div className="flow-send-glow" aria-hidden />}
              <button
                type="button"
                className={`flow-send-btn ${streaming ? 'is-stop' : ''}`}
                disabled={!streaming && !input.trim()}
                onClick={() => {
                  if (streaming) setStreaming(false);
                  else handleSend();
                }}
                title={streaming ? '停止模拟回复' : '发送预览消息'}
              >
                {streaming ? (
                  <Square size={16} strokeWidth={0} fill="white" />
                ) : (
                  <ArrowUp size={16} strokeWidth={2.2} />
                )}
              </button>
            </div>
          </div>
          <p className="mt-1 w-full text-center text-[10px] leading-tight text-[var(--flow-text-muted)] opacity-70">
            本地预览消息不会保存，也不会调用 AI 或任何后端接口
          </p>
        </form>
      </div>
    </div>
  );

  if (phase === 'rumination') {
    return (
      <div className="rumination-beautiful-root flow-light chat-shell-h relative flex min-h-0 flex-col overflow-hidden" data-phase={phase}>
        <ExploreLandingMeshLayers />
        {toolbar}
        <div className="relative z-10 flex min-h-0 flex-1 flex-col overflow-hidden">
          <header className="ol-chat-preview-rumination-header">
            <div>
              <span>REAL-LIFE VALIDATION</span>
              <h1>{copy.num} {copy.label}</h1>
              <p>把初步方向放进真实生活中检验，让选择经得起时间沉淀。</p>
            </div>
            <button type="button" title="预览模式下不会跳转">
              <FileText size={15} aria-hidden />
              完成并继续
            </button>
          </header>
          <div className="ol-chat-preview-rumination-workbench">
            <aside className="rumination-beautiful-card ol-chat-preview-table-card">
              <RuminationTableWidget
                className="min-h-0 flex-1"
                uiVariant="glass"
                cardTitle="方向验证表"
                payload={RUMINATION_TABLE}
                confirmLabel="确认当前内容"
                inputPlaceholder="填写验证行动"
                onConfirm={() => {}}
              />
            </aside>
            <section className="rumination-beautiful-card rumination-beautiful-card--chat ol-chat-preview-rumination-chat">
              <div className="ol-chat-preview-chat-caption">
                <div>
                  <h2>和 AI 一起沉淀</h2>
                  <p>选中左侧方向后，可以继续梳理验证方式</p>
                </div>
              </div>
              {messagePane}
              {inputDock}
            </section>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div
      className="flow-light careering-matte chat-shell-h ol-chat-preview-shell relative flex min-h-0 flex-col overflow-hidden"
      data-phase={phase}
      data-chat-density={chatAppearance.density}
      data-chat-sidebar-art={chatAppearance.sidebarArt ? 'on' : 'off'}
      data-chat-newbtn={chatAppearance.newChatStyle}
    >
      <ChatPhaseBackground phase={phase} engine="silk" />
      {toolbar}
      <div className="relative z-10 flex min-h-0 flex-1 overflow-hidden">
        <ChatPhaseSidebar
          threads={threads}
          activeThreadId={activeThreadId}
          onSelectThread={(thread) => setActiveThreadId(thread.id)}
          onNewChat={handleNewThread}
          onDeleteThread={handleDeleteThread}
          canNewChat={threads.length < 5}
          phaseTitle={copy.label}
          careeringMatte
          phaseStickerSrc={`/assets/openlife-journey/sticker-${phase}.webp`}
          streamBlocksSessionSwitch={streaming}
          threadsLoading={previewState === 'loading'}
        />
        <main className="flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden">
          <header className="careering-chat-header">
            <h1 className="careering-chat-phase-title">{copy.num} {copy.label}</h1>
            <div className="careering-chat-header-actions">
              <ChatAppearancePopover />
              <button type="button" className="bd-btn-black inline-flex items-center gap-2 rounded-full px-4 py-2.5 text-sm font-semibold text-white sm:px-5" title="预览模式下不会跳转">
                <FileText size={15} strokeWidth={2} className="hidden sm:inline" aria-hidden />
                <span>完成并继续</span>
              </button>
            </div>
          </header>
          <div className="flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden py-4">
            {messagePane}
          </div>
          {inputDock}
        </main>
      </div>
    </div>
  );
}
