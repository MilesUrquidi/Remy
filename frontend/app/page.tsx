"use client";

import { useState, useEffect, useRef } from "react";

// Palette
// #2C5F2E — deep forest green (primary)
// #97BC62 — fresh herb green (secondary)
// #FFF8F0 — warm white (background)
// #D4A017 — golden mustard (accent / CTA)

const BACKEND_URL = "http://localhost:8000";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

type StepCheckData = {
  completed: boolean;
  state: { completed: boolean; explanation: string };
  action: { completed: boolean; explanation: string };
};

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const LOADING_MESSAGES = [
  "Checking your pantry…",
  "Sharpening the knives…",
  "Preheating the oven…",
  "Tasting the sauce…",
  "Getting ready to cook…",
];

function isValidUrl(str: string) {
  try {
    const url = new URL(str);
    return url.protocol === "http:" || url.protocol === "https:";
  } catch {
    return false;
  }
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

export default function Home() {
  const [phase, setPhase] = useState<"prompt" | "loading" | "coaching">("prompt");
  const [inputMode, setInputMode] = useState<"describe" | "url">("describe");
  const [prompt, setPrompt] = useState("");
  const [recipeUrl, setRecipeUrl] = useState("");
  const [urlParsed, setUrlParsed] = useState(false);
  const [urlParsing, setUrlParsing] = useState(false);
  const [currentStep, setCurrentStep] = useState(0);
  const [done, setDone] = useState(false);
  const [animating, setAnimating] = useState(false);
  const [displayStep, setDisplayStep] = useState(0);
  const [loadingMsg, setLoadingMsg] = useState(LOADING_MESSAGES[0]);

  // ── Real data from backend ─────────────────────────────────────
  const [steps, setSteps] = useState<string[]>([]);
  const [stepDetails, setStepDetails] = useState<Record<string, string>>({});
  const [remySpeech, setRemySpeech] = useState<string>("");
  const [stepCompleted, setStepCompleted] = useState(false);
  const [stepCheckData, setStepCheckData] = useState<StepCheckData | null>(null);
  const [apiError, setApiError] = useState<string | null>(null);

  const eventSourceRef = useRef<EventSource | null>(null);

  // Cleanup SSE on unmount
  useEffect(() => {
    return () => { eventSourceRef.current?.close(); };
  }, []);

  // ── SSE connection ─────────────────────────────────────────────

  function connectSSE() {
    eventSourceRef.current?.close();
    const es = new EventSource(`${BACKEND_URL}/stream`);

    es.onmessage = (event) => {
      try {
        const msg = JSON.parse(event.data);

        if (msg.type === "step_check") {
          const data = msg.data;
          if (data && typeof data === "object") {
            setStepCheckData(data as StepCheckData);
            if (data.completed) setStepCompleted(true);
          }
        } else if (msg.type === "speech") {
          setRemySpeech(msg.data as string);
        }
      } catch {
        // ignore malformed frames
      }
    };

    es.onerror = () => {
      // EventSource auto-reconnects; silently suppress
    };

    eventSourceRef.current = es;
  }

  // ── Step details (optional, background fetch) ──────────────────

  async function loadStepDetails(step: string) {
    try {
      const res = await fetch(`${BACKEND_URL}/step/details?step=${encodeURIComponent(step)}`);
      const data = await res.json();
      if (data.details) {
        setStepDetails(prev => ({ ...prev, [step]: data.details }));
      }
    } catch {
      // optional — fine to fail silently
    }
  }

  // ── Navigation helpers ─────────────────────────────────────────

  function crossFadeTo(nextPhase: "prompt" | "loading" | "coaching") {
    setPhase(nextPhase);
  }

  function handleUrlChange(val: string) {
    setRecipeUrl(val);
    setUrlParsed(false);
    setUrlParsing(false);
    if (isValidUrl(val.trim())) {
      setUrlParsing(true);
      setTimeout(() => { setUrlParsing(false); setUrlParsed(true); }, 1200);
    }
  }

  function switchMode(mode: "describe" | "url") {
    setInputMode(mode);
    setUrlParsed(false);
    setUrlParsing(false);
  }

  function canStart() {
    if (inputMode === "describe") return prompt.trim().length > 0;
    return urlParsed;
  }

  // ── Start — calls backend, then connects SSE ───────────────────

  async function handleStart() {
    if (!canStart()) return;
    setApiError(null);
    crossFadeTo("loading");

    let i = 0;
    const interval = setInterval(() => {
      i = (i + 1) % LOADING_MESSAGES.length;
      setLoadingMsg(LOADING_MESSAGES[i]);
    }, 800);

    try {
      const food = inputMode === "describe" ? prompt.trim() : recipeUrl.trim();

      // 1. Generate recipe steps
      const genRes = await fetch(`${BACKEND_URL}/recipe/generate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ food }),
      });
      if (!genRes.ok) throw new Error(`Recipe generation failed (${genRes.status})`);
      const genData = await genRes.json();
      const newSteps: string[] = genData.steps;
      setSteps(newSteps);

      // 2. Start camera + AI pipeline
      await fetch(`${BACKEND_URL}/camera/start`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({}),
      });

      // 3. Set first step
      await fetch(`${BACKEND_URL}/recipe/set-step`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ step: newSteps[0] }),
      });

      // 4. Open SSE stream
      connectSSE();

      clearInterval(interval);
      setCurrentStep(0);
      setDisplayStep(0);
      setStepCompleted(false);
      setStepCheckData(null);
      setRemySpeech("");
      crossFadeTo("coaching");

      // 5. Load first step details in background
      loadStepDetails(newSteps[0]);

    } catch (err) {
      clearInterval(interval);
      const msg = err instanceof Error ? err.message : "Something went wrong";
      setApiError(`${msg} — is the backend running on port 8000?`);
      crossFadeTo("prompt");
    }
  }

  // ── Advance step ───────────────────────────────────────────────

  async function handleNext() {
    if (animating) return;
    const nextIdx = currentStep + 1;

    if (nextIdx >= steps.length) {
      eventSourceRef.current?.close();
      try { await fetch(`${BACKEND_URL}/camera/stop`, { method: "POST" }); } catch {}
      setDone(true);
      return;
    }

    setAnimating(true);
    setStepCompleted(false);
    setStepCheckData(null);

    try {
      await fetch(`${BACKEND_URL}/recipe/set-step`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ step: steps[nextIdx] }),
      });
    } catch {}

    setCurrentStep(nextIdx);
    setTimeout(() => {
      setDisplayStep(nextIdx);
      setAnimating(false);
      loadStepDetails(steps[nextIdx]);
    }, 400);
  }

  // ── PROMPT SCREEN ──────────────────────────────────────────────

  if (phase === "prompt") {
    return (
      <div className="relative flex h-screen w-screen overflow-hidden" style={{ background: "#FFF8F0" }}>
        <style>{`
          @keyframes tabSlide {
            from { opacity: 0; transform: translateY(8px); }
            to   { opacity: 1; transform: translateY(0); }
          }
          .tab-content { animation: tabSlide 0.2s ease forwards; }
          @keyframes spin { to { transform: rotate(360deg); } }
          .spinner { animation: spin 0.8s linear infinite; }
        `}</style>

        <CameraPip />

        <div className="flex-1 flex flex-col items-center justify-center gap-7 px-12">

          {/* Brand */}
          <div className="w-full max-w-lg flex flex-col items-center gap-2 text-center">
            <div className="flex items-center gap-3 mb-1">
              <span className="text-5xl">🐀</span>
              <span className="text-6xl font-bold tracking-tight" style={{ color: "#2C5F2E" }}>Remy</span>
            </div>
            <p className="text-base font-medium" style={{ color: "#97BC62" }}>your AI sous chef</p>
            <div className="w-12 h-0.5 rounded-full my-2" style={{ background: "#D4A017" }} />
            <h1 className="text-2xl font-semibold" style={{ color: "#3a3a2a" }}>What are we cooking?</h1>
            <p className="text-sm" style={{ color: "#97BC62" }}>
              Tell Remy what you want to make — he'll guide you through it hands-free.
            </p>
          </div>

          {/* Error banner */}
          {apiError && (
            <div className="w-full max-w-lg rounded-xl px-4 py-3 text-sm" style={{ background: "#fee2e2", color: "#dc2626", border: "1px solid #fca5a5" }}>
              ⚠️ {apiError}
            </div>
          )}

          {/* Mode toggle */}
          <div className="w-full max-w-lg flex rounded-2xl p-1 gap-1" style={{ background: "#e8e0d8" }}>
            {(["describe", "url"] as const).map((mode) => (
              <button
                key={mode}
                onClick={() => switchMode(mode)}
                className="flex-1 rounded-xl py-2 text-sm font-semibold transition-all"
                style={{
                  background: inputMode === mode ? "#fff" : "transparent",
                  color: inputMode === mode ? "#2C5F2E" : "#97BC62",
                  boxShadow: inputMode === mode ? "0 1px 4px #0001" : "none",
                }}
              >
                {mode === "describe" ? "✏️  Describe a dish" : "🔗  Paste a recipe URL"}
              </button>
            ))}
          </div>

          {/* Input */}
          <div className="w-full max-w-lg tab-content" key={inputMode}>
            {inputMode === "describe" ? (
              <textarea
                autoFocus
                className="w-full text-base rounded-2xl px-4 py-3 resize-none outline-none leading-relaxed h-36 focus:ring-2"
                style={{ background: "#fff", color: "#3a3a2a", border: "1.5px solid #97BC62", caretColor: "#D4A017" }}
                placeholder="e.g. Spaghetti carbonara, chocolate chip cookies, chicken stir fry…"
                value={prompt}
                onChange={(e) => setPrompt(e.target.value)}
                onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); handleStart(); } }}
              />
            ) : (
              <div className="flex flex-col gap-3">
                <div
                  className="flex items-center gap-3 rounded-2xl px-4 py-3"
                  style={{ background: "#fff", border: `1.5px solid ${urlParsed ? "#2C5F2E" : "#97BC62"}` }}
                >
                  <svg className="w-5 h-5 shrink-0" fill="none" viewBox="0 0 24 24" stroke="#97BC62" strokeWidth={1.5}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M13.828 10.172a4 4 0 00-5.656 0l-4 4a4 4 0 105.656 5.656l1.102-1.101" />
                    <path strokeLinecap="round" strokeLinejoin="round" d="M10.172 13.828a4 4 0 015.656 0l4 4a4 4 0 01-5.656 5.656l-1.102-1.101" />
                  </svg>
                  <input
                    autoFocus
                    type="url"
                    className="flex-1 text-base outline-none bg-transparent"
                    style={{ color: "#3a3a2a", caretColor: "#D4A017" }}
                    placeholder="https://www.allrecipes.com/recipe/…"
                    value={recipeUrl}
                    onChange={(e) => handleUrlChange(e.target.value)}
                  />
                  {urlParsing && (
                    <svg className="spinner w-4 h-4 shrink-0" fill="none" viewBox="0 0 24 24" stroke="#D4A017" strokeWidth={2}>
                      <path strokeLinecap="round" strokeLinejoin="round" d="M4 12a8 8 0 018-8" />
                    </svg>
                  )}
                  {urlParsed && (
                    <svg className="w-4 h-4 shrink-0" fill="none" viewBox="0 0 24 24" stroke="#2C5F2E" strokeWidth={2.5}>
                      <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
                    </svg>
                  )}
                </div>
                {urlParsed ? (
                  <p className="text-xs text-center" style={{ color: "#2C5F2E" }}>✓ URL ready — click Let&apos;s Cook to start</p>
                ) : urlParsing ? (
                  <p className="text-xs text-center" style={{ color: "#97BC62" }}>Reading recipe…</p>
                ) : (
                  <p className="text-xs text-center" style={{ color: "#b0a898" }}>
                    Works with AllRecipes, NYT Cooking, Serious Eats, Food Network & more
                  </p>
                )}
              </div>
            )}
          </div>

          <button
            onClick={handleStart}
            disabled={!canStart()}
            className="w-full max-w-lg rounded-2xl py-3 text-base font-semibold transition-all disabled:opacity-30 disabled:cursor-not-allowed hover:brightness-110 active:scale-[0.98]"
            style={{ background: "#D4A017", color: "#fff" }}
          >
            Let&apos;s Cook →
          </button>
        </div>
      </div>
    );
  }

  // ── LOADING SCREEN ─────────────────────────────────────────────

  if (phase === "loading") {
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
        <CameraPip />
        <div className="flex-1 flex flex-col items-center justify-center gap-8">
          <span className="text-7xl" style={{ filter: "drop-shadow(0 4px 12px #2C5F2E44)" }}>🐀</span>
          <div className="flex flex-col items-center gap-3">
            <span className="text-3xl font-bold" style={{ color: "#2C5F2E" }}>Remy is thinking…</span>
            <span key={loadingMsg} className="loading-msg text-base" style={{ color: "#97BC62" }}>{loadingMsg}</span>
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

  // ── COMPLETION SCREEN ──────────────────────────────────────────

  if (done) {
    return (
      <div className="relative flex h-screen w-screen overflow-hidden" style={{ background: "#FFF8F0" }}>
        <style>{`
          @keyframes popIn {
            0%   { opacity: 0; transform: scale(0.5) rotate(-10deg); }
            70%  { transform: scale(1.15) rotate(3deg); }
            100% { opacity: 1; transform: scale(1) rotate(0deg); }
          }
        `}</style>
        <CameraPip />
        <div className="flex-1 flex flex-col items-center justify-center gap-6 px-12">
          <div style={{ animation: "popIn 0.6s cubic-bezier(.34,1.56,.64,1) forwards" }} className="text-7xl">🍽️</div>
          <h2 className="text-4xl font-bold text-center" style={{ color: "#2C5F2E" }}>Bon appétit!</h2>
          <p className="text-lg text-center max-w-md" style={{ color: "#5a5a4a" }}>You nailed it. Remy is proud of you.</p>
          <button
            onClick={() => {
              eventSourceRef.current?.close();
              setPrompt(""); setRecipeUrl(""); setUrlParsed(false);
              setCurrentStep(0); setDisplayStep(0); setDone(false);
              setSteps([]); setStepDetails({}); setRemySpeech("");
              setStepCompleted(false); setStepCheckData(null);
              crossFadeTo("prompt");
            }}
            className="mt-4 rounded-2xl px-8 py-3 text-sm font-medium transition-all hover:brightness-110"
            style={{ background: "#97BC62", color: "#2C5F2E" }}
          >
            Cook something else
          </button>
        </div>
      </div>
    );
  }

  // ── COACHING SCREEN ────────────────────────────────────────────

  const currentStepLabel = steps[displayStep] ?? "";
  const currentStepDetail = stepDetails[currentStepLabel];

  return (
    <>
      <style>{`
        @keyframes stepIn {
          from { opacity: 0; transform: translateX(50px); }
          to   { opacity: 1; transform: translateX(0); }
        }
        .step-in { animation: stepIn 0.35s ease forwards; }
        .wave-bar { transform-origin: bottom; display: inline-block; width: 3px; border-radius: 2px; background: #D4A017; }
        @keyframes completedPulse {
          0%, 100% { box-shadow: 0 0 0 0 #2C5F2E55; }
          50%       { box-shadow: 0 0 0 6px #2C5F2E00; }
        }
        .completed-badge { animation: completedPulse 1.8s ease-in-out infinite; }
      `}</style>

      <div className="relative flex h-screen w-screen overflow-hidden" style={{ background: "#FFF8F0" }}>
        <CameraPip position="right-center" />

        <div className="flex-1 flex flex-col">

          {/* Header */}
          <div className="pt-7 pb-0 flex flex-col items-center gap-2">
            <div className="flex items-center gap-2">
              <span className="text-2xl">🐀</span>
              <span className="text-3xl font-bold tracking-tight" style={{ color: "#2C5F2E" }}>Remy</span>
            </div>
            {/* Step progress dots */}
            <div className="flex items-center gap-2">
              {steps.map((_, i) => (
                <div
                  key={i}
                  className="rounded-full transition-all duration-500"
                  style={{
                    width: i === currentStep ? "24px" : "8px",
                    height: "8px",
                    background: i < currentStep ? "#2C5F2E" : i === currentStep ? "#D4A017" : "#97BC62",
                  }}
                />
              ))}
            </div>
          </div>

          {/* Step content */}
          <div key={displayStep} className="step-in flex-1 flex flex-col">
            <div className="flex-1 flex flex-col justify-center px-16 gap-4" style={{ maxWidth: "55%" }}>

              {/* Step label + status badge */}
              <div className="flex items-center gap-3 flex-wrap">
                <span className="text-xs uppercase tracking-widest font-semibold" style={{ color: "#97BC62" }}>
                  Step {displayStep + 1} of {steps.length}
                </span>

                {stepCompleted && (
                  <span
                    className="completed-badge text-xs font-semibold px-2.5 py-1 rounded-full flex items-center gap-1"
                    style={{ background: "#2C5F2E15", color: "#2C5F2E", border: "1.5px solid #2C5F2E50" }}
                  >
                    ✓ Step complete!
                  </span>
                )}

                {stepCheckData && !stepCompleted && (
                  <span
                    className="text-xs font-medium px-2.5 py-1 rounded-full"
                    style={{ background: "#D4A01715", color: "#D4A017", border: "1.5px solid #D4A01740" }}
                  >
                    👁 Watching…
                  </span>
                )}
              </div>

              {/* Step title */}
              <h2 className="text-5xl font-bold leading-tight" style={{ color: "#3a3a2a" }}>
                {currentStepLabel}
              </h2>

              {/* Step how-to detail (loaded from /step/details) */}
              {currentStepDetail && (
                <p className="text-xl leading-relaxed" style={{ color: "#5a5a4a" }}>
                  {currentStepDetail}
                </p>
              )}

              {/* Live AI vision feedback */}
              {stepCheckData && (
                <div className="flex flex-col gap-1 mt-1">
                  {stepCheckData.state?.explanation && (
                    <p className="text-sm" style={{ color: "#7a9a5a" }}>
                      <span className="font-semibold">State:</span> {stepCheckData.state.explanation}
                    </p>
                  )}
                  {stepCheckData.action?.explanation &&
                    stepCheckData.action.explanation !== stepCheckData.state?.explanation && (
                    <p className="text-sm" style={{ color: "#7a9a5a" }}>
                      <span className="font-semibold">Action:</span> {stepCheckData.action.explanation}
                    </p>
                  )}
                </div>
              )}
            </div>

            {/* Remy says — speech responses */}
            <div className="mx-16 mb-6 rounded-2xl p-4 flex gap-3 items-start" style={{ background: "#2C5F2E15", border: "1px solid #2C5F2E30" }}>
              <span className="text-xl mt-0.5">🐀</span>
              <div className="flex flex-col gap-1 flex-1">
                <span className="text-xs font-semibold uppercase tracking-widest" style={{ color: "#2C5F2E" }}>Remy says</span>
                <p className="text-sm leading-relaxed" style={{ color: "#3a3a2a" }}>
                  {remySpeech || "Listening and watching… ask me anything about this step!"}
                </p>
              </div>
              <div className="ml-auto flex flex-col items-end gap-1.5 shrink-0 mt-1">
                <Waveform />
                <span className="text-xs" style={{ color: "#97BC62" }}>listening</span>
              </div>
            </div>

            {/* Up next */}
            {displayStep < steps.length - 1 && (
              <div className="px-16 pb-4 flex items-center gap-3">
                <span className="text-xs uppercase tracking-widest font-medium shrink-0" style={{ color: "#97BC62" }}>Up next</span>
                <span className="text-sm truncate" style={{ color: "#97BC62" }}>
                  {steps[displayStep + 1]}
                </span>
              </div>
            )}
          </div>

          {/* CTA button */}
          <div className="px-16 pb-8">
            <button
              onClick={handleNext}
              disabled={animating}
              className="w-full rounded-2xl py-4 text-lg font-semibold transition-all hover:brightness-110 active:scale-[0.98] disabled:opacity-50"
              style={{
                background: stepCompleted ? "#2C5F2E" : "#D4A017",
                color: "#fff",
                transition: "background 0.4s ease",
              }}
            >
              {currentStep < steps.length - 1
                ? stepCompleted ? "✓  Step Done — Next →" : "Mark Done — Next →"
                : stepCompleted ? "✓  Finish!" : "Mark Complete"}
            </button>
          </div>

        </div>
      </div>
    </>
  );
}

// ---------------------------------------------------------------------------
// Waveform visualizer
// ---------------------------------------------------------------------------

function Waveform() {
  const bars = [0.4, 0.7, 1.0, 0.6, 0.9, 0.5, 0.8, 0.4, 0.7, 1.0, 0.6, 0.5];
  return (
    <div className="flex items-end gap-0.5" style={{ height: "20px" }}>
      <style>{`
        ${bars.map((_, i) => `
          @keyframes wave${i} {
            0%, 100% { transform: scaleY(${(bars[i] * 0.3).toFixed(2)}); }
            50%       { transform: scaleY(${bars[i].toFixed(2)}); }
          }
        `).join("")}
        ${bars.map((_, i) => `.wb${i} { animation: wave${i} ${(0.6 + i * 0.07).toFixed(2)}s ease-in-out ${(i * 0.05).toFixed(2)}s infinite; }`).join("")}
      `}</style>
      {bars.map((_, i) => (
        <span key={i} className={`wave-bar wb${i}`} style={{ height: "20px" }} />
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Camera PiP
// ---------------------------------------------------------------------------

function CameraPip({ position }: { position?: "top-left" | "right-center" }) {
  const isRight = position === "right-center";
  const connected = false; // swap to true when real stream is connected

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
        <div className="w-full h-full" style={{ background: "#97BC6240" }} />
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
