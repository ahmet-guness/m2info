import json
import logging
import sqlite3
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

logger = logging.getLogger("Metin2Bot")

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
DB_PATH = DATA_DIR / "metin2.db"

TURKEY_TZ = timezone(timedelta(hours=3))


def get_connection():
    """Get thread-safe SQLite connection with WAL mode."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH), timeout=30.0, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    return conn


def init_db():
    """Create tables safely if they don't exist. Never drops or deletes data."""
    conn = get_connection()
    try:
        with conn:
            # 1. Boss cooldown timers table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS boss_timers (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    chat_id TEXT NOT NULL,
                    boss_key TEXT NOT NULL,
                    boss_name TEXT NOT NULL,
                    cooldown_seconds INTEGER NOT NULL,
                    start_timestamp REAL NOT NULL,
                    end_timestamp REAL NOT NULL,
                    notified INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)

            # 2. Chest drops table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS chest_drops (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    chat_id TEXT NOT NULL,
                    boss_key TEXT NOT NULL,
                    boss_name TEXT NOT NULL,
                    chest_count INTEGER NOT NULL DEFAULT 1,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)

            # 3. User interactive conversational states (e.g. waiting for chest number)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS user_states (
                    chat_id TEXT PRIMARY KEY,
                    state TEXT NOT NULL,
                    data_json TEXT,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)

            # 4. User favorite bosses table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS user_favorites (
                    chat_id TEXT NOT NULL,
                    boss_key TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (chat_id, boss_key)
                );
            """)

            # 5. Monthly event calendar table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS event_calendar (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    thread_url TEXT NOT NULL,
                    thread_title TEXT,
                    event_date TEXT NOT NULL,
                    display_date TEXT NOT NULL,
                    event_slot INTEGER NOT NULL,
                    event_name TEXT NOT NULL,
                    cet_time TEXT,
                    tsi_time TEXT,
                    tsi_start TEXT,
                    tsi_end TEXT,
                    notified INTEGER DEFAULT 0,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)

            # Indexes for high performance
            conn.execute("CREATE INDEX IF NOT EXISTS idx_timers_active ON boss_timers(notified, end_timestamp);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_chests_chat_date ON chest_drops(chat_id, created_at);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_cal_date ON event_calendar(event_date);")

        logger.info(f"SQLite veritabanı doğrulandı: {DB_PATH}")
    except Exception as e:
        logger.error(f"Veritabanı başlatılırken hata: {e}")
    finally:
        conn.close()


# =========================================================================
# BOSS TIMER FUNCTIONS
# =========================================================================

def add_boss_timer(chat_id: str, boss_key: str, boss_name: str, cooldown_seconds: int) -> dict:
    """Start or update a boss cooldown timer."""
    now = time.time()
    end_ts = now + cooldown_seconds

    conn = get_connection()
    try:
        with conn:
            # Cancel any existing active timer for this boss in this chat
            conn.execute("""
                UPDATE boss_timers
                SET notified = 2
                WHERE chat_id = ? AND boss_key = ? AND notified = 0;
            """, (str(chat_id), boss_key))

            # Insert new active timer
            cursor = conn.execute("""
                INSERT INTO boss_timers (chat_id, boss_key, boss_name, cooldown_seconds, start_timestamp, end_timestamp, notified)
                VALUES (?, ?, ?, ?, ?, ?, 0);
            """, (str(chat_id), boss_key, boss_name, cooldown_seconds, now, end_ts))
            timer_id = cursor.lastrowid

        end_dt = datetime.fromtimestamp(end_ts, tz=TURKEY_TZ)
        return {
            "id": timer_id,
            "chat_id": str(chat_id),
            "boss_key": boss_key,
            "boss_name": boss_name,
            "cooldown_seconds": cooldown_seconds,
            "end_timestamp": end_ts,
            "end_time_str": end_dt.strftime("%H:%M:%S"),
        }
    finally:
        conn.close()


def get_active_timers(chat_id: str = None) -> list:
    """Get all non-notified active boss timers."""
    now = time.time()
    conn = get_connection()
    try:
        query = """
            SELECT id, chat_id, boss_key, boss_name, cooldown_seconds, start_timestamp, end_timestamp
            FROM boss_timers
            WHERE notified = 0 AND end_timestamp > ?
        """
        params = [now]
        if chat_id:
            query += " AND chat_id = ?"
            params.append(str(chat_id))
        query += " ORDER BY end_timestamp ASC;"

        rows = conn.execute(query, params).fetchall()
        result = []
        for r in rows:
            remaining = int(r["end_timestamp"] - now)
            rem_h = remaining // 3600
            rem_m = (remaining % 3600) // 60
            rem_s = remaining % 60
            if rem_h > 0:
                rem_str = f"{rem_h} saat {rem_m} dk"
            elif rem_m > 0:
                rem_str = f"{rem_m} dk {rem_s} sn"
            else:
                rem_str = f"{rem_s} sn"

            end_dt = datetime.fromtimestamp(r["end_timestamp"], tz=TURKEY_TZ)
            result.append({
                "id": r["id"],
                "chat_id": r["chat_id"],
                "boss_key": r["boss_key"],
                "boss_name": r["boss_name"],
                "remaining_seconds": remaining,
                "remaining_str": rem_str,
                "end_time_str": end_dt.strftime("%H:%M:%S"),
            })
        return result
    finally:
        conn.close()


def get_expired_timers() -> list:
    """Get timers whose cooldown has completed but haven't been notified yet."""
    now = time.time()
    conn = get_connection()
    try:
        rows = conn.execute("""
            SELECT id, chat_id, boss_key, boss_name, cooldown_seconds, end_timestamp
            FROM boss_timers
            WHERE notified = 0 AND end_timestamp <= ?;
        """, (now,)).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def mark_timer_notified(timer_id: int):
    """Mark a timer as notified."""
    conn = get_connection()
    try:
        with conn:
            conn.execute("UPDATE boss_timers SET notified = 1 WHERE id = ?;", (timer_id,))
    finally:
        conn.close()


def cancel_timer(chat_id: str, boss_key: str) -> bool:
    """Cancel an active timer."""
    conn = get_connection()
    try:
        with conn:
            cursor = conn.execute("""
                UPDATE boss_timers
                SET notified = 2
                WHERE chat_id = ? AND boss_key = ? AND notified = 0;
            """, (str(chat_id), boss_key))
            return cursor.rowcount > 0
    finally:
        conn.close()


# =========================================================================
# CHEST DROP RECORDING & REPORTING
# =========================================================================

def add_chest_drop(chat_id: str, boss_key: str, boss_name: str, count: int = 1) -> dict:
    """Record dropped chests for a boss."""
    count = max(1, int(count))
    conn = get_connection()
    try:
        with conn:
            conn.execute("""
                INSERT INTO chest_drops (chat_id, boss_key, boss_name, chest_count)
                VALUES (?, ?, ?, ?);
            """, (str(chat_id), boss_key, boss_name, count))

        # Return total chests for this boss today and all time
        today_row = conn.execute("""
            SELECT SUM(chest_count) as total
            FROM chest_drops
            WHERE chat_id = ? AND boss_key = ? AND date(created_at, 'localtime') = date('now', 'localtime');
        """, (str(chat_id), boss_key)).fetchone()

        all_row = conn.execute("""
            SELECT SUM(chest_count) as total
            FROM chest_drops
            WHERE chat_id = ? AND boss_key = ?;
        """, (str(chat_id), boss_key)).fetchone()

        return {
            "boss_name": boss_name,
            "added": count,
            "today_total": today_row["total"] or count,
            "all_time_total": all_row["total"] or count,
        }
    finally:
        conn.close()


def get_chest_report(chat_id: str, days: int = None) -> dict:
    """
    Generate chest drop statistics:
      days is None -> Tüm Zamanlar (All-time)
      days == 0    -> Bugün (Today)
      days == 7    -> Bu Hafta (Son 7 gün)
      days == 30   -> Bu Ay (Son 30 gün)
      days == X    -> Son X gün
    """
    conn = get_connection()
    try:
        params = [str(chat_id)]
        if days is None:
            period_name = "Tüm Zamanlar"
            date_filter = ""
        elif days == 0:
            period_name = "Bugün"
            date_filter = "AND date(created_at, 'localtime') = date('now', 'localtime')"
        else:
            period_name = f"Son {days} Gün"
            date_filter = "AND created_at >= datetime('now', '-' || ? || ' days', 'localtime')"
            params.append(days)

        # 1. Total chests
        total_query = f"""
            SELECT SUM(chest_count) as total
            FROM chest_drops
            WHERE chat_id = ? {date_filter};
        """
        total_row = conn.execute(total_query, params).fetchone()
        grand_total = total_row["total"] or 0

        # 2. Breakdown per boss
        breakdown_query = f"""
            SELECT boss_name, SUM(chest_count) as boss_total
            FROM chest_drops
            WHERE chat_id = ? {date_filter}
            GROUP BY boss_name
            ORDER BY boss_total DESC;
        """
        rows = conn.execute(breakdown_query, params).fetchall()
        breakdown = [(r["boss_name"], r["boss_total"]) for r in rows]

        return {
            "period_name": period_name,
            "grand_total": grand_total,
            "breakdown": breakdown,
            "generated_at": datetime.now(tz=TURKEY_TZ).strftime("%d.%m.%Y %H:%M"),
        }
    finally:
        conn.close()


# =========================================================================
# USER CONVERSATIONAL STATE
# =========================================================================

def set_user_state(chat_id: str, state: str, data: dict = None):
    """Save user interaction state (e.g. waiting for chest count number)."""
    conn = get_connection()
    try:
        with conn:
            conn.execute("""
                INSERT INTO user_states (chat_id, state, data_json, updated_at)
                VALUES (?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(chat_id) DO UPDATE SET
                    state = excluded.state,
                    data_json = excluded.data_json,
                    updated_at = CURRENT_TIMESTAMP;
            """, (str(chat_id), state, json.dumps(data or {})))
    finally:
        conn.close()


def get_user_state(chat_id: str) -> tuple[str, dict]:
    """Retrieve user interaction state and payload."""
    conn = get_connection()
    try:
        row = conn.execute("SELECT state, data_json FROM user_states WHERE chat_id = ?;", (str(chat_id),)).fetchone()
        if not row:
            return None, {}
        try:
            data = json.loads(row["data_json"] or "{}")
        except Exception:
            data = {}
        return row["state"], data
    finally:
        conn.close()


def clear_user_state(chat_id: str):
    """Clear user interaction state."""
    conn = get_connection()
    try:
        with conn:
            conn.execute("DELETE FROM user_states WHERE chat_id = ?;", (str(chat_id),))
    finally:
        conn.close()


# =========================================================================
# USER FAVORITES FUNCTIONS
# =========================================================================

def get_user_favorites(chat_id: str) -> list:
    """Return list of favorite boss_keys for a user."""
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT boss_key FROM user_favorites WHERE chat_id = ? ORDER BY created_at ASC;",
            (str(chat_id),)
        ).fetchall()
        return [r["boss_key"] for r in rows]
    finally:
        conn.close()


def toggle_user_favorite(chat_id: str, boss_key: str) -> bool:
    """Toggle a boss as favorite. Returns True if now favorite, False if removed."""
    conn = get_connection()
    try:
        with conn:
            exists = conn.execute(
                "SELECT 1 FROM user_favorites WHERE chat_id = ? AND boss_key = ?;",
                (str(chat_id), boss_key)
            ).fetchone()
            if exists:
                conn.execute(
                    "DELETE FROM user_favorites WHERE chat_id = ? AND boss_key = ?;",
                    (str(chat_id), boss_key)
                )
                return False
            else:
                conn.execute(
                    "INSERT INTO user_favorites (chat_id, boss_key) VALUES (?, ?);",
                    (str(chat_id), boss_key)
                )
                return True
    finally:
        conn.close()


def is_favorite(chat_id: str, boss_key: str) -> bool:
    """Check if a boss is marked as favorite."""
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT 1 FROM user_favorites WHERE chat_id = ? AND boss_key = ?;",
            (str(chat_id), boss_key)
        ).fetchone()
        return bool(row)
    finally:
        conn.close()


# =========================================================================
# EVENT CALENDAR FUNCTIONS
# =========================================================================

def save_calendar_events(thread_url: str, thread_title: str, events: list):
    """Save or update calendar events. Completely thread-safe."""
    conn = get_connection()
    try:
        with conn:
            conn.execute("DELETE FROM event_calendar WHERE thread_url = ?;", (thread_url,))
            for ev in events:
                conn.execute("""
                    INSERT INTO event_calendar (
                        thread_url, thread_title, event_date, display_date,
                        event_slot, event_name, cet_time, tsi_time, tsi_start, tsi_end, notified
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0);
                """, (
                    thread_url, thread_title, ev["date"], ev["display_date"],
                    ev["event_slot"], ev["event_name"], ev["cet_time"], ev["tsi_time"],
                    ev.get("tsi_start", ""), ev.get("tsi_end", "")
                ))
    finally:
        conn.close()


def get_events_for_date(date_str: str) -> list:
    """Get events for a specific date (YYYY-MM-DD)."""
    conn = get_connection()
    try:
        rows = conn.execute("""
            SELECT id, thread_title, event_date, display_date, event_slot, event_name, cet_time, tsi_time, tsi_start, tsi_end
            FROM event_calendar
            WHERE event_date = ?
            ORDER BY event_slot ASC;
        """, (date_str,)).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_today_events() -> list:
    """Get events scheduled for today."""
    today_str = datetime.now(tz=TURKEY_TZ).strftime("%Y-%m-%d")
    return get_events_for_date(today_str)


def get_tomorrow_events() -> list:
    """Get events scheduled for tomorrow."""
    tomorrow_str = (datetime.now(tz=TURKEY_TZ) + timedelta(days=1)).strftime("%Y-%m-%d")
    return get_events_for_date(tomorrow_str)


def get_upcoming_events(days: int = 7) -> list:
    """Get events for the next N days starting from today."""
    today_str = datetime.now(tz=TURKEY_TZ).strftime("%Y-%m-%d")
    end_str = (datetime.now(tz=TURKEY_TZ) + timedelta(days=days)).strftime("%Y-%m-%d")
    conn = get_connection()
    try:
        rows = conn.execute("""
            SELECT id, thread_title, event_date, display_date, event_slot, event_name, cet_time, tsi_time, tsi_start, tsi_end
            FROM event_calendar
            WHERE event_date >= ? AND event_date <= ?
            ORDER BY event_date ASC, event_slot ASC;
        """, (today_str, end_str)).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_month_events() -> list:
    """Get all events for the current active month."""
    current_month_prefix = datetime.now(tz=TURKEY_TZ).strftime("%Y-%m")
    conn = get_connection()
    try:
        rows = conn.execute("""
            SELECT id, thread_title, event_date, display_date, event_slot, event_name, cet_time, tsi_time, tsi_start, tsi_end
            FROM event_calendar
            WHERE event_date LIKE ?
            ORDER BY event_date ASC, event_slot ASC;
        """, (f"{current_month_prefix}%",)).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_latest_calendar_meta() -> dict:
    """Return metadata about current loaded calendar."""
    conn = get_connection()
    try:
        row = conn.execute("""
            SELECT thread_url, thread_title, COUNT(*) as total_events, MAX(updated_at) as last_updated
            FROM event_calendar
            GROUP BY thread_url
            ORDER BY id DESC LIMIT 1;
        """).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def get_starting_events_now() -> list:
    """
    Find events scheduled for today that are currently active (or just started)
    and have not yet been notified.
    Gracefully handles midnight rollover and bot restarts during event hours.
    """
    now_dt = datetime.now(tz=TURKEY_TZ)
    today_str = now_dt.strftime("%Y-%m-%d")
    yesterday_str = (now_dt - timedelta(days=1)).strftime("%Y-%m-%d")

    conn = get_connection()
    try:
        rows = conn.execute("""
            SELECT id, thread_title, event_date, display_date, event_slot, event_name, cet_time, tsi_time, tsi_start, tsi_end
            FROM event_calendar
            WHERE (event_date = ? OR event_date = ?) AND notified = 0;
        """, (today_str, yesterday_str)).fetchall()

        starting_events = []
        for r in rows:
            ev_date_str = r["event_date"]
            tsi_start = r["tsi_start"]
            tsi_end = r["tsi_end"]

            if not tsi_start or not tsi_end:
                continue

            try:
                sh, sm = map(int, tsi_start.split(":"))
                eh, em = map(int, tsi_end.split(":"))
                ev_y, ev_m, ev_d = map(int, ev_date_str.split("-"))

                start_dt = datetime(ev_y, ev_m, ev_d, sh, sm, tzinfo=TURKEY_TZ)

                # Check if end_time crosses midnight (e.g. 22:00 -> 02:00)
                if (eh < sh) or (eh == sh and em < sm):
                    end_dt = datetime(ev_y, ev_m, ev_d, eh, em, tzinfo=TURKEY_TZ) + timedelta(days=1)
                else:
                    end_dt = datetime(ev_y, ev_m, ev_d, eh, em, tzinfo=TURKEY_TZ)

                # If event already ended in past, mark it notified silently
                if now_dt >= end_dt:
                    with conn:
                        conn.execute("UPDATE event_calendar SET notified = 1 WHERE id = ?;", (r["id"],))
                    continue

                # If event is currently ongoing:
                if start_dt <= now_dt < end_dt:
                    starting_events.append(dict(r))

            except Exception as e:
                logger.debug(f"Tarih ayrıştırma hatası [ID {r['id']}]: {e}")

        return starting_events
    finally:
        conn.close()


def mark_calendar_event_notified(event_id: int):
    """Mark an event starting notification as sent."""
    conn = get_connection()
    try:
        with conn:
            conn.execute("UPDATE event_calendar SET notified = 1 WHERE id = ?;", (event_id,))
    finally:
        conn.close()

