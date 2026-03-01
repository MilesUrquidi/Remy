"use client";

import { useState, useEffect, useRef } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import { Skeleton } from "@/components/ui/skeleton";

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
  hint?: string;
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
  "Swapping ingredients…",
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
  const [phase, setPhase] = useState<"prompt" | "loading" | "allergens" | "coaching">("prompt");
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
  const [stepImages, setStepImages] = useState<Record<string, string>>({});
  const [recipeName, setRecipeName] = useState("");
  const [remySpeech, setRemySpeech] = useState<string>("");
  const [stepCompleted, setStepCompleted] = useState(false);
  const [stepCheckData, setStepCheckData] = useState<StepCheckData | null>(null);
  const [apiError, setApiError] = useState<string | null>(null);
  const [cameraActive, setCameraActive] = useState(false);
  const [showCompletionOverlay, setShowCompletionOverlay] = useState(false);
  const [detectedAllergens, setDetectedAllergens] = useState<string[]>([]);
  const [selectedAllergens, setSelectedAllergens] = useState<string[]>([]);

  const eventSourceRef = useRef<EventSource | null>(null);
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const handleNextRef = useRef<() => Promise<void>>(async () => { });
  const currentStepLabelRef = useRef<string>("");
  const audioRef = useRef<HTMLAudioElement | null>(null);
  // True while Remy is reading a step aloud — suppresses overlapping speech events
  const stepSpeakingRef = useRef<boolean>(false);

  // Cleanup SSE and audio on unmount
  useEffect(() => {
    return () => {
      eventSourceRef.current?.close();
      if (audioRef.current) {
        audioRef.current.pause();
        audioRef.current = null;
      }
    };
  }, []);

  // Keep handleNextRef pointing at the latest handleNext closure
  useEffect(() => {
    handleNextRef.current = handleNext;
  });

  // Keep current step label ref in sync so the SSE handler can filter stale results
  useEffect(() => {
    currentStepLabelRef.current = steps[currentStep] ?? "";
  }, [steps, currentStep]);

  // Auto-advance when the AI confirms the step is complete
  useEffect(() => {
    if (!stepCompleted) return;
    setShowCompletionOverlay(true);
    const timer = setTimeout(() => {
      setShowCompletionOverlay(false);
      handleNextRef.current();
    }, 1500);
    return () => clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [stepCompleted]);

  // ── TTS playback — stop-and-replace on new speech ──────────────

  async function speak(text: string, isStepAnnouncement = false) {
    // Stop whatever is currently playing immediately
    if (audioRef.current) {
      audioRef.current.pause();
      audioRef.current.src = "";
      audioRef.current = null;
    }

    if (isStepAnnouncement) stepSpeakingRef.current = true;

    try {
      const res = await fetch(`${BACKEND_URL}/tts`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text, voice: "fable" }),
      });
      if (!res.ok) {
        if (isStepAnnouncement) stepSpeakingRef.current = false;
        return;
      }

      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const audio = new Audio(url);
      audioRef.current = audio;
      const cleanup = () => {
        URL.revokeObjectURL(url);
        stepSpeakingRef.current = false;
      };
      audio.onended = cleanup;
      audio.onerror = cleanup;
      audio.play().catch(cleanup);
    } catch {
      // TTS failure is non-fatal — text is still displayed
      stepSpeakingRef.current = false;
    }
  }

  // ── SSE connection ─────────────────────────────────────────────

  function connectSSE() {
    eventSourceRef.current?.close();
    const es = new EventSource(`${BACKEND_URL}/stream`);

    es.onmessage = (event) => {
      try {
        const msg = JSON.parse(event.data);

        if (msg.type === "step_check") {
          // Ignore stale results — require step label to match current step.
          // If msg.step is null/undefined (queued before set-step was called), discard it.
          if (!msg.step || msg.step !== currentStepLabelRef.current) return;

          // Backend strips markdown fences before sending, but handle
          // string fallback here too in case GPT slips through anyway.
          // eslint-disable-next-line @typescript-eslint/no-explicit-any
          let data: any = msg.data;
          if (typeof data === "string") {
            try {
              const stripped = data.replace(/^```(?:json)?\s*/i, "").replace(/\s*```$/, "").trim();
              data = JSON.parse(stripped);
            } catch { data = null; }
          }
          if (data && typeof data === "object") {
            setStepCheckData(data as StepCheckData);
            if (data.completed === true) setStepCompleted(true);
          }
        } else if (msg.type === "speech") {
          const text = (msg.data as string).trim();
          // Ignore JSON responses — these are step-check bleed from false VAD triggers
          if (text.startsWith("{") || text.startsWith("```") || text.startsWith("[")) return;
          // Extra guard: try parsing as JSON — if it has step-check keys, skip it
          try {
            const parsed = JSON.parse(text);
            if (parsed && typeof parsed === "object" && ("completed" in parsed || "state" in parsed || "action" in parsed)) return;
          } catch { /* not JSON — good, it's real speech */ }
          setRemySpeech(text);
          // Don't interrupt Remy reading the step aloud
          if (!stepSpeakingRef.current) speak(text);
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

  async function loadStepDetails(step: string): Promise<string | null> {
    try {
      const res = await fetch(`${BACKEND_URL}/step/details?step=${encodeURIComponent(step)}`);
      const data = await res.json();
      if (data.details) {
        setStepDetails(prev => ({ ...prev, [step]: data.details }));
        return data.details as string;
      }
    } catch {
      // optional — fine to fail silently
    }
    return null;
  }

  // ── Announce a step — reads title + detail aloud together ──────

  async function announceStep(step: string) {
    const detail = await loadStepDetails(step);
    const text = detail ? `${step}. ${detail}` : step;
    speak(text, true);
  }

  async function loadStepCaution(step: string) {
    try {
      const res = await fetch(`${BACKEND_URL}/step/safety?step=${encodeURIComponent(step)}`);
      const data = await res.json();
      if (data.caution) {
        toast(data.caution, {
          description: data.tip ? `Tip: ${data.tip}` : undefined,
          duration: 8000,
          icon: "‼️",
          style: { background: "#f0ede9", color: "#5a5a4a", border: "1px solid #e0dbd4" },
        });
      }
    } catch {
      // optional — fine to fail silently
    }
  }

  async function loadStepImage(step: string, recipe?: string) {
    if (stepImages[step]) return; // already loaded
    try {
      let url = `${BACKEND_URL}/step/image?step=${encodeURIComponent(step)}`;
      if (recipe) url += `&recipe=${encodeURIComponent(recipe)}`;
      const res = await fetch(url);
      const data = await res.json();
      if (data.image_url) {
        setStepImages(prev => ({ ...prev, [step]: data.image_url }));
      }
    } catch {
      // optional — fine to fail silently
    }
  }

  // ── Navigation helpers ─────────────────────────────────────────

  function crossFadeTo(nextPhase: "prompt" | "loading" | "allergens" | "coaching") {
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

  // ── Start cooking — camera + SSE + coaching screen ──────────────

  async function startCooking(stepsToUse: string[]) {
    // 1. Start camera + AI pipeline
    await fetch(`${BACKEND_URL}/camera/start`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ recipe: recipeName, steps: stepsToUse }),
    });

    // 2. Set first step
    await fetch(`${BACKEND_URL}/recipe/set-step`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ step: stepsToUse[0] }),
    });

    // 3. Open SSE stream
    connectSSE();

    setCurrentStep(0);
    setDisplayStep(0);
    setStepCompleted(false);
    setStepCheckData(null);
    setRemySpeech("");
    setCameraActive(true);
    crossFadeTo("coaching");

    // 4. Load first step details + image in background
    loadStepDetails(stepsToUse[0]);
    loadStepCaution(stepsToUse[0]);
    loadStepImage(stepsToUse[0], recipeName);
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
      setRecipeName(food);

      // 1. Generate steps + scan allergens in parallel
      const [genRes, allergenRes] = await Promise.all([
        fetch(`${BACKEND_URL}/recipe/generate`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ food }),
        }),
        fetch(`${BACKEND_URL}/recipe/allergens`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ food }),
        }),
      ]);

      if (!genRes.ok) throw new Error(`Recipe generation failed (${genRes.status})`);
      const genData = await genRes.json();
      const newSteps: string[] = genData.steps;
      setSteps(newSteps);
      clearInterval(interval);

      // 2. If allergens found, pause and ask user before starting camera
      const allergenData = allergenRes.ok ? await allergenRes.json() : { allergens: null };
      if (allergenData.allergens && allergenData.allergens.length > 0) {
        setDetectedAllergens(allergenData.allergens);
        setSelectedAllergens([]);
        crossFadeTo("allergens");
        return;
      }

      // 3. No allergens — go straight to cooking
      await startCooking(newSteps);
      // 4. Load first step details + image in background, then read aloud
      announceStep(newSteps[0]);
      loadStepImage(newSteps[0], food);

    } catch (err) {
      clearInterval(interval);
      const msg = err instanceof Error ? err.message : "Something went wrong";
      setApiError(`${msg} — is the backend running on port 8000?`);
      crossFadeTo("prompt");
    }
  }

  // ── Allergen continue ──────────────────────────────────────────

  async function handleAllergenContinue() {
    let stepsToUse = steps;

    if (selectedAllergens.length > 0) {
      crossFadeTo("loading");
      setLoadingMsg("Swapping ingredients…");
      try {
        const food = inputMode === "describe" ? prompt.trim() : recipeUrl.trim();
        const res = await fetch(`${BACKEND_URL}/recipe/generate-safe`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ food, avoid: selectedAllergens }),
        });
        if (res.ok) {
          const data = await res.json();
          stepsToUse = data.steps;
          setSteps(stepsToUse);
        }
      } catch {
        // Fall back to original steps if substitution fails
      }
    }

    await startCooking(stepsToUse);
  }

  // ── End recipe early and return to home ───────────────────────

  async function handleEndRecipe() {
    eventSourceRef.current?.close();
    if (audioRef.current) { audioRef.current.pause(); audioRef.current = null; }
    setCameraActive(false);
    setShowCompletionOverlay(false);
    try { await fetch(`${BACKEND_URL}/camera/stop`, { method: "POST" }); } catch { }
    setPrompt(""); setRecipeUrl(""); setUrlParsed(false);
    setCurrentStep(0); setDisplayStep(0); setDone(false);
    setSteps([]); setStepDetails({}); setStepImages({}); setRecipeName(""); setRemySpeech("");
    setStepCompleted(false); setStepCheckData(null);
    setDetectedAllergens([]); setSelectedAllergens([]);
    crossFadeTo("prompt");
  }

  // ── Advance step ───────────────────────────────────────────────

  async function handleNext() {
    if (animating) return;
    setShowCompletionOverlay(false);
    const nextIdx = currentStep + 1;

    if (nextIdx >= steps.length) {
      eventSourceRef.current?.close();
      setCameraActive(false);
      try { await fetch(`${BACKEND_URL}/camera/stop`, { method: "POST" }); } catch { }
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
    } catch { }

    setCurrentStep(nextIdx);
    setTimeout(() => {
      setDisplayStep(nextIdx);
      setAnimating(false);
      announceStep(steps[nextIdx]);
      loadStepCaution(steps[nextIdx]);
      loadStepImage(steps[nextIdx], recipeName);
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

        <div className="flex-1 flex flex-col items-center justify-center gap-7 px-12 mb-20">

          {/* Heading */}
          <div className="w-full max-w-lg flex flex-col items-center gap-2 text-center">
            <h1 className="text-2xl font-semibold" style={{ color: "#3a3a2a" }}>What are we cooking?</h1>
          </div>

          {/* Error banner */}
          {apiError && (
            <div className="w-full max-w-lg rounded-xl px-3 py-2.5 text-sm flex items-center gap-2" style={{ background: "#f0ede9", color: "#5a5a4a", border: "1px solid #e0dbd4" }}>
              <span className="shrink-0">‼️</span>
              <span className="truncate">{apiError}</span>
            </div>
          )}

          {/* Mode toggle */}
          <div className="w-full max-w-lg flex rounded-2xl p-1 gap-1" style={{ background: "#e8e0d8" }}>
            {(["describe", "url"] as const).map((mode) => (
              <button
                key={mode}
                onClick={() => switchMode(mode)}
                className="flex-1 rounded-xl py-2 text-sm font-semibold transition-all duration-200 ease-out"
                style={{
                  background: inputMode === mode ? "#fff" : "transparent",
                  color: inputMode === mode ? "#3a3a2a" : "#3a3a2a",
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
                className="w-full text-base rounded-2xl px-4 py-3 resize-none outline-none leading-relaxed h-36"
                style={{ background: "#fff", color: "#3a3a2a", border: "1px solid #fff", caretColor: "#D4A017" }}
                placeholder="e.g. Spaghetti carbonara, chocolate chip cookies, chicken stir fry…"
                value={prompt}
                onChange={(e) => setPrompt(e.target.value)}
                onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); handleStart(); } }}
              />
            ) : (
              <div className="flex flex-col gap-3">
                <div
                  className="flex items-center gap-3 rounded-2xl px-4 py-3"
                  style={{ background: "#fff", border: `1px solid ${urlParsed ? "#2C5F2E" : "#fff"}` }}
                >
                  <svg className="w-7 h-7 shrink-0 pb-1" fill="none" viewBox="0 0 30 30" stroke="#97BC62" strokeWidth={1.5}>
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
            className="w-full max-w-lg rounded-2xl py-3 text-base font-semibold transition-all duration-200 ease-out disabled:opacity-30 disabled:cursor-not-allowed hover:brightness-105 hover:scale-[1.01] active:scale-[0.98]"
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

  // ── ALLERGEN SCREEN ────────────────────────────────────────────

  if (phase === "allergens") {
    return (
      <div className="relative flex h-screen w-screen overflow-hidden" style={{ background: "#FFF8F0" }}>
        <div className="flex-1 flex flex-col items-center justify-center gap-6 px-12 overflow-y-auto py-10">

          {/* Brand */}
          <div className="w-full max-w-lg flex flex-col items-center gap-2 text-center">
            <h1 className="text-4xl font-semibold" style={{ color: "#3a3a2a" }}>Are you allergic to...</h1>
          </div>

          {/* Allergen toggle cards */}
          <div className="w-full max-w-lg grid grid-cols-2 gap-3 mt-4">
            {detectedAllergens.map(allergen => {
              const checked = selectedAllergens.includes(allergen);
              return (
                <Card
                  key={allergen}
                  onClick={() => setSelectedAllergens(prev =>
                    checked ? prev.filter(a => a !== allergen) : [...prev, allergen]
                  )}
                  className={cn(
                    "cursor-pointer transition-all hover:brightness-95 active:scale-[0.98] py-0 shadow-none",
                    checked ? "border-[#2C5F2E] bg-[#2C5F2E]/[0.06]" : "border-[#e8e0d8]"
                  )}
                >
                  <CardContent className="flex items-center gap-3 px-4 py-3">
                    <span className="text-xl">{allergenEmoji(allergen)}</span>
                    <span className="text-sm font-medium capitalize flex-1" style={{ color: "#3a3a2a" }}>{allergen}</span>
                    {checked && (
                      <svg className="w-4 h-4 shrink-0" fill="none" viewBox="0 0 24 24" stroke="#2C5F2E" strokeWidth={2.5}>
                        <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
                      </svg>
                    )}
                  </CardContent>
                </Card>
              );
            })}
          </div>

          {/* Selected badges summary */}
          {selectedAllergens.length > 0 && (
            <div className="w-full max-w-lg flex flex-wrap gap-2">
              {selectedAllergens.map(a => (
                <Badge key={a} variant="outline" className="capitalize rounded-full px-3 py-1 text-xs font-medium"
                  style={{ borderColor: "#2C5F2E50", color: "#2C5F2E", background: "#2C5F2E10" }}>
                  {allergenEmoji(a)} {a}
                </Badge>
              ))}
            </div>
          )}

          {/* CTA buttons */}
          <div className="w-full max-w-lg flex flex-col gap-3 mt-4">
            {selectedAllergens.length > 0 && (
              <button
                onClick={handleAllergenContinue}
                className="w-full rounded-2xl h-12 text-base font-semibold transition-all duration-200 ease-out hover:brightness-105 hover:scale-[1.01] active:scale-[0.98]"
                style={{ background: "#D4A017", color: "#fff" }}
              >
                Adapt recipe &amp; Continue →
              </button>
            )}
            <button
              onClick={handleAllergenContinue}
              className="w-full rounded-2xl h-12 text-base font-semibold transition-all duration-200 ease-out hover:brightness-105 hover:scale-[1.01] active:scale-[0.98]"
              style={
                selectedAllergens.length > 0
                  ? { background: "#D4A01715", color: "#D4A017", border: "1.5px solid #D4A01750" }
                  : { background: "#D4A017", color: "#fff", border: "none" }
              }
            >
              {selectedAllergens.length > 0 ? "No thanks \u2014 Let\u2019s Cook!" : "No changes \u2014 Let\u2019s Cook! \u2192"}
            </button>
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
        <div className="flex-1 flex flex-col items-center justify-center gap-6 px-12">
          <div style={{ animation: "popIn 0.6s cubic-bezier(.34,1.56,.64,1) forwards" }} className="text-7xl">🍽️</div>
          <h2 className="text-4xl font-bold text-center" style={{ color: "#2C5F2E" }}>Bon appétit!</h2>
          <p className="text-lg text-center max-w-md" style={{ color: "#5a5a4a" }}>You nailed it. Remy is proud of you.</p>
          <button
            onClick={() => {
              eventSourceRef.current?.close();
              setPrompt(""); setRecipeUrl(""); setUrlParsed(false);
              setCurrentStep(0); setDisplayStep(0); setDone(false);
              setSteps([]); setStepDetails({}); setStepImages({}); setRecipeName(""); setRemySpeech("");
              setStepCompleted(false); setStepCheckData(null);
              setDetectedAllergens([]); setSelectedAllergens([]);
              setCameraActive(false);
              crossFadeTo("prompt");
            }}
            className="mt-4 rounded-2xl px-8 py-3 text-sm font-semibold transition-all duration-200 ease-out hover:brightness-105 hover:scale-[1.01] active:scale-[0.98]"
            style={{ background: "#D4A017", color: "#fff" }}
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
  const currentStepImage = stepImages[currentStepLabel];

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
        @keyframes checkPop {
          0%   { opacity: 0; transform: scale(0.4); }
          65%  { transform: scale(1.12); }
          100% { opacity: 1; transform: scale(1); }
        }
        @keyframes overlayFadeIn {
          from { opacity: 0; }
          to   { opacity: 1; }
        }
        .check-pop { animation: checkPop 0.5s cubic-bezier(.34,1.56,.64,1) forwards; }
        .overlay-fade { animation: overlayFadeIn 0.25s ease forwards; }
        @keyframes aiPulse {
          0%, 100% { opacity: 1; }
          50%       { opacity: 0.4; }
        }
        .ai-dot { animation: aiPulse 1.4s ease-in-out infinite; }
      `}</style>

      {/* Step completion overlay */}
      {showCompletionOverlay && (
        <div
          className="overlay-fade fixed inset-0 z-50 flex flex-col items-center justify-center gap-6"
          style={{ background: "#2C5F2Edc", backdropFilter: "blur(6px)" }}
        >
          <div className="check-pop flex flex-col items-center gap-5">
            {/* Circle + checkmark */}
            <div
              className="w-36 h-36 rounded-full flex items-center justify-center"
              style={{ background: "#ffffff22", border: "3px solid #ffffffaa", boxShadow: "0 0 60px #ffffff33" }}
            >
              <svg className="w-20 h-20" fill="none" viewBox="0 0 24 24" stroke="#fff" strokeWidth={2.5}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
              </svg>
            </div>
            <p className="text-4xl font-bold tracking-tight " style={{ color: "#fff" }}>Step Complete!</p>
            <p className="text-base font-medium opacity-70 " style={{ color: "#fff" }}>Moving to next step…</p>
          </div>
        </div>
      )}

      <div className="relative flex h-screen w-screen overflow-hidden" style={{ background: "#FFF8F0" }}>
        <CameraPip position="right-center" connected={cameraActive} />

        {/* End recipe button */}
        <button
          onClick={handleEndRecipe}
          className="absolute top-5 right-5 z-20 flex items-center gap-1.5 rounded-xl px-3 py-1.5 text-xs font-semibold transition-all duration-200 ease-out hover:brightness-90 hover:scale-[1.02] active:scale-95"
          style={{ background: "#e8e0d8", color: "#7a6a5a" }}
        >
          ✕ End Recipe
        </button>

        <div className="flex-1 flex flex-col">

          {/* Header */}
          <div className="pt-7 pb-0 flex flex-col items-center gap-2">
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

              {/* Step label + status badge + up next */}
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
              </div>

              {/* Step title */}
              <h2 className="text-5xl font-bold leading-tight" style={{ color: "#3a3a2a" }}>
                {currentStepLabel}
              </h2>

              {/* Step how-to detail (loaded from /step/details) */}
              {currentStepDetail ? (
                <p className="text-xl leading-relaxed" style={{ color: "#5a5a4a" }}>
                  {currentStepDetail}
                </p>
              ) : (
                <div className="flex flex-col gap-2 mt-1">
                  <Skeleton className="h-5 w-full rounded-lg" style={{ background: "#d5cdc4" }} />
                  <Skeleton className="h-5 w-3/4 rounded-lg" style={{ background: "#d5cdc4" }} />
                </div>
              )}

              {/* Live analysis + Goal image side by side */}
              <div className="flex gap-3 mt-2" style={{ height: "240px" }}>
                {/* Live AI vision analysis card — left */}
                <div className="min-w-0" style={{ width: "240px", flexShrink: 0 }}>
                  {stepCheckData ? (
                    <div
                      className="rounded-xl p-3 flex flex-col gap-2 h-full overflow-hidden"
                      style={{
                        background: stepCompleted ? "#2C5F2E12" : "#fff",
                        border: `1.5px solid ${stepCompleted ? "#2C5F2E50" : "#e8e0d8"}`,
                        boxShadow: "0 2px 12px #0000000a",
                        transition: "border-color 0.4s ease, background 0.4s ease",
                      }}
                    >
                      {/* Card header */}
                      <div className="flex items-center gap-1.5 bg-neutral-50">
                        <span className="ai-dot w-1.5 h-1.5 rounded-full shrink-0" style={{ background: stepCompleted ? "#97BC62" : "#97BC62" }} />
                        <span className="text-[10px] font-semibold uppercase tracking-widest" style={{ color: stepCompleted ? "#97BC62" : "#97BC62" }}>
                          {stepCompleted ? "Confirmed ✓" : "Live Analysis"}
                        </span>
                      </div>

                      {/* Action description */}
                      {stepCheckData.action?.explanation && (
                        <p className="text-xs leading-relaxed" style={{ color: "#5a5a4a" }}>
                          {stepCheckData.action.explanation}
                        </p>
                      )}

                      {/* Subtle hint */}
                      {stepCheckData.hint && (
                        <p className="text-[9px] italic mt-auto" style={{ color: "#b0a898" }}>
                          {stepCheckData.hint}
                        </p>
                      )}
                    </div>
                  ) : (
                    <div className="rounded-xl p-3 flex flex-col gap-3 h-full" style={{ border: "1.5px solid #e8e0d8" }}>
                      <Skeleton className="h-3 w-24 rounded" style={{ background: "#d5cdc4" }} />
                      <Skeleton className="h-3 w-full rounded" style={{ background: "#d5cdc4" }} />
                      <Skeleton className="h-3 w-4/5 rounded" style={{ background: "#d5cdc4" }} />
                      <Skeleton className="h-3 w-3/5 rounded" style={{ background: "#d5cdc4" }} />
                    </div>
                  )}
                </div>

                {/* Goal image — right */}
                <div className="min-w-0" style={{ width: "240px", flexShrink: 0 }}>
                  {currentStepImage ? (
                    // eslint-disable-next-line @next/next/no-img-element
                    <img
                      src={currentStepImage}
                      alt={`What "${currentStepLabel}" should look like`}
                      className="w-full h-full object-cover rounded-xl"
                    />
                  ) : (
                    <Skeleton className="w-full h-full rounded-xl" style={{ background: "#d5cdc4" }} />
                  )}
                </div>
              </div>
            </div>

            {/* Remy says — speech responses */}
            <div className="mx-16 mb-6 rounded-2xl p-4 flex flex-col gap-1" style={{ background: "#97BC6218", border: "1px solid #97BC6240" }}>
              <div className="flex items-center gap-2">
                <span className="text-xs font-semibold uppercase tracking-widest" style={{ color: "#97BC62" }}>Remy says...</span>
                <div className="pb-1">
                  <Waveform />
                </div>
              </div>
              <p className="text-sm leading-relaxed" style={{ color: "#3a3a2a" }}>
                {remySpeech || "Ask me anything about this step!"}
              </p>
            </div>

          </div>

          {/* CTA button */}
          <div className="px-16 pb-8">
            <button
              onClick={handleNext}
              disabled={animating}
              className="w-full rounded-2xl py-4 text-lg font-semibold transition-all duration-200 ease-out hover:brightness-105 hover:scale-[1.01] active:scale-[0.98] disabled:opacity-50"
              style={{
                background: "#D4A017",
                color: "#fff",
              }}
            >
              {currentStep < steps.length - 1
                ? stepCompleted ? "✓  Step Done — Next →" : "Next Step →"
                : stepCompleted ? "✓  Finish!" : "Finish ✓"}
            </button>
          </div>

        </div>
      </div>
    </>
  );
}

// ---------------------------------------------------------------------------
// Allergen emoji helper
// ---------------------------------------------------------------------------

function allergenEmoji(name: string): string {
  const n = name.toLowerCase();
  if (n.includes("peanut")) return "🥜";
  if (n.includes("tree nut") || n.includes("walnut") || n.includes("almond") || n.includes("cashew") || n.includes("pecan") || n.includes("pistachio") || n.includes("hazelnut")) return "🌰";
  if (n.includes("cheese")) return "🧀";
  if (n.includes("butter") && !n.includes("peanut")) return "🧈";
  if (n.includes("dairy") || n.includes("milk") || n.includes("cream")) return "🥛";
  if (n.includes("egg")) return "🥚";
  if (n.includes("gluten") || n.includes("wheat") || n.includes("flour") || n.includes("bread")) return "🌾";
  if (n.includes("soy")) return "🫘";
  if (n.includes("shrimp") || n.includes("prawn") || n.includes("shellfish")) return "🦐";
  if (n.includes("crab")) return "🦀";
  if (n.includes("lobster")) return "🦞";
  if (n.includes("oyster") || n.includes("mussel") || n.includes("clam") || n.includes("scallop")) return "🦪";
  if (n.includes("fish") || n.includes("salmon") || n.includes("tuna") || n.includes("cod")) return "🐟";
  if (n.includes("sesame")) return "🌱";
  if (n.includes("kiwi")) return "🥝";
  if (n.includes("strawberry")) return "🍓";
  if (n.includes("avocado")) return "🥑";
  if (n.includes("mango")) return "🥭";
  if (n.includes("mustard")) return "🌿";
  if (n.includes("celery")) return "🥬";
  if (n.includes("cinnamon") || n.includes("spice")) return "🫙";
  return "⚠️";
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

function CameraPip({ position, connected = false }: { position?: "top-left" | "right-center"; connected?: boolean }) {
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
