from __future__ import annotations

from datetime import datetime
from pathlib import Path

import cv2

from config import CAMERA_INDEX, EVENT_LOG_PATH, FRAME_SKIP
from database import fetch_all_members, init_db
from face_service import (
    build_embedding_from_frame,
    csv_to_vector,
    find_best_match,
    pretty_match_output,
)


def load_member_embeddings():
    rows = fetch_all_members()
    return {
        member_id: (name, csv_to_vector(embedding_csv))
        for member_id, name, embedding_csv in rows
    }


def log_event(payload: str) -> None:
    Path(EVENT_LOG_PATH).parent.mkdir(parents=True, exist_ok=True)
    with open(EVENT_LOG_PATH, "a", encoding="utf-8") as file:
        file.write(f"{datetime.now().isoformat()} {payload}\n")


def main() -> None:
    init_db()
    member_embeddings = load_member_embeddings()

    print(f"Loaded {len(member_embeddings)} members")
    print("Press Q to quit")

    cap = cv2.VideoCapture(CAMERA_INDEX)
    if not cap.isOpened():
        raise RuntimeError("Unable to open camera")

    frame_count = 0
    last_result = "No face"

    try:
        while True:
            ret, frame = cap.read()
            if not ret:
                continue

            frame_count += 1
            if frame_count % FRAME_SKIP == 0:
                embedding = build_embedding_from_frame(frame)
                if embedding is not None:
                    member_id, name, score, decision = find_best_match(embedding, member_embeddings)
                    last_result = pretty_match_output(member_id, name, score, decision)
                    log_event(last_result)

            cv2.putText(
                frame,
                last_result,
                (20, 35),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.6,
                (0, 255, 0),
                2,
            )
            cv2.imshow("Premium Lounge Entry", frame)

            if cv2.waitKey(1) & 0xFF == ord("q"):
                break
    finally:
        cap.release()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
