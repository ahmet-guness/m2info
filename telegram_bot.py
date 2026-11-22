import json
import logging
import ssl
import time
import urllib.parse
import urllib.request

from boss_data import BOSS_CATEGORIES, BOSSES, get_boss_by_name, get_boss_image
from calendar_scraper import sync_event_calendar, is_tracked_event
from database import (
    add_boss_timer,
    add_chest_drop,
    clear_user_state,
    get_active_timers,
    get_chest_report,
    get_user_state,
    set_user_state,
    cancel_timer,
    get_user_favorites,
    toggle_user_favorite,
    is_favorite,
    get_today_events,
    get_tomorrow_events,
    get_upcoming_events,
    get_month_events,
    get_latest_calendar_meta
)
from notifier import TelegramNotifier

logger = logging.getLogger("Metin2Bot")


class TelegramBotListener:
    def __init__(self, bot_token: str, notifier: TelegramNotifier):
        self.bot_token = bot_token
        self.notifier = notifier
        self.api_base = f"https://api.telegram.org/bot{self.bot_token}"
        self.offset = 0
        self.running = False

    def get_updates(self, timeout: int = 15) -> list:
        """Poll Telegram for new updates using standard library."""
        endpoint = f"{self.api_base}/getUpdates"
        payload = {
            "offset": self.offset,
            "timeout": timeout,
            "allowed_updates": ["message", "callback_query"],
        }
        try:
            data = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(endpoint, data=data, headers={"Content-Type": "application/json"})
            ctx = ssl.create_default_context()
            with urllib.request.urlopen(req, context=ctx, timeout=timeout + 10) as resp:
                result = json.loads(resp.read().decode("utf-8"))
                if result.get("ok"):
                    return result.get("result", [])
        except urllib.error.URLError:
            pass
        except Exception as e:
            logger.debug(f"getUpdates hatası: {e}")
        return []

    def start_polling(self):
        """Main polling loop running in background thread."""
        self.running = True
        logger.info("Telegram komut dinleyicisi (Long Polling) başlatıldı.")
        while self.running:
            try:
                updates = self.get_updates(timeout=10)
                for update in updates:
                    self.offset = update["update_id"] + 1
                    self.process_update(update)
            except Exception as e:
                logger.error(f"Polling döngüsünde hata: {e}", exc_info=True)
                time.sleep(2)

    def stop(self):
        self.running = False

    # =========================================================================
    # UPDATE PROCESSOR
    # =========================================================================

    def process_update(self, update: dict):
        if "message" in update:
            self.handle_message(update["message"])
        elif "callback_query" in update:
            self.handle_callback_query(update["callback_query"])

    # =========================================================================
    # MESSAGE HANDLER
    # =========================================================================

    def handle_message(self, message: dict):
        chat_id = str(message.get("chat", {}).get("id", ""))
        text = (message.get("text") or "").strip()
        if not text:
            return

        state, state_data = get_user_state(chat_id)
        if state == "waiting_chest_count":
            self.handle_state_chest_count(chat_id, text, state_data)
            return
        elif state == "waiting_report_days":
            self.handle_state_report_days(chat_id, text)
            return

        cmd = text.split()[0].lower()

        if cmd in ("/start", "/help", "/yardim"):
            self.cmd_help(chat_id)
        elif cmd in ("/bosscd", "/boss"):
            self.cmd_bosscd(chat_id)
        elif cmd in ("/favori", "/favoriler", "/fav"):
            self.cmd_favori(chat_id)
        elif cmd in ("/takvim", "/etkinlik", "/event"):
            self.cmd_takvim(chat_id, text)
        elif cmd in ("/kalan", "/timers", "/sureler"):
            self.cmd_kalan(chat_id)
        elif cmd == "/sandik":
            self.cmd_sandik(chat_id, text)
        elif cmd == "/rapor":
            self.cmd_rapor(chat_id, text)
        elif cmd == "/iptal":
            clear_user_state(chat_id)
            self.notifier.send_message("❌ İşlem iptal edildi.", target_chat_id=chat_id)

    def cmd_help(self, chat_id: str):
        msg = (
            "✨ ━━━━━━━━━━━━━━━━━━━━ ✨\n"
            "⚔️ <b>METİN2 FARM & BİLDİRİM ASİSTANI</b> ⚔️\n"
            "✨ ━━━━━━━━━━━━━━━━━━━━ ✨\n\n"
            "Aşağıdaki komutlarla farmınızı ve etkinliklerinizi kolayca takip edebilirsiniz:\n\n"
            "⏱️ <b>Boss Soğuma & Sayaç:</b>\n"
            "• <code>/bosscd</code> : Boss menüsünü açar, kestiğiniz bossun sayacını başlatır (Fotoğraflı Kart).\n"
            "• <code>/favori</code> : Sık kestiğiniz bossları favorilere ekler (Tek tıkla başlatma).\n"
            "• <code>/kalan</code> : Aktif tüm boss sayaçlarını ve kalan süreleri gösterir.\n\n"
            "📅 <b>Etkinlik Takvimi:</b>\n"
            "• <code>/takvim</code> : Marmara & Bagjanamu günün ve haftanın drop etkinliklerini gösterir.\n\n"
            "📦 <b>Sandık Takibi & Raporlama:</b>\n"
            "• <code>/sandik</code> : Hızlı sandık ekleme menüsünü açar.\n"
            "  <i>Örnek kısayol: <code>/sandik nemere 3</code></i>\n"
            "• <code>/rapor</code> : Günlük, haftalık ve tüm zamanlar sandık raporunu verir.\n"
            "  <i>Örnek kısayol: <code>/rapor 3</code> (Son 3 günün raporu)</i>\n\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "🛡️ <i>Otomatik Happy Hour, Bakım ve Sunucu Durum bildirimleri de arka planda aktiftir.</i>"
        )
        self.notifier.send_message(msg, target_chat_id=chat_id)

    # =========================================================================
    # BOSS CD COMMAND & MENUS
    # =========================================================================

    def cmd_bosscd(self, chat_id: str):
        """Open boss categories keyboard with quick favorite boss access."""
        favorites = get_user_favorites(chat_id)
        buttons = []

        # 1. If user has favorites, put them at the top as 1-click action buttons
        if favorites:
            fav_row = []
            for b_key in favorites:
                b_info = BOSSES.get(b_key, {})
                b_name = b_info.get("name", b_key)
                icon = b_info.get("icon", "⚔️")
                cd_str = b_info.get("display_cd", "")
                fav_row.append({"text": f"{icon} {b_name} ({cd_str})", "callback_data": f"startcd:{b_key}"})
                if len(fav_row) == 2:
                    buttons.append(fav_row)
                    fav_row = []
            if fav_row:
                buttons.append(fav_row)

        # 2. Category buttons
        for cat_key, cat_data in BOSS_CATEGORIES.items():
            buttons.append([{"text": cat_data["title"], "callback_data": f"cat:{cat_key}"}])

        # 3. Favorite manager button
        fav_btn_label = "⭐ Favorileri Düzenle" if favorites else "⭐ Favori Boss Ekle"
        buttons.append([{"text": fav_btn_label, "callback_data": "fav:menu"}])

        keyboard = {"inline_keyboard": buttons}
        msg = "⚔️ <b>BOSS SOĞUMA SÜRESİ BAŞLAT</b>\n\n"
        if favorites:
            msg += "⭐ <b>FAVORİ BOSSLARINIZ:</b> <i>(Tek tıkla sayacı başlatın)</i>\n\n"
        msg += (
            "📁 <b>TÜM KATEGORİLER:</b>\n"
            "<i>(Kategori seçip bossa tıklayarak sayacı başlatabilirsiniz)</i>"
        )
        self.notifier.send_message(msg, reply_markup=keyboard, target_chat_id=chat_id)

    def cmd_favori(self, chat_id: str):
        """Open favorite boss selector."""
        self.show_favori_menu(chat_id)

    def cmd_kalan(self, chat_id: str):
        """List active boss cooldown timers."""
        timers = get_active_timers(chat_id)
        if not timers:
            msg = (
                "⏳ <b>Aktif Boss Sayacı Bulunmuyor</b>\n\n"
                "Şu anda bekleyen bir boss sayacınız yok.\n"
                "Yeni sayaç başlatmak için <code>/bosscd</code> yazabilirsiniz."
            )
            self.notifier.send_message(msg, target_chat_id=chat_id)
            return

        lines = ["⏳ <b>AKTİF BOSS SOĞUMA SÜRELERİ</b>", "━━━━━━━━━━━━━━━━━━━━"]
        for t in timers:
            boss_info = BOSSES.get(t["boss_key"], {})
            icon = boss_info.get("icon", "⚔️")
            lines.append(f"{icon} <b>{t['boss_name']}</b>")
            lines.append(f"   ⏱️ Kalan: <code>{t['remaining_str']}</code>")
            lines.append(f"   🔔 Bitiş Saati: <code>{t['end_time_str']}</code>\n")

        lines.append("━━━━━━━━━━━━━━━━━━━━")
        lines.append("<i>Süre dolduğunda bot size fotoğraflı bildirim gönderecektir.</i>")
        self.notifier.send_message("\n".join(lines), target_chat_id=chat_id)

    # =========================================================================
    # SANDIK & RAPOR COMMANDS
    # =========================================================================

    def cmd_sandik(self, chat_id: str, text: str):
        """Handle /sandik command."""
        parts = text.split()
        if len(parts) >= 3:
            query = parts[1]
            try:
                count = int(parts[2])
            except ValueError:
                count = 1

            matched = get_boss_by_name(query)
            if matched:
                b_key, b_data = matched
                res = add_chest_drop(chat_id, b_key, b_data["name"], count)
                img = get_boss_image(b_key)
                caption = (
                    f"✅ <b>{count} adet {b_data['name']} Sandığı</b> kaydedildi!\n\n"
                    f"📅 Bugünkü toplam: <b>{res['today_total']} adet</b>\n"
                    f"🏆 Tüm zamanlar: <b>{res['all_time_total']} adet</b>"
                )
                self.notifier.send_photo(photo_url=img, caption=caption, target_chat_id=chat_id)
                return

        buttons = []
        for cat_key, cat_data in BOSS_CATEGORIES.items():
            buttons.append([{"text": cat_data["title"], "callback_data": f"chestcat:{cat_key}"}])

        keyboard = {"inline_keyboard": buttons}
        msg = "📦 <b>SANDIK EKLEME MENÜSÜ</b>\n\nSandık eklemek istediğiniz bossun kategorisini seçin:"
        self.notifier.send_message(msg, reply_markup=keyboard, target_chat_id=chat_id)

    def cmd_rapor(self, chat_id: str, text: str):
        """Handle /rapor command."""
        parts = text.split()
        if len(parts) >= 2:
            arg = parts[1].lower()
            if arg in ("tum", "tüm", "all"):
                self.send_report(chat_id, days=None)
                return
            elif arg in ("bugun", "bugün", "today", "0"):
                self.send_report(chat_id, days=0)
                return
            elif arg in ("hafta", "week", "7"):
                self.send_report(chat_id, days=7)
                return
            elif arg in ("ay", "month", "30"):
                self.send_report(chat_id, days=30)
                return
            else:
                try:
                    d = int(arg)
                    self.send_report(chat_id, days=d)
                    return
                except ValueError:
                    pass

        buttons = [
            [
                {"text": "📅 Bugün", "callback_data": "rep:0"},
                {"text": "🗓️ Bu Hafta (7 Gün)", "callback_data": "rep:7"},
            ],
            [
                {"text": "📆 Bu Ay (30 Gün)", "callback_data": "rep:30"},
                {"text": "📊 Tüm Zamanlar", "callback_data": "rep:all"},
            ],
            [
                {"text": "🔢 Özel Gün Sayısı Gir", "callback_data": "rep:custom"},
            ]
        ]
        keyboard = {"inline_keyboard": buttons}
        msg = "📊 <b>METİN2 SANDIK RAPORU</b>\n\nRaporlamak istediğiniz zaman aralığını seçin:"
        self.notifier.send_message(msg, reply_markup=keyboard, target_chat_id=chat_id)

    def send_report(self, chat_id: str, days: int = None, message_id: int = None):
        """Generate and display chest report."""
        rep = get_chest_report(chat_id, days=days)
        period = rep["period_name"]
        total = rep["grand_total"]
        breakdown = rep["breakdown"]

        lines = [
            "📊 ━━━━━━━━━━━━━━━━━━━━ 📊",
            f"📦 <b>SANDIK RAPORU ({period.upper()})</b>",
            "📊 ━━━━━━━━━━━━━━━━━━━━ 📊",
            "",
        ]

        if not breakdown or total == 0:
            lines.append("<i>Bu dönemde henüz kaydedilmiş bir sandık bulunmuyor.</i>\n")
        else:
            for boss_name, count in breakdown:
                matched = get_boss_by_name(boss_name)
                icon = matched[1].get("icon", "📦") if matched else "📦"
                lines.append(f"{icon} <b>{boss_name}:</b> <code>{count} adet</code>")

            lines.append("")
            lines.append("━━━━━━━━━━━━━━━━━━━━")
            lines.append(f"🏆 <b>Toplam Sandık:</b> <b>{total} adet</b>")

        lines.append(f"\n🕒 <i>Oluşturulma: {rep['generated_at']}</i>")
        msg = "\n".join(lines)

        back_kb = {"inline_keyboard": [[{"text": "🔄 Farklı Dönem Seç", "callback_data": "rep:menu"}]]}

        if message_id:
            self.notifier.edit_message_text(msg, chat_id=chat_id, message_id=message_id, reply_markup=back_kb)
        else:
            self.notifier.send_message(msg, reply_markup=back_kb, target_chat_id=chat_id)

    # =========================================================================
    # CALLBACK QUERY HANDLER (BUTTON CLICKS)
    # =========================================================================

    def handle_callback_query(self, query: dict):
        query_id = query["id"]
        chat_id = str(query.get("message", {}).get("chat", {}).get("id", ""))
        message_id = query.get("message", {}).get("message_id")
        data = query.get("data", "")

        self.notifier.answer_callback_query(query_id)

        # 1. Back to main categories
        if data in ("cat:back", "boss:back_cat"):
            self.show_categories(chat_id, message_id, mode="cd")
            return
        elif data == "chestcat:back":
            self.show_categories(chat_id, message_id, mode="chest")
            return
        elif data == "rep:menu":
            buttons = [
                [
                    {"text": "📅 Bugün", "callback_data": "rep:0"},
                    {"text": "🗓️ Bu Hafta (7 Gün)", "callback_data": "rep:7"},
                ],
                [
                    {"text": "📆 Bu Ay (30 Gün)", "callback_data": "rep:30"},
                    {"text": "📊 Tüm Zamanlar", "callback_data": "rep:all"},
                ],
                [
                    {"text": "🔢 Özel Gün Sayısı Gir", "callback_data": "rep:custom"},
                ]
            ]
            keyboard = {"inline_keyboard": buttons}
            msg = "📊 <b>METİN2 SANDIK RAPORU</b>\n\nRaporlamak istediğiniz zaman aralığını seçin:"
            self.notifier.edit_message_text(msg, chat_id=chat_id, message_id=message_id, reply_markup=keyboard)
            return

        # 2. Category clicked -> Show Bosses in that Category
        if data.startswith("cat:"):
            cat_key = data.split(":", 1)[1]
            self.show_bosses_in_category(chat_id, message_id, cat_key, mode="cd")
            return
        elif data.startswith("chestcat:"):
            cat_key = data.split(":", 1)[1]
            self.show_bosses_in_category(chat_id, message_id, cat_key, mode="chest")
            return

        # 3. Boss clicked -> Start Cooldown + Send Photo with Chest Buttons
        if data.startswith("startcd:"):
            boss_key = data.split(":", 1)[1]
            self.start_boss_cd(chat_id, message_id, boss_key)
            return

        # 4. Boss clicked in chest menu -> Show chest count options
        if data.startswith("addchest:"):
            boss_key = data.split(":", 1)[1]
            self.show_chest_count_options(chat_id, message_id, boss_key)
            return

        # 5. Quick chest count clicked
        if data.startswith("savechest:"):
            parts = data.split(":")
            boss_key = parts[1]
            count = int(parts[2])
            b_data = BOSSES.get(boss_key, {})
            b_name = b_data.get("name", boss_key)

            res = add_chest_drop(chat_id, boss_key, b_name, count)
            caption = (
                f"✅ <b>{count} adet {b_name} Sandığı</b> kaydedildi!\n\n"
                f"📅 <b>Bugünkü Toplam:</b> {res['today_total']} adet\n"
                f"🏆 <b>Tüm Zamanlar:</b> {res['all_time_total']} adet\n\n"
                f"<i>Raporları görüntülemek için /rapor yazabilirsiniz.</i>"
            )
            # Edit caption if photo message, or edit text if text message
            self.notifier.edit_message_caption(caption, chat_id=chat_id, message_id=message_id, reply_markup=None)
            return

        # 6. Manual chest count prompted
        if data.startswith("manualchest:"):
            boss_key = data.split(":", 1)[1]
            b_name = BOSSES.get(boss_key, {}).get("name", boss_key)
            set_user_state(chat_id, "waiting_chest_count", {"boss_key": boss_key, "message_id": message_id})
            caption = (
                f"✏️ <b>{b_name} Sandık Adedi Girişi</b>\n\n"
                f"Lütfen kaç sandık düştüğünü sohbete rakam olarak yazın:\n"
                f"<i>(Örn: <code>5</code> veya <code>12</code>)</i>\n\n"
                f"İptal etmek için <code>/iptal</code> yazabilirsiniz."
            )
            self.notifier.edit_message_caption(caption, chat_id=chat_id, message_id=message_id, reply_markup=None)
            return

        # 7. No chest dropped
        if data == "nochest":
            caption = "👌 <b>Sayaç çalışıyor.</b> Sandık eklenmedi."
            self.notifier.edit_message_caption(caption, chat_id=chat_id, message_id=message_id, reply_markup=None)
            return

        # 8. Report buttons
        if data.startswith("rep:"):
            rep_type = data.split(":", 1)[1]
            if rep_type == "all":
                self.send_report(chat_id, days=None, message_id=message_id)
            elif rep_type == "custom":
                set_user_state(chat_id, "waiting_report_days", {"message_id": message_id})
                msg = (
                    "🔢 <b>ÖZEL GÜN SAYISI</b>\n\n"
                    "Kaç günlük sandık raporu almak istiyorsunuz?\n"
                    "Lütfen gün sayısını yazın (Örn: <code>3</code> veya <code>14</code>):"
                )
                self.notifier.edit_message_text(msg, chat_id=chat_id, message_id=message_id, reply_markup=None)
            else:
                try:
                    d = int(rep_type)
                    self.send_report(chat_id, days=d, message_id=message_id)
                except ValueError:
                    pass
            return

        # 9. Favorite Boss management callbacks
        if data == "fav:menu":
            self.show_favori_menu(chat_id, message_id=message_id)
            return
        elif data.startswith("favtoggle:"):
            b_key = data.split(":", 1)[1]
            toggle_user_favorite(chat_id, b_key)
            self.show_favori_menu(chat_id, message_id=message_id)
            return
        elif data == "fav:done":
            self.show_categories(chat_id, message_id, mode="cd")
            return

        # 10. Calendar callbacks
        if data.startswith("cal:"):
            cal_action = data.split(":", 1)[1]
            if cal_action == "refresh":
                sync_event_calendar()
                self.show_calendar_view(chat_id, view_type="today", message_id=message_id)
            elif cal_action in ("today", "tomorrow", "week", "month"):
                self.show_calendar_view(chat_id, view_type=cal_action, message_id=message_id)
            return

    # =========================================================================
    # UI HELPER FUNCTIONS
    # =========================================================================

    def show_categories(self, chat_id: str, message_id: int, mode: str = "cd"):
        prefix = "cat" if mode == "cd" else "chestcat"
        buttons = []
        favorites = []

        if mode == "cd":
            favorites = get_user_favorites(chat_id)
            if favorites:
                fav_row = []
                for b_key in favorites:
                    b_info = BOSSES.get(b_key, {})
                    b_name = b_info.get("name", b_key)
                    icon = b_info.get("icon", "⚔️")
                    cd_str = b_info.get("display_cd", "")
                    fav_row.append({"text": f"{icon} {b_name} ({cd_str})", "callback_data": f"startcd:{b_key}"})
                    if len(fav_row) == 2:
                        buttons.append(fav_row)
                        fav_row = []
                if fav_row:
                    buttons.append(fav_row)

        for cat_key, cat_data in BOSS_CATEGORIES.items():
            buttons.append([{"text": cat_data["title"], "callback_data": f"{prefix}:{cat_key}"}])

        if mode == "cd":
            fav_btn_label = "⭐ Favorileri Düzenle" if favorites else "⭐ Favori Boss Ekle"
            buttons.append([{"text": fav_btn_label, "callback_data": "fav:menu"}])

        keyboard = {"inline_keyboard": buttons}
        if mode == "cd":
            title = "⚔️ <b>BOSS SOĞUMA SÜRESİ BAŞLAT</b>"
            msg = f"{title}\n\n"
            if favorites:
                msg += "⭐ <b>FAVORİ BOSSLARINIZ:</b> <i>(Tek tıkla sayacı başlatın)</i>\n\n"
            msg += "📁 <b>TÜM KATEGORİLER:</b>\n<i>(Kategori seçip bossa tıklayarak sayacı başlatabilirsiniz)</i>"
        else:
            title = "📦 <b>SANDIK EKLEME MENÜSÜ</b>"
            msg = f"{title}\n\nKategoriyi seçin:"

        self.notifier.edit_message_text(msg, chat_id=chat_id, message_id=message_id, reply_markup=keyboard)

    def show_favori_menu(self, chat_id: str, message_id: int = None):
        """Display interactive checkbox list of all bosses to toggle favorites."""
        favorites = set(get_user_favorites(chat_id))
        buttons = []
        row = []
        for b_key, b_info in BOSSES.items():
            b_name = b_info.get("name", b_key)
            icon = b_info.get("icon", "⚔️")
            is_fav = b_key in favorites
            check = "✅" if is_fav else "⬜"
            btn_text = f"{check} {icon} {b_name}"
            row.append({"text": btn_text, "callback_data": f"favtoggle:{b_key}"})
            if len(row) == 2:
                buttons.append(row)
                row = []
        if row:
            buttons.append(row)

        buttons.append([
            {"text": "⬅️ Boss Menüsüne Dön", "callback_data": "cat:back"},
            {"text": "✔️ Tamam", "callback_data": "fav:done"}
        ])

        keyboard = {"inline_keyboard": buttons}
        msg = (
            "⭐ <b>FAVORİ BOSSLARI DÜZENLE</b>\n\n"
            "Sık kestiğiniz bossları favorilere ekleyin. Favori bosslarınız <code>/bosscd</code> "
            "menüsünün en üstünde tek tıkla başlatma butonu olarak listelenir.\n\n"
            "<i>(Eklemek veya çıkarmak için boss butonuna tıklayın)</i>"
        )
        if message_id:
            self.notifier.edit_message_text(msg, chat_id=chat_id, message_id=message_id, reply_markup=keyboard)
        else:
            self.notifier.send_message(msg, reply_markup=keyboard, target_chat_id=chat_id)

    # =========================================================================
    # EVENT CALENDAR UI
    # =========================================================================

    def cmd_takvim(self, chat_id: str, text: str):
        """Handle /takvim command."""
        parts = text.split()
        if len(parts) >= 2:
            sub = parts[1].lower()
            if sub in ("yenile", "sync", "guncelle", "güncelle"):
                res = sync_event_calendar()
                if res.get("success"):
                    self.notifier.send_message(
                        f"✅ <b>Etkinlik takvimi güncellendi!</b>\n\n"
                        f"📌 <b>Başlık:</b> {res['title']}\n"
                        f"🔢 <b>Toplam Etkinlik:</b> {res['count']} adet",
                        target_chat_id=chat_id
                    )
                else:
                    self.notifier.send_message(
                        f"⚠️ <b>Takvim güncellenemedi:</b> {res.get('error')}",
                        target_chat_id=chat_id
                    )
                return
            elif sub in ("link", "url") and len(parts) >= 3:
                custom_url = parts[2].strip()
                res = sync_event_calendar(manual_url=custom_url)
                if res.get("success"):
                    self.notifier.send_message(
                        f"✅ <b>Özel takvim linki yüklendi!</b>\n\n"
                        f"📌 <b>Başlık:</b> {res['title']}\n"
                        f"🔢 <b>Toplam Etkinlik:</b> {res['count']} adet",
                        target_chat_id=chat_id
                    )
                else:
                    self.notifier.send_message(
                        f"⚠️ <b>Takvim yüklenemedi:</b> {res.get('error')}",
                        target_chat_id=chat_id
                    )
                return

        self.show_calendar_view(chat_id, view_type="today")

    def show_calendar_view(self, chat_id: str, view_type: str = "today", message_id: int = None):
        """Render event calendar in specified view mode."""
        meta = get_latest_calendar_meta()
        if not meta:
            sync_res = sync_event_calendar()
            if sync_res.get("success"):
                meta = get_latest_calendar_meta()

        if not meta:
            msg = (
                "📅 <b>MARMARA & BAGJANAMU ETKİNLİK TAKVİMİ</b>\n\n"
                "ℹ️ <i>Bu ay için forumda henüz bir etkinlik takvimi konusu bulunamadı veya yayınlanmadı.</i>\n\n"
                "Yeniden kontrol etmek için: <code>/takvim yenile</code>"
            )
            if message_id:
                self.notifier.edit_message_text(msg, chat_id=chat_id, message_id=message_id)
            else:
                self.notifier.send_message(msg, target_chat_id=chat_id)
            return

        lines = [
            "📅 ━━━━━━━━━━━━━━━━━━━━ 📅",
            f"🏆 <b>{meta.get('thread_title', 'MARMARA & BAGJANAMU ETKİNLİK TAKVİMİ').upper()}</b>",
            "📅 ━━━━━━━━━━━━━━━━━━━━ 📅",
            ""
        ]

        if view_type == "today":
            today_events = get_today_events()
            tomorrow_events = get_tomorrow_events()

            if today_events:
                d_name = today_events[0].get("display_date", "Bugün")
                lines.append(f"🌟 <b>BUGÜNÜN ETKİNLİKLERİ ({d_name})</b>\n")
                for ev in today_events:
                    name = ev.get("event_name", "")
                    tsi = ev.get("tsi_time", "")
                    cet = ev.get("cet_time", "")
                    icon = "🔔" if is_tracked_event(name) else "▫️"
                    lines.append(f"• ⏰ <b>{tsi} TSİ:</b> {icon} <b>{name}</b> <i>(Avrupa: {cet})</i>")
                lines.append("")
            else:
                lines.append("🌟 <b>BUGÜN:</b> <i>Bugün için takvimde planlanmış özel bir drop etkinliği yok.</i>\n")

            if tomorrow_events:
                d_name = tomorrow_events[0].get("display_date", "Yarın")
                lines.append(f"➡️ <b>YARININ ETKİNLİKLERİ ({d_name})</b>\n")
                for ev in tomorrow_events:
                    name = ev.get("event_name", "")
                    tsi = ev.get("tsi_time", "")
                    icon = "🔔" if is_tracked_event(name) else "▫️"
                    lines.append(f"• ⏰ <b>{tsi} TSİ:</b> {icon} <b>{name}</b>")
                lines.append("")

        elif view_type == "tomorrow":
            tomorrow_events = get_tomorrow_events()
            if tomorrow_events:
                d_name = tomorrow_events[0].get("display_date", "Yarın")
                lines.append(f"➡️ <b>YARININ ETKİNLİKLERİ ({d_name})</b>\n")
                for ev in tomorrow_events:
                    name = ev.get("event_name", "")
                    tsi = ev.get("tsi_time", "")
                    cet = ev.get("cet_time", "")
                    icon = "🔔" if is_tracked_event(name) else "▫️"
                    lines.append(f"• ⏰ <b>{tsi} TSİ:</b> {icon} <b>{name}</b> <i>(Avrupa: {cet})</i>")
                lines.append("")
            else:
                lines.append("➡️ <b>YARIN:</b> <i>Yarın için planlanmış etkinlik bulunmuyor.</i>\n")

        elif view_type == "week":
            week_events = get_upcoming_events(7)
            lines.append("🗓️ <b>ÖNÜMÜZDEKİ 7 GÜNÜN ETKİNLİKLERİ</b>\n")
            if week_events:
                current_d = None
                for ev in week_events:
                    d_str = ev.get("display_date", ev.get("event_date", ""))
                    if d_str != current_d:
                        current_d = d_str
                        lines.append(f"📅 <b>{current_d}:</b>")
                    name = ev.get("event_name", "")
                    tsi = ev.get("tsi_time", "")
                    icon = "🔔" if is_tracked_event(name) else "▫️"
                    lines.append(f"  • ⏰ {tsi} TSİ: {icon} <b>{name}</b>")
                lines.append("")
            else:
                lines.append("<i>Yaklaşan etkinlik bulunamadı.</i>\n")

        elif view_type == "month":
            month_events = get_month_events()
            lines.append("📋 <b>AYLIK TÜM ETKİNLİKLER</b>\n")
            if month_events:
                current_d = None
                for ev in month_events:
                    d_str = ev.get("display_date", ev.get("event_date", ""))
                    if d_str != current_d:
                        current_d = d_str
                        lines.append(f"📅 <b>{current_d}:</b>")
                    name = ev.get("event_name", "")
                    tsi = ev.get("tsi_time", "")
                    icon = "🔔" if is_tracked_event(name) else "▫️"
                    lines.append(f"  • ⏰ {tsi}: {icon} <b>{name}</b>")
                lines.append("")
            else:
                lines.append("<i>Bu ay için kayıtlı etkinlik yok.</i>\n")

        lines.append("━━━━━━━━━━━━━━━━━━━━")
        lines.append("<i>ℹ️ 🔔 Simgeli etkinlikler başladığında bot otomatik bildirim gönderir.</i>\n")
        lines.append(f"🔗 <a href=\"{meta.get('thread_url', '')}\">Resmi Forum Takvim Konusu</a>")

        buttons = [
            [
                {"text": "📅 Bugün", "callback_data": "cal:today"},
                {"text": "➡️ Yarın", "callback_data": "cal:tomorrow"},
            ],
            [
                {"text": "🗓️ Bu Hafta (7 Gün)", "callback_data": "cal:week"},
                {"text": "📋 Tüm Ay", "callback_data": "cal:month"},
            ],
            [
                {"text": "🔄 Takvimi Yenile", "callback_data": "cal:refresh"},
            ]
        ]
        keyboard = {"inline_keyboard": buttons}
        msg_text = "\n".join(lines)

        if message_id:
            self.notifier.edit_message_text(msg_text, chat_id=chat_id, message_id=message_id, reply_markup=keyboard)
        else:
            self.notifier.send_message(msg_text, reply_markup=keyboard, target_chat_id=chat_id)

    def show_bosses_in_category(self, chat_id: str, message_id: int, cat_key: str, mode: str = "cd"):
        cat_data = BOSS_CATEGORIES.get(cat_key)
        if not cat_data:
            return

        buttons = []
        row = []
        for b_key in cat_data["bosses"]:
            b_info = BOSSES.get(b_key, {})
            b_name = b_info.get("name", b_key)
            icon = b_info.get("icon", "⚔️")
            cd_str = b_info.get("display_cd", "")
            btn_text = f"{icon} {b_name} ({cd_str})" if mode == "cd" else f"{icon} {b_name}"
            cb_data = f"startcd:{b_key}" if mode == "cd" else f"addchest:{b_key}"

            row.append({"text": btn_text, "callback_data": cb_data})
            if len(row) == 2:
                buttons.append(row)
                row = []
        if row:
            buttons.append(row)

        back_cb = "cat:back" if mode == "cd" else "chestcat:back"
        buttons.append([{"text": "⬅️ Kategorilere Dön", "callback_data": back_cb}])

        keyboard = {"inline_keyboard": buttons}
        msg = f"<b>{cat_data['title']}</b>\n\nBoss seçiniz:"
        self.notifier.edit_message_text(msg, chat_id=chat_id, message_id=message_id, reply_markup=keyboard)

    def start_boss_cd(self, chat_id: str, message_id: int, boss_key: str):
        b_info = BOSSES.get(boss_key, {})
        b_name = b_info.get("name", boss_key)
        icon = b_info.get("icon", "⚔️")
        cd_sec = b_info.get("cooldown_seconds", 3600)
        display_cd = b_info.get("display_cd", "")
        img_url = get_boss_image(boss_key)

        res = add_boss_timer(chat_id, boss_key, b_name, cd_sec)

        chest_buttons = [
            [
                {"text": "📦 +1", "callback_data": f"savechest:{boss_key}:1"},
                {"text": "📦 +2", "callback_data": f"savechest:{boss_key}:2"},
                {"text": "📦 +3", "callback_data": f"savechest:{boss_key}:3"},
                {"text": "📦 +4", "callback_data": f"savechest:{boss_key}:4"},
            ],
            [
                {"text": "✏️ Sayı Yaz", "callback_data": f"manualchest:{boss_key}"},
                {"text": "❌ Sandık Yok", "callback_data": "nochest"},
            ]
        ]
        keyboard = {"inline_keyboard": chest_buttons}

        caption = (
            f"⏳ <b>{icon} {b_name.upper()} SAYAÇ BAŞLATILDI!</b>\n\n"
            f"⏱️ <b>Soğuma Süresi:</b> <code>{display_cd}</code>\n"
            f"🔔 <b>Hazır Olacağı Saat:</b> <code>{res['end_time_str']} (TSİ)</code>\n\n"
            f"<i>Süre bittiğinde buradan bildirim alacaksınız.</i>\n\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"📦 <b>Düşen sandık sayısını seçin:</b>"
        )

        # If started from menu, update previous message to remove old buttons
        if message_id:
            confirm_msg = f"⏳ <b>{icon} {b_name}</b> için soğuma sayacı başlatıldı. Aşağıdaki karttan sandık durumunu kaydedebilirsiniz."
            self.notifier.edit_message_text(confirm_msg, chat_id=chat_id, message_id=message_id, reply_markup=None)

        self.notifier.send_photo(photo_url=img_url, caption=caption, reply_markup=keyboard, target_chat_id=chat_id)

    def show_chest_count_options(self, chat_id: str, message_id: int, boss_key: str):
        b_info = BOSSES.get(boss_key, {})
        b_name = b_info.get("name", boss_key)
        icon = b_info.get("icon", "📦")
        img_url = get_boss_image(boss_key)

        chest_buttons = [
            [
                {"text": "📦 1 Adet", "callback_data": f"savechest:{boss_key}:1"},
                {"text": "📦 2 Adet", "callback_data": f"savechest:{boss_key}:2"},
                {"text": "📦 3 Adet", "callback_data": f"savechest:{boss_key}:3"},
            ],
            [
                {"text": "📦 4 Adet", "callback_data": f"savechest:{boss_key}:4"},
                {"text": "📦 5 Adet", "callback_data": f"savechest:{boss_key}:5"},
                {"text": "✏️ Farklı Sayı", "callback_data": f"manualchest:{boss_key}"},
            ],
            [
                {"text": "⬅️ Geri Dön", "callback_data": "chestcat:back"},
            ]
        ]
        keyboard = {"inline_keyboard": chest_buttons}
        caption = f"{icon} <b>{b_name} Sandığı</b>\n\nKaç adet düştüğünü seçin:"
        if message_id:
            self.notifier.edit_message_text(
                f"📦 <b>{b_name}</b> seçildi. Aşağıdaki karttan düşen sandık adedini belirleyin:",
                chat_id=chat_id,
                message_id=message_id,
                reply_markup=None
            )

        self.notifier.send_photo(photo_url=img_url, caption=caption, reply_markup=keyboard, target_chat_id=chat_id)

    # =========================================================================
    # CONVERSATIONAL STATE HANDLERS
    # =========================================================================

    def handle_state_chest_count(self, chat_id: str, text: str, data: dict):
        boss_key = data.get("boss_key", "")
        b_info = BOSSES.get(boss_key, {})
        b_name = b_info.get("name", boss_key)
        img_url = get_boss_image(boss_key)

        try:
            count = int(text.strip())
            if count <= 0:
                raise ValueError
        except ValueError:
            self.notifier.send_message("⚠️ Lütfen geçerli bir pozitif sayı yazın (Örn: <code>5</code>):", target_chat_id=chat_id)
            return

        clear_user_state(chat_id)
        res = add_chest_drop(chat_id, boss_key, b_name, count)
        caption = (
            f"✅ <b>{count} adet {b_name} Sandığı</b> kaydedildi!\n\n"
            f"📅 <b>Bugünkü Toplam:</b> {res['today_total']} adet\n"
            f"🏆 <b>Tüm Zamanlar:</b> {res['all_time_total']} adet\n\n"
            f"<i>Raporları görüntülemek için /rapor yazabilirsiniz.</i>"
        )
        self.notifier.send_photo(photo_url=img_url, caption=caption, target_chat_id=chat_id)

    def handle_state_report_days(self, chat_id: str, text: str):
        try:
            days = int(text.strip())
            if days <= 0:
                raise ValueError
        except ValueError:
            self.notifier.send_message("⚠️ Lütfen geçerli bir gün sayısı yazın (Örn: <code>3</code>):", target_chat_id=chat_id)
            return

        clear_user_state(chat_id)
        self.send_report(chat_id, days=days)
