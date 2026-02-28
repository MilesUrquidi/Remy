import json
import requests
from bs4 import BeautifulSoup
from openai import OpenAI
from dotenv import load_dotenv
from chatgpt import _TASK_DECOMP_SYSTEM, _TASK_DECOMP_EXAMPLES

load_dotenv()
client = OpenAI()


def fetch_recipe(url: str) -> str:
    """Scrape visible text from a recipe URL."""
    response = requests.get(url, timeout=10, headers={"User-Agent": "Mozilla/5.0"})
    soup = BeautifulSoup(response.text, "html.parser")
    # Remove scripts, styles, and nav clutter
    for tag in soup(["script", "style", "nav", "footer", "header"]):
        tag.decompose()
    return soup.get_text(separator=" ", strip=True)


def steps_from_url(url: str) -> list[str]:
    """Fetch a recipe from a URL and return camera-verifiable steps."""
    print(f"Fetching recipe from: {url}\n")
    raw_text = fetch_recipe(url)

    # Ask GPT to validate the page is actually a food/drink recipe
    check = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": "You check if a webpage contains a food or drink recipe. Reply with only 'yes' or 'no'."},
            {"role": "user", "content": raw_text[:2000]}
        ],
        temperature=0,
    )
    if check.choices[0].message.content.strip().lower() != "yes":
        raise ValueError("That URL doesn't appear to contain a food or drink recipe. Please provide a valid recipe link.")

    messages = [{"role": "system", "content": _TASK_DECOMP_SYSTEM}]
    messages.extend(_TASK_DECOMP_EXAMPLES)
    messages.append({"role": "user", "content": f"Here is a recipe from the web. Break it into steps:\n\n{raw_text[:4000]}"})

    response = client.chat.completions.create(
        model="gpt-4o",
        messages=messages,
        temperature=0.3,
    )

    return json.loads(response.choices[0].message.content.strip())


if __name__ == "__main__":
    url = input("Paste a recipe URL: ")
    try:
        steps = steps_from_url(url)
        print("\nSteps:")
        for i, step in enumerate(steps, 1):
            print(f"  {i}. {step}")
        print(f"\nAs list: {steps}")
    except ValueError as e:
        print(f"\n❌ Error: {e}")
