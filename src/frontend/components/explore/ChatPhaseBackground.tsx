import type { PhaseKey } from '@/lib/explore/session';

/** rumination：保留原悬浮球光晕 */
const PHASE_BLOBS: Record<PhaseKey, [string, string, string, string]> = {
  values: [
    'rgba(91, 141, 184, 0.7)',
    'rgba(100, 155, 210, 0.55)',
    'rgba(130, 175, 220, 0.6)',
    'rgba(160, 195, 235, 0.5)',
  ],
  strengths: [
    'rgba(106, 158, 127, 0.7)',
    'rgba(100, 175, 130, 0.55)',
    'rgba(130, 190, 150, 0.6)',
    'rgba(160, 210, 175, 0.5)',
  ],
  interests: [
    'rgba(196, 114, 90, 0.7)',
    'rgba(210, 120, 95, 0.55)',
    'rgba(225, 140, 110, 0.6)',
    'rgba(240, 165, 130, 0.5)',
  ],
  purpose: [
    'rgba(201, 168, 76, 0.7)',
    'rgba(215, 175, 90, 0.55)',
    'rgba(228, 195, 120, 0.6)',
    'rgba(240, 215, 150, 0.5)',
  ],
  rumination: [
    'rgba(139, 92, 246, 0.7)',
    'rgba(147, 51, 234, 0.55)',
    'rgba(167, 139, 250, 0.6)',
    'rgba(196, 181, 253, 0.5)',
  ],
};

/**
 * Silk 背景主题键（与 careering-chat-matte.css 中 data-careering-theme 对应）
 * 约定：信念 Blue · 禀赋 Green · 热忱 Pink · 使命 Yellow
 */
const SILK_THEME_KEY: Partial<Record<PhaseKey, 'blue' | 'yellow' | 'green' | 'pink'>> = {
  values: 'blue',
  strengths: 'green',
  interests: 'pink',
  purpose: 'yellow',
};

interface ChatPhaseBackgroundProps {
  phase: PhaseKey;
  /** mesh：原四球；silk：newchat6 苍蓝/奶黄/薄荷/樱红 + 涟漪面（仅前四维） */
  engine?: 'mesh' | 'silk';
}

export default function ChatPhaseBackground({ phase, engine = 'mesh' }: ChatPhaseBackgroundProps) {
  if (engine === 'silk' && SILK_THEME_KEY[phase]) {
    const tk = SILK_THEME_KEY[phase]!;
    return (
      <div
        className="careering-bg-root"
        data-careering-theme={tk}
        aria-hidden
      >
        <div className="careering-bg-solid" />
        <div className="careering-silk-blob careering-silk-blob--1" />
        <div className="careering-silk-blob careering-silk-blob--2" />
        <div className="careering-silk-blob careering-silk-blob--3" />
      </div>
    );
  }

  const blobs = PHASE_BLOBS[phase];
  return (
    <div className="fixed inset-0 pointer-events-none z-0 overflow-hidden" aria-hidden>
      <div
        className="flow-phase-blob absolute w-[45vw] h-[45vw] rounded-full blur-[100px] opacity-90"
        style={{ background: blobs[0], top: '-8%', left: '-8%' }}
      />
      <div
        className="flow-phase-blob flow-phase-blob-2 absolute w-[38vw] h-[38vw] rounded-full blur-[90px] opacity-90"
        style={{ background: blobs[1], bottom: '-5%', right: '-5%' }}
      />
      <div
        className="flow-phase-blob flow-phase-blob-3 absolute w-[32vw] h-[32vw] rounded-full blur-[85px] opacity-85"
        style={{ background: blobs[2], top: '35%', left: '25%' }}
      />
      <div
        className="flow-phase-blob flow-phase-blob-4 absolute w-[28vw] h-[28vw] rounded-full blur-[80px] opacity-80"
        style={{ background: blobs[3], top: '-5%', right: '18%' }}
      />
      <div
        className="absolute inset-0 opacity-90"
        style={{
          background: `linear-gradient(135deg, rgba(255,255,255,0.5) 0%, rgba(255,255,255,0.7) 50%, rgba(255,255,255,0.5) 100%)`,
        }}
      />
    </div>
  );
}
