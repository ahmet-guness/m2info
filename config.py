import json
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

DEFAULT_BOARDS = [
    {
        "id": "809",
        "name": "Mutlu Saatler",
        "type": "happy_hour",
        "feed_url": "https://board.tr.metin2.gameforge.com/index.php?board-feed/809/",
        "board_url": "https://board.tr.metin2.gameforge.com/index.php?board/809-mutlu-saatler/",
    },
    {
        "id": "910",
        "name": "Bakım ve Sunucu Haberleri",
        "type": "maintenance_and_server",
        "feed_url": "https://board.tr.metin2.gameforge.com/index.php?board-feed/910/",
        "board_url": "https://board.tr.metin2.gameforge.com/index.php?board/910-bak%C4%B1m-ve-sunucu-haberleri/",
    },
]

# Varsayılan bildirim gönderilecek etkinlik listesi (Kullanıcı tercihi)
DEFAULT_TRACKED_EVENTS = [
    "Kötü Ruh Kovma Kağıdı",
    "Cor Draconis",
    "Küçük Kutsama",
    "Nesneyi Efsunla",
    "Ay Işığı",
    "Balıkçılık",
    "Münzevi Tavsiyesi",
    "Envanter Genişletme"
]


def load_env_file(filepath: Path) -> dict:
    """Simple .env parser without external dependencies."""
    env_vars = {}
    if not filepath.exists():
        return env_vars
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" in line:
                    key, val = line.split("=", 1)
                    key = key.strip()
                    val = val.strip().strip("'\"")
                    env_vars[key] = val
    except Exception:
        pass
    return env_vars


def get_config():
    """Load configuration from environment, .env or config.json."""
    env_file = BASE_DIR / ".env"
    file_env = load_env_file(env_file)

    config_json_file = BASE_DIR / "config.json"
    json_conf = {}
    if config_json_file.exists() and config_json_file.is_file():
        try:
            with open(config_json_file, "r", encoding="utf-8") as f:
                json_conf = json.load(f)
        except Exception:
            pass

    def get_val(key, default=""):
        return os.environ.get(key) or file_env.get(key) or json_conf.get(key) or default

    def get_int(key, default_val: int) -> int:
        raw = get_val(key, default_val)
        try:
            return int(raw)
        except (ValueError, TypeError):
            return default_val

    bot_token = str(get_val("TELEGRAM_BOT_TOKEN", "")).strip()
    chat_id = str(get_val("TELEGRAM_CHAT_ID", "")).strip()
    check_interval = get_int("CHECK_INTERVAL_SECONDS", 180)
    status_check_interval = get_int("STATUS_CHECK_INTERVAL_SECONDS", 60)
    notify_on_first_run = str(get_val("NOTIFY_ON_FIRST_RUN", "false")).lower() in ("true", "1", "yes")
    tracked_server = str(get_val("TRACKED_SERVER", "Bagjanamu")).strip() or "Bagjanamu"

    raw_tracked_events = get_val("TRACKED_EVENTS", "")
    if raw_tracked_events:
        tracked_events = [e.strip() for e in str(raw_tracked_events).split(",") if e.strip()]
    else:
        tracked_events = list(DEFAULT_TRACKED_EVENTS)

    return {
        "bot_token": bot_token,
        "chat_id": chat_id,
        "check_interval": max(30, check_interval),
        "status_check_interval": max(15, status_check_interval),
        "notify_on_first_run": notify_on_first_run,
        "tracked_server": tracked_server,
        "tracked_events": tracked_events,
        "gstatus_url": "https://www.g-status.com/en-gb/game/metin2",
        "boards": DEFAULT_BOARDS,
    }
