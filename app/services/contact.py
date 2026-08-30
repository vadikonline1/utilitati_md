"""Contact form messages submitted from the public /contact page.

Messages are stored locally so an admin can review them from /admin. A message
is only delivered by email when SMTP is configured (recipient = smtp_from).
"""

from __future__ import annotations

from typing import Any

from ..db import _conn


def save_contact_message(name: str, email: str, subject: str, message: str) -> int:
    with _conn() as conn:
        cur = conn.execute(
            """INSERT INTO contact_messages (name, email, subject, message)
               VALUES (?, ?, ?, ?)""",
            (name.strip(), email.strip(), subject.strip(), message.strip()),
        )
        return cur.lastrowid


def list_contact_messages(limit: int = 200) -> list[dict[str, Any]]:
    with _conn() as conn:
        rows = conn.execute(
            "SELECT * FROM contact_messages ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [dict(r) for r in rows]


def delete_contact_message(message_id: int) -> bool:
    with _conn() as conn:
        cur = conn.execute(
            "DELETE FROM contact_messages WHERE id = ?", (message_id,)
        )
        return cur.rowcount > 0