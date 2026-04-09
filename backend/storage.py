from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any


def _utc_now_iso() -> str:
    return datetime.utcnow().replace(microsecond=0).isoformat()


def _normalize_contact(contact: str | None) -> str | None:
    if not contact:
        return None
    normalized = contact.strip()
    if not normalized:
        return None
    return normalized


def _display_name(user: dict[str, Any]) -> str:
    first_name = (user.get("first_name") or "").strip()
    last_name = (user.get("last_name") or "").strip()
    full_name = " ".join(part for part in (first_name, last_name) if part).strip()
    if full_name:
        return full_name
    username = user.get("username")
    if username:
        return f"@{username}"
    return f"user_{user.get('id')}"


def _event_scope_filter(username: str | None) -> tuple[str, tuple[Any, ...]]:
    normalized_username = f"@{username.lower()}" if username else ""
    return (
        """
        (e.owner_tg_id = ? OR EXISTS (
            SELECT 1
            FROM participants p
            WHERE p.event_id = e.id
              AND (p.tg_user_id = ? OR (? != '' AND lower(p.contact) = ?))
        ))
        """,
        (
            None,  # placeholder, substituted by caller with user_id
            None,  # placeholder, substituted by caller with user_id
            normalized_username,
            normalized_username,
        ),
    )


class Storage:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    @contextmanager
    def _connect(self):
        connection = sqlite3.connect(self.db_path, check_same_thread=False)
        connection.row_factory = sqlite3.Row
        try:
            yield connection
            connection.commit()
        finally:
            connection.close()

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                PRAGMA foreign_keys = ON;

                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    event_date TEXT,
                    owner_tg_id INTEGER NOT NULL,
                    owner_name TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS participants (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_id INTEGER NOT NULL,
                    name TEXT NOT NULL,
                    contact TEXT,
                    tg_user_id INTEGER,
                    is_owner INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(event_id) REFERENCES events(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS receipts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_id INTEGER NOT NULL,
                    store_name TEXT,
                    total_sum REAL,
                    receipt_datetime TEXT,
                    qr_payload TEXT,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(event_id) REFERENCES events(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS receipt_items (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    receipt_id INTEGER NOT NULL,
                    position_index INTEGER NOT NULL,
                    name TEXT NOT NULL,
                    quantity REAL,
                    price REAL,
                    sum REAL NOT NULL,
                    FOREIGN KEY(receipt_id) REFERENCES receipts(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS item_assignments (
                    item_id INTEGER NOT NULL,
                    participant_id INTEGER NOT NULL,
                    assigned_at TEXT NOT NULL,
                    PRIMARY KEY(item_id, participant_id),
                    FOREIGN KEY(item_id) REFERENCES receipt_items(id) ON DELETE CASCADE,
                    FOREIGN KEY(participant_id) REFERENCES participants(id) ON DELETE CASCADE
                );
                """
            )

    def create_event(
        self,
        *,
        owner: dict[str, Any],
        title: str,
        event_date: str | None,
        participants: list[dict[str, Any]],
    ) -> int:
        title = title.strip()
        if not title:
            raise ValueError("Название события не должно быть пустым.")

        owner_id = int(owner["id"])
        owner_name = _display_name(owner)
        now_iso = _utc_now_iso()

        with self._connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO events (title, event_date, owner_tg_id, owner_name, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (title, event_date, owner_id, owner_name, now_iso),
            )
            event_id = int(cursor.lastrowid)

            conn.execute(
                """
                INSERT INTO participants (event_id, name, contact, tg_user_id, is_owner, created_at)
                VALUES (?, ?, ?, ?, 1, ?)
                """,
                (
                    event_id,
                    owner_name,
                    f"@{owner.get('username')}" if owner.get("username") else None,
                    owner_id,
                    now_iso,
                ),
            )

            for participant in participants:
                name = (participant.get("name") or "").strip()
                if not name:
                    continue
                contact = _normalize_contact(participant.get("contact"))
                tg_user_id = participant.get("tg_user_id")
                conn.execute(
                    """
                    INSERT INTO participants (event_id, name, contact, tg_user_id, is_owner, created_at)
                    VALUES (?, ?, ?, ?, 0, ?)
                    """,
                    (
                        event_id,
                        name,
                        contact,
                        int(tg_user_id) if tg_user_id is not None else None,
                        now_iso,
                    ),
                )

        return event_id

    def add_participant(
        self,
        *,
        event_id: int,
        name: str,
        contact: str | None,
        tg_user_id: int | None = None,
    ) -> int:
        name = name.strip()
        if not name:
            raise ValueError("Имя участника не должно быть пустым.")

        with self._connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO participants (event_id, name, contact, tg_user_id, is_owner, created_at)
                VALUES (?, ?, ?, ?, 0, ?)
                """,
                (
                    event_id,
                    name,
                    _normalize_contact(contact),
                    tg_user_id,
                    _utc_now_iso(),
                ),
            )
            return int(cursor.lastrowid)

    def remove_participant(self, event_id: int, participant_id: int) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                DELETE FROM participants
                WHERE id = ? AND event_id = ? AND is_owner = 0
                """,
                (participant_id, event_id),
            )

    def insert_receipt(
        self,
        *,
        event_id: int,
        store_name: str | None,
        total_sum: float | None,
        receipt_datetime: str | None,
        qr_payload: str | None,
        items: list[dict[str, Any]],
    ) -> int:
        with self._connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO receipts (event_id, store_name, total_sum, receipt_datetime, qr_payload, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    event_id,
                    store_name,
                    total_sum,
                    receipt_datetime,
                    qr_payload,
                    _utc_now_iso(),
                ),
            )
            receipt_id = int(cursor.lastrowid)

            for index, item in enumerate(items, start=1):
                conn.execute(
                    """
                    INSERT INTO receipt_items (receipt_id, position_index, name, quantity, price, sum)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        receipt_id,
                        index,
                        str(item.get("name") or f"Позиция {index}"),
                        float(item.get("quantity") or 1),
                        float(item.get("price")) if item.get("price") is not None else None,
                        float(item.get("sum") or 0),
                    ),
                )
        return receipt_id

    def set_item_assignments(
        self,
        *,
        event_id: int,
        item_id: int,
        participant_ids: list[int],
    ) -> None:
        with self._connect() as conn:
            item_row = conn.execute(
                """
                SELECT i.id
                FROM receipt_items i
                JOIN receipts r ON r.id = i.receipt_id
                WHERE i.id = ? AND r.event_id = ?
                """,
                (item_id, event_id),
            ).fetchone()
            if item_row is None:
                raise ValueError("Позиция не найдена в этом событии.")

            valid_participant_ids = {
                int(row["id"])
                for row in conn.execute(
                    "SELECT id FROM participants WHERE event_id = ?",
                    (event_id,),
                ).fetchall()
            }

            invalid = [pid for pid in participant_ids if pid not in valid_participant_ids]
            if invalid:
                raise ValueError("В назначении есть участники не из этого события.")

            conn.execute(
                "DELETE FROM item_assignments WHERE item_id = ?",
                (item_id,),
            )
            for participant_id in sorted(set(participant_ids)):
                conn.execute(
                    """
                    INSERT INTO item_assignments (item_id, participant_id, assigned_at)
                    VALUES (?, ?, ?)
                    """,
                    (item_id, participant_id, _utc_now_iso()),
                )

    def get_event_detail(self, event_id: int) -> dict[str, Any] | None:
        with self._connect() as conn:
            event = conn.execute(
                """
                SELECT id, title, event_date, owner_tg_id, owner_name, created_at
                FROM events
                WHERE id = ?
                """,
                (event_id,),
            ).fetchone()
            if event is None:
                return None

            participants = [
                {
                    "id": int(row["id"]),
                    "name": row["name"],
                    "contact": row["contact"],
                    "tg_user_id": row["tg_user_id"],
                    "is_owner": bool(row["is_owner"]),
                }
                for row in conn.execute(
                    """
                    SELECT id, name, contact, tg_user_id, is_owner
                    FROM participants
                    WHERE event_id = ?
                    ORDER BY is_owner DESC, id ASC
                    """,
                    (event_id,),
                ).fetchall()
            ]

            latest_receipt = conn.execute(
                """
                SELECT id, store_name, total_sum, receipt_datetime, qr_payload, created_at
                FROM receipts
                WHERE event_id = ?
                ORDER BY id DESC
                LIMIT 1
                """,
                (event_id,),
            ).fetchone()

            receipt_payload: dict[str, Any] | None = None
            items_payload: list[dict[str, Any]] = []
            if latest_receipt is not None:
                receipt_id = int(latest_receipt["id"])
                assignment_rows = conn.execute(
                    """
                    SELECT item_id, participant_id
                    FROM item_assignments
                    WHERE item_id IN (
                        SELECT id
                        FROM receipt_items
                        WHERE receipt_id = ?
                    )
                    """,
                    (receipt_id,),
                ).fetchall()
                assignment_map: dict[int, list[int]] = {}
                for row in assignment_rows:
                    assignment_map.setdefault(int(row["item_id"]), []).append(
                        int(row["participant_id"])
                    )

                items_payload = [
                    {
                        "id": int(item["id"]),
                        "name": item["name"],
                        "quantity": item["quantity"],
                        "price": item["price"],
                        "sum": item["sum"],
                        "assigned_participant_ids": assignment_map.get(int(item["id"]), []),
                    }
                    for item in conn.execute(
                        """
                        SELECT id, name, quantity, price, sum
                        FROM receipt_items
                        WHERE receipt_id = ?
                        ORDER BY position_index ASC, id ASC
                        """,
                        (receipt_id,),
                    ).fetchall()
                ]

                receipt_payload = {
                    "id": receipt_id,
                    "store_name": latest_receipt["store_name"],
                    "total_sum": latest_receipt["total_sum"],
                    "receipt_datetime": latest_receipt["receipt_datetime"],
                    "qr_payload": latest_receipt["qr_payload"],
                    "created_at": latest_receipt["created_at"],
                    "items": items_payload,
                }

            participants_count = len(participants)
            total_sum = float(receipt_payload["total_sum"] or 0) if receipt_payload else 0.0
            selected_items_sum = 0.0
            if receipt_payload:
                selected_items_sum = sum(
                    float(item["sum"] or 0)
                    for item in items_payload
                    if item["assigned_participant_ids"]
                )

            summary = {
                "total_sum": round(total_sum, 2),
                "selected_sum": round(selected_items_sum, 2),
                "per_person": round(total_sum / participants_count, 2)
                if participants_count > 0
                else 0.0,
            }

            return {
                "id": int(event["id"]),
                "title": event["title"],
                "event_date": event["event_date"],
                "owner_tg_id": int(event["owner_tg_id"]),
                "owner_name": event["owner_name"],
                "participants": participants,
                "receipt": receipt_payload,
                "summary": summary,
                "created_at": event["created_at"],
            }

    def user_can_access_event(
        self, *, event_id: int, user_id: int, username: str | None
    ) -> bool:
        normalized_username = f"@{username.lower()}" if username else ""
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT 1
                FROM events e
                WHERE e.id = ?
                  AND (
                    e.owner_tg_id = ?
                    OR EXISTS (
                        SELECT 1
                        FROM participants p
                        WHERE p.event_id = e.id
                          AND (p.tg_user_id = ? OR (? != '' AND lower(p.contact) = ?))
                    )
                  )
                """,
                (event_id, user_id, user_id, normalized_username, normalized_username),
            ).fetchone()
            return row is not None

    def list_user_events(self, *, user_id: int, username: str | None) -> list[dict[str, Any]]:
        normalized_username = f"@{username.lower()}" if username else ""
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT e.id, e.title, e.event_date, e.created_at
                FROM events e
                WHERE (
                    e.owner_tg_id = ?
                    OR EXISTS (
                        SELECT 1
                        FROM participants p
                        WHERE p.event_id = e.id
                          AND (p.tg_user_id = ? OR (? != '' AND lower(p.contact) = ?))
                    )
                )
                ORDER BY e.id DESC
                """,
                (user_id, user_id, normalized_username, normalized_username),
            ).fetchall()

            events: list[dict[str, Any]] = []
            for row in rows:
                event_id = int(row["id"])
                participants_count = conn.execute(
                    "SELECT COUNT(*) AS count FROM participants WHERE event_id = ?",
                    (event_id,),
                ).fetchone()["count"]
                latest_receipt = conn.execute(
                    """
                    SELECT total_sum
                    FROM receipts
                    WHERE event_id = ?
                    ORDER BY id DESC
                    LIMIT 1
                    """,
                    (event_id,),
                ).fetchone()
                total_sum = float(latest_receipt["total_sum"] or 0) if latest_receipt else 0.0
                events.append(
                    {
                        "id": event_id,
                        "title": row["title"],
                        "event_date": row["event_date"],
                        "participants_count": int(participants_count),
                        "total_sum": round(total_sum, 2),
                        "per_person": round(total_sum / participants_count, 2)
                        if participants_count
                        else 0.0,
                    }
                )
            return events

    def list_recent_receipts(
        self, *, user_id: int, username: str | None, limit: int = 3
    ) -> list[dict[str, Any]]:
        normalized_username = f"@{username.lower()}" if username else ""
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT r.id, r.event_id, r.store_name, r.total_sum, r.receipt_datetime, e.title AS event_title
                FROM receipts r
                JOIN events e ON e.id = r.event_id
                WHERE (
                    e.owner_tg_id = ?
                    OR EXISTS (
                        SELECT 1
                        FROM participants p
                        WHERE p.event_id = e.id
                          AND (p.tg_user_id = ? OR (? != '' AND lower(p.contact) = ?))
                    )
                )
                ORDER BY r.id DESC
                LIMIT ?
                """,
                (user_id, user_id, normalized_username, normalized_username, limit),
            ).fetchall()
            return [
                {
                    "id": int(row["id"]),
                    "event_id": int(row["event_id"]),
                    "event_title": row["event_title"],
                    "store_name": row["store_name"] or "Магазин",
                    "total_sum": float(row["total_sum"] or 0),
                    "receipt_datetime": row["receipt_datetime"],
                }
                for row in rows
            ]

    def calculate_event(self, event_id: int) -> dict[str, Any]:
        detail = self.get_event_detail(event_id)
        if detail is None:
            raise ValueError("Событие не найдено.")
        if detail["receipt"] is None:
            raise ValueError("В событии ещё нет загруженного чека.")

        participants = detail["participants"]
        items = detail["receipt"]["items"]
        totals = {int(participant["id"]): 0.0 for participant in participants}
        unassigned_sum = 0.0
        unassigned_count = 0

        for item in items:
            item_sum = float(item.get("sum") or 0)
            assigned_ids = [int(pid) for pid in item.get("assigned_participant_ids") or []]
            if not assigned_ids:
                unassigned_sum += item_sum
                unassigned_count += 1
                continue

            share = item_sum / len(assigned_ids)
            for participant_id in assigned_ids:
                totals[participant_id] += share

        result_rows = [
            {
                "participant_id": int(participant["id"]),
                "name": participant["name"],
                "amount": round(totals.get(int(participant["id"]), 0.0), 2),
                "is_owner": bool(participant["is_owner"]),
            }
            for participant in participants
        ]
        result_rows.sort(key=lambda row: row["amount"], reverse=True)

        return {
            "event_id": event_id,
            "event_title": detail["title"],
            "total_sum": round(float(detail["summary"]["total_sum"]), 2),
            "distributed_sum": round(sum(row["amount"] for row in result_rows), 2),
            "unassigned_sum": round(unassigned_sum, 2),
            "unassigned_items_count": unassigned_count,
            "results": result_rows,
        }

    def get_profile_stats(self, *, user_id: int, username: str | None) -> dict[str, Any]:
        events = self.list_user_events(user_id=user_id, username=username)
        receipts = self.list_recent_receipts(user_id=user_id, username=username, limit=500)
        unique_participants = set()
        with self._connect() as conn:
            for event in events:
                rows = conn.execute(
                    "SELECT name, contact FROM participants WHERE event_id = ?",
                    (event["id"],),
                ).fetchall()
                for row in rows:
                    unique_participants.add((row["name"], row["contact"]))

        return {
            "events_count": len(events),
            "participants_count": len(unique_participants),
            "total_split_sum": round(sum(item["total_sum"] for item in receipts), 2),
        }

