import json
import gc
import numpy as np
from concurrent.futures import ThreadPoolExecutor, as_completed
from ..models import Student, StudentClass
from .preprocess import preprocess_image, check_face_quality, enhance_for_glasses
from .detect import extract_faces
from .recognize import batch_match, match_face, build_student_matrix, clear_model_cache

THRESH_HIGH = 0.55
THRESH_MID = 0.40
THRESH_SEEN = 2


def _process_one_photo(args):
    photo_idx, path, student_embeddings, precomputed = args
    img = preprocess_image(path)
    if img is None:
        return photo_idx, {}

    face_crops = extract_faces(img)
    photo_best_scores = {}

    valid_crops = []
    for crop in face_crops:
        quality = check_face_quality(crop)
        if not quality['valid']:
            continue
        if quality['has_glasses']:
            crop = enhance_for_glasses(crop)
        valid_crops.append(crop)

    if not valid_crops:
        return photo_idx, {}

    matrix, norms, student_ids = precomputed
    if matrix is None:
        return photo_idx, {}

    results = batch_match(valid_crops, student_embeddings)
    for sid, score in results:
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
            'enrolled_class': class_name,
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

    precomputed = build_student_matrix(student_embeddings)

    scores_per_student = {sid: [0.0, 0.0, 0.0] for sid in student_info}
    seen_count = {sid: 0 for sid in student_info}

    tasks = [(i, path, student_embeddings, precomputed) for i, path in enumerate(photo_paths)]

    with ThreadPoolExecutor(max_workers=3) as executor:
        futures = {executor.submit(_process_one_photo, t): t[0] for t in tasks}
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
            'seen_in': f"{count}/3",
        })

    del student_embeddings
    gc.collect()
    clear_model_cache()

    return results
