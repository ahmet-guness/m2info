import logging
import re
import ssl
import urllib.request
from datetime import datetime

logger = logging.getLogger("Metin2Bot")

GSTATUS_URL = "https://www.g-status.com/en-gb/game/metin2"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "tr-TR,tr;q=0.9,en-US;q=0.8,en;q=0.7",
}


class GStatusChecker:
    def __init__(self, url: str = GSTATUS_URL):
        self.url = url

    def fetch_html(self) -> str:
        req = urllib.request.Request(self.url, headers=HEADERS)
        ctx = ssl.create_default_context()
        with urllib.request.urlopen(req, context=ctx, timeout=15) as resp:
            return resp.read().decode("utf-8", errors="ignore")

    def check_server(self, server_name: str = "Bagjanamu") -> dict:
        """
        Scrape g-status.com for the specified server and return status summary.
        Handles errors gracefully without throwing exceptions.
        """
        try:
            html_data = self.fetch_html()
        except Exception as e:
            logger.warning(f"g-status.com adresine erişilemedi ({self.url}): {e}")
            return {
                "server_name": server_name,
                "is_online": False,
                "status": "UNKNOWN",
                "login_online": False,
                "online_count": 0,
                "total_count": 0,
                "channels": [],
                "last_offline": "",
                "checked_at": datetime.now().strftime("%d.%m.%Y %H:%M:%S"),
            }

        # Find all server wrappers (with or without end comment)
        wrappers = re.findall(
            r'<div\s+class="server_wrap">([\s\S]*?)(?:<!-- Server Wrapper End -->|(?=<div\s+class="server_wrap">)|$)',
            html_data
        )

        server_lower = server_name.lower()
        channels = []
        last_offline = ""

        for w in wrappers:
            name_m = re.search(r'<div\s+class="server_name">([^<]+)</div>', w)
            if not name_m:
                continue
            name = name_m.group(1).strip()

            if server_lower in name.lower():
                status_m = re.search(r'<div\s+class="status\s+([^"]+)">([^<]+)</div>', w)
                status_cls = status_m.group(1).strip().lower() if status_m else "unknown"
                status_text = status_m.group(2).strip().upper() if status_m else "UNKNOWN"

                last_off_m = re.search(r'<div\s+class="last_offline_date">([^<]+)</div>', w)
                if last_off_m:
                    last_offline = last_off_m.group(1).strip()

                is_ch_online = (status_cls == "online" or status_text == "ONLINE")
                channels.append({
                    "name": name,
                    "status": status_text,
                    "is_online": is_ch_online,
                })

        if not channels:
            logger.warning(f"g-status.com üzerinde '{server_name}' için kanal bilgisi bulunamadı.")
            return {
                "server_name": server_name,
                "is_online": False,
                "status": "UNKNOWN",
                "login_online": False,
                "online_count": 0,
                "total_count": 0,
                "channels": [],
                "last_offline": "",
                "checked_at": datetime.now().strftime("%d.%m.%Y %H:%M:%S"),
            }

        total_count = len(channels)
        online_count = sum(1 for ch in channels if ch["is_online"])

        # Find Login channel specifically
        login_ch = next((ch for ch in channels if "login" in ch["name"].lower()), None)
        login_online = login_ch["is_online"] if login_ch else (online_count > 0)

        # Server is considered ONLINE if Login is up and at least 1 channel is up
        is_online = login_online and (online_count > 0)
        status_str = "ONLINE" if is_online else "OFFLINE"

        return {
            "server_name": server_name,
            "is_online": is_online,
            "status": status_str,
            "login_online": login_online,
            "online_count": online_count,
            "total_count": total_count,
            "channels": channels,
            "last_offline": last_offline,
            "checked_at": datetime.now().strftime("%d.%m.%Y %H:%M:%S"),
        }
