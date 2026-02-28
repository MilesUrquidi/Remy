"use client";

import { useState } from "react";

// Palette
// #2C5F2E — deep forest green (primary)
// #97BC62 — fresh herb green (secondary)
// #FFF8F0 — warm white (background)
// #D4A017 — golden mustard (accent / CTA)

type Step = {
  title: string;
  description: string;
};

const MOCK_STEPS: Step[] = [
  { title: "Gather your ingredients", description: "Get everything out before you start — butter, garlic, pasta, parmesan, and eggs." },
  { title: "Boil the pasta", description: "Salt your water generously — it should taste like the sea. Cook pasta to al dente." },
  { title: "Make the sauce", description: "Whisk eggs and parmesan together off the heat. Add pasta water slowly to temper." },
  { title: "Combine", description: "Toss hot pasta with the egg mixture quickly — the heat cooks the eggs without scrambling." },
  { title: "Plate and serve", description: "Twirl into a bowl, crack black pepper generously, and top with extra parmesan." },
];

const MOCK_REMY_SAYS = [
  "I can see your ingredients laid out — looks good! Make sure your eggs are room temperature before we start.",
  "Your water is boiling nicely. Don't forget the salt — a good handful, not a pinch!",
  "Whisk those eggs vigorously. You want a smooth, pale yellow mixture before adding the cheese.",
  "Work fast here! The pasta needs to be steaming hot when it hits the egg mixture.",
  "Beautiful! A little more pepper never hurt anyone. Serve immediately while it's hot.",
];

const LOADING_MESSAGES = [
  "Checking your pantry…",
  "Sharpening the knives…",
  "Preheating the oven…",
  "Tasting the sauce…",
  "Getting ready to cook…",
];

// Mock recipe preview data (shown after URL is pasted)
const MOCK_RECIPE_PREVIEW = {
  name: "Spaghetti Carbonara",
  source: "cooking.nytimes.com",
  time: "30 min",
  servings: "4 servings",
  steps: 5,
};

function isValidUrl(str: string) {
  try {
    const url = new URL(str);
    return url.protocol === "http:" || url.protocol === "https:";
  } catch {
    return false;
  }
}

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

  function crossFadeTo(nextPhase: "prompt" | "loading" | "coaching") {
    setPhase(nextPhase);
  }

  function handleUrlChange(val: string) {
    setRecipeUrl(val);
    setUrlParsed(false);
    setUrlParsing(false);
    if (isValidUrl(val.trim())) {
      setUrlParsing(true);
      setTimeout(() => {
        setUrlParsing(false);
        setUrlParsed(true);
      }, 1200);
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

  function handleStart() {
    if (!canStart()) return;
    crossFadeTo("loading");
    let i = 0;
    const interval = setInterval(() => {
      i = (i + 1) % LOADING_MESSAGES.length;
      setLoadingMsg(LOADING_MESSAGES[i]);
    }, 800);
    setTimeout(() => {
      clearInterval(interval);
      crossFadeTo("coaching");
    }, 2500);
  }

  function handleNext() {
    if (animating) return;
    if (currentStep >= MOCK_STEPS.length - 1) {
      setDone(true);
      return;
    }
    setAnimating(true);
    const next = currentStep + 1;
    setCurrentStep(next);
    setTimeout(() => {
      setDisplayStep(next);
      setAnimating(false);
    }, 400);
  }

  // ── PROMPT SCREEN ──────────────────────────────────────────────
  if (phase === "prompt") {
    return (
      <div
        className="relative flex h-screen w-screen overflow-hidden"
        style={{ background: "#FFF8F0" }}
      >
        <style>{`
          @keyframes tabSlide {
            from { opacity: 0; transform: translateY(8px); }
            to   { opacity: 1; transform: translateY(0); }
          }
          .tab-content { animation: tabSlide 0.2s ease forwards; }
          @keyframes previewIn {
            from { opacity: 0; transform: translateY(6px); }
            to   { opacity: 1; transform: translateY(0); }
          }
          .preview-in { animation: previewIn 0.3s ease forwards; }
          @keyframes spin { to { transform: rotate(360deg); } }
          .spinner { animation: spin 0.8s linear infinite; }
        `}</style>

        <CameraPip />

        <div className="flex-1 flex flex-col items-center justify-center gap-7 px-12">
          <div className="w-full max-w-lg flex flex-col items-center gap-2 text-center">
            <div className="flex items-center gap-3 mb-1">
              <span className="text-5xl">🐀</span>
              <span className="text-6xl font-bold tracking-tight" style={{ color: "#2C5F2E" }}>Remy</span>
            </div>
            <p className="text-base font-medium" style={{ color: "#97BC62" }}>your AI sous chef</p>
            <div className="w-12 h-0.5 rounded-full my-2" style={{ background: "#D4A017" }} />
            <h1 className="text-2xl font-semibold" style={{ color: "#3a3a2a" }}>What are we cooking?</h1>
            <p className="text-sm" style={{ color: "#97BC62" }}>Tell Remy what you want to make, or paste a recipe link — he'll guide you through it hands-free.</p>
          </div>

          {/* Mode toggle tabs */}
          <div className="w-full max-w-lg flex rounded-2xl p-1 gap-1" style={{ background: "#e8e0d8" }}>
            <button
              onClick={() => switchMode("describe")}
              className="flex-1 rounded-xl py-2 text-sm font-semibold transition-all"
              style={{
                background: inputMode === "describe" ? "#fff" : "transparent",
                color: inputMode === "describe" ? "#2C5F2E" : "#97BC62",
                boxShadow: inputMode === "describe" ? "0 1px 4px #0001" : "none",
              }}
            >
              ✏️  Describe a dish
            </button>
            <button
              onClick={() => switchMode("url")}
              className="flex-1 rounded-xl py-2 text-sm font-semibold transition-all"
              style={{
                background: inputMode === "url" ? "#fff" : "transparent",
                color: inputMode === "url" ? "#2C5F2E" : "#97BC62",
                boxShadow: inputMode === "url" ? "0 1px 4px #0001" : "none",
              }}
            >
              🔗  Paste a recipe URL
            </button>
          </div>

          {/* Input area */}
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
                    <path strokeLinecap="round" strokeLinejoin="round" d="M12 21a9.004 9.004 0 008.716-6.747M12 21a9.004 9.004 0 01-8.716-6.747M12 21c2.485 0 4.5-4.03 4.5-9S14.485 3 12 3m0 18c-2.485 0-4.5-4.03-4.5-9S9.515 3 12 3m0 0a8.997 8.997 0 017.843 4.582M12 3a8.997 8.997 0 00-7.843 4.582m15.686 0A11.953 11.953 0 0112 10.5c-2.998 0-5.74-1.1-7.843-2.918m15.686 0A8.959 8.959 0 0121 12c0 .778-.099 1.533-.284 2.253" />
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

                {urlParsed && (
                  <div className="preview-in rounded-2xl p-4 flex gap-4 items-center" style={{ background: "#2C5F2E0D", border: "1.5px solid #2C5F2E30" }}>
                    <div className="rounded-xl shrink-0 flex items-center justify-center text-2xl" style={{ width: 56, height: 56, background: "#97BC6240" }}>
                      🍝
                    </div>
                    <div className="flex flex-col gap-0.5 flex-1 min-w-0">
                      <span className="font-semibold text-base truncate" style={{ color: "#2C5F2E" }}>{MOCK_RECIPE_PREVIEW.name}</span>
                      <span className="text-xs truncate" style={{ color: "#97BC62" }}>{MOCK_RECIPE_PREVIEW.source}</span>
                      <div className="flex items-center gap-3 mt-1">
                        <span className="text-xs" style={{ color: "#5a5a4a" }}>⏱ {MOCK_RECIPE_PREVIEW.time}</span>
                        <span className="text-xs" style={{ color: "#5a5a4a" }}>👥 {MOCK_RECIPE_PREVIEW.servings}</span>
                        <span className="text-xs" style={{ color: "#5a5a4a" }}>📋 {MOCK_RECIPE_PREVIEW.steps} steps</span>
                      </div>
                    </div>
                    <button onClick={() => { setRecipeUrl(""); setUrlParsed(false); }} className="shrink-0 text-xs underline" style={{ color: "#97BC62" }}>
                      Change
                    </button>
                  </div>
                )}

                {!urlParsed && !urlParsing && (
                  <p className="text-xs text-center" style={{ color: "#b0a898" }}>
                    Works with AllRecipes, NYT Cooking, Serious Eats, Food Network & more
                  </p>
                )}
                {urlParsing && (
                  <p className="text-xs text-center" style={{ color: "#97BC62" }}>Reading recipe…</p>
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
            {inputMode === "url" && urlParsed ? `Cook "${MOCK_RECIPE_PREVIEW.name}" →` : "Let's Cook →"}
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
            onClick={() => { setPrompt(""); setRecipeUrl(""); setUrlParsed(false); setCurrentStep(0); setDisplayStep(0); setDone(false); crossFadeTo("prompt"); }}
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
  const step = MOCK_STEPS[displayStep];
  const remySays = MOCK_REMY_SAYS[displayStep];

  return (
    <>
      <style>{`
        @keyframes stepIn {
          from { opacity: 0; transform: translateX(50px); }
          to   { opacity: 1; transform: translateX(0); }
        }
        .step-in { animation: stepIn 0.35s ease forwards; }
        .wave-bar { transform-origin: bottom; display: inline-block; width: 3px; border-radius: 2px; background: #D4A017; }
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
            <div className="flex items-center gap-2">
              {MOCK_STEPS.map((_, i) => (
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
              <span className="text-xs uppercase tracking-widest font-semibold" style={{ color: "#97BC62" }}>
                Step {displayStep + 1} of {MOCK_STEPS.length}
              </span>
              <h2 className="text-6xl font-bold leading-tight" style={{ color: "#3a3a2a" }}>
                {step.title}
              </h2>
              <p className="text-2xl leading-relaxed" style={{ color: "#5a5a4a" }}>
                {step.description}
              </p>
            </div>

            {/* Remy says */}
            <div className="mx-16 mb-6 rounded-2xl p-4 flex gap-3 items-start" style={{ background: "#2C5F2E15", border: "1px solid #2C5F2E30" }}>
              <span className="text-xl mt-0.5">🐀</span>
              <div className="flex flex-col gap-1 flex-1">
                <span className="text-xs font-semibold uppercase tracking-widest" style={{ color: "#2C5F2E" }}>Remy says</span>
                <p className="text-sm leading-relaxed" style={{ color: "#3a3a2a" }}>{remySays}</p>
              </div>
              <div className="ml-auto flex flex-col items-end gap-1.5 shrink-0 mt-1">
                <Waveform />
                <span className="text-xs" style={{ color: "#97BC62" }}>listening</span>
              </div>
            </div>

            {displayStep < MOCK_STEPS.length - 1 && (
              <div className="px-16 pb-4 flex items-center gap-3">
                <span className="text-xs uppercase tracking-widest font-medium shrink-0" style={{ color: "#97BC62" }}>Up next</span>
                <span className="text-sm truncate" style={{ color: "#97BC62" }}>
                  {MOCK_STEPS[displayStep + 1].title}
                </span>
              </div>
            )}
          </div>

          <div className="px-16 pb-8">
            <button
              onClick={handleNext}
              disabled={animating}
              className="w-full rounded-2xl py-4 text-lg font-semibold transition-all hover:brightness-110 active:scale-[0.98] disabled:opacity-50"
              style={{ background: "#D4A017", color: "#fff" }}
            >
              {currentStep < MOCK_STEPS.length - 1 ? "✓  Step Done — Next" : "✓  Complete"}
            </button>
          </div>
        </div>
      </div>
    </>
  );
}

// ── Waveform visualizer ────────────────────────────────────────

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

// ── Camera PiP ────────────────────────────────────────────────

function CameraPip({ position }: { position?: "top-left" | "right-center" }) {
  const isRight = position === "right-center";
  // Swap to true when a real stream is connected
  const connected = false;

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
        /* replace with <video> tag when backend is ready */
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
