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

        cmd_word = text.split()[0].lower()

        # Handle cancellation FIRST before checking conversational states
        if cmd_word in ("/iptal", "iptal", "/cancel", "cancel"):
            self.cmd_iptal(chat_id)
            return

        state, state_data = get_user_state(chat_id)
        if state == "waiting_chest_count":
            self.handle_state_chest_count(chat_id, text, state_data)
            return
        elif state == "waiting_report_days":
            self.handle_state_report_days(chat_id, text, state_data)
            return

        cmd = cmd_word

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

    def cmd_iptal(self, chat_id: str):
        """Cancel any pending user action or offer cancelling active boss cooldowns."""
        state, state_data = get_user_state(chat_id)
        clear_user_state(chat_id)

        msg_id = state_data.get("message_id") if state_data else None
        boss_key = state_data.get("boss_key") if state_data else None

        if state == "waiting_chest_count":
            b_name = BOSSES.get(boss_key, {}).get("name", "Boss") if boss_key else "Boss"
            caption = (
                f"👌 <b>SAYAÇ ÇALIŞIYOR</b>\n\n"
                f"<blockquote>{b_name} için sandık girişi iptal edildi.\n"
                f"Soğuma süresi dolduğunda bildirim gönderilecektir.</blockquote>"
            )
            if msg_id:
                self.notifier.edit_message_caption(caption, chat_id=chat_id, message_id=msg_id, reply_markup=None)
            else:
                self.notifier.send_message(caption, target_chat_id=chat_id)
            return

        if state == "waiting_report_days":
            msg = (
                "❌ <b>RAPOR İPTAL EDİLDİ</b>\n\n"
                "<blockquote>Özel gün sayısı girişi iptal edildi.</blockquote>"
            )
            if msg_id:
                self.notifier.edit_message_text(msg, chat_id=chat_id, message_id=msg_id, reply_markup=None)
            else:
                self.notifier.send_message(msg, target_chat_id=chat_id)
            return

        # If no conversational state was waiting, check active timers
        timers = get_active_timers(chat_id)
        if timers:
            buttons = []
            for t in timers:
                buttons.append([{"text": f"🗑️ {t['boss_name']} Sayacını İptal Et", "callback_data": f"canceltimer:{t['boss_key']}"}])
            buttons.append([{"text": "❌ Kapat", "callback_data": "close_menu"}])
            msg = (
                "⏱️ <b>AKTİF BOSS SAYAÇLARI</b>\n\n"
                "<blockquote>Bekleyen bir veri girişi bulunmuyor.\n"
                "İptal etmek istediğiniz aktif boss sayacını seçebilirsiniz:</blockquote>"
            )
            self.notifier.send_message(msg, reply_markup={"inline_keyboard": buttons}, target_chat_id=chat_id)
        else:
            msg = (
                "❌ <b>İPTAL EDİLECEK İŞLEM YOK</b>\n\n"
                "<blockquote>Şu anda iptal edilecek bekleyen bir sayı girişi veya aktif boss sayacı bulunmuyor.</blockquote>"
            )
            self.notifier.send_message(msg, target_chat_id=chat_id)

    def cmd_help(self, chat_id: str):
        msg = (
            "⚔️ <b>METİN2 FARM & BİLDİRİM ASİSTANI</b>\n\n"
            "<blockquote>⏱️ <b>Boss Soğuma & Sayaç:</b>\n"
            "• <code>/bosscd</code> : Boss menüsü & fotoğraf kartı\n"
            "• <code>/favori</code> : Sık kestiğiniz bossları favorilere ekler\n"
            "• <code>/kalan</code> : Aktif sayaçları ve kalan süreleri gösterir\n\n"
            "📅 <b>Etkinlik Takvimi:</b>\n"
            "• <code>/takvim</code> : Marmara & Bagjanamu drop takvimi\n\n"
            "📦 <b>Sandık Takibi & Rapor:</b>\n"
            "• <code>/sandik</code> : Hızlı sandık ekleme menüsü\n"
            "• <code>/rapor</code> : Günlük, haftalık ve tüm zamanlar dökümü\n\n"
            "❌ <b>İptal & Kapatma:</b>\n"
            "• <code>/iptal</code> : Sayı girişini veya aktif boss sayacını iptal eder</blockquote>\n\n"
            "🛡️ <i>Otomatik Happy Hour, Bakım ve Sunucu Durum takibi 7/24 aktiftir.</i>"
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
        buttons.append([
            {"text": fav_btn_label, "callback_data": "fav:menu"},
            {"text": "❌ Kapat", "callback_data": "close_menu"}
        ])

        keyboard = {"inline_keyboard": buttons}
        msg = "⚔️ <b>BOSS SOĞUMA SÜRESİ BAŞLAT</b>\n\n"
        if favorites:
            msg += "<blockquote>⭐ <b>Favoriler:</b> Tek tıkla sayacı başlatın\n📁 <b>Kategoriler:</b> Listeden boss seçin</blockquote>"
        else:
            msg += "<blockquote>📁 Kestiğiniz bossun kategorisini seçin:</blockquote>"
        self.notifier.send_message(msg, reply_markup=keyboard, target_chat_id=chat_id)

    def cmd_favori(self, chat_id: str):
        """Open favorite boss selector."""
        self.show_favori_menu(chat_id)

    def cmd_kalan(self, chat_id: str):
        """List active boss cooldown timers."""
        timers = get_active_timers(chat_id)
        if not timers:
            msg = (
                "⏳ <b>AKTİF BOSS SAYACI YOK</b>\n\n"
                "<blockquote>Şu anda bekleyen bir boss sayacınız bulunmuyor.</blockquote>\n\n"
                "Yeni sayaç başlatmak için: <code>/bosscd</code>"
            )
            self.notifier.send_message(msg, target_chat_id=chat_id)
            return

        lines = ["⏳ <b>AKTİF BOSS SOĞUMA SÜRELERİ</b>\n"]
        b_lines = []
        buttons = []
        for t in timers:
            boss_info = BOSSES.get(t["boss_key"], {})
            icon = boss_info.get("icon", "⚔️")
            b_lines.append(f"{icon} <b>{t['boss_name']}</b>\n   ⏳ Kalan: <code>{t['remaining_str']}</code> (Bitiş: {t['end_time_str']} TSİ)")
            buttons.append([{"text": f"🗑️ {t['boss_name']} Sayacını İptal Et", "callback_data": f"canceltimer:{t['boss_key']}"}])

        buttons.append([
            {"text": "🔄 Yenile", "callback_data": "kalan:refresh"},
            {"text": "❌ Kapat", "callback_data": "close_menu"}
        ])

        lines.append(f"<blockquote>{chr(10).join(b_lines)}</blockquote>\n")
        lines.append("<i>Süre dolduğunda bot size fotoğraflı bildirim gönderecektir.</i>")
        keyboard = {"inline_keyboard": buttons}
        self.notifier.send_message("\n".join(lines), reply_markup=keyboard, target_chat_id=chat_id)

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
                    f"✅ <b>{count} ADET {b_data['name'].upper()} SANDIĞI KAYDEDİLDİ</b>\n\n"
                    f"<blockquote>📅 <b>Bugün:</b> <code>{res['today_total']} adet</code>\n"
                    f"🏆 <b>Tüm Zamanlar:</b> <code>{res['all_time_total']} adet</code></blockquote>\n\n"
                    f"<i>Raporları görüntülemek için /rapor yazabilirsiniz.</i>"
                )
                self.notifier.send_photo(photo_url=img, caption=caption, target_chat_id=chat_id)
                return

        buttons = []
        for cat_key, cat_data in BOSS_CATEGORIES.items():
            buttons.append([{"text": cat_data["title"], "callback_data": f"chestcat:{cat_key}"}])
        buttons.append([{"text": "❌ Kapat", "callback_data": "close_menu"}])

        keyboard = {"inline_keyboard": buttons}
        msg = "📦 <b>SANDIK EKLEME MENÜSÜ</b>\n\n<blockquote>Sandık eklemek istediğiniz bossun kategorisini seçin:</blockquote>"
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
                {"text": "🔢 Özel Gün Sayısı", "callback_data": "rep:custom"},
                {"text": "❌ Kapat", "callback_data": "close_menu"},
            ]
        ]
        keyboard = {"inline_keyboard": buttons}
        msg = "📊 <b>METİN2 SANDIK RAPORU</b>\n\n<blockquote>Raporlamak istediğiniz zaman aralığını seçin:</blockquote>"
        self.notifier.send_message(msg, reply_markup=keyboard, target_chat_id=chat_id)

    def send_report(self, chat_id: str, days: int = None, message_id: int = None):
        """Generate and display chest report with elite card styling."""
        rep = get_chest_report(chat_id, days=days)
        period = rep["period_name"]
        total = rep["grand_total"]
        breakdown = rep["breakdown"]

        msg = (
            f"📊 <b>METİN2 SANDIK RAPORU</b>\n"
            f"🗓️ <b>Dönem:</b> <code>{period.upper()}</code>\n\n"
        )

        if not breakdown or total == 0:
            msg += (
                "<blockquote>ℹ️ <i>Bu dönemde henüz kaydedilmiş bir sandık bulunmuyor.</i></blockquote>\n\n"
            )
        else:
            b_lines = []
            for boss_name, count in breakdown:
                matched = get_boss_by_name(boss_name)
                icon = matched[1].get("icon", "📦") if matched else "📦"
                b_lines.append(f"{icon} <b>{boss_name}:</b> <code>{count} adet</code>")

            msg += (
                f"<blockquote>{chr(10).join(b_lines)}\n\n"
                f"🏆 <b>Toplam Sandık:</b> <code>{total} adet</code></blockquote>\n\n"
            )

        msg += f"🕒 <i>Rapor Tarihi: {rep['generated_at']}</i>"

        back_kb = {"inline_keyboard": [
            [
                {"text": "🔄 Farklı Dönem Seç", "callback_data": "rep:menu"},
                {"text": "❌ Kapat", "callback_data": "close_menu"}
            ]
        ]}

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

        # 0. Close menu or cancel actions
        if data == "close_menu":
            deleted = self.notifier.delete_message(chat_id, message_id)
            if not deleted:
                self.notifier.edit_message_text("❌ <i>Menü kapatıldı.</i>", chat_id=chat_id, message_id=message_id, reply_markup=None)
            return

        if data == "cancel_state":
            state, state_data = get_user_state(chat_id)
            clear_user_state(chat_id)
            if state == "waiting_chest_count":
                boss_key = state_data.get("boss_key") if state_data else None
                b_name = BOSSES.get(boss_key, {}).get("name", "Boss") if boss_key else "Boss"
                caption = (
                    f"👌 <b>SAYAÇ ÇALIŞIYOR</b>\n\n"
                    f"<blockquote>{b_name} için sandık girişi iptal edildi.\n"
                    f"Soğuma süresi tamamlandığında bildirim gönderilecektir.</blockquote>"
                )
                self.notifier.edit_message_caption(caption, chat_id=chat_id, message_id=message_id, reply_markup=None)
            elif state == "waiting_report_days":
                msg = "❌ <b>Rapor günü girişi iptal edildi.</b>"
                self.notifier.edit_message_text(msg, chat_id=chat_id, message_id=message_id, reply_markup=None)
            else:
                self.notifier.edit_message_text("❌ <b>İşlem iptal edildi.</b>", chat_id=chat_id, message_id=message_id, reply_markup=None)
            return

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
                    {"text": "❌ Kapat", "callback_data": "close_menu"},
                ]
            ]
            keyboard = {"inline_keyboard": buttons}
            msg = "📊 <b>METİN2 SANDIK RAPORU</b>\n\n<blockquote>Raporlamak istediğiniz zaman aralığını seçin:</blockquote>"
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
                f"✅ <b>{count} ADET {b_name.upper()} SANDIĞI KAYDEDİLDİ</b>\n\n"
                f"<blockquote>📅 <b>Bugünkü Toplam:</b> <code>{res['today_total']} adet</code>\n"
                f"🏆 <b>Tüm Zamanlar:</b> <code>{res['all_time_total']} adet</code></blockquote>\n\n"
                f"<i>Raporları görüntülemek için /rapor yazabilirsiniz.</i>"
            )
            post_kb = {"inline_keyboard": [
                [
                    {"text": "📊 Raporu Aç", "callback_data": "rep:0"},
                    {"text": "❌ Kapat", "callback_data": "close_menu"}
                ]
            ]}
            self.notifier.edit_message_caption(caption, chat_id=chat_id, message_id=message_id, reply_markup=post_kb)
            return

        # 6. Manual chest count prompted
        if data.startswith("manualchest:"):
            boss_key = data.split(":", 1)[1]
            b_name = BOSSES.get(boss_key, {}).get("name", boss_key)
            set_user_state(chat_id, "waiting_chest_count", {"boss_key": boss_key, "message_id": message_id})
            caption = (
                f"✏️ <b>{b_name.upper()} SANDIK GİRİŞİ</b>\n\n"
                f"<blockquote>Lütfen kaç sandık düştüğünü sohbete rakam olarak yazın:\n"
                f"<i>Örn: <code>5</code> veya <code>12</code></i></blockquote>\n\n"
                f"<i>İptal etmek için aşağıdaki butona basabilir veya /iptal yazabilirsiniz.</i>"
            )
            cancel_kb = {"inline_keyboard": [[{"text": "❌ İptal Et", "callback_data": "cancel_state"}]]}
            self.notifier.edit_message_caption(caption, chat_id=chat_id, message_id=message_id, reply_markup=cancel_kb)
            return

        # 7. No chest dropped
        if data == "nochest":
            caption = (
                "👌 <b>SAYAÇ ÇALIŞIYOR</b>\n\n"
                "<blockquote>Sandık kaydedilmedi. Soğuma süresi dolduğunda bildirim gönderilecektir.</blockquote>"
            )
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
                    "🔢 <b>ÖZEL GÜN SAYISI GİRİŞİ</b>\n\n"
                    "<blockquote>Kaç günlük sandık raporu almak istiyorsunuz?\n"
                    "Lütfen gün sayısını sohbete yazın:\n"
                    "<i>Örn: <code>3</code> veya <code>14</code></i></blockquote>\n\n"
                    "<i>İptal etmek için aşağıdaki butona tıklayabilirsiniz.</i>"
                )
                cancel_kb = {"inline_keyboard": [
                    [{"text": "⬅️ Rapor Menüsüne Dön", "callback_data": "rep:menu"}],
                    [{"text": "❌ İptal Et", "callback_data": "cancel_state"}]
                ]}
                self.notifier.edit_message_text(msg, chat_id=chat_id, message_id=message_id, reply_markup=cancel_kb)
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

        # 11. Cancel boss cooldown timer
        if data.startswith("canceltimer:"):
            b_key = data.split(":", 1)[1]
            b_name = BOSSES.get(b_key, {}).get("name", b_key)
            cancelled = cancel_timer(chat_id, b_key)
            if cancelled:
                self.notifier.answer_callback_query(query_id, text=f"{b_name} sayacı iptal edildi!")
            else:
                self.notifier.answer_callback_query(query_id, text="Sayaç zaten bitmiş veya bulunamadı.")

            timers = get_active_timers(chat_id)
            if timers:
                lines = ["⏳ <b>AKTİF BOSS SOĞUMA SÜRELERİ</b>\n"]
                b_lines = []
                buttons = []
                for t in timers:
                    boss_info = BOSSES.get(t["boss_key"], {})
                    icon = boss_info.get("icon", "⚔️")
                    b_lines.append(f"{icon} <b>{t['boss_name']}</b>\n   ⏳ Kalan: <code>{t['remaining_str']}</code> (Bitiş: {t['end_time_str']} TSİ)")
                    buttons.append([{"text": f"🗑️ {t['boss_name']} Sayacını İptal Et", "callback_data": f"canceltimer:{t['boss_key']}"}])
                buttons.append([
                    {"text": "🔄 Yenile", "callback_data": "kalan:refresh"},
                    {"text": "❌ Kapat", "callback_data": "close_menu"}
                ])
                lines.append(f"<blockquote>{chr(10).join(b_lines)}</blockquote>\n")
                lines.append(f"🗑️ <i>{b_name} sayacı iptal edildi.</i>")
                self.notifier.edit_message_text("\n".join(lines), chat_id=chat_id, message_id=message_id, reply_markup={"inline_keyboard": buttons})
            else:
                msg = (
                    "⏳ <b>AKTİF BOSS SAYACI YOK</b>\n\n"
                    f"<blockquote>🗑️ <b>{b_name}</b> sayacı başarıyla iptal edildi.\n"
                    "Şu anda bekleyen başka bir boss sayacınız bulunmuyor.</blockquote>\n\n"
                    "Yeni sayaç başlatmak için: <code>/bosscd</code>"
                )
                self.notifier.edit_message_text(msg, chat_id=chat_id, message_id=message_id, reply_markup=None)
            return

        # 12. Refresh cooldown timers view
        if data == "kalan:refresh":
            timers = get_active_timers(chat_id)
            if not timers:
                msg = (
                    "⏳ <b>AKTİF BOSS SAYACI YOK</b>\n\n"
                    "<blockquote>Şu anda bekleyen bir boss sayacınız bulunmuyor.</blockquote>\n\n"
                    "Yeni sayaç başlatmak için: <code>/bosscd</code>"
                )
                self.notifier.edit_message_text(msg, chat_id=chat_id, message_id=message_id, reply_markup=None)
                return

            lines = ["⏳ <b>AKTİF BOSS SOĞUMA SÜRELERİ</b>\n"]
            b_lines = []
            buttons = []
            for t in timers:
                boss_info = BOSSES.get(t["boss_key"], {})
                icon = boss_info.get("icon", "⚔️")
                b_lines.append(f"{icon} <b>{t['boss_name']}</b>\n   ⏳ Kalan: <code>{t['remaining_str']}</code> (Bitiş: {t['end_time_str']} TSİ)")
                buttons.append([{"text": f"🗑️ {t['boss_name']} Sayacını İptal Et", "callback_data": f"canceltimer:{t['boss_key']}"}])

            buttons.append([
                {"text": "🔄 Yenile", "callback_data": "kalan:refresh"},
                {"text": "❌ Kapat", "callback_data": "close_menu"}
            ])
            lines.append(f"<blockquote>{chr(10).join(b_lines)}</blockquote>\n")
            lines.append("<i>Süre dolduğunda bot size fotoğraflı bildirim gönderecektir.</i>")
            self.notifier.edit_message_text("\n".join(lines), chat_id=chat_id, message_id=message_id, reply_markup={"inline_keyboard": buttons})
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
                msg += "<blockquote>⭐ <b>Favoriler:</b> Tek tıkla sayacı başlatın\n📁 <b>Kategoriler:</b> Listeden boss seçin</blockquote>"
            else:
                msg += "<blockquote>📁 Kestiğiniz bossun kategorisini seçin:</blockquote>"
        else:
            title = "📦 <b>SANDIK EKLEME MENÜSÜ</b>"
            msg = f"{title}\n\n<blockquote>Sandık eklemek istediğiniz bossun kategorisini seçin:</blockquote>"

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
            "<blockquote>Sık kestiğiniz bossları favorilere ekleyin.\n"
            "Favori bosslarınız <code>/bosscd</code> menüsünün en üstünde tek tıkla başlatma butonu olarak listelenir.</blockquote>\n\n"
            "<i>(Listeye eklemek veya çıkarmak için butona dokunun)</i>"
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
                        f"<blockquote>📌 <b>Başlık:</b> {res['title']}\n"
                        f"🔢 <b>Toplam Etkinlik:</b> <code>{res['count']} adet</code></blockquote>",
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
                        f"<blockquote>📌 <b>Başlık:</b> {res['title']}\n"
                        f"🔢 <b>Toplam Etkinlik:</b> <code>{res['count']} adet</code></blockquote>",
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
        """Render event calendar in specified view mode with elite card formatting."""
        meta = get_latest_calendar_meta()
        if not meta:
            sync_res = sync_event_calendar()
            if sync_res.get("success"):
                meta = get_latest_calendar_meta()

        if not meta:
            msg = (
                "📅 <b>MARMARA & BAGJANAMU ETKİNLİK TAKVİMİ</b>\n\n"
                "<blockquote>ℹ️ <i>Bu ay için forumda henüz bir etkinlik takvimi konusu bulunamadı veya yayınlanmadı.</i></blockquote>\n\n"
                "Yeniden kontrol etmek için: <code>/takvim yenile</code>"
            )
            if message_id:
                self.notifier.edit_message_text(msg, chat_id=chat_id, message_id=message_id)
            else:
                self.notifier.send_message(msg, target_chat_id=chat_id)
            return

        title_str = meta.get('thread_title', 'Marmara & Bagjanamu Etkinlik Takvimi')
        lines = [
            "📅 <b>MARMARA & BAGJANAMU ETKİNLİK TAKVİMİ</b>\n",
            f"<blockquote>📌 <b>Kaynak:</b> <i>{self.notifier.escape_html(title_str)}</i></blockquote>\n"
        ]

        if view_type == "today":
            today_events = get_today_events()
            tomorrow_events = get_tomorrow_events()

            if today_events:
                d_name = today_events[0].get("display_date", "Bugün")
                ev_lines = []
                for ev in today_events:
                    name = ev.get("event_name", "")
                    tsi = ev.get("tsi_time", "")
                    cet = ev.get("cet_time", "")
                    icon = "🔔" if is_tracked_event(name) else "▫️"
                    ev_lines.append(f"• ⏰ <code>{tsi} TSİ</code> {icon} <b>{name}</b>")
                lines.append(f"🌟 <b>BUGÜNÜN ETKİNLİKLERİ ({d_name}):</b>")
                lines.append(f"<blockquote>{chr(10).join(ev_lines)}</blockquote>\n")
            else:
                lines.append("🌟 <b>BUGÜNÜN ETKİNLİKLERİ:</b>\n<blockquote><i>Bugün için planlanmış drop etkinliği yok.</i></blockquote>\n")

            if tomorrow_events:
                d_name = tomorrow_events[0].get("display_date", "Yarın")
                ev_lines = []
                for ev in tomorrow_events:
                    name = ev.get("event_name", "")
                    tsi = ev.get("tsi_time", "")
                    icon = "🔔" if is_tracked_event(name) else "▫️"
                    ev_lines.append(f"• ⏰ <code>{tsi} TSİ</code> {icon} <b>{name}</b>")
                lines.append(f"➡️ <b>YARININ ETKİNLİKLERİ ({d_name}):</b>")
                lines.append(f"<blockquote>{chr(10).join(ev_lines)}</blockquote>\n")

        elif view_type == "tomorrow":
            tomorrow_events = get_tomorrow_events()
            if tomorrow_events:
                d_name = tomorrow_events[0].get("display_date", "Yarın")
                ev_lines = []
                for ev in tomorrow_events:
                    name = ev.get("event_name", "")
                    tsi = ev.get("tsi_time", "")
                    icon = "🔔" if is_tracked_event(name) else "▫️"
                    ev_lines.append(f"• ⏰ <code>{tsi} TSİ</code> {icon} <b>{name}</b>")
                lines.append(f"➡️ <b>YARININ ETKİNLİKLERİ ({d_name}):</b>")
                lines.append(f"<blockquote>{chr(10).join(ev_lines)}</blockquote>\n")
            else:
                lines.append("➡️ <b>YARININ ETKİNLİKLERİ:</b>\n<blockquote><i>Yarın için planlanmış etkinlik bulunmuyor.</i></blockquote>\n")

        elif view_type == "week":
            week_events = get_upcoming_events(7)
            lines.append("🗓️ <b>ÖNÜMÜZDEKİ 7 GÜNÜN ETKİNLİKLERİ:</b>\n")
            if week_events:
                current_d = None
                day_lines = []
                for ev in week_events:
                    d_str = ev.get("display_date", ev.get("event_date", ""))
                    if d_str != current_d:
                        if day_lines:
                            lines.append(f"<blockquote>{chr(10).join(day_lines)}</blockquote>\n")
                            day_lines = []
                        current_d = d_str
                        lines.append(f"📅 <b>{current_d}:</b>")
                    name = ev.get("event_name", "")
                    tsi = ev.get("tsi_time", "")
                    icon = "🔔" if is_tracked_event(name) else "▫️"
                    day_lines.append(f"• ⏰ <code>{tsi} TSİ</code> {icon} <b>{name}</b>")
                if day_lines:
                    lines.append(f"<blockquote>{chr(10).join(day_lines)}</blockquote>\n")
            else:
                lines.append("<blockquote><i>Yaklaşan etkinlik bulunamadı.</i></blockquote>\n")

        elif view_type == "month":
            month_events = get_month_events()
            lines.append("📋 <b>AYLIK TÜM ETKİNLİKLER:</b>\n")
            if month_events:
                current_d = None
                day_lines = []
                for ev in month_events:
                    d_str = ev.get("display_date", ev.get("event_date", ""))
                    if d_str != current_d:
                        if day_lines:
                            lines.append(f"<blockquote>{chr(10).join(day_lines)}</blockquote>\n")
                            day_lines = []
                        current_d = d_str
                        lines.append(f"📅 <b>{current_d}:</b>")
                    name = ev.get("event_name", "")
                    tsi = ev.get("tsi_time", "")
                    icon = "🔔" if is_tracked_event(name) else "▫️"
                    day_lines.append(f"• ⏰ <code>{tsi} TSİ</code> {icon} <b>{name}</b>")
                if day_lines:
                    lines.append(f"<blockquote>{chr(10).join(day_lines)}</blockquote>\n")
            else:
                lines.append("<blockquote><i>Bu ay için kayıtlı etkinlik yok.</i></blockquote>\n")

        lines.append(
            "<blockquote>🔔 <b>Otomatik Alarm:</b> Simgeli etkinlikler başladığında bot bildirim gönderir.</blockquote>\n"
            f"🔗 <a href=\"{meta.get('thread_url', '')}\"><b>Resmi Forum Takvim Konusu</b></a>"
        )

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
                {"text": "🔄 Yenile", "callback_data": "cal:refresh"},
                {"text": "❌ Kapat", "callback_data": "close_menu"},
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
        buttons.append([
            {"text": "⬅️ Kategorilere Dön", "callback_data": back_cb},
            {"text": "❌ Kapat", "callback_data": "close_menu"}
        ])

        keyboard = {"inline_keyboard": buttons}
        mode_title = "Soğuma Sayacı Başlat" if mode == "cd" else "Sandık Ekle"
        msg = (
            f"📁 <b>{cat_data['title'].upper()}</b>\n\n"
            f"<blockquote>🎯 <b>İşlem:</b> <code>{mode_title}</code>\n"
            f"Lütfen listeden bir boss seçiniz:</blockquote>"
        )
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
            f"⏳ <b>{icon} {b_name.upper()} SAYAÇ BAŞLATILDI</b>\n\n"
            f"<blockquote>⏱️ <b>Soğuma Süresi:</b> <code>{display_cd}</code>\n"
            f"🔔 <b>Hazır Olacağı Saat:</b> <code>{res['end_time_str']} (TSİ)</code></blockquote>\n\n"
            f"📦 <i>Düşen sandık sayısını aşağıdaki butonlardan seçin:</i>"
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
                {"text": "❌ Kapat", "callback_data": "close_menu"},
            ]
        ]
        keyboard = {"inline_keyboard": chest_buttons}
        caption = (
            f"{icon} <b>{b_name.upper()} SANDIĞI</b>\n\n"
            f"<blockquote>Kaç adet sandık düştüğünü seçiniz:</blockquote>"
        )
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
        orig_msg_id = data.get("message_id")

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
            f"✅ <b>{count} ADET {b_name.upper()} SANDIĞI KAYDEDİLDİ</b>\n\n"
            f"<blockquote>📅 <b>Bugünkü Toplam:</b> <code>{res['today_total']} adet</code>\n"
            f"🏆 <b>Tüm Zamanlar:</b> <code>{res['all_time_total']} adet</code></blockquote>\n\n"
            f"<i>Raporları görüntülemek için /rapor yazabilirsiniz.</i>"
        )
        post_kb = {"inline_keyboard": [
            [
                {"text": "📊 Raporu Aç", "callback_data": "rep:0"},
                {"text": "❌ Kapat", "callback_data": "close_menu"}
            ]
        ]}

        # If there's an active prompt photo message, update its caption so images aren't duplicated!
        if orig_msg_id:
            updated = self.notifier.edit_message_caption(caption, chat_id=chat_id, message_id=orig_msg_id, reply_markup=post_kb)
            if not updated:
                self.notifier.send_photo(photo_url=img_url, caption=caption, reply_markup=post_kb, target_chat_id=chat_id)
        else:
            self.notifier.send_photo(photo_url=img_url, caption=caption, reply_markup=post_kb, target_chat_id=chat_id)

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
