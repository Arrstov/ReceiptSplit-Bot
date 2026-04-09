from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
DB_PATH = DATA_DIR / "mvp.sqlite3"


def _utc_now_iso() -> str:
    return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


def _display_name_from_profile(profile: dict[str, Any]) -> str:
    if profile.get("username"):
        return f"@{profile['username']}"

    parts = [profile.get("first_name") or "", profile.get("last_name") or ""]
    full_name = " ".join(part for part in parts if part).strip()
    if full_name:
        return full_name

    return f"User {profile['user_id']}"


def _parse_money_to_cents(value: Any) -> int:
    if value is None:
        return 0

    if isinstance(value, int):
        return value

    text = str(value).strip().replace(",", ".")
    if not text:
        return 0

    try:
        amount = float(text)
    except ValueError:
        return 0

    return int(round(amount * 100))


def _format_cents(value: int) -> str:
    return f"{value / 100:.2f}"


def _connect() -> sqlite3.Connection:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def init_db() -> None:
    with _connect() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS profiles (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                last_name TEXT,
                phone TEXT,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                event_date TEXT,
                owner_user_id INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY(owner_user_id) REFERENCES profiles(user_id)
            );

            CREATE TABLE IF NOT EXISTS event_members (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_id INTEGER NOT NULL,
                user_id INTEGER,
                display_name TEXT NOT NULL,
                username TEXT,
                phone TEXT,
                is_admin INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                UNIQUE(event_id, user_id),
                FOREIGN KEY(event_id) REFERENCES events(id) ON DELETE CASCADE,
                FOREIGN KEY(user_id) REFERENCES profiles(user_id)
            );

            CREATE TABLE IF NOT EXISTS receipts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_id INTEGER NOT NULL,
                uploaded_by_user_id INTEGER NOT NULL,
                store_name TEXT,
                total_cents INTEGER NOT NULL DEFAULT 0,
                receipt_timestamp TEXT,
                raw_qr TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY(event_id) REFERENCES events(id) ON DELETE CASCADE,
                FOREIGN KEY(uploaded_by_user_id) REFERENCES profiles(user_id)
            );

            CREATE TABLE IF NOT EXISTS receipt_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                receipt_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                quantity REAL NOT NULL DEFAULT 1,
                price_cents INTEGER NOT NULL DEFAULT 0,
                sum_cents INTEGER NOT NULL DEFAULT 0,
                FOREIGN KEY(receipt_id) REFERENCES receipts(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS item_assignments (
                item_id INTEGER NOT NULL,
                member_id INTEGER NOT NULL,
                assigned_by_user_id INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                PRIMARY KEY(item_id, member_id),
                FOREIGN KEY(item_id) REFERENCES receipt_items(id) ON DELETE CASCADE,
                FOREIGN KEY(member_id) REFERENCES event_members(id) ON DELETE CASCADE,
                FOREIGN KEY(assigned_by_user_id) REFERENCES profiles(user_id)
            );
            """
        )


def upsert_profile(user: dict[str, Any]) -> dict[str, Any]:
    profile = {
        "user_id": int(user["id"]),
        "username": user.get("username"),
        "first_name": user.get("first_name"),
        "last_name": user.get("last_name"),
        "phone": user.get("phone_number") or user.get("phone"),
    }

    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO profiles (user_id, username, first_name, last_name, phone, updated_at)
            VALUES (:user_id, :username, :first_name, :last_name, :phone, :updated_at)
            ON CONFLICT(user_id) DO UPDATE SET
                username = excluded.username,
                first_name = excluded.first_name,
                last_name = excluded.last_name,
                phone = COALESCE(excluded.phone, profiles.phone),
                updated_at = excluded.updated_at
            """,
            {
                **profile,
                "updated_at": _utc_now_iso(),
            },
        )

    profile["display_name"] = _display_name_from_profile(profile)
    return profile


def get_profile(user_id: int) -> dict[str, Any] | None:
    with _connect() as conn:
        row = conn.execute(
            """
            SELECT user_id, username, first_name, last_name, phone
            FROM profiles
            WHERE user_id = ?
            """,
            (user_id,),
        ).fetchone()

    if row is None:
        return None

    profile = dict(row)
    profile["display_name"] = _display_name_from_profile(profile)
    return profile


def list_contacts_for_user(user_id: int, *, limit: int = 30) -> list[dict[str, Any]]:
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT DISTINCT p.user_id, p.username, p.first_name, p.last_name, p.phone, p.updated_at
            FROM profiles p
            WHERE p.user_id != ?
            ORDER BY p.updated_at DESC
            LIMIT ?
            """,
            (user_id, limit),
        ).fetchall()

    contacts = []
    for row in rows:
        contact = dict(row)
        contact["display_name"] = _display_name_from_profile(contact)
        contacts.append(contact)
    return contacts


def create_event(
    *,
    owner_user_id: int,
    title: str,
    event_date: str | None,
    participants: list[dict[str, Any]],
) -> dict[str, Any]:
    created_at = _utc_now_iso()

    with _connect() as conn:
        owner = conn.execute(
            """
            SELECT user_id, username, first_name, last_name, phone
            FROM profiles
            WHERE user_id = ?
            """,
            (owner_user_id,),
        ).fetchone()
        if owner is None:
            raise ValueError("Owner profile is not found.")

        owner_data = dict(owner)
        owner_display_name = _display_name_from_profile(owner_data)

        cursor = conn.execute(
            """
            INSERT INTO events (title, event_date, owner_user_id, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (title.strip(), event_date, owner_user_id, created_at),
        )
        event_id = int(cursor.lastrowid)

        conn.execute(
            """
            INSERT INTO event_members (
                event_id, user_id, display_name, username, phone, is_admin, created_at
            ) VALUES (?, ?, ?, ?, ?, 1, ?)
            """,
            (
                event_id,
                owner_user_id,
                owner_display_name,
                owner_data.get("username"),
                owner_data.get("phone"),
                created_at,
            ),
        )

        for participant in participants:
            participant_user_id = participant.get("user_id")
            if participant_user_id is not None and int(participant_user_id) == owner_user_id:
                continue

            if participant_user_id is not None:
                contact = conn.execute(
                    """
                    SELECT user_id, username, first_name, last_name, phone
                    FROM profiles
                    WHERE user_id = ?
                    """,
                    (int(participant_user_id),),
                ).fetchone()
                if contact is None:
                    continue

                contact_data = dict(contact)
                conn.execute(
                    """
                    INSERT OR IGNORE INTO event_members (
                        event_id, user_id, display_name, username, phone, is_admin, created_at
                    ) VALUES (?, ?, ?, ?, ?, 0, ?)
                    """,
                    (
                        event_id,
                        int(contact_data["user_id"]),
                        _display_name_from_profile(contact_data),
                        contact_data.get("username"),
                        contact_data.get("phone"),
                        created_at,
                    ),
                )
                continue

            name = str(participant.get("display_name") or "").strip()
            if not name:
                continue

            conn.execute(
                """
                INSERT INTO event_members (
                    event_id, user_id, display_name, username, phone, is_admin, created_at
                ) VALUES (?, NULL, ?, ?, ?, 0, ?)
                """,
                (
                    event_id,
                    name,
                    participant.get("username"),
                    participant.get("phone"),
                    created_at,
                ),
            )

    event = get_event_for_user(event_id=event_id, user_id=owner_user_id)
    if event is None:
        raise ValueError("Event creation failed.")
    return event


def _is_member(conn: sqlite3.Connection, *, event_id: int, user_id: int) -> bool:
    row = conn.execute(
        """
        SELECT 1
        FROM event_members
        WHERE event_id = ? AND user_id = ?
        """,
        (event_id, user_id),
    ).fetchone()
    return row is not None


def _is_admin(conn: sqlite3.Connection, *, event_id: int, user_id: int) -> bool:
    row = conn.execute(
        """
        SELECT is_admin
        FROM event_members
        WHERE event_id = ? AND user_id = ?
        """,
        (event_id, user_id),
    ).fetchone()
    return bool(row and row["is_admin"])


def list_events_for_user(user_id: int, *, limit: int | None = None) -> list[dict[str, Any]]:
    query = (
        """
        SELECT
            e.id,
            e.title,
            e.event_date,
            e.owner_user_id,
            e.created_at,
            COUNT(DISTINCT m.id) AS participants_count,
            COALESCE(SUM(r.total_cents), 0) AS total_cents,
            MAX(r.created_at) AS last_receipt_at
        FROM events e
        JOIN event_members em ON em.event_id = e.id
        LEFT JOIN event_members m ON m.event_id = e.id
        LEFT JOIN receipts r ON r.event_id = e.id
        WHERE em.user_id = ?
        GROUP BY e.id
        ORDER BY COALESCE(MAX(r.created_at), e.created_at) DESC
        """
    )

    params: list[Any] = [user_id]
    if limit is not None:
        query += " LIMIT ?"
        params.append(limit)

    with _connect() as conn:
        rows = conn.execute(query, tuple(params)).fetchall()

    events: list[dict[str, Any]] = []
    for row in rows:
        total_cents = int(row["total_cents"] or 0)
        participants_count = int(row["participants_count"] or 0)
        events.append(
            {
                "id": int(row["id"]),
                "title": row["title"],
                "event_date": row["event_date"],
                "owner_user_id": int(row["owner_user_id"]),
                "created_at": row["created_at"],
                "last_receipt_at": row["last_receipt_at"],
                "participants_count": participants_count,
                "total_amount": _format_cents(total_cents),
                "per_person_amount": _format_cents(total_cents // participants_count if participants_count else 0),
            }
        )

    return events


def list_recent_receipts_for_user(user_id: int, *, limit: int = 3) -> list[dict[str, Any]]:
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT
                r.id,
                r.event_id,
                r.store_name,
                r.total_cents,
                r.created_at,
                e.title AS event_title
            FROM receipts r
            JOIN events e ON e.id = r.event_id
            JOIN event_members em ON em.event_id = e.id
            WHERE em.user_id = ?
            ORDER BY r.created_at DESC
            LIMIT ?
            """,
            (user_id, limit),
        ).fetchall()

    receipts: list[dict[str, Any]] = []
    for row in rows:
        receipts.append(
            {
                "id": int(row["id"]),
                "event_id": int(row["event_id"]),
                "event_title": row["event_title"],
                "store_name": row["store_name"] or "Без названия",
                "total_amount": _format_cents(int(row["total_cents"] or 0)),
                "created_at": row["created_at"],
            }
        )
    return receipts


def get_dashboard(user_id: int) -> dict[str, Any]:
    return {
        "events": list_events_for_user(user_id, limit=3),
        "receipts": list_recent_receipts_for_user(user_id, limit=3),
    }


def get_event_for_user(event_id: int, user_id: int) -> dict[str, Any] | None:
    with _connect() as conn:
        if not _is_member(conn, event_id=event_id, user_id=user_id):
            return None

        event_row = conn.execute(
            """
            SELECT id, title, event_date, owner_user_id, created_at
            FROM events
            WHERE id = ?
            """,
            (event_id,),
        ).fetchone()
        if event_row is None:
            return None

        participants_rows = conn.execute(
            """
            SELECT id, user_id, display_name, username, phone, is_admin
            FROM event_members
            WHERE event_id = ?
            ORDER BY is_admin DESC, display_name ASC
            """,
            (event_id,),
        ).fetchall()

        receipts_rows = conn.execute(
            """
            SELECT id, store_name, total_cents, created_at
            FROM receipts
            WHERE event_id = ?
            ORDER BY created_at DESC
            """,
            (event_id,),
        ).fetchall()

        items_rows = conn.execute(
            """
            SELECT
                i.id,
                i.receipt_id,
                i.name,
                i.quantity,
                i.price_cents,
                i.sum_cents,
                r.store_name
            FROM receipt_items i
            JOIN receipts r ON r.id = i.receipt_id
            WHERE r.event_id = ?
            ORDER BY i.id ASC
            """,
            (event_id,),
        ).fetchall()

        assignments_rows = conn.execute(
            """
            SELECT ia.item_id, ia.member_id
            FROM item_assignments ia
            JOIN receipt_items i ON i.id = ia.item_id
            JOIN receipts r ON r.id = i.receipt_id
            WHERE r.event_id = ?
            """,
            (event_id,),
        ).fetchall()

    participants: list[dict[str, Any]] = []
    me_member_id: int | None = None
    owner_user_id = int(event_row["owner_user_id"])
    for row in participants_rows:
        member = {
            "id": int(row["id"]),
            "user_id": int(row["user_id"]) if row["user_id"] is not None else None,
            "display_name": row["display_name"],
            "username": row["username"],
            "phone": row["phone"],
            "is_admin": bool(row["is_admin"]),
            "is_owner": bool(row["user_id"] == owner_user_id),
            "is_me": bool(row["user_id"] == user_id),
        }
        if member["is_me"]:
            me_member_id = member["id"]
        participants.append(member)

    assignments_by_item: dict[int, set[int]] = {}
    for row in assignments_rows:
        item_id = int(row["item_id"])
        member_id = int(row["member_id"])
        assignments_by_item.setdefault(item_id, set()).add(member_id)

    items: list[dict[str, Any]] = []
    selected_cents = 0
    for row in items_rows:
        item_id = int(row["id"])
        assigned_member_ids = sorted(assignments_by_item.get(item_id, set()))
        sum_cents = int(row["sum_cents"] or 0)
        if assigned_member_ids:
            selected_cents += sum_cents

        items.append(
            {
                "id": item_id,
                "receipt_id": int(row["receipt_id"]),
                "store_name": row["store_name"] or "Без названия",
                "name": row["name"],
                "quantity": float(row["quantity"] or 1),
                "price": _format_cents(int(row["price_cents"] or 0)),
                "sum": _format_cents(sum_cents),
                "assigned_member_ids": assigned_member_ids,
                "assigned_count": len(assigned_member_ids),
                "is_mine": bool(me_member_id and me_member_id in assigned_member_ids),
            }
        )

    total_cents = sum(int(row["total_cents"] or 0) for row in receipts_rows)
    participants_count = len(participants)

    receipts: list[dict[str, Any]] = []
    for row in receipts_rows:
        receipts.append(
            {
                "id": int(row["id"]),
                "store_name": row["store_name"] or "Без названия",
                "total_amount": _format_cents(int(row["total_cents"] or 0)),
                "created_at": row["created_at"],
            }
        )

    return {
        "event": {
            "id": int(event_row["id"]),
            "title": event_row["title"],
            "event_date": event_row["event_date"],
            "owner_user_id": owner_user_id,
            "created_at": event_row["created_at"],
        },
        "participants": participants,
        "receipts": receipts,
        "items": items,
        "summary": {
            "total_amount": _format_cents(total_cents),
            "selected_amount": _format_cents(selected_cents),
            "per_person_amount": _format_cents(total_cents // participants_count if participants_count else 0),
            "participants_count": participants_count,
        },
        "permissions": {
            "is_admin": any(participant["is_me"] and participant["is_admin"] for participant in participants),
            "me_member_id": me_member_id,
        },
    }


def add_receipt_to_event(
    *,
    event_id: int,
    user_id: int,
    store_name: str | None,
    total_amount: Any,
    receipt_timestamp: str | None,
    raw_qr: str | None,
    items: list[dict[str, Any]],
) -> dict[str, Any]:
    created_at = _utc_now_iso()

    with _connect() as conn:
        if not _is_member(conn, event_id=event_id, user_id=user_id):
            raise PermissionError("User is not participant of the event.")

        cursor = conn.execute(
            """
            INSERT INTO receipts (
                event_id,
                uploaded_by_user_id,
                store_name,
                total_cents,
                receipt_timestamp,
                raw_qr,
                created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event_id,
                user_id,
                store_name,
                _parse_money_to_cents(total_amount),
                receipt_timestamp,
                raw_qr,
                created_at,
            ),
        )
        receipt_id = int(cursor.lastrowid)

        inserted_items = 0
        for item in items:
            name = str(item.get("name") or "Без названия").strip()
            if not name:
                continue
            quantity = float(item.get("quantity") or 1)
            price_cents = _parse_money_to_cents(item.get("price"))
            sum_cents = _parse_money_to_cents(item.get("sum"))
            if sum_cents == 0 and price_cents and quantity:
                sum_cents = int(round(price_cents * quantity))

            conn.execute(
                """
                INSERT INTO receipt_items (
                    receipt_id,
                    name,
                    quantity,
                    price_cents,
                    sum_cents
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (receipt_id, name, quantity, price_cents, sum_cents),
            )
            inserted_items += 1

    return {
        "receipt_id": receipt_id,
        "items_inserted": inserted_items,
    }


def toggle_my_item_assignment(*, event_id: int, item_id: int, user_id: int) -> bool:
    with _connect() as conn:
        member_row = conn.execute(
            """
            SELECT id
            FROM event_members
            WHERE event_id = ? AND user_id = ?
            """,
            (event_id, user_id),
        ).fetchone()
        if member_row is None:
            raise PermissionError("User is not participant of the event.")

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
            raise ValueError("Item not found.")

        member_id = int(member_row["id"])
        existing = conn.execute(
            """
            SELECT 1
            FROM item_assignments
            WHERE item_id = ? AND member_id = ?
            """,
            (item_id, member_id),
        ).fetchone()

        if existing:
            conn.execute(
                """
                DELETE FROM item_assignments
                WHERE item_id = ? AND member_id = ?
                """,
                (item_id, member_id),
            )
            return False

        conn.execute(
            """
            INSERT INTO item_assignments (item_id, member_id, assigned_by_user_id, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (item_id, member_id, user_id, _utc_now_iso()),
        )
        return True


def set_item_assignment(*, event_id: int, item_id: int, member_id: int, user_id: int, assigned: bool) -> bool:
    with _connect() as conn:
        if not _is_admin(conn, event_id=event_id, user_id=user_id):
            raise PermissionError("User is not admin of the event.")

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
            raise ValueError("Item not found.")

        member_row = conn.execute(
            """
            SELECT id
            FROM event_members
            WHERE id = ? AND event_id = ?
            """,
            (member_id, event_id),
        ).fetchone()
        if member_row is None:
            raise ValueError("Participant not found.")

        if assigned:
            conn.execute(
                """
                INSERT OR IGNORE INTO item_assignments (item_id, member_id, assigned_by_user_id, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (item_id, member_id, user_id, _utc_now_iso()),
            )
            return True

        conn.execute(
            """
            DELETE FROM item_assignments
            WHERE item_id = ? AND member_id = ?
            """,
            (item_id, member_id),
        )
        return False


def calculate_event(event_id: int, user_id: int) -> dict[str, Any]:
    with _connect() as conn:
        if not _is_member(conn, event_id=event_id, user_id=user_id):
            raise PermissionError("User is not participant of the event.")

        event_row = conn.execute(
            """
            SELECT id, title, owner_user_id
            FROM events
            WHERE id = ?
            """,
            (event_id,),
        ).fetchone()
        if event_row is None:
            raise ValueError("Event not found.")

        participants_rows = conn.execute(
            """
            SELECT id, user_id, display_name, is_admin
            FROM event_members
            WHERE event_id = ?
            ORDER BY is_admin DESC, display_name ASC
            """,
            (event_id,),
        ).fetchall()

        items_rows = conn.execute(
            """
            SELECT i.id, i.sum_cents
            FROM receipt_items i
            JOIN receipts r ON r.id = i.receipt_id
            WHERE r.event_id = ?
            """,
            (event_id,),
        ).fetchall()

        assignments_rows = conn.execute(
            """
            SELECT ia.item_id, ia.member_id
            FROM item_assignments ia
            JOIN receipt_items i ON i.id = ia.item_id
            JOIN receipts r ON r.id = i.receipt_id
            WHERE r.event_id = ?
            """,
            (event_id,),
        ).fetchall()

    totals_by_member: dict[int, int] = {int(row["id"]): 0 for row in participants_rows}
    assignments_by_item: dict[int, list[int]] = {}
    for row in assignments_rows:
        assignments_by_item.setdefault(int(row["item_id"]), []).append(int(row["member_id"]))

    total_receipt_cents = 0
    selected_cents = 0
    for row in items_rows:
        item_id = int(row["id"])
        item_sum_cents = int(row["sum_cents"] or 0)
        total_receipt_cents += item_sum_cents
        member_ids = assignments_by_item.get(item_id, [])
        if not member_ids:
            continue

        selected_cents += item_sum_cents
        share = item_sum_cents // len(member_ids)
        remainder = item_sum_cents % len(member_ids)
        for index, member_id in enumerate(member_ids):
            totals_by_member[member_id] += share + (1 if index < remainder else 0)

    participants: list[dict[str, Any]] = []
    for row in participants_rows:
        member_id = int(row["id"])
        amount_cents = totals_by_member.get(member_id, 0)
        participants.append(
            {
                "member_id": member_id,
                "user_id": int(row["user_id"]) if row["user_id"] is not None else None,
                "display_name": row["display_name"],
                "is_admin": bool(row["is_admin"]),
                "is_owner": bool(row["user_id"] == event_row["owner_user_id"]),
                "amount": _format_cents(amount_cents),
                "amount_cents": amount_cents,
            }
        )

    participants.sort(key=lambda participant: participant["amount_cents"], reverse=True)

    return {
        "event": {
            "id": int(event_row["id"]),
            "title": event_row["title"],
            "owner_user_id": int(event_row["owner_user_id"]),
        },
        "summary": {
            "total_items_amount": _format_cents(total_receipt_cents),
            "selected_items_amount": _format_cents(selected_cents),
            "participants_count": len(participants),
        },
        "participants": participants,
    }


def get_profile_stats(user_id: int) -> dict[str, Any]:
    with _connect() as conn:
        events_count_row = conn.execute(
            """
            SELECT COUNT(DISTINCT e.id) AS count
            FROM events e
            JOIN event_members em ON em.event_id = e.id
            WHERE em.user_id = ?
            """,
            (user_id,),
        ).fetchone()

        participants_count_row = conn.execute(
            """
            SELECT COUNT(DISTINCT m.id) AS count
            FROM events e
            JOIN event_members em ON em.event_id = e.id
            JOIN event_members m ON m.event_id = e.id
            WHERE em.user_id = ?
            """,
            (user_id,),
        ).fetchone()

        total_row = conn.execute(
            """
            SELECT COALESCE(SUM(r.total_cents), 0) AS total
            FROM receipts r
            JOIN event_members em ON em.event_id = r.event_id
            WHERE em.user_id = ?
            """,
            (user_id,),
        ).fetchone()

    return {
        "events_count": int(events_count_row["count"] or 0),
        "participants_count": int(participants_count_row["count"] or 0),
        "total_split_amount": _format_cents(int(total_row["total"] or 0)),
    }
