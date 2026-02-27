from __future__ import annotations

import base64
import json
import io
import secrets
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Tuple

import cv2
import numpy as np
from PIL import Image
from fastapi import FastAPI, File, Form, Header, HTTPException, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles

ROOT_DIR = Path(__file__).resolve().parent
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from config import EMBEDDING_BACKEND, EVENT_LOG_PATH
from database import (
    delete_member,
    create_or_update_application,
    get_member,
    get_member_full,
    init_db,
    list_applications,
    list_users_for_admin,
    list_approved_embeddings,
    list_approved_face_images,
    set_application_status,
    update_member_admin,
)
from email_service import send_decision_email
from face_service import (
    build_embedding_from_frame,
    build_lbph_face_from_bgr_image,
    build_lbph_face_from_frame,
    csv_to_vector,
    find_best_match,
    find_best_match_lbph,
    vector_to_csv,
)

app = FastAPI(title="VIP Lounge Face Access", version="2.0.0")

TOKEN_TTL_MINUTES = 480
CHALLENGE_TTL_SECONDS = 30

TOKENS: Dict[str, Dict[str, object]] = {}
LIVE_CHALLENGES: Dict[str, Dict[str, object]] = {}

AUTH_USERS = {
    "admin": {"username": "admin", "password": "admin123"},
    "user": {"username": "user", "password": "user123"},
}

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


app.mount("/web", StaticFiles(directory=str(ROOT_DIR / "web")), name="web")


def _append_event(payload: dict) -> None:
    Path(EVENT_LOG_PATH).parent.mkdir(parents=True, exist_ok=True)
    with open(EVENT_LOG_PATH, "a", encoding="utf-8") as file:
        file.write(f"{datetime.utcnow().isoformat()} {json.dumps(payload)}\\n")


def _bytes_to_bgr(image_bytes: bytes) -> np.ndarray:
    array = np.frombuffer(image_bytes, dtype=np.uint8)
    frame = cv2.imdecode(array, cv2.IMREAD_COLOR)
    if frame is None:
        raise HTTPException(status_code=400, detail="Invalid image")
    return frame


def _create_token(role: str, username: str) -> str:
    token = secrets.token_urlsafe(24)
    TOKENS[token] = {
        "role": role,
        "username": username,
        "expires_at": datetime.utcnow() + timedelta(minutes=TOKEN_TTL_MINUTES),
    }
    return token


def _extract_bearer(authorization: str | None) -> str:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid authorization header")
    return authorization.replace("Bearer ", "", 1).strip()


def _require_token(authorization: str | None, allowed_roles: set[str]) -> Dict[str, object]:
    token = _extract_bearer(authorization)
    session = TOKENS.get(token)
    if not session:
        raise HTTPException(status_code=401, detail="Invalid token")

    if session["expires_at"] < datetime.utcnow():
        TOKENS.pop(token, None)
        raise HTTPException(status_code=401, detail="Token expired")

    if session["role"] not in allowed_roles:
        raise HTTPException(status_code=403, detail="Insufficient role")
    return {"token": token, **session}


def _create_live_challenge(token: str, purpose: str) -> str:
    challenge_id = secrets.token_urlsafe(16)
    LIVE_CHALLENGES[challenge_id] = {
        "token": token,
        "purpose": purpose,
        "expires_at": datetime.utcnow() + timedelta(seconds=CHALLENGE_TTL_SECONDS),
        "used": False,
    }
    return challenge_id


def _consume_live_challenge(challenge_id: str, token: str, purpose: str) -> None:
    challenge = LIVE_CHALLENGES.get(challenge_id)
    if not challenge:
        raise HTTPException(status_code=401, detail="Missing or invalid live capture challenge")

    if challenge["used"]:
        raise HTTPException(status_code=401, detail="Live capture challenge already used")

    if challenge["token"] != token or challenge["purpose"] != purpose:
        raise HTTPException(status_code=401, detail="Live capture challenge mismatch")

    if challenge["expires_at"] < datetime.utcnow():
        LIVE_CHALLENGES.pop(challenge_id, None)
        raise HTTPException(status_code=401, detail="Live capture challenge expired")

    challenge["used"] = True


def _load_approved_embeddings() -> Dict[str, Tuple[str, np.ndarray]]:
    rows = list_approved_embeddings()
    return {member_id: (name, csv_to_vector(embedding_csv)) for member_id, name, embedding_csv in rows}


def _load_approved_faces_for_lbph() -> Dict[str, Tuple[str, np.ndarray]]:
    rows = list_approved_face_images()
    approved_faces: Dict[str, Tuple[str, np.ndarray]] = {}

    for member_id, name, image_bytes in rows:
        if not image_bytes:
            continue
        try:
            frame = _bytes_to_bgr(image_bytes)
        except HTTPException:
            continue
        prepared_face = build_lbph_face_from_bgr_image(frame)
        if prepared_face is None:
            continue
        approved_faces[member_id] = (name, prepared_face)

    return approved_faces


@app.on_event("startup")
def on_startup() -> None:
    init_db()


@app.get("/")
def home() -> FileResponse:
    return FileResponse(str(ROOT_DIR / "web" / "index.html"))


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok", "service": "vip-face-access-api"}


@app.post("/api/auth/login")
def auth_login(
    username: str = Form(...),
    password: str = Form(...),
    role: str = Form(default=""),
) -> dict:
    username_clean = username.strip()
    password_clean = password.strip()
    requested_role = role.strip().lower()

    if requested_role:
        if requested_role not in AUTH_USERS:
            raise HTTPException(status_code=400, detail="Invalid role")
        user_record = AUTH_USERS[requested_role]
        if username_clean != user_record["username"] or password_clean != user_record["password"]:
            raise HTTPException(status_code=401, detail="Invalid credentials")
        role_key = requested_role
    else:
        role_key = ""
        for candidate_role, user_record in AUTH_USERS.items():
            if username_clean == user_record["username"] and password_clean == user_record["password"]:
                role_key = candidate_role
                break
        if not role_key:
            raise HTTPException(status_code=401, detail="Invalid credentials")

    token = _create_token(role=role_key, username=username_clean)
    return {"ok": True, "token": token, "role": role_key, "expires_in_minutes": TOKEN_TTL_MINUTES}


@app.get("/api/auth/me")
def auth_me(authorization: str | None = Header(default=None, alias="Authorization")) -> dict:
    session = _require_token(authorization, allowed_roles={"admin", "user"})
    expires_at = session.get("expires_at")
    return {
        "ok": True,
        "role": session["role"],
        "username": session["username"],
        "expires_at": expires_at.isoformat() if isinstance(expires_at, datetime) else None,
    }


@app.post("/api/auth/logout")
def auth_logout(authorization: str | None = Header(default=None, alias="Authorization")) -> dict:
    token = _extract_bearer(authorization)
    TOKENS.pop(token, None)
    return {"ok": True, "message": "Logged out"}


@app.post("/api/auth/challenge")
def live_capture_challenge(
    purpose: str = Form(...),
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> dict:
    session = _require_token(authorization, allowed_roles={"admin"})
    purpose_clean = purpose.strip().lower()
    if purpose_clean not in {"review", "admin-register"}:
        raise HTTPException(status_code=400, detail="Invalid challenge purpose")

    challenge_id = _create_live_challenge(token=session["token"], purpose=purpose_clean)
    return {"ok": True, "challenge_id": challenge_id, "expires_in_seconds": CHALLENGE_TTL_SECONDS}


@app.post("/api/register")
async def register_user(
    name: str = Form(...),
    email: str = Form(...),
    image: UploadFile = File(...),
) -> dict:
    name_clean = name.strip()
    if not name_clean:
        raise HTTPException(status_code=400, detail="Name is required")

    email_clean = email.strip().lower()
    if not email_clean or "@" not in email_clean:
        raise HTTPException(status_code=400, detail="Valid email is required")

    image_bytes = await image.read()
    frame = _bytes_to_bgr(image_bytes)

    embedding = build_embedding_from_frame(frame)
    if embedding is None:
        raise HTTPException(status_code=400, detail="No face detected in image")

    member_id = f"U{secrets.randbelow(10_000_000):07d}"
    create_or_update_application(
        member_id=member_id,
        name=name_clean,
        email=email_clean,
        embedding_csv=vector_to_csv(embedding),
        face_image=image_bytes,
    )

    _append_event(
        {
            "type": "APPLICATION_SUBMITTED",
            "member_id": member_id,
            "name": name_clean,
            "email": email_clean,
            "submitted_by": "public_user_portal",
        }
    )

    return {
        "ok": True,
        "message": "Application submitted (or updated) for admin review",
        "application": {
            "member_id": member_id,
            "name": name_clean,
            "email": email_clean,
            "application_status": "pending",
        },
    }


@app.get("/api/applications")
def applications(
    status: str = "all",
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> dict:
    _require_token(authorization, allowed_roles={"admin"})
    status_clean = status.strip().lower()
    status_filter = None if status_clean == "all" else status_clean
    if status_filter and status_filter not in {"pending", "approved", "rejected"}:
        raise HTTPException(status_code=400, detail="Invalid status filter")

    rows = list_applications(status_filter)
    return {
        "count": len(rows),
        "applications": [
            {
                "member_id": member_id,
                "name": name,
                "email": email,
                "application_status": application_status,
                "review_note": review_note,
                "reviewed_by": reviewed_by,
                "reviewed_at": reviewed_at,
                "created_at": created_at,
            }
            for member_id, name, email, application_status, review_note, reviewed_by, reviewed_at, created_at in rows
        ],
    }


@app.get("/api/admin/users")
def admin_users(
    status: str = "all",
    q: str = "",
    limit: int = 200,
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> dict:
    _require_token(authorization, allowed_roles={"admin"})

    status_clean = status.strip().lower()
    search_clean = q.strip()
    status_filter = None if status_clean == "all" else status_clean

    if status_filter and status_filter not in {"pending", "approved", "rejected"}:
        raise HTTPException(status_code=400, detail="Invalid status filter")

    rows = list_users_for_admin(status=status_filter, search=search_clean, limit=limit)
    return {
        "count": len(rows),
        "users": [
            {
                "member_id": member_id,
                "name": name,
                "email": email,
                "application_status": application_status,
                "review_note": review_note,
                "reviewed_by": reviewed_by,
                "reviewed_at": reviewed_at,
                "created_at": created_at,
            }
            for member_id, name, email, application_status, review_note, reviewed_by, reviewed_at, created_at in rows
        ],
    }


@app.get("/api/admin/users/{member_id}")
def admin_user_detail(
    member_id: str,
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> dict:
    _require_token(authorization, allowed_roles={"admin"})
    member = get_member_full(member_id.strip())
    if not member:
        raise HTTPException(status_code=404, detail="User not found")

    (
        member_id_db,
        name,
        email,
        embedding,
        face_image,
        application_status,
        review_note,
        reviewed_by,
        reviewed_at,
        created_at,
    ) = member

    return {
        "ok": True,
        "user": {
            "member_id": member_id_db,
            "name": name,
            "email": email,
            "embedding_dims": len(embedding.split(",")) if embedding else 0,
            "has_face_image": bool(face_image),
            "application_status": application_status,
            "review_note": review_note,
            "reviewed_by": reviewed_by,
            "reviewed_at": reviewed_at,
            "created_at": created_at,
        },
    }


@app.get("/api/admin/users/{member_id}/face-image")
def admin_user_face_image(
    member_id: str,
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> Response:
    _require_token(authorization, allowed_roles={"admin"})
    member = get_member_full(member_id.strip())
    if not member:
        raise HTTPException(status_code=404, detail="User not found")

    face_image = member[4]
    if not face_image:
        raise HTTPException(status_code=404, detail="Face image not found")
    return Response(content=face_image, media_type="image/jpeg")


@app.post("/api/admin/users/update")
def admin_update_user(
    member_id: str = Form(...),
    name: str = Form(default=""),
    email: str = Form(default=""),
    application_status: str = Form(default=""),
    review_note: str | None = Form(default=None),
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> dict:
    session = _require_token(authorization, allowed_roles={"admin"})

    member_id_clean = member_id.strip()
    if not member_id_clean:
        raise HTTPException(status_code=400, detail="Member ID is required")

    member = get_member_full(member_id_clean)
    if not member:
        raise HTTPException(status_code=404, detail="User not found")

    previous_status = str(member[5] or "").strip().lower()
    existing_email = str(member[2] or "").strip()
    existing_name = str(member[1] or "").strip()

    name_value = name.strip() if name.strip() else None
    email_value = email.strip().lower() if email.strip() else None
    status_value = application_status.strip().lower() if application_status.strip() else None
    note_value = review_note.strip() if review_note is not None else None

    if email_value is not None and "@" not in email_value:
        raise HTTPException(status_code=400, detail="Invalid email")

    if status_value and status_value not in {"pending", "approved", "rejected"}:
        raise HTTPException(status_code=400, detail="Invalid application status")

    if name_value is None and email_value is None and status_value is None and note_value is None:
        raise HTTPException(status_code=400, detail="No update fields provided")

    updated = update_member_admin(
        member_id=member_id_clean,
        reviewed_by=str(session["username"]),
        name=name_value,
        email=email_value,
        application_status=status_value,
        review_note=note_value,
    )
    if not updated:
        raise HTTPException(status_code=404, detail="User not found")

    _append_event(
        {
            "type": "ADMIN_USER_UPDATED",
            "member_id": member_id_clean,
            "updated_by": session["username"],
            "name": name_value,
            "email": email_value,
            "application_status": status_value,
            "review_note": note_value,
        }
    )

    email_result = None
    if status_value in {"approved", "rejected"} and status_value != previous_status:
        recipient_email = email_value if email_value is not None else existing_email
        recipient_name = name_value if name_value is not None else existing_name
        ok, msg = send_decision_email(
            recipient_email=recipient_email,
            recipient_name=recipient_name or "User",
            member_id=member_id_clean,
            decision=status_value,
            review_note=note_value or "",
        )
        email_result = {"sent": ok, "message": msg, "to": recipient_email or None}
        _append_event(
            {
                "type": "APPLICATION_EMAIL_NOTIFICATION",
                "member_id": member_id_clean,
                "decision": status_value,
                "email": recipient_email,
                "sent": ok,
                "message": msg,
            }
        )

    return {
        "ok": True,
        "member_id": member_id_clean,
        "message": "User updated",
        "email_notification": email_result,
    }


@app.delete("/api/admin/users/{member_id}")
def admin_delete_user(
    member_id: str,
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> dict:
    session = _require_token(authorization, allowed_roles={"admin"})
    member_id_clean = member_id.strip()
    if not member_id_clean:
        raise HTTPException(status_code=400, detail="Member ID is required")

    deleted = delete_member(member_id_clean)
    if not deleted:
        raise HTTPException(status_code=404, detail="User not found")

    _append_event({"type": "ADMIN_USER_DELETED", "member_id": member_id_clean, "deleted_by": session["username"]})
    return {"ok": True, "member_id": member_id_clean, "message": "User deleted"}


@app.post("/api/applications/decision")
def decide_application(
    member_id: str = Form(...),
    decision: str = Form(...),
    note: str = Form(default=""),
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> dict:
    session = _require_token(authorization, allowed_roles={"admin"})

    decision_clean = decision.strip().lower()
    if decision_clean not in {"approved", "rejected"}:
        raise HTTPException(status_code=400, detail="Decision must be approved or rejected")

    member = get_member(member_id.strip())
    if not member:
        raise HTTPException(status_code=404, detail="Application not found")

    detail = get_member_full(member_id.strip())
    recipient_name = str(detail[1] or "User") if detail else "User"
    recipient_email = str(detail[2] or "").strip() if detail else ""

    updated = set_application_status(
        member_id=member_id.strip(),
        status=decision_clean,
        reviewed_by=str(session["username"]),
        review_note=note.strip(),
    )
    if not updated:
        raise HTTPException(status_code=404, detail="Application not found")

    _append_event(
        {
            "type": "APPLICATION_DECISION",
            "member_id": member_id.strip(),
            "decision": decision_clean,
            "reviewed_by": session["username"],
            "note": note.strip(),
        }
    )

    ok, msg = send_decision_email(
        recipient_email=recipient_email,
        recipient_name=recipient_name,
        member_id=member_id.strip(),
        decision=decision_clean,
        review_note=note.strip(),
    )
    _append_event(
        {
            "type": "APPLICATION_EMAIL_NOTIFICATION",
            "member_id": member_id.strip(),
            "decision": decision_clean,
            "email": recipient_email,
            "sent": ok,
            "message": msg,
        }
    )

    return {
        "ok": True,
        "member_id": member_id.strip(),
        "decision": decision_clean,
        "email_notification": {"sent": ok, "message": msg, "to": recipient_email or None},
    }


@app.get("/api/events")
def events(limit: int = 30, authorization: str | None = Header(default=None, alias="Authorization")) -> dict:
    _require_token(authorization, allowed_roles={"admin"})
    log_path = Path(EVENT_LOG_PATH)
    if not log_path.exists():
        return {"events": []}

    lines = log_path.read_text(encoding="utf-8").splitlines()
    return {"events": lines[-max(1, min(limit, 300)) :]}


@app.post("/api/gate/verify")
async def gate_verify(image: UploadFile = File(...), device_id: str = Form(default="gate-camera")) -> dict:
    image_bytes = await image.read()
    frame = _bytes_to_bgr(image_bytes)

    if EMBEDDING_BACKEND == "lbph":
        probe_face = build_lbph_face_from_frame(frame)
        if probe_face is None:
            return {"ok": True, "decision": "DENY", "reason": "face_not_detected", "score": 0.0}
        approved_faces = _load_approved_faces_for_lbph()
        member_id, name, score, match_decision = find_best_match_lbph(probe_face, approved_faces)
    else:
        probe_embedding = build_embedding_from_frame(frame)
        if probe_embedding is None:
            return {"ok": True, "decision": "DENY", "reason": "face_not_detected", "score": 0.0}

        approved_embeddings = _load_approved_embeddings()
        member_id, name, score, match_decision = find_best_match(probe_embedding, approved_embeddings)

    decision = "ALLOW" if match_decision == "ALLOW" and member_id else "DENY"
    reason = "vip_approved" if decision == "ALLOW" else "not_vip_or_not_matched"

    _append_event(
        {
            "type": "GATE_ATTEMPT",
            "device_id": device_id,
            "member_id": member_id,
            "name": name,
            "score": round(score, 4),
            "decision": decision,
            "reason": reason,
        }
    )

    return {
        "ok": True,
        "decision": decision,
        "member_id": member_id,
        "name": name,
        "score": round(score, 4),
        "reason": reason,
    }


@app.websocket("/ws/gate-live")
async def websocket_gate_live(websocket: WebSocket):
    await websocket.accept()

    try:
        frame_count = 0
        while True:
            data = await websocket.receive_text()
            frame_count += 1

            try:
                frame_bytes = base64.b64decode(data)
                image = Image.open(io.BytesIO(frame_bytes))
                frame = cv2.cvtColor(np.array(image), cv2.COLOR_RGB2BGR)
            except Exception as exc:
                await websocket.send_json({"ok": False, "face_detected": False, "error": f"Frame decode error: {exc}"})
                continue

            if EMBEDDING_BACKEND == "lbph":
                probe_face = build_lbph_face_from_frame(frame)
                if probe_face is None:
                    await websocket.send_json({
                        "ok": True,
                        "face_detected": False,
                        "confidence_pct": 0,
                        "frame_count": frame_count,
                    })
                    continue

                approved_faces = _load_approved_faces_for_lbph()
                member_id, name, score, match_decision = find_best_match_lbph(probe_face, approved_faces)
            else:
                probe_embedding = build_embedding_from_frame(frame)
                if probe_embedding is None:
                    await websocket.send_json({
                        "ok": True,
                        "face_detected": False,
                        "confidence_pct": 0,
                        "frame_count": frame_count,
                    })
                    continue

                approved_embeddings = _load_approved_embeddings()
                member_id, name, score, match_decision = find_best_match(probe_embedding, approved_embeddings)

            decision = "ALLOW" if match_decision == "ALLOW" and member_id else "DENY"
            reason = "vip_approved" if decision == "ALLOW" else "not_vip_or_not_matched"
            confidence_pct = int(min(100, max(0, score * 100)))

            await websocket.send_json(
                {
                    "ok": True,
                    "face_detected": True,
                    "matched_member_id": member_id,
                    "name": name,
                    "score": round(score, 4),
                    "confidence_pct": confidence_pct,
                    "decision": decision,
                    "reason": reason,
                    "frame_count": frame_count,
                }
            )
    except WebSocketDisconnect:
        pass


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app_server:app", host="127.0.0.1", port=8000, reload=False)
