import numpy as np
import threading
import gc
from deepface import DeepFace

MODELS = ['ArcFace', 'Facenet512']
_lock = threading.Lock()


def _get_embedding(face_crop):
    model_embeddings = []
    for model_name in MODELS:
        try:
            with _lock:
                objs = DeepFace.represent(
                    img_path=face_crop,
                    model_name=model_name,
                    enforce_detection=False,
                    detector_backend='skip'
                )
            if objs:
                model_embeddings.append(np.array(objs[0]['embedding']))
        except Exception as e:
            print(f"Error generating {model_name} embedding: {e}")

    if not model_embeddings:
        return None
    return np.mean(model_embeddings, axis=0)


def clear_model_cache():
    try:
        from deepface import DeepFace
        if hasattr(DeepFace, 'models'):
            DeepFace.models.clear()
        gc.collect()
    except Exception:
        pass


def batch_match(face_crops, student_embeddings):
    if not student_embeddings or not face_crops:
        return []

    face_embs = []
    for crop in face_crops:
        emb = _get_embedding(crop)
        if emb is not None:
            face_embs.append(emb)

    if not face_embs:
        return []

    all_stored = []
    all_student_ids = []
    for sid, embeddings in student_embeddings.items():
        for emb in embeddings:
            all_stored.append(emb)
            all_student_ids.append(sid)

    if not all_stored:
        return []

    stored_matrix = np.array(all_stored)
    stored_norms = np.linalg.norm(stored_matrix, axis=1)
    stored_norms[stored_norms == 0] = 1.0

    face_results = []
    for face_emb in face_embs:
        face_norm = np.linalg.norm(face_emb)
        if face_norm == 0:
            face_results.append((None, 0.0))
            continue

        dot_products = stored_matrix @ face_emb
        sims = dot_products / (stored_norms * face_norm)

        best_idx = int(np.argmax(sims))
        best_score = float(sims[best_idx])
        best_sid = all_student_ids[best_idx]

        face_results.append((best_sid, best_score))

    return face_results


def match_face(face_crop, student_embeddings):
    if not student_embeddings or face_crop is None or face_crop.size == 0:
        return None, 0.0

    face_emb = _get_embedding(face_crop)
    if face_emb is None:
        return None, 0.0

    all_stored = []
    all_student_ids = []
    for sid, embeddings in student_embeddings.items():
        for emb in embeddings:
            all_stored.append(emb)
            all_student_ids.append(sid)

    if not all_stored:
        return None, 0.0

    stored_matrix = np.array(all_stored)
    stored_norms = np.linalg.norm(stored_matrix, axis=1)
    stored_norms[stored_norms == 0] = 1.0

    face_norm = np.linalg.norm(face_emb)
    if face_norm == 0:
        return None, 0.0

    dot_products = stored_matrix @ face_emb
    sims = dot_products / (stored_norms * face_norm)

    best_idx = int(np.argmax(sims))
    return all_student_ids[best_idx], float(sims[best_idx])
