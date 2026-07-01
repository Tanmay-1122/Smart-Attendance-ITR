import os
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3'
os.environ['TF_ENABLE_ONEDNN_OPTS'] = '0'

import io
import gc
import base64
import json
import numpy as np
import cv2
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

app = FastAPI(title="SmartAttend Face API")

_arcface_loaded = False
_facenet_loaded = False


def _load_models():
    global _arcface_loaded, _facenet_loaded
    if _arcface_loaded:
        return
    from deepface import DeepFace
    DeepFace.build_model(model_name='ArcFace')
    _arcface_loaded = True
    DeepFace.build_model(model_name='Facenet512')
    _facenet_loaded = True


def _decode_image(b64: str) -> np.ndarray:
    if ',' in b64:
        b64 = b64.split(',', 1)[1]
    raw = base64.b64decode(b64)
    arr = np.frombuffer(raw, np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError("Failed to decode image")
    return img


def _preprocess(image: np.ndarray) -> np.ndarray:
    h, w = image.shape[:2]
    if w > 800:
        scale = 800 / w
        image = cv2.resize(image, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)

    lab = cv2.cvtColor(image, cv2.COLOR_BGR2LAB)
    l, a, b = cv2.split(lab)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    cl = clahe.apply(l)
    return cv2.cvtColor(cv2.merge((cl, a, b)), cv2.COLOR_LAB2BGR)


def _detect_faces(image: np.ndarray) -> list:
    from retinaface import RetinaFace
    image_rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
    detections = RetinaFace.detect_faces(image_rgb, threshold=0.9)

    if not detections or (isinstance(detections, dict) and not detections):
        return []

    if isinstance(detections, dict):
        detections = [detections[k] for k in detections if isinstance(detections[k], dict) and 'facial_area' in detections[k]]

    faces = []
    h, w = image.shape[:2]

    for det in detections:
        confidence = det.get('score', det.get('confidence', 0.0))
        if confidence < 0.90:
            continue

        fa = det.get('facial_area', None)
        if fa is None:
            continue

        x1, y1, x2, y2 = fa[0], fa[1], fa[2], fa[3]
        fw, fh = x2 - x1, y2 - y1
        if fw < 50 or fh < 50:
            continue

        landmarks = det.get('landmarks', {})
        left_eye = landmarks.get('left_eye', None)
        right_eye = landmarks.get('right_eye', None)

        angle = 0
        if left_eye and right_eye:
            dY = right_eye[1] - left_eye[1]
            dX = right_eye[0] - left_eye[0]
            angle = np.degrees(np.arctan2(dY, dX))
            if abs(angle) > 35:
                continue
            eye_center = ((left_eye[0] + right_eye[0]) / 2.0, (left_eye[1] + right_eye[1]) / 2.0)
            M = cv2.getRotationMatrix2D(eye_center, angle, 1.0)
            rotated = cv2.warpAffine(image, M, (w, h), flags=cv2.INTER_LINEAR)
        else:
            rotated = image

        pad = int(min(fw, fh) * 0.12)
        cx1, cy1 = max(0, x1 - pad), max(0, y1 - pad)
        cx2, cy2 = min(w, x2 + pad), min(h, y2 + pad)

        if (cx2 - cx1) >= 50 and (cy2 - cy1) >= 50:
            crop = rotated[cy1:cy2, cx1:cx2]
            faces.append({
                'crop': crop,
                'confidence': float(confidence),
                'bbox': [int(cx1), int(cy1), int(cx2), int(cy2)],
            })

    return faces


def _check_quality(face_crop: np.ndarray) -> dict:
    h, w = face_crop.shape[:2]
    if w < 50 or h < 50:
        return {'valid': False, 'reason': 'face_too_small'}

    gray = cv2.cvtColor(face_crop, cv2.COLOR_BGR2GRAY)
    laplacian_var = cv2.Laplacian(gray, cv2.CV_64F).var()
    if laplacian_var < 25:
        return {'valid': False, 'reason': 'face_blurry'}

    return {'valid': True, 'reason': ''}


def _enhance_glasses(face_crop: np.ndarray) -> np.ndarray:
    h, w = face_crop.shape[:2]
    if h < 40 or w < 40:
        return face_crop
    result = face_crop.copy()
    y_start, y_end = int(h * 0.20), int(h * 0.55)
    eye_region = result[y_start:y_end, :]
    gray = cv2.cvtColor(eye_region, cv2.COLOR_BGR2GRAY)
    clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(4, 4))
    enhanced = clahe.apply(gray)
    alpha = 0.4
    for c in range(3):
        eye_region[:, :, c] = cv2.addWeighted(eye_region[:, :, c], 1 - alpha, enhanced, alpha, 0)
    kernel = np.array([[-1, -1, -1], [-1, 9, -1], [-1, -1, -1]], dtype=np.float32)
    eye_region = cv2.filter2D(eye_region, -1, kernel)
    result[y_start:y_end, :] = eye_region
    return result


def _get_embedding(face_crop: np.ndarray) -> np.ndarray | None:
    from deepface import DeepFace
    embeddings = []
    for model_name in ['ArcFace', 'Facenet512']:
        try:
            # Encode crop to temp file for deepface
            _, buf = cv2.imencode('.jpg', face_crop)
            tmp = io.BytesIO(buf.tobytes())
            objs = DeepFace.represent(
                img_path=face_crop,
                model_name=model_name,
                enforce_detection=False,
                detector_backend='skip',
            )
            if objs:
                embeddings.append(np.array(objs[0]['embedding'], dtype=np.float32))
        except Exception:
            pass
    if not embeddings:
        return None
    return np.mean(embeddings, axis=0)


def _get_arcface_embedding(face_crop: np.ndarray) -> np.ndarray | None:
    from deepface import DeepFace
    try:
        objs = DeepFace.represent(
            img_path=face_crop,
            model_name='ArcFace',
            enforce_detection=False,
            detector_backend='skip',
        )
        if objs:
            return np.array(objs[0]['embedding'], dtype=np.float32)
    except Exception:
        pass
    return None


def _cosine_match(face_emb, stored_matrix, stored_norms, student_ids):
    face_norm = np.linalg.norm(face_emb)
    if face_norm == 0:
        return None, 0.0
    sims = (stored_matrix @ face_emb) / (stored_norms * face_norm)
    best_idx = int(np.argmax(sims))
    return student_ids[best_idx], float(sims[best_idx])


# ---------- API Models ----------

class DetectRequest(BaseModel):
    image: str  # base64


class EnrollRequest(BaseModel):
    photos: list[str]  # list of 3 base64 images
    student_id: int


class ScanRequest(BaseModel):
    photos: list[str]  # list of 3 base64 images
    student_embeddings: dict  # {student_id: [[emb1...], [emb2...]]}


# ---------- Endpoints ----------

@app.get("/health")
def health():
    return {"status": "ok", "models_loaded": _arcface_loaded}


@app.post("/api/detect")
def detect_faces(req: DetectRequest):
    try:
        img = _decode_image(req.image)
    except Exception as e:
        raise HTTPException(400, f"Invalid image: {e}")

    img = _preprocess(img)
    faces = _detect_faces(img)

    results = []
    for f in faces:
        quality = _check_quality(f['crop'])
        results.append({
            'confidence': f['confidence'],
            'bbox': f['bbox'],
            'quality': quality,
        })

    return {"faces": results, "count": len(results)}


@app.post("/api/enroll")
def enroll_student(req: EnrollRequest):
    _load_models()

    if len(req.photos) < 3:
        raise HTTPException(400, "Exactly 3 photos required")

    embeddings = []
    for idx, photo_b64 in enumerate(req.photos):
        try:
            img = _decode_image(photo_b64)
        except Exception:
            raise HTTPException(400, f"Invalid image {idx+1}")

        img = _preprocess(img)
        faces = _detect_faces(img)

        valid_crops = []
        for f in faces:
            quality = _check_quality(f['crop'])
            if quality['valid']:
                crop = f['crop']
                # detect glasses heuristic
                h, w = crop.shape[:2]
                y1, y2 = int(h * 0.25), int(h * 0.55)
                strip = crop[y1:y2, :]
                gray = cv2.cvtColor(strip, cv2.COLOR_BGR2GRAY)
                edges = cv2.Canny(gray, 50, 150)
                rows_with_edges = np.sum(edges > 0, axis=1)
                if np.sum(rows_with_edges > w * 0.3) > 2:
                    crop = _enhance_glasses(crop)
                valid_crops.append(crop)

        if not valid_crops:
            raise HTTPException(400, f"No clear face detected in photo {idx+1}")

        emb = _get_embedding(valid_crops[0])
        if emb is None:
            raise HTTPException(400, f"Could not generate embedding for photo {idx+1}")
        embeddings.append(emb.tolist())

    gc.collect()

    return {
        "student_id": req.student_id,
        "embeddings": embeddings,
        "count": len(embeddings),
    }


@app.post("/api/scan")
def scan_faces(req: ScanRequest):
    _load_models()

    if len(req.photos) < 3:
        raise HTTPException(400, "Exactly 3 photos required")

    if not req.student_embeddings:
        raise HTTPException(400, "No student embeddings provided")

    # Build lookup matrix
    all_stored = []
    all_ids = []
    for sid, embs in req.student_embeddings.items():
        for emb in embs:
            all_stored.append(emb)
            all_ids.append(int(sid))

    if not all_stored:
        raise HTTPException(400, "Empty embedding matrix")

    stored_matrix = np.array(all_stored, dtype=np.float32)
    stored_norms = np.linalg.norm(stored_matrix, axis=1)
    stored_norms[stored_norms == 0] = 1.0

    THRESH_HIGH = 0.55
    THRESH_MID = 0.40
    THRESH_SEEN = 2

    scores_per_student = {int(sid): [0.0, 0.0, 0.0] for sid in req.student_embeddings}
    seen_count = {int(sid): 0 for sid in req.student_embeddings}

    for photo_idx, photo_b64 in enumerate(req.photos):
        try:
            img = _decode_image(photo_b64)
        except Exception:
            continue

        img = _preprocess(img)
        faces = _detect_faces(img)

        photo_scores = {}
        for f in faces:
            quality = _check_quality(f['crop'])
            if not quality['valid']:
                continue
            crop = f['crop']
            h, w = crop.shape[:2]
            y1, y2 = int(h * 0.25), int(h * 0.55)
            strip = crop[y1:y2, :]
            gray = cv2.cvtColor(strip, cv2.COLOR_BGR2GRAY)
            edges = cv2.Canny(gray, 50, 150)
            rows_with_edges = np.sum(edges > 0, axis=1)
            if np.sum(rows_with_edges > w * 0.3) > 2:
                crop = _enhance_glasses(crop)

            emb = _get_arcface_embedding(crop)
            if emb is None:
                continue
            sid, score = _cosine_match(emb, stored_matrix, stored_norms, all_ids)
            if sid is not None:
                if sid not in photo_scores or score > photo_scores[sid]:
                    photo_scores[sid] = score

        for sid, score in photo_scores.items():
            if sid in scores_per_student:
                scores_per_student[sid][photo_idx] = score
                if score >= THRESH_MID:
                    seen_count[sid] += 1

    gc.collect()

    results = []
    for sid in scores_per_student:
        best_score = max(scores_per_student[sid])
        count = seen_count[sid]
        if best_score >= THRESH_HIGH:
            status = 'PRESENT'
        elif best_score >= THRESH_MID and count >= THRESH_SEEN:
            status = 'PRESENT'
        elif best_score >= THRESH_MID:
            status = 'REVIEW'
        else:
            status = 'ABSENT'
        results.append({
            'student_id': sid,
            'status': status,
            'best_score': round(best_score, 4),
            'seen_in': f"{count}/3",
        })

    return {"results": results}
