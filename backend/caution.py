import json

from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()
client = OpenAI()


def get_safety_caution(step: str) -> dict | None:
    """
    Generate a safety caution and prevention tip for a recipe step if relevant.
    Returns {"caution": str, "tip": str}, or None if the step has no safety concerns.
    """
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {
                "role": "system",
                "content": (
                    "You are a kitchen safety expert. Given a recipe step, decide if it poses a physical risk. "
                    "If yes, reply with JSON: {\"caution\": \"<5 words max>\", \"tip\": \"<7 words max>\"}. "
                    "If no risk, reply with only: none"
                )
            },
            {"role": "user", "content": f"Recipe step: {step}"}
        ],
        temperature=0.3,
        response_format={"type": "text"},
    )

    result = response.choices[0].message.content.strip()
    if result.lower() == "none":
        return None

    try:
        cleaned = result.replace("```json", "").replace("```", "").strip()
        return json.loads(cleaned)
    except Exception:
        # Fallback: treat entire response as caution with no tip
        return {"caution": result, "tip": None}


if __name__ == "__main__":
    step = input("Enter a recipe step: ")
    data = get_safety_caution(step)
    print(f"[debug] raw result: {data}")
    if data:
        print(f"\n⚠️  {data['caution']}")
        if data.get("tip"):
            print(f"💡 {data['tip']}")
