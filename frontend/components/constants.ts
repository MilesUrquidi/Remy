// Palette
// #2C5F2E — deep forest green (primary)
// #97BC62 — fresh herb green (secondary)
// #FFF8F0 — warm white (background)
// #D4A017 — golden mustard (accent / CTA)

export const BACKEND_URL = "http://localhost:8000";

export type StepCheckData = {
  completed: boolean;
  state: { completed: boolean; explanation: string };
  action: { completed: boolean; explanation: string };
  hint?: string;
};

export type Phase = "prompt" | "loading" | "allergens" | "coaching";

export const LOADING_MESSAGES = [
  "Checking your pantry\u2026",
  "Sharpening the knives\u2026",
  "Preheating the oven\u2026",
  "Tasting the sauce\u2026",
  "Getting ready to cook\u2026",
  "Swapping ingredients\u2026",
];

export function isValidUrl(str: string) {
  try {
    const url = new URL(str);
    return url.protocol === "http:" || url.protocol === "https:";
  } catch {
    return false;
  }
}

export function allergenEmoji(name: string): string {
  const n = name.toLowerCase();
  if (n.includes("peanut")) return "\uD83E\uDD5C";
  if (n.includes("tree nut") || n.includes("walnut") || n.includes("almond") || n.includes("cashew") || n.includes("pecan") || n.includes("pistachio") || n.includes("hazelnut")) return "\uD83C\uDF30";
  if (n.includes("cheese")) return "\uD83E\uDDC0";
  if (n.includes("butter") && !n.includes("peanut")) return "\uD83E\uDDC8";
  if (n.includes("dairy") || n.includes("milk") || n.includes("cream")) return "\uD83E\uDD5B";
  if (n.includes("egg")) return "\uD83E\uDD5A";
  if (n.includes("gluten") || n.includes("wheat") || n.includes("flour") || n.includes("bread")) return "\uD83C\uDF3E";
  if (n.includes("soy")) return "\uD83E\uDED8";
  if (n.includes("shrimp") || n.includes("prawn") || n.includes("shellfish")) return "\uD83E\uDD90";
  if (n.includes("crab")) return "\uD83E\uDD80";
  if (n.includes("lobster")) return "\uD83E\uDD9E";
  if (n.includes("oyster") || n.includes("mussel") || n.includes("clam") || n.includes("scallop")) return "\uD83E\uDDAA";
  if (n.includes("fish") || n.includes("salmon") || n.includes("tuna") || n.includes("cod")) return "\uD83D\uDC1F";
  if (n.includes("sesame")) return "\uD83C\uDF31";
  if (n.includes("kiwi")) return "\uD83E\uDD5D";
  if (n.includes("strawberry")) return "\uD83C\uDF53";
  if (n.includes("avocado")) return "\uD83E\uDD51";
  if (n.includes("mango")) return "\uD83E\uDD6D";
  if (n.includes("mustard")) return "\uD83C\uDF3F";
  if (n.includes("celery")) return "\uD83E\uDD6C";
  if (n.includes("cinnamon") || n.includes("spice")) return "\uD83E\uDED9";
  return "\u26A0\uFE0F";
}
