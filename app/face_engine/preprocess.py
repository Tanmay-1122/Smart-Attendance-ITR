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


def check_face_quality(face_crop):
    h, w = face_crop.shape[:2]
    result = {'valid': True, 'reason': ''}

    if w < 60 or h < 60:
        result['valid'] = False
        result['reason'] = 'face_too_small'
        return result

    gray = cv2.cvtColor(face_crop, cv2.COLOR_BGR2GRAY)
    laplacian_var = cv2.Laplacian(gray, cv2.CV_64F).var()
    if laplacian_var < 30:
        result['valid'] = False
        result['reason'] = 'face_blurry'
        return result

    return result
