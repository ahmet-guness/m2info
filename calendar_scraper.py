import logging
import re
import ssl
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta

from database import save_calendar_events, get_latest_calendar_meta

logger = logging.getLogger("Metin2Bot")

TURKEY_TZ = timezone(timedelta(hours=3))
BOARD_688_RSS = "https://board.tr.metin2.gameforge.com/index.php?board-feed/688/"
BOARD_688_HTML = "https://board.tr.metin2.gameforge.com/index.php?board/688-oyun-event/"

TURKISH_MONTHS = {
    "ocak": 1, "şubat": 2, "mart": 3, "nisan": 4, "mayıs": 5, "haziran": 6,
    "temmuz": 7, "ağustos": 8, "eylül": 9, "ekim": 10, "kasım": 11, "aralık": 12
}


def clean_html(text: str) -> str:
    """Remove HTML tags and normalize whitespace."""
    text = re.sub(r'<[^>]+>', ' ', text)
    return ' '.join(text.split())


def is_tracked_event(event_name: str, tracked_list: list = None) -> bool:
    """
    Check if an event matches the whitelist of events for notifications.
    Case-insensitive, Turkish-character safe.
    """
    if not event_name:
        return False
    from scraper import turkish_lower
    from config import DEFAULT_TRACKED_EVENTS

    ev_clean = turkish_lower(clean_html(event_name).strip())
    whitelist = tracked_list if tracked_list is not None else DEFAULT_TRACKED_EVENTS

    for target in whitelist:
        t_clean = turkish_lower(target.strip())
        if t_clean in ev_clean or ev_clean in t_clean:
            return True
        if t_clean.replace(" ", "") in ev_clean.replace(" ", ""):
            return True
    return False


def fetch_url(url: str, timeout: int = 12) -> str:
    """Fetch URL with custom User-Agent and SSL context."""
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Metin2Bot/1.0"}
    )
    ctx = ssl.create_default_context()
    with urllib.request.urlopen(req, timeout=timeout, context=ctx) as r:
        return r.read().decode("utf-8", errors="ignore")


def discover_latest_calendar_thread() -> dict:
    """
    Find the latest Marmara & Bagjanamu event calendar thread from board 688 RSS and HTML.
    Returns: dict with 'title' and 'link', or None.
    """
    # 1. Check RSS feed
    try:
        xml_content = fetch_url(BOARD_688_RSS)
        root = ET.fromstring(xml_content.encode("utf-8"))
        channel = root.find("channel")
        if channel is not None:
            for item in channel.findall("item"):
                title = item.findtext("title", "")
                link = item.findtext("link", "")
                title_lower = title.lower()
                if "bagjanamu" in title_lower and ("etkinlik" in title_lower or "takvim" in title_lower):
                    logger.info(f"RSS üzerinden güncel takvim konusu bulundu: {title}")
                    return {"title": title, "link": link}
    except Exception as e:
        logger.debug(f"RSS takvim arama hatası: {e}")

    # 2. Check HTML fallback
    try:
        html = fetch_url(BOARD_688_HTML)
        threads = re.findall(r'href="([^"]*thread/(\d+)-[^"]*)"[^>]*>(.*?)</a>', html)
        for link, tid, ttitle in threads:
            clean_title = clean_html(ttitle)
            clean_lower = clean_title.lower()
            if "bagjanamu" in clean_lower and ("etkinlik" in clean_lower or "takvim" in clean_lower):
                logger.info(f"HTML üzerinden güncel takvim konusu bulundu: {clean_title}")
                return {"title": clean_title, "link": link}
    except Exception as e:
        logger.debug(f"HTML takvim arama hatası: {e}")

    return None


def parse_calendar_from_thread(thread_url: str) -> tuple[str, list]:
    """
    Parse the official HTML table from the calendar thread into structured event rows.
    Returns: (title, list of event dicts)
    """
    html = fetch_url(thread_url)

    # Extract thread title
    title_m = re.search(r'<title>(.*?)</title>', html, re.IGNORECASE)
    thread_title = clean_html(title_m.group(1)) if title_m else "Metin2 Etkinlik Takvimi"
    # Remove board suffix from title
    thread_title = thread_title.split(" - Oyun Event")[0].strip()

    idx = html.find('class="messageText"')
    if idx == -1:
        return thread_title, []

    snippet = html[idx:idx + 40000]

    table_m = re.search(r'<table.*?>(.*?)</table>', snippet, re.DOTALL)
    if not table_m:
        return thread_title, []

    table_html = table_m.group(1)
    tr_matches = re.findall(r'<tr.*?>(.*?)</tr>', table_html, re.DOTALL)
    if not tr_matches:
        return thread_title, []

    # Row 0: Header with time slots (e.g. Event 1 (16:00-20:00), Event 2 (20:00-24:00))
    header_cols = re.findall(r'<t[dh].*?>(.*?)</t[dh]>', tr_matches[0], re.DOTALL)
    header_texts = [clean_html(c) for c in header_cols]

    time_slots = []
    for h in header_texts[1:]:
        m = re.search(r'(\d{1,2}:\d{2})\s*[-–]\s*(\d{1,2}:\d{2})', h)
        if m:
            time_slots.append((m.group(1), m.group(2)))
        else:
            time_slots.append(("", ""))

    events = []

    for row_html in tr_matches[1:]:
        td_matches = re.findall(r'<td.*?>(.*?)</td>', row_html, re.DOTALL)
        if not td_matches:
            continue
        cols = [clean_html(c) for c in td_matches]
        if not cols or not cols[0]:
            continue

        date_str = cols[0]

        day = None
        month = None
        year = datetime.now(tz=TURKEY_TZ).year

        dm = re.search(r'\b(\d{1,2})\b', date_str)
        if dm:
            day = int(dm.group(1))

        # Match whole word for month to avoid "mart" inside "cumartesi"
        date_words = re.findall(r'[a-zA-ZçğıöşüÇĞİÖŞÜ]+', date_str.lower())
        for word in date_words:
            if word in TURKISH_MONTHS:
                month = TURKISH_MONTHS[word]
                break

        ym = re.search(r'\b(20\d{2})\b', date_str)
        if ym:
            year = int(ym.group(1))

        if not day or not month:
            continue

        iso_date = f"{year:04d}-{month:02d}-{day:02d}"

        # Daylight Saving difference: Germany is UTC+1 in winter (diff = +2 to TSİ), UTC+2 in summer (diff = +1 to TSİ)
        diff_hours = 2 if (month >= 11 or month <= 3) else 1

        for idx_slot, event_name in enumerate(cols[1:]):
            if not event_name or event_name == "-":
                continue
            cet_start, cet_end = time_slots[idx_slot] if idx_slot < len(time_slots) else ("", "")

            tsi_start = ""
            tsi_end = ""
            if cet_start:
                try:
                    sh, sm = map(int, cet_start.split(":"))
                    th = (sh + diff_hours) % 24
                    tsi_start = f"{th:02d}:{sm:02d}"
                except Exception:
                    pass
            if cet_end:
                try:
                    eh, em = map(int, cet_end.split(":"))
                    th = (eh + diff_hours) % 24
                    tsi_end = f"{th:02d}:{em:02d}"
                except Exception:
                    pass

            events.append({
                "date": iso_date,
                "display_date": date_str,
                "event_slot": idx_slot + 1,
                "event_name": event_name,
                "cet_time": f"{cet_start}-{cet_end}" if cet_start else "",
                "tsi_time": f"{tsi_start}-{tsi_end}" if tsi_start else "",
                "tsi_start": tsi_start,
                "tsi_end": tsi_end,
            })

    return thread_title, events


def sync_event_calendar(manual_url: str = None) -> dict:
    """
    Fetch and sync event calendar with database.
    Can be run automatically or triggered via Telegram command.
    """
    thread_url = manual_url
    title = None

    if not thread_url:
        discovered = discover_latest_calendar_thread()
        if discovered:
            thread_url = discovered["link"]
            title = discovered["title"]

    if not thread_url:
        # Check if we already have a previous calendar loaded
        meta = get_latest_calendar_meta()
        if meta:
            thread_url = meta["thread_url"]
            title = meta["thread_title"]
        else:
            return {
                "success": False,
                "error": "Forumda Marmara & Bagjanamu etkinlik takvimi konusu henüz bulunamadı."
            }

    try:
        parsed_title, events = parse_calendar_from_thread(thread_url)
        if not events:
            return {
                "success": False,
                "error": "Etkinlik tablosu okunamadı veya tabloda kayıt bulunamadı."
            }

        final_title = title or parsed_title
        save_calendar_events(thread_url, final_title, events)
        logger.info(f"Etkinlik takvimi senkronize edildi: {final_title} ({len(events)} etkinlik)")
        return {
            "success": True,
            "title": final_title,
            "url": thread_url,
            "count": len(events),
        }
    except Exception as e:
        logger.error(f"Etkinlik takvimi senkronizasyon hatası: {e}", exc_info=True)
        return {
            "success": False,
            "error": str(e)
        }
