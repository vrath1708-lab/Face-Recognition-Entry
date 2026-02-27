import sqlite3
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Tuple

from config import DB_PATH


def _connect() -> sqlite3.Connection:
    Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DB_PATH)
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def init_db() -> None:
    with _connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS members (
                member_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                email TEXT,
                embedding TEXT NOT NULL,
                face_image BLOB,
                application_status TEXT NOT NULL DEFAULT 'pending',
                review_note TEXT,
                reviewed_by TEXT,
                reviewed_at TEXT,
                created_at TEXT NOT NULL
            )
            """
        )

        existing_columns = {row[1] for row in conn.execute("PRAGMA table_info(members)").fetchall()}
        if "face_image" not in existing_columns:
            conn.execute("ALTER TABLE members ADD COLUMN face_image BLOB")
        if "application_status" not in existing_columns:
            conn.execute("ALTER TABLE members ADD COLUMN application_status TEXT NOT NULL DEFAULT 'pending'")
        if "review_note" not in existing_columns:
            conn.execute("ALTER TABLE members ADD COLUMN review_note TEXT")
        if "reviewed_by" not in existing_columns:
            conn.execute("ALTER TABLE members ADD COLUMN reviewed_by TEXT")
        if "reviewed_at" not in existing_columns:
            conn.execute("ALTER TABLE members ADD COLUMN reviewed_at TEXT")
        if "created_at" not in existing_columns:
            conn.execute("ALTER TABLE members ADD COLUMN created_at TEXT")
            conn.execute("UPDATE members SET created_at = ? WHERE created_at IS NULL", (datetime.utcnow().isoformat(),))
        if "email" not in existing_columns:
            conn.execute("ALTER TABLE members ADD COLUMN email TEXT")

        conn.commit()


def create_or_update_application(member_id: str, name: str, email: str, embedding_csv: str, face_image: bytes) -> None:
    now = datetime.utcnow().isoformat()
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO members(member_id, name, email, embedding, face_image, application_status, review_note, reviewed_by, reviewed_at, created_at)
            VALUES (?, ?, ?, ?, ?, 'pending', NULL, NULL, NULL, ?)
            ON CONFLICT(member_id) DO UPDATE SET
                name = excluded.name,
                email = excluded.email,
                embedding = excluded.embedding,
                face_image = excluded.face_image,
                application_status = 'pending',
                review_note = NULL,
                reviewed_by = NULL,
                reviewed_at = NULL
            """,
            (member_id, name, email, embedding_csv, face_image, now),
        )
        conn.commit()


def get_member(member_id: str) -> Optional[Tuple[str, str, str, str]]:
    with _connect() as conn:
        row = conn.execute(
            "SELECT member_id, name, embedding, application_status FROM members WHERE member_id = ?",
            (member_id,),
        ).fetchone()
    return row


def list_applications(status: str | None = None) -> List[Tuple[str, str, Optional[str], str, Optional[str], Optional[str], Optional[str], str]]:
    query = """
        SELECT member_id, name, email, application_status, review_note, reviewed_by, reviewed_at, created_at
        FROM members
    """
    params: tuple = ()
    if status:
        query += " WHERE application_status = ?"
        params = (status,)
    query += " ORDER BY created_at DESC"

    with _connect() as conn:
        rows = conn.execute(query, params).fetchall()
    return rows


def set_application_status(member_id: str, status: str, reviewed_by: str, review_note: str = "") -> bool:
    now = datetime.utcnow().isoformat()
    with _connect() as conn:
        cursor = conn.execute(
            """
            UPDATE members
            SET application_status = ?, review_note = ?, reviewed_by = ?, reviewed_at = ?
            WHERE member_id = ?
            """,
            (status, review_note, reviewed_by, now, member_id),
        )
        conn.commit()
        return cursor.rowcount > 0


def list_approved_embeddings() -> List[Tuple[str, str, str]]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT member_id, name, embedding FROM members WHERE application_status = 'approved'"
        ).fetchall()
    return rows


def list_approved_face_images() -> List[Tuple[str, str, bytes]]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT member_id, name, face_image FROM members WHERE application_status = 'approved' AND face_image IS NOT NULL"
        ).fetchall()
    return rows


def get_member_full(member_id: str) -> Optional[Tuple[str, str, Optional[str], str, Optional[bytes], str, Optional[str], Optional[str], Optional[str], str]]:
    with _connect() as conn:
        row = conn.execute(
            """
            SELECT member_id, name, email, embedding, face_image, application_status, review_note, reviewed_by, reviewed_at, created_at
            FROM members
            WHERE member_id = ?
            """,
            (member_id,),
        ).fetchone()
    return row


def list_users_for_admin(
    status: str | None = None,
    search: str | None = None,
    limit: int = 200,
) -> List[Tuple[str, str, Optional[str], str, Optional[str], Optional[str], Optional[str], str]]:
    query = """
        SELECT member_id, name, email, application_status, review_note, reviewed_by, reviewed_at, created_at
        FROM members
    """
    conditions: List[str] = []
    params: List[object] = []

    if status:
        conditions.append("application_status = ?")
        params.append(status)

    if search:
        conditions.append("(member_id LIKE ? OR name LIKE ? OR email LIKE ?)")
        wildcard = f"%{search}%"
        params.extend([wildcard, wildcard, wildcard])

    if conditions:
        query += " WHERE " + " AND ".join(conditions)

    query += " ORDER BY created_at DESC LIMIT ?"
    params.append(max(1, min(limit, 500)))

    with _connect() as conn:
        rows = conn.execute(query, tuple(params)).fetchall()
    return rows


def update_member_admin(
    member_id: str,
    reviewed_by: str,
    name: str | None = None,
    email: str | None = None,
    application_status: str | None = None,
    review_note: str | None = None,
) -> bool:
    updates: List[str] = []
    params: List[object] = []

    if name is not None:
        updates.append("name = ?")
        params.append(name)

    if email is not None:
        updates.append("email = ?")
        params.append(email)

    if application_status is not None:
        updates.append("application_status = ?")
        params.append(application_status)
        updates.append("reviewed_by = ?")
        params.append(reviewed_by)
        updates.append("reviewed_at = ?")
        params.append(datetime.utcnow().isoformat())

    if review_note is not None:
        updates.append("review_note = ?")
        params.append(review_note)

    if not updates:
        return False

    params.append(member_id)
    sql = f"UPDATE members SET {', '.join(updates)} WHERE member_id = ?"

    with _connect() as conn:
        cursor = conn.execute(sql, tuple(params))
        conn.commit()
        return cursor.rowcount > 0


def delete_member(member_id: str) -> bool:
    with _connect() as conn:
        cursor = conn.execute("DELETE FROM members WHERE member_id = ?", (member_id,))
        conn.commit()
        return cursor.rowcount > 0
