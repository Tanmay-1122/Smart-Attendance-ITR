import numpy as np
import gc
from deepface import DeepFace

_ARCFACE_MODEL = None
_FACENET_MODEL = None
_model_lock = None


def _ensure_models_loaded():
    global _ARCFACE_MODEL, _FACENET_MODEL, _model_lock
    if _ARCFACE_MODEL is not None:
        return

    import threading
    _model_lock = threading.Lock()

    with _model_lock:
        if _ARCFACE_MODEL is not None:
            return
        DeepFace.build_model(model_name='ArcFace')
        _ARCFACE_MODEL = True
        DeepFace.build_model(model_name='Facenet512')
        _FACENET_MODEL = True


def _get_embedding(face_crop):
    _ensure_models_loaded()

    embeddings = []
    for model_name in ['ArcFace', 'Facenet512']:
        try:
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


def _get_arcface_embedding(face_crop):
    """Faster single-model embedding for batch matching."""
    _ensure_models_loaded()
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


def clear_model_cache():
    try:
        global _ARCFACE_MODEL, _FACENET_MODEL
        if hasattr(DeepFace, 'models'):
            DeepFace.models.clear()
        _ARCFACE_MODEL = None
        _FACENET_MODEL = None
        gc.collect()
    except Exception:
        pass


def build_student_matrix(student_embeddings):
    """Precompute a flat matrix of all stored embeddings and their student IDs."""
    all_stored = []
    all_student_ids = []
    for sid, embeddings in student_embeddings.items():
        for emb in embeddings:
            all_stored.append(emb)
            all_student_ids.append(sid)

    if not all_stored:
        return None, None

    matrix = np.array(all_stored, dtype=np.float32)
    norms = np.linalg.norm(matrix, axis=1)
    norms[norms == 0] = 1.0
    return matrix, norms, all_student_ids


def _cosine_match(face_emb, stored_matrix, stored_norms, student_ids):
    face_norm = np.linalg.norm(face_emb)
    if face_norm == 0:
        return None, 0.0

    dot_products = stored_matrix @ face_emb
    sims = dot_products / (stored_norms * face_norm)

    best_idx = int(np.argmax(sims))
    return student_ids[best_idx], float(sims[best_idx])


def batch_match(face_crops, student_embeddings):
    if not student_embeddings or not face_crops:
        return []

    matrix, norms, student_ids = build_student_matrix(student_embeddings)
    if matrix is None:
        return []

    face_results = []
    for crop in face_crops:
        emb = _get_arcface_embedding(crop)
        if emb is None:
            continue
        sid, score = _cosine_match(emb, matrix, norms, student_ids)
        face_results.append((sid, score))

    return face_results


def match_face(face_crop, student_embeddings):
    if not student_embeddings or face_crop is None or face_crop.size == 0:
        return None, 0.0

    face_emb = _get_embedding(face_crop)
    if face_emb is None:
        return None, 0.0

    matrix, norms, student_ids = build_student_matrix(student_embeddings)
    if matrix is None:
        return None, 0.0

    return _cosine_match(face_emb, matrix, norms, student_ids)
