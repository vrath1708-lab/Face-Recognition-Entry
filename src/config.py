import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
DB_PATH = DATA_DIR / "members.db"
EVENT_LOG_PATH = DATA_DIR / "events.log"

SIMILARITY_THRESHOLD = 0.62
CAMERA_INDEX = 0
FRAME_SKIP = 3

# Embedding backend options:
# - legacy: existing grayscale flatten embedding (fastest, backward-compatible)
# - ml: ML-enhanced embedding (LBP + HOG)
# - hybrid: concatenates legacy + ML-enhanced vectors
# - lbph: LBPH recognizer-based matching using approved face images
EMBEDDING_BACKEND = os.getenv("EMBEDDING_BACKEND", "hybrid").strip().lower()

# When vector dimensions mismatch (existing data vs new backend),
# align dimensions safely and apply this factor to keep thresholds conservative.
MISMATCH_SIMILARITY_FACTOR = 0.97

# Backend-specific thresholds (can be overridden via environment variables)
SIMILARITY_THRESHOLD_LEGACY = float(os.getenv("SIMILARITY_THRESHOLD_LEGACY", "0.62"))
SIMILARITY_THRESHOLD_ML = float(os.getenv("SIMILARITY_THRESHOLD_ML", "0.56"))
SIMILARITY_THRESHOLD_HYBRID = float(os.getenv("SIMILARITY_THRESHOLD_HYBRID", "0.72"))
SIMILARITY_THRESHOLD_LBPH = float(os.getenv("SIMILARITY_THRESHOLD_LBPH", "0.58"))
MATCH_MARGIN_THRESHOLD = float(os.getenv("MATCH_MARGIN_THRESHOLD", "0.08"))
SINGLE_CANDIDATE_EXTRA_THRESHOLD = float(os.getenv("SINGLE_CANDIDATE_EXTRA_THRESHOLD", "0.08"))
ORB_GOOD_MATCH_THRESHOLD = int(os.getenv("ORB_GOOD_MATCH_THRESHOLD", "8"))
ORB_EVIDENCE_RATIO_THRESHOLD = float(os.getenv("ORB_EVIDENCE_RATIO_THRESHOLD", "0.08"))


def get_similarity_threshold() -> float:
	backend = EMBEDDING_BACKEND
	if backend == "lbph":
		return SIMILARITY_THRESHOLD_LBPH
	if backend == "ml":
		return SIMILARITY_THRESHOLD_ML
	if backend == "hybrid":
		return SIMILARITY_THRESHOLD_HYBRID
	return SIMILARITY_THRESHOLD_LEGACY
