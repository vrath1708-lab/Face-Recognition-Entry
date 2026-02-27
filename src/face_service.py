from __future__ import annotations

import json
from typing import Dict, Optional, Tuple

import cv2
import numpy as np

from config import EMBEDDING_BACKEND, MISMATCH_SIMILARITY_FACTOR, get_similarity_threshold


def _extract_primary_face(frame: np.ndarray) -> Optional[np.ndarray]:
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    detector = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
    faces = detector.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=(60, 60))

    if len(faces) == 0:
        return None

    x, y, w, h = max(faces, key=lambda item: item[2] * item[3])
    return frame[y : y + h, x : x + w]


def _fallback_embedding(face_region: np.ndarray) -> np.ndarray:
    gray = cv2.cvtColor(face_region, cv2.COLOR_BGR2GRAY)
    resized = cv2.resize(gray, (64, 64))
    normalized = resized.astype(np.float32) / 255.0
    embedding = normalized.flatten()
    return embedding


def _lbp_histogram(gray_image: np.ndarray) -> np.ndarray:
    source = cv2.resize(gray_image, (96, 96)).astype(np.uint8)
    center = source[1:-1, 1:-1]

    neighbors = [
        source[:-2, :-2],
        source[:-2, 1:-1],
        source[:-2, 2:],
        source[1:-1, 2:],
        source[2:, 2:],
        source[2:, 1:-1],
        source[2:, :-2],
        source[1:-1, :-2],
    ]

    codes = np.zeros_like(center, dtype=np.uint8)
    for index, neighbor in enumerate(neighbors):
        codes |= ((neighbor >= center).astype(np.uint8) << index)

    histogram, _ = np.histogram(codes, bins=256, range=(0, 256))
    histogram = histogram.astype(np.float32)
    histogram /= (np.sum(histogram) + 1e-8)
    return histogram


def _hog_descriptor(gray_image: np.ndarray) -> np.ndarray:
    resized = cv2.resize(gray_image, (64, 128))
    hog = cv2.HOGDescriptor()
    descriptor = hog.compute(resized)
    if descriptor is None:
        return np.zeros((3780,), dtype=np.float32)
    vector = descriptor.flatten().astype(np.float32)
    vector /= (np.linalg.norm(vector) + 1e-8)
    return vector


def _ml_enhanced_embedding(face_region: np.ndarray) -> np.ndarray:
    gray = cv2.cvtColor(face_region, cv2.COLOR_BGR2GRAY)
    equalized = cv2.equalizeHist(gray)
    lbp = _lbp_histogram(equalized)
    hog = _hog_descriptor(equalized)
    combined = np.concatenate([lbp, hog]).astype(np.float32)
    combined /= (np.linalg.norm(combined) + 1e-8)
    return combined


def _build_embedding(face_region: np.ndarray) -> np.ndarray:
    backend = EMBEDDING_BACKEND
    legacy = _fallback_embedding(face_region)

    if backend == "lbph":
        return legacy

    if backend == "legacy":
        return legacy

    ml_embedding = _ml_enhanced_embedding(face_region)

    if backend == "ml":
        return ml_embedding

    if backend == "hybrid":
        combined = np.concatenate([legacy, ml_embedding]).astype(np.float32)
        combined /= (np.linalg.norm(combined) + 1e-8)
        return combined

    return legacy


def _prepare_lbph_face(face_region: np.ndarray) -> np.ndarray:
    gray = cv2.cvtColor(face_region, cv2.COLOR_BGR2GRAY)
    equalized = cv2.equalizeHist(gray)
    resized = cv2.resize(equalized, (128, 128)).astype(np.uint8)
    return resized


def build_lbph_face_from_frame(frame: np.ndarray) -> Optional[np.ndarray]:
    face_region = _extract_primary_face(frame)
    if face_region is None:
        return None
    return _prepare_lbph_face(face_region)


def build_lbph_face_from_bgr_image(image_bgr: np.ndarray) -> Optional[np.ndarray]:
    face_region = _extract_primary_face(image_bgr)
    if face_region is None:
        if image_bgr.size == 0:
            return None
        face_region = image_bgr
    return _prepare_lbph_face(face_region)


def vector_to_csv(vector: np.ndarray) -> str:
    return ",".join([str(float(x)) for x in vector.tolist()])


def csv_to_vector(csv_string: str) -> np.ndarray:
    return np.array([float(x) for x in csv_string.split(",")], dtype=np.float32)


def build_embedding_from_image(image_path: str) -> np.ndarray:
    image = cv2.imread(image_path)
    if image is None:
        raise ValueError(f"Unable to read image: {image_path}")

    face_region = _extract_primary_face(image)
    if face_region is None:
        raise ValueError("No face found in enrollment image")

    return _build_embedding(face_region)


def build_embedding_from_frame(frame: np.ndarray) -> Optional[np.ndarray]:
    face_region = _extract_primary_face(frame)
    if face_region is None:
        return None
    return _build_embedding(face_region)


def cosine_similarity(vec_a: np.ndarray, vec_b: np.ndarray) -> float:
    denominator = (np.linalg.norm(vec_a) * np.linalg.norm(vec_b)) + 1e-8
    return float(np.dot(vec_a, vec_b) / denominator)


def _align_vectors(vec_a: np.ndarray, vec_b: np.ndarray) -> Tuple[np.ndarray, np.ndarray, bool]:
    if vec_a.shape[0] == vec_b.shape[0]:
        return vec_a, vec_b, False

    target_dim = min(vec_a.shape[0], vec_b.shape[0])
    axis_a = np.linspace(0, vec_a.shape[0] - 1, num=target_dim, dtype=np.float32)
    axis_b = np.linspace(0, vec_b.shape[0] - 1, num=target_dim, dtype=np.float32)

    aligned_a = np.interp(axis_a, np.arange(vec_a.shape[0], dtype=np.float32), vec_a).astype(np.float32)
    aligned_b = np.interp(axis_b, np.arange(vec_b.shape[0], dtype=np.float32), vec_b).astype(np.float32)
    return aligned_a, aligned_b, True


def find_best_match(
    probe_embedding: np.ndarray,
    member_embeddings: Dict[str, Tuple[str, np.ndarray]],
) -> Tuple[Optional[str], Optional[str], float, str]:
    if not member_embeddings:
        return None, None, 0.0, "DENY"

    best_member_id = None
    best_name = None
    best_score = -1.0

    for member_id, (name, stored_embedding) in member_embeddings.items():
        probe, stored, mismatched = _align_vectors(probe_embedding, stored_embedding)
        score = cosine_similarity(probe, stored)
        if mismatched:
            score *= MISMATCH_SIMILARITY_FACTOR
        if score > best_score:
            best_score = score
            best_member_id = member_id
            best_name = name

    threshold = get_similarity_threshold()
    decision = "ALLOW" if best_score >= threshold else "DENY"
    return best_member_id, best_name, best_score, decision


def find_best_match_lbph(
    probe_face: np.ndarray,
    approved_faces: Dict[str, Tuple[str, np.ndarray]],
) -> Tuple[Optional[str], Optional[str], float, str]:
    if probe_face is None or probe_face.size == 0 or not approved_faces:
        return None, None, 0.0, "DENY"

    label_to_member: Dict[int, Tuple[str, str]] = {}
    train_images = []
    labels = []

    for index, (member_id, (name, face_image)) in enumerate(approved_faces.items()):
        if face_image is None or face_image.size == 0:
            continue
        normalized = cv2.resize(face_image, (128, 128)).astype(np.uint8)
        train_images.append(normalized)
        labels.append(index)
        label_to_member[index] = (member_id, name)

    if not train_images:
        return None, None, 0.0, "DENY"

    if hasattr(cv2, "face") and hasattr(cv2.face, "LBPHFaceRecognizer_create"):
        recognizer = cv2.face.LBPHFaceRecognizer_create()
        recognizer.train(train_images, np.array(labels, dtype=np.int32))
        predicted_label, distance = recognizer.predict(cv2.resize(probe_face, (128, 128)).astype(np.uint8))

        member = label_to_member.get(int(predicted_label))
        if member is None:
            return None, None, 0.0, "DENY"

        member_id, name = member
        distance_value = float(max(0.0, distance))
        score = float(max(0.0, min(1.0, 1.0 - min(distance_value, 120.0) / 120.0)))
        decision = "ALLOW" if score >= get_similarity_threshold() else "DENY"
        return member_id, name, score, decision

    probe_hist = _lbp_histogram(probe_face)
    best_member_id = None
    best_name = None
    best_score = -1.0

    for member_id, (name, stored_face) in approved_faces.items():
        if stored_face is None or stored_face.size == 0:
            continue
        stored_hist = _lbp_histogram(stored_face)
        hist_score = float(cv2.compareHist(probe_hist.astype(np.float32), stored_hist.astype(np.float32), cv2.HISTCMP_CORREL))
        normalized_score = (hist_score + 1.0) / 2.0
        if normalized_score > best_score:
            best_score = normalized_score
            best_member_id = member_id
            best_name = name

    if best_member_id is None:
        return None, None, 0.0, "DENY"

    safe_score = float(max(0.0, min(1.0, best_score)))
    decision = "ALLOW" if safe_score >= get_similarity_threshold() else "DENY"
    return best_member_id, best_name, safe_score, decision


def pretty_match_output(member_id: Optional[str], name: Optional[str], score: float, decision: str) -> str:
    payload = {
        "member_id": member_id,
        "name": name,
        "score": round(score, 4),
        "decision": decision,
    }
    return json.dumps(payload)
