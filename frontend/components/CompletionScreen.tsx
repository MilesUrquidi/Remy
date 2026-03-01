"use client";

interface CompletionScreenProps {
  onCookAgain: () => void;
}

export default function CompletionScreen({ onCookAgain }: CompletionScreenProps) {
  return (
    <div className="relative flex h-screen w-screen overflow-hidden" style={{ background: "#FFF8F0" }}>
      <style>{`
        @keyframes popIn {
          0%   { opacity: 0; transform: scale(0.5) rotate(-10deg); }
          70%  { transform: scale(1.15) rotate(3deg); }
          100% { opacity: 1; transform: scale(1) rotate(0deg); }
        }
      `}</style>
      <div className="flex-1 flex flex-col items-center justify-center gap-6 px-12">
        <div style={{ animation: "popIn 0.6s cubic-bezier(.34,1.56,.64,1) forwards" }} className="text-7xl">{"\uD83C\uDF7D\uFE0F"}</div>
        <h2 className="text-4xl font-bold text-center" style={{ color: "#2C5F2E" }}>Bon app{"\u00E9"}tit!</h2>
        <p className="text-lg text-center max-w-md" style={{ color: "#5a5a4a" }}>You nailed it. Remy is proud of you.</p>
        <button
          onClick={onCookAgain}
          className="mt-4 rounded-2xl px-8 py-3 text-sm font-semibold transition-all duration-200 ease-out hover:brightness-105 hover:scale-[1.01] active:scale-[0.98]"
          style={{ background: "#D4A017", color: "#fff" }}
        >
          Cook something else
        </button>
      </div>
    </div>
  );
}
