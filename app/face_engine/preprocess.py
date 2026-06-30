import cv2
import numpy as np


def preprocess_image(image_path):
    image = cv2.imread(image_path)
    if image is None:
        return None

    h, w = image.shape[:2]
    if w > 800:
        scale = 800 / w
        image = cv2.resize(image, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)

    lab = cv2.cvtColor(image, cv2.COLOR_BGR2LAB)
    l, a, b = cv2.split(lab)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    cl = clahe.apply(l)
    image = cv2.cvtColor(cv2.merge((cl, a, b)), cv2.COLOR_LAB2BGR)

    return image


def enhance_for_glasses(face_crop):
    """Enhance contrast in the eye region to help with glasses reflections and frames."""
    h, w = face_crop.shape[:2]
    if h < 40 or w < 40:
        return face_crop

    result = face_crop.copy()

    y_start = int(h * 0.20)
    y_end = int(h * 0.55)
    eye_region = result[y_start:y_end, :]

    gray = cv2.cvtColor(eye_region, cv2.COLOR_BGR2GRAY)
    clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(4, 4))
    enhanced_gray = clahe.apply(gray)

    alpha = 0.4
    for c in range(3):
        eye_region[:, :, c] = cv2.addWeighted(
            eye_region[:, :, c], 1 - alpha,
            enhanced_gray, alpha, 0
        )

    kernel = np.array([[-1, -1, -1], [-1, 9, -1], [-1, -1, -1]], dtype=np.float32)
    eye_region = cv2.filter2D(eye_region, -1, kernel)
    result[y_start:y_end, :] = eye_region

    return result


def check_face_quality(face_crop):
    h, w = face_crop.shape[:2]
    result = {'valid': True, 'reason': '', 'has_glasses': False}

    if w < 50 or h < 50:
        result['valid'] = False
        result['reason'] = 'face_too_small'
        return result

    gray = cv2.cvtColor(face_crop, cv2.COLOR_BGR2GRAY)
    laplacian_var = cv2.Laplacian(gray, cv2.CV_64F).var()
    if laplacian_var < 25:
        result['valid'] = False
        result['reason'] = 'face_blurry'
        return result

    result['has_glasses'] = _detect_glasses(face_crop)

    return result


def _detect_glasses(face_crop):
    """Heuristic: detect glasses by looking for dark horizontal edges in the eye region."""
    h, w = face_crop.shape[:2]
    y_start = int(h * 0.25)
    y_end = int(h * 0.55)
    eye_strip = face_crop[y_start:y_end, :]

    gray = cv2.cvtColor(eye_strip, cv2.COLOR_BGR2GRAY)
    edges = cv2.Canny(gray, 50, 150)

    rows_with_edges = np.sum(edges > 0, axis=1)
    dark_rows = np.sum(rows_with_edges > w * 0.3)

    return dark_rows > 2
