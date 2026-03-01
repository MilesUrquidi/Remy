"use client";

import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import { allergenEmoji } from "./constants";

interface AllergenScreenProps {
  detectedAllergens: string[];
  selectedAllergens: string[];
  onToggleAllergen: (allergen: string) => void;
  onContinue: () => void;
}

export default function AllergenScreen({
  detectedAllergens, selectedAllergens, onToggleAllergen, onContinue,
}: AllergenScreenProps) {
  return (
    <div className="relative flex h-screen w-screen overflow-hidden" style={{ background: "#FFF8F0" }}>
      <div className="flex-1 flex flex-col items-center justify-center gap-6 px-12 overflow-y-auto py-10">

        {/* Heading */}
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
                onClick={() => onToggleAllergen(allergen)}
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
              onClick={onContinue}
              className="w-full rounded-2xl h-12 text-base font-semibold transition-all duration-200 ease-out hover:brightness-105 hover:scale-[1.01] active:scale-[0.98]"
              style={{ background: "#D4A017", color: "#fff" }}
            >
              Adapt recipe &amp; Continue {"\u2192"}
            </button>
          )}
          <button
            onClick={onContinue}
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
