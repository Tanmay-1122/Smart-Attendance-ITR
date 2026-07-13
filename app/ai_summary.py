import os
import traceback
from flask import current_app


def summarize_homework(title, description, file_text=None):
    """Use Google Gemini to generate a student-friendly homework summary."""
    from .api_config import get_api_config
    api_key = get_api_config('GOOGLE_AI_KEY')
    if not api_key:
        print("[AI SUMMARY] No API key configured.")
        return None

    try:
        from google import genai
        client = genai.Client(api_key=api_key)

        content = f"Homework Title: {title}\n"
        if description:
            content += f"Description: {description}\n"
        if file_text:
            content += f"\nFile Content (first 3000 chars):\n{file_text[:3000]}\n"

        prompt = f"""You are a helpful study assistant. Summarize the following homework assignment for students.
Be concise, clear, and highlight key requirements.

{content}

Provide a clear summary in 3-5 sentences covering what the homework is about, key requirements, and any important notes."""

        response = client.models.generate_content(
            model='gemini-2.0-flash',
            contents=prompt,
        )
        return response.text.strip()
    except Exception as e:
        print(f"[AI SUMMARY] Error: {e}")
        traceback.print_exc()
        return None


def extract_text_from_file(file_path, file_name):
    """Extract text from common file types for summarization."""
    ext = file_name.rsplit('.', 1)[-1].lower() if '.' in file_name else ''

    if ext in {'txt', 'md'}:
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                return f.read()[:5000]
        except Exception:
            return None

    if ext == 'pdf':
        try:
            import subprocess
            result = subprocess.run(
                ['pdftotext', file_path, '-'],
                capture_output=True, text=True, timeout=10
            )
            return result.stdout[:5000] if result.returncode == 0 else None
        except Exception:
            return None

    return None
