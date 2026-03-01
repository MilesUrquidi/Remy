"use client";

const BARS = [0.4, 0.7, 1.0, 0.6, 0.9, 0.5, 0.8, 0.4, 0.7, 1.0, 0.6, 0.5];

export default function Waveform() {
  return (
    <div className="flex items-end gap-0.5" style={{ height: "20px" }}>
      <style>{`
        ${BARS.map((_, i) => `
          @keyframes wave${i} {
            0%, 100% { transform: scaleY(${(BARS[i] * 0.3).toFixed(2)}); }
            50%       { transform: scaleY(${BARS[i].toFixed(2)}); }
          }
        `).join("")}
        ${BARS.map((_, i) => `.wb${i} { animation: wave${i} ${(0.6 + i * 0.07).toFixed(2)}s ease-in-out ${(i * 0.05).toFixed(2)}s infinite; }`).join("")}
      `}</style>
      {BARS.map((_, i) => (
        <span
          key={i}
          className={`wave-bar wb${i}`}
          style={{
            height: "20px",
            transformOrigin: "bottom",
            display: "inline-block",
            width: "3px",
            borderRadius: "2px",
            background: "#D4A017",
          }}
        />
      ))}
    </div>
  );
}
