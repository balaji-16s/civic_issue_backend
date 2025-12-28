import google.generativeai as genai
import os
import re

genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))
model = genai.GenerativeModel("models/gemini-2.5-flash")

def analyze_issue(description: str):

    prompt = f"""
    You are an AI civic issue triage assistant.

    Analyze this issue: "{description}"

    Respond ONLY in JSON format with fields:
    {{
      "category": "...",
      "severity": "...",
      "department": "...",
      "actions": ["...", "...", "..."]
    }}

    Severity must be one of:
    Low, Medium, High, Critical
    """

    response = model.generate_content(prompt)

    text = response.text.strip()

    # Extract JSON from response safely
    json_match = re.search(r"\{.*\}", text, re.DOTALL)

    if not json_match:
        return {"error": "Invalid AI response format"}

    import json
    return json.loads(json_match.group())
