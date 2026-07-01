import cv2
import numpy as np
from retinaface import RetinaFace

_detector = None


def get_detector():
    global _detector
    if _detector is None:
        import os
        os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3'
    return _detector


def extract_faces(image):
    if image is None:
        return []

    image_rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
    detections = RetinaFace.detect_faces(image_rgb, threshold=0.9)

    if not detections or isinstance(detections, dict) and not detections:
        return []

    aligned_faces = []
    h, w = image.shape[:2]

    if isinstance(detections, dict):
        detections = [detections[k] for k in detections if isinstance(detections[k], dict) and 'facial_area' in detections[k]]

    for det in detections:
        confidence = det.get('score', det.get('confidence', 0.0))
        if confidence < 0.90:
            continue

        fa = det.get('facial_area', None)
        if fa is None:
            continue

        x1, y1, x2, y2 = fa[0], fa[1], fa[2], fa[3]
        fw = x2 - x1
        fh = y2 - y1

        if fw < 50 or fh < 50:
            continue

        landmarks = det.get('landmarks', {})
        left_eye = landmarks.get('left_eye', None)
        right_eye = landmarks.get('right_eye', None)

        angle = 0
        if left_eye is not None and right_eye is not None:
            dY = left_eye[1] - right_eye[1]
            dX = left_eye[0] - right_eye[0]
            angle = np.degrees(np.arctan2(dY, dX))

            if abs(angle) > 35:
                continue

            eye_center = (
                float((left_eye[0] + right_eye[0]) / 2.0),
                float((left_eye[1] + right_eye[1]) / 2.0),
            )
            M = cv2.getRotationMatrix2D(eye_center, angle, 1.0)
            rotated_image = cv2.warpAffine(image, M, (w, h), flags=cv2.INTER_LINEAR)
        else:
            rotated_image = image

        pad = int(min(fw, fh) * 0.12)
        cx1 = max(0, x1 - pad)
        cy1 = max(0, y1 - pad)
        cx2 = min(w, x2 + pad)
        cy2 = min(h, y2 + pad)

        if (cx2 - cx1) >= 50 and (cy2 - cy1) >= 50:
            cropped = rotated_image[cy1:cy2, cx1:cx2]
            aligned_faces.append(cropped)

    return aligned_faces
