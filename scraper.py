import email.utils
import html
import logging
import re
import ssl
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta

logger = logging.getLogger("Metin2Bot")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "tr-TR,tr;q=0.9,en-US;q=0.8,en;q=0.7",
}

TURKISH_MONTHS = {
    'ocak': 1, 'şubat': 2, 'subat': 2, 'mart': 3, 'nisan': 4,
    'mayıs': 5, 'mayis': 5, 'haziran': 6, 'temmuz': 7,
    'ağustos': 8, 'agustos': 8, 'eylül': 9, 'eylul': 9,
    'ekim': 10, 'kasım': 11, 'kasim': 11, 'aralık': 12, 'aralik': 12
}


def turkish_lower(text: str) -> str:
    """Normalize text to lowercase respecting Turkish characters."""
    if not text:
        return ""
    tr_map = str.maketrans({
        'İ': 'i',
        'I': 'ı',
        'Ğ': 'ğ',
        'Ü': 'ü',
        'Ş': 'ş',
        'Ö': 'ö',
        'Ç': 'ç',
    })
    return text.translate(tr_map).lower()


def clean_html_text(raw_html: str) -> str:
    """Convert HTML content into clean readable plain text."""
    if not raw_html:
        return ""
    text = re.sub(r'<br\s*/?>', '\n', raw_html, flags=re.IGNORECASE)
    text = re.sub(r'</p>', '\n', text, flags=re.IGNORECASE)
    text = re.sub(r'<[^>]+>', ' ', text)
    text = html.unescape(text)
    lines = [re.sub(r'[ \t]+', ' ', line).strip() for line in text.split('\n')]
    cleaned_lines = []
    prev_empty = False
    for line in lines:
        if line:
            cleaned_lines.append(line)
            prev_empty = False
        elif not prev_empty:
            cleaned_lines.append("")
            prev_empty = True
    return "\n".join(cleaned_lines).strip()


def extract_thread_id(url_or_guid: str) -> str:
    """Extract thread ID number from WoltLab URL or GUID."""
    m = re.search(r'thread/(\d+)', url_or_guid or '')
    if m:
        return m.group(1)
    return url_or_guid or ""


def classify_board_910_item(title: str, description: str, tracked_server: str = "Bagjanamu") -> str:
    """
    Classify thread from Board 910 (Bakım ve Sunucu Haberleri).
    Returns:
      'maintenance'    -> Bakım duyurusu (her zaman bildirilir)
      'tracked_server' -> Sadece takip edilen sunucu duyurusu (örn. Bagjanamu)
      'skip'           -> Diğer sunucu haberleri (Lucifer, Charon vb.) veya alakasız
    """
    full_text = turkish_lower(f"{title} {description}")

    # Check for maintenance keywords
    is_maintenance = any(k in full_text for k in [
        "bakım", "bakim", "maintenance", "network bakımı", "destek sistemi bakımı"
    ])

    # Check for tracked server keywords (e.g. Bagjanamu)
    server_norm = turkish_lower(tracked_server)
    variants = [server_norm]
    if "bagjanamu" in server_norm:
        variants.extend(["bagcanamu", "bağcanamu", "bağjanamu"])

    is_tracked_server = any(v in full_text for v in variants)

    if is_maintenance:
        return "maintenance"
    elif is_tracked_server:
        return "tracked_server"
    else:
        return "skip"


def parse_happy_hour_details(title: str, text: str, pub_date_str: str = "") -> dict:
    """Extract bonus rate, start time, end time, and end timestamp from text."""
    full_text = f"{title} {text}"

    # 1. Bonus rate (%25, %30, etc.)
    bonus = None
    bonus_match = re.search(r'%(\d{2,3})', full_text)
    if bonus_match:
        bonus = f"%{bonus_match.group(1)}"
    else:
        bonus_match_alt = re.search(r'(\d{2,3})%', full_text)
        if bonus_match_alt:
            bonus = f"%{bonus_match_alt.group(1)}"

    # 2. Reference year (Turkey UTC+3)
    ref_year = datetime.now().year
    if pub_date_str:
        try:
            dt = email.utils.parsedate_to_datetime(pub_date_str)
            ref_year = dt.year
        except Exception:
            pass

    month_pattern = r'(?:' + '|'.join(TURKISH_MONTHS.keys()) + r')'

    # Pattern A: "8 Kasım saat 12:00 ile 9 Kasım saat 23:59" or "25 Ekim 12:00 ile 26 Ekim 23:59"
    date_regex = re.compile(
        rf'(\d{{1,2}})\s+({month_pattern})(?:\s+(\d{{4}}))?(?:\s+saat)?\s+(\d{{1,2}}[:.]\d{{2}})\s*(?:ile|-|/)\s*'
        rf'(\d{{1,2}})\s+({month_pattern})(?:\s+(\d{{4}}))?(?:\s+saat)?\s+(\d{{1,2}}[:.]\d{{2}})',
        re.IGNORECASE
    )

    match = date_regex.search(full_text)
    if match:
        s_day, s_month_name, s_year, s_time, e_day, e_month_name, e_year, e_time = match.groups()
        start_year = int(s_year) if s_year else ref_year
        end_year = int(e_year) if e_year else start_year

        s_month = TURKISH_MONTHS[s_month_name.lower()]
        e_month = TURKISH_MONTHS[e_month_name.lower()]

        # Handle year rollover: Metin2 Happy Hours typically last 24-72 hours.
        if s_month == 12 and e_month == 1 and not e_year:
            end_year += 1
        elif e_month < s_month and not e_year:
            end_year = start_year
            e_month = s_month

        start_str = f"{s_day} {s_month_name.capitalize()} {s_time}"
        end_str = f"{e_day} {e_month_name.capitalize()} {e_time}"

        end_h, end_min = map(int, e_time.replace('.', ':').split(':'))
        tr_tz = timezone(timedelta(hours=3))
        try:
            end_dt = datetime(end_year, e_month, int(e_day), end_h, end_min, tzinfo=tr_tz)
            end_ts = end_dt.timestamp()
            end_iso = end_dt.isoformat()
        except Exception:
            end_ts = None
            end_iso = None

        return {
            "bonus": bonus or "Belirtilmedi",
            "start_str": start_str,
            "end_str": end_str,
            "end_timestamp": end_ts,
            "end_iso": end_iso
        }

    # Pattern B: Single day with range e.g. "8 Kasım saat 12:00 ile 23:59"
    single_date_regex = re.compile(
        rf'(\d{{1,2}})\s+({month_pattern})(?:\s+(\d{{4}}))?(?:\s+saat)?\s+(\d{{1,2}}[:.]\d{{2}})\s*(?:ile|-)\s*(?:saat\s*)?(\d{{1,2}}[:.]\d{{2}})',
        re.IGNORECASE
    )
    single_match = single_date_regex.search(full_text)
    if single_match:
        d, m_name, y, t_start, t_end = single_match.groups()
        s_year = int(y) if y else ref_year
        s_month = TURKISH_MONTHS[m_name.lower()]
        s_day = int(d)
        start_str = f"{s_day} {m_name.capitalize()} {t_start}"
        end_str = f"{s_day} {m_name.capitalize()} {t_end}"

        end_h, end_m = map(int, t_end.replace('.', ':').split(':'))
        tr_tz = timezone(timedelta(hours=3))
        try:
            end_dt = datetime(s_year, s_month, s_day, end_h, end_m, tzinfo=tr_tz)
            end_ts = end_dt.timestamp()
            end_iso = end_dt.isoformat()
        except Exception:
            end_ts = None
            end_iso = None

        return {
            "bonus": bonus or "Belirtilmedi",
            "start_str": start_str,
            "end_str": end_str,
            "end_timestamp": end_ts,
            "end_iso": end_iso
        }

    return {
        "bonus": bonus or "Belirtilmedi",
        "start_str": "Belirtilmedi",
        "end_str": "Belirtilmedi",
        "end_timestamp": None,
        "end_iso": None
    }


class ForumScraper:
    def __init__(self, feed_url: str, board_url: str, board_type: str = "happy_hour"):
        self.feed_url = feed_url
        self.board_url = board_url
        self.board_type = board_type

    def _fetch_url(self, url: str) -> str:
        req = urllib.request.Request(url, headers=HEADERS)
        ctx = ssl.create_default_context()
        with urllib.request.urlopen(req, context=ctx, timeout=15) as response:
            return response.read().decode("utf-8", errors="ignore")

    def fetch_full_thread_text(self, thread_url: str) -> str:
        """Fetch the full original text of a thread's first post."""
        if not thread_url:
            return ""
        try:
            html_content = self._fetch_url(thread_url)
            m = re.search(r'<div\s+class="messageText"[^>]*>([\s\S]*?)</div>', html_content)
            if m:
                return clean_html_text(m.group(1))
        except Exception as e:
            logger.warning(f"Konu tam metni çekilemedi ({thread_url}): {e}")
        return ""

    def fetch_from_rss(self) -> list:
        """Fetch threads via WoltLab RSS feed."""
        xml_data = self._fetch_url(self.feed_url)
        root = ET.fromstring(xml_data)
        channel = root.find("channel")
        if channel is None:
            return []

        threads = []
        for item in channel.findall("item"):
            title = (item.find("title").text or "").strip()
            link = (item.find("link").text or "").strip()
            guid = (item.find("guid").text or "").strip()
            pub_date = (item.find("pubDate").text or "").strip()

            desc_elem = item.find("description")
            raw_desc = desc_elem.text if desc_elem is not None and desc_elem.text else ""
            cleaned_desc = clean_html_text(raw_desc)

            thread_id = extract_thread_id(guid) or extract_thread_id(link)

            if thread_id and title:
                item_data = {
                    "id": thread_id,
                    "title": title,
                    "link": link,
                    "pub_date": pub_date,
                    "description": cleaned_desc,
                    "board_type": self.board_type,
                    "bonus": "Belirtilmedi",
                    "start_str": "Belirtilmedi",
                    "end_str": "Belirtilmedi",
                    "end_timestamp": None,
                    "end_iso": None,
                }

                if self.board_type == "happy_hour":
                    details = parse_happy_hour_details(title, cleaned_desc, pub_date)
                    if details["end_timestamp"] is None and link:
                        full_text = self.fetch_full_thread_text(link)
                        if full_text:
                            cleaned_desc = full_text
                            details = parse_happy_hour_details(title, full_text, pub_date)
                            item_data["description"] = cleaned_desc

                    item_data["bonus"] = details["bonus"]
                    item_data["start_str"] = details["start_str"]
                    item_data["end_str"] = details["end_str"]
                    item_data["end_timestamp"] = details["end_timestamp"]
                    item_data["end_iso"] = details["end_iso"]

                threads.append(item_data)
        return threads

    def fetch_from_html(self) -> list:
        """
        Fallback method: Scrape thread list from HTML board page fast.
        Does NOT fetch full text for every item in list to keep it fast.
        """
        html_data = self._fetch_url(self.board_url)
        threads = []

        # WoltLab thread list rows: <ol id="thread..." data-thread-id="123"...> ... </ol>
        row_matches = re.findall(
            r'<ol[^>]*data-thread-id="(\d+)"[^>]*>([\s\S]*?)</ol>',
            html_data
        )

        seen_ids = set()
        for tid, row_html in row_matches:
            if tid in seen_ids:
                continue
            seen_ids.add(tid)

            # Topic link inside row: class contains wbbTopicLink or messageGroupLink
            link_m = re.search(
                r'<a\s+[^>]*href="([^"]*thread/' + tid + r'[^"]*)"[^>]*>([\s\S]*?)</a>',
                row_html
            )
            if not link_m:
                link_m = re.search(r'href="([^"]*thread/' + tid + r'[^"]*)"', row_html)
                link = link_m.group(1) if link_m else ""
                title = f"Konu {tid}"
            else:
                link = link_m.group(1)
                title = clean_html_text(link_m.group(2))

            time_m = re.search(r'<time\s+datetime="([^"]+)"', row_html)
            pub_date = time_m.group(1) if time_m else ""

            threads.append({
                "id": tid,
                "title": title,
                "link": link,
                "pub_date": pub_date,
                "description": "",
                "board_type": self.board_type,
                "bonus": "Belirtilmedi",
                "start_str": "Belirtilmedi",
                "end_str": "Belirtilmedi",
                "end_timestamp": None,
                "end_iso": None,
            })

        return threads

    def get_latest_threads(self) -> list:
        """Attempt RSS fetch first, fallback to HTML parsing."""
        try:
            items = self.fetch_from_rss()
            if items:
                logger.info(f"[{self.board_type}] RSS akışından {len(items)} konu başarıyla çekildi.")
                return items
        except Exception as e:
            logger.warning(f"[{self.board_type}] RSS akışı çekilirken hata: {e}. HTML yedek kontrolüne geçiliyor...")

        try:
            items = self.fetch_from_html()
            logger.info(f"[{self.board_type}] HTML sayfasından {len(items)} konu başarıyla çekildi.")
            return items
        except Exception as e:
            logger.error(f"[{self.board_type}] HTML yedek kontrolü de başarısız oldu: {e}")
            return []
