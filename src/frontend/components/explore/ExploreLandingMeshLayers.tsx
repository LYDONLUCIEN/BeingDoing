'use client';

/**
 * 与激活页 /explore/activate 相同的 mesh 光晕 + 噪点背景层（fixed，pointer-events: none）
 */
export default function ExploreLandingMeshLayers() {
  return (
    <>
      <div className="landing-mesh-bg fixed inset-0 z-0" aria-hidden>
        <div className="landing-mesh-blob landing-mesh-blob-1" />
        <div className="landing-mesh-blob landing-mesh-blob-2" />
        <div className="landing-mesh-blob landing-mesh-blob-3" />
        <div className="landing-mesh-blob landing-mesh-blob-4" />
      </div>
      <div className="landing-mesh-noise fixed inset-0 z-[1]" aria-hidden />
    </>
  );
}
