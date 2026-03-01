"use client";

import { Skeleton } from "@/components/ui/skeleton";
import CameraPip from "./CameraPip";
import Waveform from "./Waveform";
import type { StepCheckData } from "./constants";

interface CoachingScreenProps {
  steps: string[];
  currentStep: number;
  displayStep: number;
  stepCompleted: boolean;
  animating: boolean;
  cameraActive: boolean;
  stepCheckData: StepCheckData | null;
  stepDetail: string | undefined;
  stepImage: string | undefined;
  remySpeech: string;
  showCompletionOverlay: boolean;
  onNext: () => void;
  onEndRecipe: () => void;
}

export default function CoachingScreen({
  steps, currentStep, displayStep, stepCompleted, animating, cameraActive,
  stepCheckData, stepDetail, stepImage, remySpeech,
  showCompletionOverlay, onNext, onEndRecipe,
}: CoachingScreenProps) {
  const currentStepLabel = steps[displayStep] ?? "";

  return (
    <>
      <style>{`
        @keyframes stepIn {
          from { opacity: 0; transform: translateX(50px); }
          to   { opacity: 1; transform: translateX(0); }
        }
        .step-in { animation: stepIn 0.35s ease forwards; }
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
            <div
              className="w-36 h-36 rounded-full flex items-center justify-center"
              style={{ background: "#ffffff22", border: "3px solid #ffffffaa", boxShadow: "0 0 60px #ffffff33" }}
            >
              <svg className="w-20 h-20" fill="none" viewBox="0 0 24 24" stroke="#fff" strokeWidth={2.5}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
              </svg>
            </div>
            <p className="text-4xl font-bold tracking-tight" style={{ color: "#fff" }}>Step Complete!</p>
            <p className="text-base font-medium opacity-70" style={{ color: "#fff" }}>Moving to next step</p>
          </div>
        </div>
      )}

      <div className="relative flex h-screen w-screen overflow-hidden" style={{ background: "#FFF8F0" }}>
        <CameraPip position="right-center" connected={cameraActive} />

        {/* End recipe button */}
        <button
          onClick={onEndRecipe}
          className="absolute top-5 right-5 z-20 flex items-center gap-1.5 rounded-xl px-3 py-1.5 text-xs font-semibold transition-all duration-200 ease-out hover:brightness-90 hover:scale-[1.02] active:scale-95"
          style={{ background: "#e8e0d8", color: "#7a6a5a" }}
        >
          {"\u2715"} End Recipe
        </button>

        <div className="flex-1 flex flex-col">

          {/* Header — step progress dots */}
          <div className="pt-7 pb-0 flex flex-col items-center gap-2">
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

              {/* Step label + status */}
              <div className="flex items-center gap-3 flex-wrap">
                <span className="text-xs uppercase tracking-widest font-semibold" style={{ color: "#97BC62" }}>
                  Step {displayStep + 1} of {steps.length}
                </span>
                {stepCompleted && (
                  <span
                    className="completed-badge text-xs font-semibold px-2.5 py-1 rounded-full flex items-center gap-1"
                    style={{ background: "#2C5F2E15", color: "#2C5F2E", border: "1.5px solid #2C5F2E50" }}
                  >
                    {"\u2713"} Step complete!
                  </span>
                )}
              </div>

              {/* Step title */}
              <h2 className="text-5xl font-bold leading-tight" style={{ color: "#3a3a2a" }}>
                {currentStepLabel}
              </h2>

              {/* Step how-to detail */}
              {stepDetail ? (
                <p className="text-xl leading-relaxed" style={{ color: "#5a5a4a" }}>
                  {stepDetail}
                </p>
              ) : (
                <div className="flex flex-col gap-2 mt-1">
                  <Skeleton className="h-5 w-full rounded-lg" style={{ background: "#d5cdc4" }} />
                  <Skeleton className="h-5 w-3/4 rounded-lg" style={{ background: "#d5cdc4" }} />
                </div>
              )}

              {/* Live analysis + Goal image */}
              <div className="flex gap-3 mt-2" style={{ height: "240px" }}>
                {/* Live AI vision analysis card */}
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
                      <div className="flex items-center gap-1.5 bg-neutral-50">
                        <span className="ai-dot w-1.5 h-1.5 rounded-full shrink-0" style={{ background: "#97BC62" }} />
                        <span className="text-[10px] font-semibold uppercase tracking-widest" style={{ color: "#97BC62" }}>
                          {stepCompleted ? "Confirmed \u2713" : "Live Analysis"}
                        </span>
                      </div>
                      {stepCheckData.action?.explanation && (
                        <p className="text-xs leading-relaxed" style={{ color: "#5a5a4a" }}>
                          {stepCheckData.action.explanation}
                        </p>
                      )}
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

                {/* Goal image */}
                <div className="min-w-0" style={{ width: "240px", flexShrink: 0 }}>
                  {stepImage ? (
                    // eslint-disable-next-line @next/next/no-img-element
                    <img
                      src={stepImage}
                      alt={`What "${currentStepLabel}" should look like`}
                      className="w-full h-full object-cover rounded-xl"
                    />
                  ) : (
                    <Skeleton className="w-full h-full rounded-xl" style={{ background: "#d5cdc4" }} />
                  )}
                </div>
              </div>
            </div>

            {/* Remy says */}
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
              onClick={onNext}
              disabled={animating}
              className="w-full rounded-2xl py-4 text-lg font-semibold transition-all duration-200 ease-out hover:brightness-105 hover:scale-[1.01] active:scale-[0.98] disabled:opacity-50"
              style={{ background: "#D4A017", color: "#fff" }}
            >
              {currentStep < steps.length - 1
                ? stepCompleted ? "\u2713  Step Done \u2014 Next \u2192" : "Next Step \u2192"
                : stepCompleted ? "\u2713  Finish!" : "Finish \u2713"}
            </button>
          </div>

        </div>
      </div>
    </>
  );
}
