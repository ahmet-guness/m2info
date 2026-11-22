import argparse
import email.utils
import json
import logging
import os
import sys
import threading
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

from config import get_config
from database import (
    init_db,
    get_expired_timers,
    mark_timer_notified,
    get_starting_events_now,
    mark_calendar_event_notified,
    get_latest_calendar_meta
)
from boss_data import BOSSES, get_boss_image
from calendar_scraper import sync_event_calendar, is_tracked_event
from notifier import TelegramNotifier
from scraper import ForumScraper, classify_board_910_item, parse_happy_hour_details
from server_status import GStatusChecker
from telegram_bot import TelegramBotListener

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
STATE_FILE = DATA_DIR / "seen_threads.json"
LOG_FILE = BASE_DIR / "bot.log"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
    ],
)
logger = logging.getLogger("Metin2Bot")


def format_turkey_date(raw_date: str) -> str:
    """Format RFC 2822 date to Turkey local time (UTC+3)."""
    if not raw_date:
        return ""
    try:
        dt = email.utils.parsedate_to_datetime(raw_date)
        tr_tz = timezone(timedelta(hours=3))
        dt_tr = dt.astimezone(tr_tz)
        return dt_tr.strftime("%d.%m.%Y %H:%M")
    except Exception:
        return raw_date


class Metin2HappyHourBot:
    def __init__(self, notify_latest_on_first_run: bool = False):
        self.config = get_config()
        self.tracked_server = self.config.get("tracked_server", "Bagjanamu")
        self.tracked_events = self.config.get("tracked_events", [])
        self.notifier = TelegramNotifier(
            bot_token=self.config["bot_token"],
            chat_id=self.config["chat_id"]
        )
        self.status_checker = GStatusChecker(url=self.config["gstatus_url"])
        self.scrapers = [
            ForumScraper(
                feed_url=b["feed_url"],
                board_url=b["board_url"],
                board_type=b["type"],
            )
            for b in self.config["boards"]
        ]
        self.notify_latest_on_first_run = (
            notify_latest_on_first_run or self.config["notify_on_first_run"]
        )
        self._ensure_data_dir()
        init_db()  # Initialize SQLite database (never drops existing data)
        self.seen_ids, self.active_events, self.server_status = self._load_state()

        # Ensure event calendar is synced
        try:
            if not get_latest_calendar_meta():
                logger.info("Etkinlik takvimi ilk kez yükleniyor...")
                sync_event_calendar()
        except Exception as e:
            logger.debug(f"Başlangıç takvim yüklemesi: {e}")

        # Telegram interactive command listener
        self.listener = TelegramBotListener(
            bot_token=self.config["bot_token"],
            notifier=self.notifier
        )

    def _ensure_data_dir(self):
        DATA_DIR.mkdir(parents=True, exist_ok=True)

    def _load_state(self) -> tuple[set, dict, dict]:
        if not STATE_FILE.exists():
            return set(), {}, {}
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                seen = set(data.get("seen_ids", []))
                active = data.get("active_events", {})
                status = data.get("server_status", {})
                return seen, active, status
        except Exception as e:
            logger.warning(f"Kayıtlı veri okunamadı, yeniden oluşturulacak: {e}")
            return set(), {}, {}

    def _save_state(self):
        try:
            data = {
                "last_updated": datetime.now().isoformat(),
                "total_seen": len(self.seen_ids),
                "seen_ids": list(self.seen_ids),
                "active_events": self.active_events,
                "server_status": self.server_status,
            }
            with open(STATE_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Veriler kaydedilirken hata: {e}")

    # =========================================================================
    # PERIODIC TIMERS & EXPIRATIONS
    # =========================================================================

    def check_active_events_expiration(self):
        """Check if any ongoing Happy Hour has reached its end time."""
        now = time.time()
        updated = False

        for event_id, event in list(self.active_events.items()):
            end_ts = event.get("end_timestamp")
            ended_notified = event.get("ended_notified", False)

            if end_ts and not ended_notified:
                if now >= end_ts:
                    # Only alert if expired recently (within 2 hours) to avoid stale spam on cold restarts
                    if now - end_ts <= 7200:
                        logger.info(f"MUTLU SAATLER BİTTİ BİLDİRİMİ GÖNDERİLİYOR: [{event_id}] {event.get('title')}")
                        sent = self.notifier.notify_happy_hour_ended(event)
                        if sent:
                            event["ended_notified"] = True
                            updated = True
                        else:
                            logger.warning(f"Bitiş bildirimi gönderilemedi: [{event_id}]")
                    else:
                        event["ended_notified"] = True
                        updated = True

            # Prune events older than 14 days
            if end_ts and (now - end_ts > 86400 * 14):
                del self.active_events[event_id]
                updated = True

        if updated:
            self._save_state()

    def check_expired_boss_timers(self):
        """Check if any boss cooldown has completed in SQLite."""
        try:
            expired = get_expired_timers()
            for t in expired:
                boss_key = t["boss_key"]
                boss_name = t["boss_name"]
                chat_id = t["chat_id"]
                timer_id = t["id"]

                boss_info = BOSSES.get(boss_key, {})
                display_cd = boss_info.get("display_cd", f"{t['cooldown_seconds'] // 60} dakika")

                logger.info(f"⚔️ BOSS SOĞUMA SÜRESİ BİTTİ: {boss_name} -> Chat ID: {chat_id}")
                img_url = get_boss_image(boss_key)
                sent = self.notifier.notify_boss_cooldown_expired(
                    chat_id=chat_id,
                    boss_name=boss_name,
                    display_cd=display_cd,
                    photo_url=img_url
                )
                if sent:
                    mark_timer_notified(timer_id)
        except Exception as e:
            logger.error(f"Boss sayaçları kontrol edilirken hata: {e}")

    def check_starting_calendar_events(self):
        """Check if any scheduled daily event is starting right now."""
        try:
            starting = get_starting_events_now()
            for ev in starting:
                ev_name = ev.get("event_name", "")
                if is_tracked_event(ev_name, self.tracked_events):
                    logger.info(f"🎁 ETKİNLİK BAŞLADI BİLDİRİMİ GÖNDERİLİYOR: {ev_name}")
                    sent = self.notifier.notify_event_starting(ev)
                    if sent:
                        mark_calendar_event_notified(ev["id"])
                else:
                    logger.info(f"ℹ️ [Etkinlik Filtrelendi - Bildirim Gönderilmedi]: {ev_name}")
                    mark_calendar_event_notified(ev["id"])
        except Exception as e:
            logger.debug(f"Etkinlik başlangıç kontrolünde hata: {e}")

    # =========================================================================
    # LIVE STATUS & FORUM CHECKS
    # =========================================================================

    def check_live_server_status(self):
        """Check live online/offline state of tracked server via g-status.com."""
        try:
            res = self.status_checker.check_server(self.tracked_server)
            curr_status = res.get("status", "UNKNOWN")

            if curr_status == "UNKNOWN":
                return

            prev_info = self.server_status.get(self.tracked_server)

            if not prev_info:
                logger.info(
                    f"[G-Status] Canlı durum ilk kez kaydedildi: {self.tracked_server} = {curr_status} "
                    f"({res.get('online_count')}/{res.get('total_count')} kanal aktif)"
                )
                self.server_status[self.tracked_server] = {
                    "status": curr_status,
                    "login_online": res.get("login_online", False),
                    "online_count": res.get("online_count", 0),
                    "total_count": res.get("total_count", 0),
                    "last_checked": res.get("checked_at", ""),
                }
                self._save_state()
                return

            prev_status = prev_info.get("status")

            # State change: ONLINE -> OFFLINE
            if prev_status == "ONLINE" and curr_status == "OFFLINE":
                logger.info(f"🔴 SUNUCU KAPANDI TESPİT EDİLDİ: {self.tracked_server} -> OFFLINE")
                sent = self.notifier.notify_server_status_down(res)
                if sent:
                    self.server_status[self.tracked_server]["status"] = "OFFLINE"
                    self.server_status[self.tracked_server]["last_checked"] = res.get("checked_at", "")
                    self._save_state()

            # State change: OFFLINE -> ONLINE
            elif prev_status == "OFFLINE" and curr_status == "ONLINE":
                logger.info(f"🟢 SUNUCU TEKRAR AÇILDI TESPİT EDİLDİ: {self.tracked_server} -> ONLINE")
                sent = self.notifier.notify_server_status_up(res)
                if sent:
                    self.server_status[self.tracked_server]["status"] = "ONLINE"
                    self.server_status[self.tracked_server]["last_checked"] = res.get("checked_at", "")
                    self._save_state()

            self.server_status[self.tracked_server]["online_count"] = res.get("online_count", 0)
            self.server_status[self.tracked_server]["total_count"] = res.get("total_count", 0)
            self.server_status[self.tracked_server]["last_checked"] = res.get("checked_at", "")

        except Exception as e:
            logger.warning(f"G-Status canlı sunucu kontrolünde hata: {e}")

    def check_for_updates(self):
        """Fetch all configured boards and handle new announcements."""
        now = time.time()
        is_first_run = len(self.seen_ids) == 0

        for scraper in self.scrapers:
            threads = scraper.get_latest_threads()
            if not threads:
                continue

            if is_first_run:
                logger.info(f"[{scraper.board_type}] İlk çalıştırma: Mevcut {len(threads)} konu hafızaya alınıyor...")
                for t in threads:
                    self.seen_ids.add(t["id"])
                    if scraper.board_type == "happy_hour":
                        end_ts = t.get("end_timestamp")
                        if end_ts and end_ts > now:
                            logger.info(f"Devam eden Happy Hour bulundu: [{t['id']}] {t['title']} (Bitiş: {t.get('end_str')})")
                            self.active_events[t["id"]] = {
                                "id": t["id"],
                                "title": t["title"],
                                "bonus": t.get("bonus", ""),
                                "start_str": t.get("start_str", ""),
                                "end_str": t.get("end_str", ""),
                                "end_timestamp": end_ts,
                                "link": t["link"],
                                "ended_notified": False,
                            }
                continue

            new_threads = [t for t in threads if t["id"] not in self.seen_ids]
            if not new_threads:
                continue

            new_threads.reverse()
            for t in new_threads:
                if not t.get("description") and t.get("link"):
                    full_text = scraper.fetch_full_thread_text(t["link"])
                    if full_text:
                        t["description"] = full_text
                        if scraper.board_type == "happy_hour":
                            details = parse_happy_hour_details(t["title"], full_text, t.get("pub_date", ""))
                            t["bonus"] = details["bonus"]
                            t["start_str"] = details["start_str"]
                            t["end_str"] = details["end_str"]
                            t["end_timestamp"] = details["end_timestamp"]
                            t["end_iso"] = details["end_iso"]

                t_formatted = dict(t)
                t_formatted["pub_date"] = format_turkey_date(t.get("pub_date", ""))

                if scraper.board_type == "happy_hour":
                    logger.info(f"YENİ MUTLU SAATLER: [{t['id']}] {t['title']}")
                    sent = self.notifier.notify_happy_hour(t_formatted)
                    if sent:
                        self.seen_ids.add(t["id"])
                        end_ts = t.get("end_timestamp")
                        if end_ts:
                            self.active_events[t["id"]] = {
                                "id": t["id"],
                                "title": t["title"],
                                "bonus": t.get("bonus", ""),
                                "start_str": t.get("start_str", ""),
                                "end_str": t.get("end_str", ""),
                                "end_timestamp": end_ts,
                                "link": t["link"],
                                "ended_notified": (now >= end_ts),
                            }
                        self._save_state()

                elif scraper.board_type == "maintenance_and_server":
                    category = classify_board_910_item(
                        title=t["title"],
                        description=t["description"],
                        tracked_server=self.tracked_server
                    )

                    if category == "maintenance":
                        logger.info(f"YENİ BAKIM DUYURUSU: [{t['id']}] {t['title']}")
                        sent = self.notifier.notify_maintenance(t_formatted)
                        if sent:
                            self.seen_ids.add(t["id"])
                            self._save_state()
                    elif category == "tracked_server":
                        logger.info(f"YENİ {self.tracked_server.upper()} DUYURUSU: [{t['id']}] {t['title']}")
                        sent = self.notifier.notify_server_news(t_formatted, server_name=self.tracked_server)
                        if sent:
                            self.seen_ids.add(t["id"])
                            self._save_state()
                    else:
                        logger.info(f"[Filtrelendi / Diğer Sunucu]: [{t['id']}] {t['title']}")
                        self.seen_ids.add(t["id"])
                        self._save_state()

        if is_first_run:
            self._save_state()
            logger.info(f"İlk kurulum tamamlandı. Toplam {len(self.seen_ids)} konu hafızaya alındı.")
            if self.notify_latest_on_first_run:
                hh_scraper = self.scrapers[0]
                hh_threads = hh_scraper.get_latest_threads()
                if hh_threads:
                    latest = dict(hh_threads[0])
                    latest["pub_date"] = format_turkey_date(latest.get("pub_date", ""))
                    self.notifier.notify_happy_hour(latest)

        self.check_active_events_expiration()

    # =========================================================================
    # MAIN DAEMON LOOP
    # =========================================================================

    def run_daemon(self):
        """Run bot with both Telegram long polling listener and background scrapers."""
        board_interval = self.config["check_interval"]
        status_interval = self.config["status_check_interval"]

        logger.info("=" * 60)
        logger.info("Metin2 Bildirim & Farm Asistanı Botu Başlatıldı.")
        logger.info(f"Takip Edilen Sunucu: {self.tracked_server}")
        logger.info(f"Forum Kontrol Sıklığı: {board_interval} sn | G-Status: {status_interval} sn")
        logger.info(f"Telegram Durumu: {'Hazır' if self.notifier.is_configured() else 'EKSİK (Token/Chat ID girin!)'}")
        logger.info("=" * 60)

        if not self.notifier.is_configured():
            logger.warning("DİKKAT: .env veya config.json içinde TELEGRAM_BOT_TOKEN veya TELEGRAM_CHAT_ID boş!")

        # Start interactive Telegram command listener in background thread
        if self.notifier.is_configured():
            listener_thread = threading.Thread(target=self.listener.start_polling, daemon=True)
            listener_thread.start()

        last_forum_check = 0
        last_status_check = 0
        last_calendar_check = time.time()

        while True:
            try:
                now = time.time()

                # 1. Forum checks (Happy Hour & Bakım Duyuruları)
                if now - last_forum_check >= board_interval:
                    self.check_for_updates()
                    last_forum_check = now

                # 2. G-Status live server online/offline checks
                if now - last_status_check >= status_interval:
                    self.check_live_server_status()
                    last_status_check = now

                # 3. Active Happy Hour expiration check
                self.check_active_events_expiration()

                # 4. Boss cooldown timers check (checks every loop iteration)
                self.check_expired_boss_timers()

                # 5. Starting daily event notifications
                self.check_starting_calendar_events()

                # 6. Periodic calendar auto-sync (every 12 hours)
                if now - last_calendar_check >= 43200:
                    try:
                        sync_event_calendar()
                        last_calendar_check = now
                    except Exception:
                        pass

            except Exception as e:
                logger.error(f"Döngü sırasında hata: {e}", exc_info=True)

            time.sleep(5)


def main():
    parser = argparse.ArgumentParser(description="Metin2 Telegram Bildirim & Farm Asistanı")
    parser.add_argument("--test", action="store_true", help="Telegram bot bağlantısını ve ayarları test eder")
    parser.add_argument("--check-once", action="store_true", help="Tek bir kontrol yapar ve çıkar")
    parser.add_argument("--check-status", action="store_true", help="G-Status üzerinden sunucu canlı durumunu sorgular")
    parser.add_argument("--notify-latest", action="store_true", help="En son duyuruyu hemen Telegram'a gönderir")
    args = parser.parse_args()

    bot = Metin2HappyHourBot(notify_latest_on_first_run=args.notify_latest)

    if args.check_status:
        print(f"\n--- G-STATUS CANLI DURUM SORGUSU: {bot.tracked_server} ---")
        res = bot.status_checker.check_server(bot.tracked_server)
        print(f"Sunucu: {res['server_name']}")
        print(f"Genel Durum: {res['status']}")
        print(f"Login Durumu: {'ONLINE' if res['login_online'] else 'OFFLINE'}")
        print(f"Kanal Sayısı: {res['online_count']}/{res['total_count']} Açık")
        print(f"Son Offline Tarihi: {res['last_offline'] or 'Bilinmiyor'}")
        print("\nKanallar:")
        for ch in res["channels"]:
            print(f"  • {ch['name']}: {ch['status']}")
        print(f"\nSorgulama Zamanı: {res['checked_at']}\n")
        sys.exit(0)

    if args.test:
        print("\n--- TELEGRAM BAĞLANTI TESTİ ---")
        if not bot.notifier.is_configured():
            print("HATA: TELEGRAM_BOT_TOKEN veya TELEGRAM_CHAT_ID ayarlanmamış!")
            print("Lütfen .env dosyasını doldurun.\n")
            sys.exit(1)
        success = bot.notifier.send_test_message(tracked_server=bot.tracked_server)
        if success:
            print("BAŞARILI: Test mesajı Telegram'a iletildi!\n")
        else:
            print("BAŞARISIZ: Telegram'a mesaj gönderilemedi. Token veya Chat ID'nizi kontrol edin.\n")
        sys.exit(0 if success else 1)

    if args.check_once:
        logger.info("Tek seferlik kontrol modu çalıştırılıyor...")
        bot.check_for_updates()
        bot.check_live_server_status()
        bot.check_expired_boss_timers()
        logger.info("Kontrol tamamlandı.")
        sys.exit(0)

    try:
        bot.run_daemon()
    except KeyboardInterrupt:
        logger.info("Bot kullanıcı tarafından sonlandırıldı.")
        bot.listener.stop()


if __name__ == "__main__":
    main()
