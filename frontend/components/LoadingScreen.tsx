"use client";

interface LoadingScreenProps {
  message: string;
}

export default function LoadingScreen({ message }: LoadingScreenProps) {
  return (
    <div className="relative flex h-screen w-screen overflow-hidden" style={{ background: "#FFF8F0" }}>
      <style>{`
        @keyframes bounce1 { 0%,80%,100%{transform:translateY(0)} 40%{transform:translateY(-10px)} }
        @keyframes bounce2 { 0%,80%,100%{transform:translateY(0)} 40%{transform:translateY(-10px)} }
        @keyframes bounce3 { 0%,80%,100%{transform:translateY(0)} 40%{transform:translateY(-10px)} }
        .dot1 { animation: bounce1 1.2s ease-in-out infinite; }
        .dot2 { animation: bounce2 1.2s ease-in-out 0.2s infinite; }
        .dot3 { animation: bounce3 1.2s ease-in-out 0.4s infinite; }
        @keyframes msgFade {
          0%   { opacity: 0; transform: translateY(6px); }
          20%  { opacity: 1; transform: translateY(0); }
          80%  { opacity: 1; transform: translateY(0); }
          100% { opacity: 0; transform: translateY(-6px); }
        }
        .loading-msg { animation: msgFade 0.8s ease forwards; }
      `}</style>
      <div className="flex-1 flex flex-col items-center justify-center gap-8">
        <span className="text-7xl" style={{ filter: "drop-shadow(0 4px 12px #2C5F2E44)" }}>{"\uD83D\uDC00"}</span>
        <div className="flex flex-col items-center gap-3">
          <span className="text-3xl font-bold" style={{ color: "#2C5F2E" }}>Remy is thinking</span>
          <span key={message} className="loading-msg text-base" style={{ color: "#97BC62" }}>{message}</span>
        </div>
        <div className="flex items-end gap-2" style={{ height: "28px" }}>
          <span className="dot1 w-3 h-3 rounded-full inline-block" style={{ background: "#D4A017" }} />
          <span className="dot2 w-3 h-3 rounded-full inline-block" style={{ background: "#97BC62" }} />
          <span className="dot3 w-3 h-3 rounded-full inline-block" style={{ background: "#2C5F2E" }} />
        </div>
      </div>
    </div>
  );
}
