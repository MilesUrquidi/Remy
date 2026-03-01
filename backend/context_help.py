import re
import html
import urllib.parse
import requests
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()
client = OpenAI()


# --- Image URL via direct Bing scrape ---

def _get_image_url(query: str) -> str | None:
    """Scrape Bing Image Search for the first result URL."""
    try:
        url = "https://www.bing.com/images/search?" + urllib.parse.urlencode({"q": query, "first": 1})
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        }
        resp = requests.get(url, headers=headers, timeout=8)
        resp.raise_for_status()

        # Bing HTML-encodes quotes as &quot; — decode first, then extract murl values
        decoded = html.unescape(resp.text)
        matches = re.findall(r'"murl"\s*:\s*"(https?://[^"]+)"', decoded)
        if matches:
            return matches[0]
    except Exception as e:
        print(f"[context_help] Bing image search failed: {e}")

    return None


# --- Step context ---

_DETAILS_SYSTEM = """You are a cooking assistant. Given a recipe step, describe ONLY the key action in one sentence.
Focus on the technique or motion — skip setup instructions and ingredient prep.

Examples:
Step: "Matcha and water are whisked until frothy"
→ Use a bamboo whisk (chasen) in a brisk zigzag motion until the mixture is smooth and frothy with a layer of bubbles on the surface.

Step: "Peanut butter is spread across one slice"
→ Use a butter knife to spread a generous, even layer of peanut butter across one slice of bread, reaching the edges.

Step: "Drink is stirred with a spoon"
→ Use a long spoon to stir from the bottom up a few times until the layers are evenly mixed."""


def get_step_details(step: str) -> dict:
    """
    Returns a brief one-sentence explanation of how to perform the step.

    Args:
        step: A single recipe step string.

    Returns:
        {"step": str, "details": str}
    """
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": _DETAILS_SYSTEM},
            {"role": "user", "content": f"Step: {step}"},
        ],
        temperature=0.3,
    )
    return {
        "step": step,
        "details": response.choices[0].message.content.strip(),
    }


def get_step_image(step: str, recipe: str | None = None) -> dict:
    """
    Returns an image URL showing what the completed state of the step looks like.

    Args:
        step: A single recipe step string.
        recipe: The recipe name for context (e.g. "matcha latte").

    Returns:
        {"step": str, "image_url": str | None}
    """
    # Ask GPT for a kitchen/food-specific search query for this step
    query_response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {
                "role": "system",
                "content": (
                    "Given a cooking recipe step, return ONLY the key subject (3-5 words max) that describes what the result looks like.\n"
                    "Strip away all fluff — just the core object or food state.\n"
                    "Think: what would you Google to find the simplest, most basic photo of this?\n\n"
                    "Example: Step: 'A mug is placed on the counter' → 'empty white mug'\n"
                    "Example: Step: 'A bowl is placed on a flat surface' → 'empty mixing bowl'\n"
                    "Example: Step: 'Matcha powder is sifted into a mug' → 'matcha powder in mug'\n"
                    "Example: Step: 'Butter is melted in a pan' → 'melted butter in pan'\n"
                    "Example: Step: 'Eggs and sugar are whisked together' → 'whisked eggs and sugar'\n"
                    "Example: Step: 'Dough is kneaded on a floured surface' → 'kneaded dough ball'\n"
                    "Return only the search subject, nothing else."
                ),
            },
            {"role": "user", "content": f"Step: {step}"},
        ],
        temperature=0.3,
    )
    query = query_response.choices[0].message.content.strip().strip('"\'')
    print(f"[context_help] Image query: {query}")

    # Search for the simplest, most basic photo
    image_url = _get_image_url(query + " simple white background")

    # Fallback: try without the background hint
    if not image_url:
        print(f"[context_help] No results, retrying without background hint")
        image_url = _get_image_url(query)

    # Last resort: search the raw step text
    if not image_url:
        short_step = " ".join(step.split()[:5])
        print(f"[context_help] Still no results, trying raw step: {short_step}")
        image_url = _get_image_url(short_step)

    return {
        "step": step,
        "image_url": image_url,
    }


if __name__ == "__main__":
    TEST_STEP = "Matcha powder is sifted into a mug"

    print(f"Testing step: '{TEST_STEP}'\n")

    print("--- get_step_details ---")
    print(get_step_details(TEST_STEP))

    print("\n--- get_step_image ---")
    print(get_step_image(TEST_STEP))
