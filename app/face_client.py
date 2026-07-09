import base64
import requests
from flask import current_app


def _get_api_url():
    from .api_config import get_api_config
    return get_api_config('HF_FACE_API_URL', '').rstrip('/')


def _encode_image(path: str) -> str:
    with open(path, 'rb') as f:
        return base64.b64encode(f.read()).decode('utf-8')


def detect_faces(image_path: str) -> dict:
    api_url = _get_api_url()
    if not api_url:
        raise RuntimeError("HF_FACE_API_URL not configured")
    b64 = _encode_image(image_path)
    resp = requests.post(f"{api_url}/api/detect", json={'image': b64}, timeout=60)
    resp.raise_for_status()
    return resp.json()


def enroll_student(image_paths: list[str], student_id: int) -> dict:
    api_url = _get_api_url()
    if not api_url:
        raise RuntimeError("HF_FACE_API_URL not configured")
    photos = [_encode_image(p) for p in image_paths]
    resp = requests.post(f"{api_url}/api/enroll", json={
        'photos': photos,
        'student_id': student_id,
    }, timeout=300)
    if not resp.ok:
        raise RuntimeError(f"Face API error ({resp.status_code}): {resp.text}")
    return resp.json()


def scan_faces(image_paths: list[str], student_embeddings: dict) -> dict:
    api_url = _get_api_url()
    if not api_url:
        raise RuntimeError("HF_FACE_API_URL not configured")
    photos = [_encode_image(p) for p in image_paths]
    resp = requests.post(f"{api_url}/api/scan", json={
        'photos': photos,
        'student_embeddings': student_embeddings,
    }, timeout=300)
    if not resp.ok:
        raise RuntimeError(f"Face API error ({resp.status_code}): {resp.text}")
    return resp.json()


def identify_face(image_path: str, student_embeddings: dict) -> dict:
    api_url = _get_api_url()
    if not api_url:
        raise RuntimeError("HF_FACE_API_URL not configured")
    photo = _encode_image(image_path)
    resp = requests.post(f"{api_url}/api/identify", json={
        'photo': photo,
        'student_embeddings': student_embeddings,
    }, timeout=15)
    if not resp.ok:
        raise RuntimeError(f"Face API error ({resp.status_code}): {resp.text}")
    return resp.json()


def check_api_health() -> bool:
    api_url = _get_api_url()
    if not api_url:
        return False
    try:
        resp = requests.get(f"{api_url}/health", timeout=5)
        return resp.ok
    except Exception:
        return False
