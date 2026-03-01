"use client";

import { BACKEND_URL } from "./constants";

interface CameraPipProps {
  position?: "top-left" | "right-center";
  connected?: boolean;
}

export default function CameraPip({ position, connected = false }: CameraPipProps) {
  const isRight = position === "right-center";

  return (
    <div
      className="absolute z-10 rounded-2xl overflow-hidden shadow-lg"
      style={isRight ? {
        top: "44%", right: "180px", transform: "translateY(-50%)",
        width: "580px", aspectRatio: "16/9",
        background: "#1c1c1c",
        border: "2px solid #2C5F2E33",
      } : {
        top: "20px", left: "20px",
        width: "480px", aspectRatio: "16/9",
        background: "#1c1c1c",
        border: "2px solid #2C5F2E33",
      }}
    >
      {connected ? (
        // eslint-disable-next-line @next/next/no-img-element
        <img
          src={`${BACKEND_URL}/camera/feed`}
          alt="Live camera feed"
          className="w-full h-full object-cover"
        />
      ) : (
        <div className="w-full h-full flex flex-col items-center justify-center gap-2">
          <svg className="w-6 h-6 opacity-30" fill="none" viewBox="0 0 24 24" stroke="#fff" strokeWidth={1.5}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M15.75 10.5l4.72-2.36A.75.75 0 0121.75 8.9v6.2a.75.75 0 01-1.28.53l-4.72-2.36M3.75 7.5h9a2.25 2.25 0 012.25 2.25v4.5A2.25 2.25 0 0112.75 16.5h-9A2.25 2.25 0 011.5 14.25v-4.5A2.25 2.25 0 013.75 7.5z" />
            <path strokeLinecap="round" strokeLinejoin="round" d="M3 3l18 18" />
          </svg>
          <span className="text-xs opacity-30 tracking-wide" style={{ color: "#fff" }}>No camera connected</span>
        </div>
      )}

      {/* Status badge */}
      <div className="absolute top-2 left-2 flex items-center gap-1.5 rounded-full px-2 py-0.5" style={{ background: "#000000aa" }}>
        <span className="w-1.5 h-1.5 rounded-full animate-pulse" style={{ background: connected ? "#D4A017" : "#666" }} />
        <span className="font-medium tracking-widest uppercase" style={{ color: connected ? "#FFF8F0" : "#888", fontSize: "9px" }}>
          {connected ? "Live" : "Offline"}
        </span>
      </div>
    </div>
  );
}
