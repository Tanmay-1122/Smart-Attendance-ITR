import json
import gc
import numpy as np
from concurrent.futures import ThreadPoolExecutor, as_completed
from ..models import Student, StudentClass
from .preprocess import preprocess_image, check_face_quality
from .detect import extract_faces
from .recognize import match_face, batch_match, clear_model_cache

THRESH_HIGH = 0.60
THRESH_MID  = 0.45
THRESH_SEEN = 2


def _process_one_photo(args):
    photo_idx, path, student_embeddings = args
    img = preprocess_image(path)
    if img is None:
        return photo_idx, {}

    face_crops = extract_faces(img)
    photo_best_scores = {}

    for crop in face_crops:
        quality = check_face_quality(crop)
        if not quality['valid']:
            continue

        sid, score = match_face(crop, student_embeddings)
        if sid is not None:
            if sid not in photo_best_scores or score > photo_best_scores[sid]:
                photo_best_scores[sid] = score

    return photo_idx, photo_best_scores


def _process_one_photo_batch(args):
    photo_idx, path, student_embeddings = args
    img = preprocess_image(path)
    if img is None:
        print(f"[SCAN] Photo {photo_idx}: preprocess returned None")
        return photo_idx, {}

    face_crops = extract_faces(img)
    print(f"[SCAN] Photo {photo_idx}: detected {len(face_crops)} face(s)")
    photo_best_scores = {}

    valid_crops = []
    for crop in face_crops:
        quality = check_face_quality(crop)
        if quality['valid']:
            valid_crops.append(crop)
        else:
            print(f"[SCAN] Photo {photo_idx}: face rejected - {quality['reason']}")

    if not valid_crops:
        return photo_idx, {}

    results = batch_match(valid_crops, student_embeddings)
    for sid, score in results:
        print(f"[SCAN] Photo {photo_idx}: matched student {sid} with score {score:.4f}")
        if sid is not None:
            if sid not in photo_best_scores or score > photo_best_scores[sid]:
                photo_best_scores[sid] = score

    return photo_idx, photo_best_scores


def process_three_photos(photo_paths, class_name, class_id=None):
    if class_id:
        enrolled_ids = [sc.student_id for sc in StudentClass.query.filter_by(class_id=class_id).all()]
        students = Student.query.filter(Student.id.in_(enrolled_ids)).all() if enrolled_ids else []
    else:
        students = Student.query.all()

    student_embeddings = {}
    student_info = {}
    for s in students:
        student_info[s.id] = {
            'name': s.user.name if s.user else "Unknown",
            'roll_number': s.roll_number,
            'enrolled_class': class_name
        }
        if s.face_embedding:
            try:
                emb_data = json.loads(s.face_embedding)
                if emb_data and isinstance(emb_data[0], list):
                    student_embeddings[s.id] = emb_data
                else:
                    student_embeddings[s.id] = [emb_data]
            except Exception:
                pass

    scores_per_student = {sid: [0.0, 0.0, 0.0] for sid in student_info}
    seen_count = {sid: 0 for sid in student_info}

    tasks = [(i, path, student_embeddings) for i, path in enumerate(photo_paths)]

    use_batch = len(student_embeddings) > 10
    process_fn = _process_one_photo_batch if use_batch else _process_one_photo

    with ThreadPoolExecutor(max_workers=3) as executor:
        futures = {executor.submit(process_fn, t): t[0] for t in tasks}
        for future in as_completed(futures):
            photo_idx, photo_best_scores = future.result()
            for sid, score in photo_best_scores.items():
                scores_per_student[sid][photo_idx] = score
                if score >= THRESH_MID:
                    seen_count[sid] += 1

    results = []
    for sid in student_info:
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
            'name': student_info[sid]['name'],
            'roll_number': student_info[sid]['roll_number'],
            'enrolled_class': student_info[sid]['enrolled_class'],
            'status': status,
            'best_score': best_score,
            'seen_in': f"{count}/3"
        })

    del student_embeddings
    gc.collect()
    clear_model_cache()

    return results
