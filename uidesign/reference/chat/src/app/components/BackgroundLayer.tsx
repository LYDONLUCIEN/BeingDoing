import { useEffect, useState } from 'react';

type BackgroundType = 'mesh' | 'frequency' | 'prism';

interface BackgroundLayerProps {
  type: BackgroundType;
  active: boolean;
}

function BackgroundLayer({ type, active }: BackgroundLayerProps) {
  const baseClasses = `fixed top-0 left-0 right-0 bottom-0 transition-opacity duration-[800ms] ease-in-out pointer-events-none ${
    active ? 'opacity-100 visible' : 'opacity-0 invisible'
  }`;

  if (type === 'mesh') {
    return (
      <div className={baseClasses} style={{ zIndex: 1 }}>
        <div className="absolute w-[40vw] h-[40vw] rounded-full blur-[80px] opacity-90 animate-float top-[-5%] left-[-5%]" 
             style={{ background: 'rgba(162, 194, 232, 0.9)', animationDelay: '0s' }} />
        <div className="absolute w-[35vw] h-[35vw] rounded-full blur-[80px] opacity-90 animate-float bottom-0 right-[-5%]" 
             style={{ background: 'rgba(181, 216, 198, 0.9)', animationDelay: '-3s' }} />
        <div className="absolute w-[30vw] h-[30vw] rounded-full blur-[80px] opacity-90 animate-float top-[40%] left-[30%]" 
             style={{ background: 'rgba(244, 179, 179, 0.9)', animationDelay: '-7s' }} />
        <div className="absolute w-[25vw] h-[25vw] rounded-full blur-[80px] opacity-90 animate-float top-[-5%] right-[20%]" 
             style={{ background: 'rgba(253, 224, 147, 0.9)', animationDelay: '-11s' }} />
      </div>
    );
  }

  if (type === 'frequency') {
    return (
      <div className={`${baseClasses} overflow-hidden`} style={{ zIndex: 1 }}>
        <div className="absolute top-1/2 left-1/2 w-[100px] h-[100px] border-2 rounded-full animate-ripple" 
             style={{ borderColor: 'rgba(162, 194, 232, 0.9)', animationDelay: '0s' }} />
        <div className="absolute top-1/2 left-1/2 w-[100px] h-[100px] border-2 rounded-full animate-ripple" 
             style={{ borderColor: 'rgba(181, 216, 198, 0.9)', animationDelay: '2s' }} />
        <div className="absolute top-1/2 left-1/2 w-[100px] h-[100px] border-2 rounded-full animate-ripple" 
             style={{ borderColor: 'rgba(244, 179, 179, 0.9)', animationDelay: '4s' }} />
        <div className="absolute top-1/2 left-1/2 w-[100px] h-[100px] border-2 rounded-full animate-ripple" 
             style={{ borderColor: 'rgba(253, 224, 147, 0.9)', animationDelay: '6s' }} />
      </div>
    );
  }

  if (type === 'prism') {
    return (
      <div 
        className={baseClasses} 
        style={{ 
          zIndex: 1,
          background: 'linear-gradient(120deg, #faf9f8 0%, #faf9f8 30%, rgba(162, 194, 232, 0.9) 45%, rgba(181, 216, 198, 0.9) 50%, rgba(253, 224, 147, 0.9) 55%, rgba(244, 179, 179, 0.9) 60%, #faf9f8 75%, #faf9f8 100%)',
          backgroundSize: '300% 300%',
          animation: 'prismSweep 8s linear infinite alternate',
        }}
      />
    );
  }

  return null;
}

export function AnimatedBackground() {
  const [activeBackground, setActiveBackground] = useState<BackgroundType>('mesh');

  return (
    <>
      <style>{`
        @keyframes float {
          0% { transform: translate(0, 0) scale(1); }
          100% { transform: translate(10vw, 10vh) scale(1.2); }
        }

        .animate-float {
          animation: float 15s infinite alternate cubic-bezier(0.4, 0, 0.2, 1);
          will-change: transform;
        }

        @keyframes rippleExpand {
          0% { transform: translate(-50%, -50%) scale(0.1); opacity: 0.8; }
          100% { transform: translate(-50%, -50%) scale(30); opacity: 0; }
        }

        .animate-ripple {
          animation: rippleExpand 8s cubic-bezier(0.1, 0.8, 0.5, 1) infinite;
          will-change: transform, opacity;
          background: rgba(0, 0, 0, 0.01);
        }

        @keyframes prismSweep {
          0% { background-position: 0% 50%; }
          100% { background-position: 100% 50%; }
        }
      `}</style>

      {/* Background layers */}
      <BackgroundLayer type="mesh" active={activeBackground === 'mesh'} />
      <BackgroundLayer type="frequency" active={activeBackground === 'frequency'} />
      <BackgroundLayer type="prism" active={activeBackground === 'prism'} />

      {/* Noise overlay */}
      <div 
        className="fixed top-0 left-0 w-screen h-screen pointer-events-none opacity-[0.05]" 
        style={{ 
          zIndex: 2,
          backgroundImage: "url(\"data:image/svg+xml,%3Csvg viewBox='0 0 200 200' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='noiseFilter'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.8' numOctaves='3' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23noiseFilter)'/%3E%3C/svg%3E\")"
        }}
      />
    </>
  );
}
