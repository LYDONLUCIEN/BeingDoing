import { useState } from 'react';

type BackgroundType = 'mesh' | 'frequency' | 'prism';

interface BackgroundLayersProps {
  language: 'en' | 'zh';
}

export function BackgroundLayers({ language }: BackgroundLayersProps) {
  const [activeBg] = useState<BackgroundType>('prism');

  return (
    <>
      {/* Background 1: Mesh Blobs */}
      <div className={`bg-layer ${activeBg === 'mesh' ? 'active' : ''}`}>
        <div className="mesh-blob blob-1"></div>
        <div className="mesh-blob blob-2"></div>
        <div className="mesh-blob blob-3"></div>
        <div className="mesh-blob blob-4"></div>
      </div>

      {/* Background 2: Radar Ripples */}
      <div className={`bg-layer ${activeBg === 'frequency' ? 'active' : ''}`}>
        <div className="ring ring-1"></div>
        <div className="ring ring-2"></div>
        <div className="ring ring-3"></div>
        <div className="ring ring-4"></div>
      </div>

      {/* Background 3: Prism Sweep */}
      <div className={`bg-layer prism-bg ${activeBg === 'prism' ? 'active' : ''}`}></div>

      {/* Noise Overlay */}
      <div className="noise-overlay"></div>
    </>
  );
}