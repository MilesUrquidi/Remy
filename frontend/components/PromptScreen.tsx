"use client";

interface PromptScreenProps {
  inputMode: "describe" | "url";
  prompt: string;
  recipeUrl: string;
  urlParsed: boolean;
  urlParsing: boolean;
  apiError: string | null;
  canStart: boolean;
  onSwitchMode: (mode: "describe" | "url") => void;
  onPromptChange: (value: string) => void;
  onUrlChange: (value: string) => void;
  onStart: () => void;
}

export default function PromptScreen({
  inputMode, prompt, recipeUrl, urlParsed, urlParsing, apiError,
  canStart, onSwitchMode, onPromptChange, onUrlChange, onStart,
}: PromptScreenProps) {
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
            <span className="shrink-0">{"\u203C\uFE0F"}</span>
            <span className="truncate">{apiError}</span>
          </div>
        )}

        {/* Mode toggle */}
        <div className="w-full max-w-lg flex rounded-2xl p-1 gap-1" style={{ background: "#e8e0d8" }}>
          {(["describe", "url"] as const).map((mode) => (
            <button
              key={mode}
              onClick={() => onSwitchMode(mode)}
              className="flex-1 rounded-xl py-2 text-sm font-semibold transition-all duration-200 ease-out"
              style={{
                background: inputMode === mode ? "#fff" : "transparent",
                color: "#3a3a2a",
                boxShadow: inputMode === mode ? "0 1px 4px #0001" : "none",
              }}
            >
              {mode === "describe" ? "\u270F\uFE0F  Describe a dish" : "\uD83D\uDD17  Paste a recipe URL"}
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
              placeholder="e.g. Spaghetti carbonara, chocolate chip cookies, chicken stir fry"
              value={prompt}
              onChange={(e) => onPromptChange(e.target.value)}
              onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); onStart(); } }}
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
                  placeholder="https://www.allrecipes.com/recipe/"
                  value={recipeUrl}
                  onChange={(e) => onUrlChange(e.target.value)}
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
                <p className="text-xs text-center" style={{ color: "#2C5F2E" }}>{"\u2713"} URL ready — click Let&apos;s Cook to start</p>
              ) : urlParsing ? (
                <p className="text-xs text-center" style={{ color: "#97BC62" }}>Reading recipe</p>
              ) : (
                <p className="text-xs text-center" style={{ color: "#b0a898" }}>
                  Works with AllRecipes, NYT Cooking, Serious Eats, Food Network & more
                </p>
              )}
            </div>
          )}
        </div>

        <button
          onClick={onStart}
          disabled={!canStart}
          className="w-full max-w-lg rounded-2xl py-3 text-base font-semibold transition-all duration-200 ease-out disabled:opacity-30 disabled:cursor-not-allowed hover:brightness-105 hover:scale-[1.01] active:scale-[0.98]"
          style={{ background: "#D4A017", color: "#fff" }}
        >
          Let&apos;s Cook {"\u2192"}
        </button>
      </div>
    </div>
  );
}
