import os
import json
import traceback
from flask import current_app


def extract_marks_from_image(image_path):
    """Use Google Gemini Vision to extract student marks from a marksheet image."""
    from .api_config import get_api_config
    api_key = get_api_config('GOOGLE_AI_KEY')
    if not api_key:
        print("[MARKS OCR] No API key configured.")
        return None

    try:
        from google import genai

        with open(image_path, 'rb') as f:
            image_bytes = f.read()

        client = genai.Client(api_key=api_key)

        prompt = """You are analyzing a marksheet or grade sheet image. Extract all student entries.

For each student, return a JSON object with these exact keys:
- roll_number (string) — the student's roll number or ID
- name (string) — the student's full name
- marks_obtained (number) — the marks the student scored
- total_marks (number) — the maximum possible marks
- percentage (number or null) — the percentage if visible, otherwise null

Return ONLY a valid JSON array of these objects. No markdown, no explanation, no code fences.
Example format:
[{"roll_number": "IT001", "name": "John Doe", "marks_obtained": 85, "total_marks": 100, "percentage": 85.0}]"""

        response = client.models.generate_content(
            model='gemini-2.0-flash',
            contents=[prompt, genai.types.Part.from_bytes(data=image_bytes, mime_type='image/jpeg')],
        )

        text = response.text.strip()
        text = text.removeprefix('```json').removeprefix('```').removesuffix('```').strip()

        data = json.loads(text)
        if not isinstance(data, list):
            print(f"[MARKS OCR] Response is not a list: {type(data)}")
            return None

        print(f"[MARKS OCR] Extracted {len(data)} student entries")
        return data
    except Exception as e:
        print(f"[MARKS OCR] Error: {e}")
        traceback.print_exc()
        return None
