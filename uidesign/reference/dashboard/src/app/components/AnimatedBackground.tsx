export function AnimatedBackground() {
  return (
    <>
      {/* Mesh Blob Background */}
      <div className="fixed top-0 left-0 right-0 bottom-0 -z-10 pointer-events-none overflow-hidden">
        <div className="absolute w-[40vw] h-[40vw] top-[-5%] left-[-5%] bg-[#A2C2E8]/90 rounded-full blur-[80px] animate-[float_15s_infinite_alternate_cubic-bezier(0.4,0,0.2,1)]" />
        <div className="absolute w-[35vw] h-[35vw] bottom-0 right-[-5%] bg-[#B5D8C6]/90 rounded-full blur-[80px] animate-[float_15s_infinite_alternate_cubic-bezier(0.4,0,0.2,1)] [animation-delay:-3s]" />
        <div className="absolute w-[30vw] h-[30vw] top-[40%] left-[30%] bg-[#F4B3B3]/90 rounded-full blur-[80px] animate-[float_15s_infinite_alternate_cubic-bezier(0.4,0,0.2,1)] [animation-delay:-7s]" />
        <div className="absolute w-[25vw] h-[25vw] top-[-5%] right-[20%] bg-[#FDE093]/90 rounded-full blur-[80px] animate-[float_15s_infinite_alternate_cubic-bezier(0.4,0,0.2,1)] [animation-delay:-11s]" />
      </div>

      {/* Noise Overlay */}
      <div
        className="fixed top-0 left-0 w-screen h-screen -z-5 pointer-events-none opacity-[0.05]"
        style={{
          backgroundImage: `url("data:image/svg+xml,%3Csvg viewBox='0 0 200 200' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='noiseFilter'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.8' numOctaves='3' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23noiseFilter)'/%3E%3C/svg%3E")`,
        }}
      />
    </>
  );
}
