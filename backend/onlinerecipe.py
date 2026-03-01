import json
import re

import requests
from bs4 import BeautifulSoup
from openai import OpenAI
from dotenv import load_dotenv
from chatgpt import _TASK_DECOMP_SYSTEM, _TASK_DECOMP_EXAMPLES

load_dotenv()
client = OpenAI()


# ---------------------------------------------------------------------------
# Few-shot examples specific to the URL / structured-recipe flow.
# These show GPT that when a recipe provides exact measurements, those
# amounts must be carried through into every camera-verifiable step.
# ---------------------------------------------------------------------------

_URL_RECIPE_EXAMPLES = [
    {
        "role": "user",
        "content": (
            "Here is a recipe. Break it into camera-verifiable steps:\n\n"
            "Recipe: Classic Pancakes\n\n"
            "Ingredients:\n"
            "- 1½ cups all-purpose flour\n"
            "- 3½ tsp baking powder\n"
            "- 1 tbsp white sugar\n"
            "- ¼ tsp salt\n"
            "- 1¼ cups milk\n"
            "- 1 egg\n"
            "- 3 tbsp melted butter\n\n"
            "Instructions:\n"
            "1. Mix flour, baking powder, sugar, and salt together in a large bowl.\n"
            "2. Whisk milk, egg, and melted butter in a separate bowl.\n"
            "3. Pour the wet ingredients into the dry bowl and stir until just combined.\n"
            "4. Heat a skillet over medium-high heat.\n"
            "5. Pour ¼ cup of batter onto the skillet for each pancake.\n"
            "6. Cook until bubbles form across the surface, then flip.\n"
            "7. Cook the second side until golden brown."
        ),
    },
    {
        "role": "assistant",
        "content": json.dumps([
            "A large bowl is placed on the counter",
            "1½ cups of flour is added to the bowl",
            "3½ tsp of baking powder is added to the bowl",
            "1 tbsp of sugar is added to the bowl",
            "¼ tsp of salt is added to the bowl",
            "Dry ingredients are mixed together in the bowl",
            "A separate bowl is placed on the counter",
            "1¼ cups of milk is poured into the second bowl",
            "1 egg is cracked into the second bowl",
            "3 tbsp of melted butter is added to the second bowl",
            "Wet ingredients are whisked together",
            "Wet mixture is poured into the dry bowl",
            "Batter is stirred until just combined",
            "A skillet is placed on the stovetop over medium-high heat",
            "¼ cup of batter is poured onto the heated skillet",
            "Bubbles are forming across the pancake surface",
            "Pancake is flipped and the second side is golden brown",
        ]),
    },
    {
        "role": "user",
        "content": (
            "Here is a recipe. Break it into camera-verifiable steps:\n\n"
            "Recipe: Chocolate Chip Cookies\n\n"
            "Ingredients:\n"
            "- 2¼ cups all-purpose flour\n"
            "- 1 tsp baking soda\n"
            "- 1 tsp salt\n"
            "- 1 cup (2 sticks) butter, softened\n"
            "- ¾ cup granulated sugar\n"
            "- ¾ cup packed brown sugar\n"
            "- 2 large eggs\n"
            "- 2 tsp vanilla extract\n"
            "- 2 cups chocolate chips\n\n"
            "Instructions:\n"
            "1. Preheat oven to 375°F.\n"
            "2. Mix flour, baking soda, and salt in a bowl.\n"
            "3. Beat butter, granulated sugar, and brown sugar in a large bowl until creamy.\n"
            "4. Add eggs and vanilla to the butter mixture and beat in.\n"
            "5. Gradually blend in the flour mixture.\n"
            "6. Stir in chocolate chips.\n"
            "7. Drop rounded tablespoons of dough onto ungreased baking sheets.\n"
            "8. Bake for 9–11 minutes until golden brown."
        ),
    },
    {
        "role": "assistant",
        "content": json.dumps([
            "Oven is set to 375°F",
            "A bowl is placed on the counter",
            "2¼ cups of flour is added to the bowl",
            "1 tsp of baking soda is added to the bowl",
            "1 tsp of salt is added to the bowl",
            "Dry ingredients are mixed together",
            "A large bowl is placed on the counter",
            "1 cup of softened butter is added to the large bowl",
            "¾ cup of granulated sugar is added to the large bowl",
            "¾ cup of brown sugar is added to the large bowl",
            "Butter and sugars are beaten until creamy",
            "2 eggs are cracked into the butter mixture",
            "2 tsp of vanilla extract is added to the butter mixture",
            "Eggs and vanilla are beaten into the mixture",
            "Flour mixture is gradually blended into the butter bowl",
            "2 cups of chocolate chips are stirred into the dough",
            "Rounded tablespoons of dough are placed on baking sheets",
            "Baking sheets are placed in the oven",
            "Cookies are golden brown and done baking",
        ]),
    },
]


# ---------------------------------------------------------------------------
# Structured recipe extraction
# ---------------------------------------------------------------------------

def fetch_recipe(url: str) -> str:
    """
    Fetch a recipe page and return its content as a clean text string.

    Strategy:
      1. JSON-LD  (schema.org/Recipe) — used by AllRecipes, Food Network,
                   NYT Cooking, Serious Eats, BBC Good Food, etc.
                   Gives exact ingredient measurements and clean instructions.
      2. HTML microdata  (itemtype=schema.org/Recipe)
      3. Fallback — strips scripts/nav/ads and returns raw page text,
                    capped at 4 000 chars so we stay within GPT context.
      4. If the page can't be fetched at all (e.g. 403), return the URL so
         GPT can still attempt generation from its training data.
    """
    html = _fetch_html(url)

    if html is None:
        # Site blocked us — let GPT try from training data
        print(f"[onlinerecipe] Could not fetch page, passing URL to GPT: {url}")
        return url

    soup = BeautifulSoup(html, "lxml")

    # Try structured data first
    data = _extract_jsonld(soup) or _extract_microdata(soup)
    if data:
        text = _format_structured(data)
        if text:
            return text

    # Fallback: remove noise and dump visible text
    for tag in soup(["script", "style", "nav", "footer", "header"]):
        tag.decompose()
    return soup.get_text(separator=" ", strip=True)[:4000]


def _fetch_html(url: str) -> str | None:
    """
    Fetch the raw HTML for a URL, mimicking a real Chrome browser as closely
    as possible to avoid bot-detection 403s on sites like AllRecipes.

    Uses a persistent Session (so cookies set on redirect are kept) and sends
    the full set of headers Chrome sends on a fresh top-level navigation.

    Returns None if the request fails for any reason.
    """
    session = requests.Session()
    headers = {
        # Core identity
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        # What Chrome sends on a fresh top-level navigation
        "Accept": (
            "text/html,application/xhtml+xml,application/xml;"
            "q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,"
            "application/signed-exchange;v=b3;q=0.7"
        ),
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
        "Upgrade-Insecure-Requests": "1",
        # Sec-Fetch-* headers — Chrome always sends these on navigation
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Sec-Fetch-User": "?1",
        # Client hints
        "Sec-Ch-Ua": '"Chromium";v="124", "Google Chrome";v="124", "Not-A.Brand";v="99"',
        "Sec-Ch-Ua-Mobile": "?0",
        "Sec-Ch-Ua-Platform": '"macOS"',
    }
    try:
        resp = session.get(url, headers=headers, timeout=12, allow_redirects=True)
        resp.raise_for_status()
        return resp.text
    except requests.exceptions.HTTPError as e:
        print(f"[onlinerecipe] HTTP {e.response.status_code} fetching {url}")
        return None
    except Exception as e:
        print(f"[onlinerecipe] fetch failed for {url}: {e}")
        return None


def _extract_jsonld(soup: BeautifulSoup) -> dict | None:
    """Find a schema.org/Recipe object inside any JSON-LD <script> tag."""
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string or "")
        except (json.JSONDecodeError, TypeError):
            continue

        # Could be a bare object, a list, or wrapped in @graph
        candidates: list = []
        if isinstance(data, list):
            candidates = data
        elif isinstance(data, dict):
            candidates = data.get("@graph", [data])

        for item in candidates:
            if not isinstance(item, dict):
                continue
            t = item.get("@type", "")
            types = t if isinstance(t, list) else [t]
            if "Recipe" in types:
                return item

    return None


def _extract_microdata(soup: BeautifulSoup) -> dict | None:
    """Extract recipe from HTML microdata (itemtype=schema.org/Recipe)."""
    recipe_el = soup.find(
        attrs={"itemtype": re.compile(r"schema\.org/Recipe", re.I)}
    )
    if not recipe_el:
        return None

    result: dict = {}

    name_el = recipe_el.find(attrs={"itemprop": "name"})
    if name_el:
        result["name"] = name_el.get_text(strip=True)

    ingredients = [
        el.get_text(strip=True)
        for el in recipe_el.find_all(attrs={"itemprop": "recipeIngredient"})
        if el.get_text(strip=True)
    ]
    if ingredients:
        result["recipeIngredient"] = ingredients

    instructions = [
        el.get_text(separator=" ", strip=True)
        for el in recipe_el.find_all(attrs={"itemprop": "recipeInstructions"})
        if el.get_text(separator=" ", strip=True)
    ]
    if instructions:
        result["recipeInstructions"] = instructions

    return result or None


def _format_structured(data: dict) -> str:
    """
    Turn a schema.org Recipe dict into plain text for GPT.
    Handles the varied shapes recipeInstructions can take:
      - plain string
      - list of strings
      - list of HowToStep   {"@type": "HowToStep", "text": "..."}
      - list of HowToSection {"@type": "HowToSection", "itemListElement": [...]}
    """
    lines: list[str] = []

    name = data.get("name", "")
    if name:
        lines.append(f"Recipe: {name}")

    ingredients = data.get("recipeIngredient", [])
    if ingredients:
        lines.append("\nIngredients:")
        for ing in ingredients:
            if isinstance(ing, str) and ing:
                lines.append(f"- {ing}")

    step_texts = _flatten_instructions(data.get("recipeInstructions", []))
    if step_texts:
        lines.append("\nInstructions:")
        for i, text in enumerate(step_texts, 1):
            lines.append(f"{i}. {text}")

    return "\n".join(lines)


def _flatten_instructions(instructions) -> list[str]:
    """Recursively flatten any instruction shape into a list of step strings."""
    if not instructions:
        return []
    if isinstance(instructions, str):
        return [s.strip() for s in instructions.splitlines() if s.strip()]

    steps: list[str] = []
    for item in instructions:
        if isinstance(item, str):
            if item.strip():
                steps.append(item.strip())
        elif isinstance(item, dict):
            if item.get("@type") == "HowToSection":
                steps.extend(_flatten_instructions(item.get("itemListElement", [])))
            else:
                text = (item.get("text") or item.get("name") or "").strip()
                if text:
                    steps.append(text)
    return steps


# ---------------------------------------------------------------------------
# GPT step generation from URL
# ---------------------------------------------------------------------------

def steps_from_url(url: str, avoid: list[str] | None = None) -> list[str]:
    """
    Fetch a recipe from a URL and return camera-verifiable steps.

    Args:
        url:   Direct link to a recipe page.
        avoid: Optional list of allergens to substitute (e.g. ["eggs", "dairy"]).

    Returns:
        List of step strings in order.
    """
    print(f"[onlinerecipe] Fetching: {url}")
    recipe_text = fetch_recipe(url)

    # Build the user message — include allergen note if needed
    user_content = f"Here is a recipe. Break it into camera-verifiable steps:\n\n{recipe_text}"
    if avoid:
        user_content += f"\n\nSubstitute these allergens with safe alternatives: {', '.join(avoid)}"

    messages = [{"role": "system", "content": _TASK_DECOMP_SYSTEM}]
    messages.extend(_TASK_DECOMP_EXAMPLES)
    messages.extend(_URL_RECIPE_EXAMPLES)
    messages.append({"role": "user", "content": user_content})

    response = client.chat.completions.create(
        model="gpt-4o",
        messages=messages,
        temperature=0.3,
    )

    return json.loads(response.choices[0].message.content.strip())


# ---------------------------------------------------------------------------
# CLI test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys
    test_url = (
        sys.argv[1]
        if len(sys.argv) > 1
        else "https://www.allrecipes.com/recipe/10813/best-chocolate-chip-cookies/"
    )
    try:
        steps = steps_from_url(test_url)
        print("\nSteps:")
        for i, step in enumerate(steps, 1):
            print(f"  {i}. {step}")
    except ValueError as e:
        print(f"\n❌ {e}")
