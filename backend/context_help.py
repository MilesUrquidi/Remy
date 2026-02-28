import tempfile
from icrawler.builtin import BingImageCrawler
from icrawler import ImageDownloader
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()
client = OpenAI()


# --- Image URL capture (no download) ---

class _URLOnlyDownloader(ImageDownloader):
    """Hooks into icrawler to capture the first image URL without saving anything."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.captured_url = None

    def download(self, task, default_ext, timeout=None, max_retry=3, overwrite=False, **kwargs):
        if self.captured_url is None:
            self.captured_url = task.get("file_url")


def _get_image_url(query: str) -> str | None:
    with tempfile.TemporaryDirectory() as tmp:
        crawler = BingImageCrawler(
            downloader_cls=_URLOnlyDownloader,
            storage={"root_dir": tmp},
            downloader_threads=1,
        )
        crawler.crawl(keyword=query, max_num=1)
        return crawler.downloader.captured_url


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


def get_step_image(step: str) -> dict:
    """
    Returns an image URL showing what the completed state of the step looks like.

    Args:
        step: A single recipe step string.

    Returns:
        {"step": str, "image_url": str | None}
    """
    # Ask GPT for a precise search query describing the completed state
    query_response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {
                "role": "system",
                "content": (
                    "Given a recipe step, return a short image search query (5 words max) "
                    "that finds a photo of what the result looks like after the step is complete. "
                    "Return only the search query, nothing else."
                ),
            },
            {"role": "user", "content": f"Step: {step}"},
        ],
        temperature=0.3,
    )
    query = query_response.choices[0].message.content.strip()
    image_url = _get_image_url(query)

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
