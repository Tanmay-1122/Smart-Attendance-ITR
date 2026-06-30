import cv2
import numpy as np
from mtcnn import MTCNN

_detector = None

def get_detector():
    global _detector
    if _detector is None:
        import os
        os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3'
        _detector = MTCNN()
    return _detector

def extract_faces(image):
    if image is None:
        return []

    detector = get_detector()
    image_rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
    detections = detector.detect_faces(image_rgb)

    aligned_faces = []
    h, w = image.shape[:2]

    for det in detections:
        confidence = det.get('confidence', 0.0)
        if confidence < 0.85:
            continue

        x, y, width, height = det['box']
        if width < 60 or height < 60:
            continue

        keypoints = det.get('keypoints')
        if keypoints and 'left_eye' in keypoints and 'right_eye' in keypoints:
            left_eye = keypoints['left_eye']
            right_eye = keypoints['right_eye']

            dY = right_eye[1] - left_eye[1]
            dX = right_eye[0] - left_eye[0]
            angle = np.degrees(np.arctan2(dY, dX))

            if abs(angle) > 30:
                continue

            eye_center = (float((left_eye[0] + right_eye[0]) / 2.0),
                          float((left_eye[1] + right_eye[1]) / 2.0))
            M = cv2.getRotationMatrix2D(eye_center, angle, 1.0)
            rotated_image = cv2.warpAffine(image, M, (w, h), flags=cv2.INTER_LINEAR)
        else:
            rotated_image = image

        pad = int(min(width, height) * 0.1)
        x1 = max(0, x - pad)
        y1 = max(0, y - pad)
        x2 = min(w, x + width + pad)
        y2 = min(h, y + height + pad)

        if (x2 - x1) >= 60 and (y2 - y1) >= 60:
            cropped = rotated_image[y1:y2, x1:x2]
            aligned_faces.append(cropped)

    return aligned_faces
