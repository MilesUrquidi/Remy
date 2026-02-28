from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

client = OpenAI()

def ai_text_output(prompt):
    response = client.chat.completions.create(
        model="gpt-4.1-mini",
        messages=[
            {"role": "user", "content": prompt}
        ]
    )
    print(response.choices[0].message.content)

ai_text_output('hi, tell me a sentence about yourself')