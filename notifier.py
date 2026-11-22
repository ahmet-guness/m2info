import html
import json
import logging
import ssl
import urllib.parse
import urllib.request

logger = logging.getLogger("Metin2Bot")


class TelegramNotifier:
    def __init__(self, bot_token: str, chat_id: str):
        self.bot_token = bot_token
        self.chat_id = str(chat_id)
        self.api_base = f"https://api.telegram.org/bot{self.bot_token}"

    def is_configured(self) -> bool:
        return bool(self.bot_token and self.chat_id)

    def escape_html(self, text: str) -> str:
        """Escape text for Telegram HTML parse mode."""
        if not text:
            return ""
        return html.escape(str(text), quote=False)

    def escape_attr(self, text: str) -> str:
        """Escape attribute (like href) for Telegram HTML."""
        if not text:
            return ""
        return html.escape(str(text), quote=True)

    def send_message(self, text: str, parse_mode: str = "HTML", disable_preview: bool = False,
                     reply_markup: dict = None, target_chat_id: str = None) -> dict:
        """Send message via Telegram Bot API using standard library."""
        if not self.is_configured():
            logger.error("Telegram bot token veya chat_id ayarlanmamış!")
            return {}

        endpoint = f"{self.api_base}/sendMessage"
        payload = {
            "chat_id": str(target_chat_id or self.chat_id),
            "text": text,
            "parse_mode": parse_mode,
            "disable_web_page_preview": disable_preview,
        }
        if reply_markup:
            payload["reply_markup"] = reply_markup

        try:
            data = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(
                endpoint,
                data=data,
                headers={"Content-Type": "application/json"}
            )
            ctx = ssl.create_default_context()
            with urllib.request.urlopen(req, context=ctx, timeout=15) as resp:
                resp_data = json.loads(resp.read().decode("utf-8"))
                if resp_data.get("ok"):
                    return resp_data.get("result", {})
                else:
                    logger.error(f"Telegram API hatası: {resp_data}")
                    return {}
        except urllib.error.HTTPError as e:
            try:
                err_body = e.read().decode("utf-8")
                logger.error(f"Telegram HTTP {e.code} Hatası: {err_body}")
            except Exception:
                logger.error(f"Telegram HTTP {e.code} Hatası: {e.reason}")
            return {}
        except Exception as e:
            logger.error(f"Telegram mesajı gönderilemedi: {e}")
            return {}

    def send_photo(self, photo_url: str, caption: str, parse_mode: str = "HTML",
                   reply_markup: dict = None, target_chat_id: str = None) -> dict:
        """Send a photo with caption and inline keyboard. Fallback to text if photo fails."""
        if not self.is_configured():
            return {}

        endpoint = f"{self.api_base}/sendPhoto"
        payload = {
            "chat_id": str(target_chat_id or self.chat_id),
            "photo": photo_url,
            "caption": caption,
            "parse_mode": parse_mode,
        }
        if reply_markup:
            payload["reply_markup"] = reply_markup

        try:
            data = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(
                endpoint,
                data=data,
                headers={"Content-Type": "application/json"}
            )
            ctx = ssl.create_default_context()
            with urllib.request.urlopen(req, context=ctx, timeout=15) as resp:
                resp_data = json.loads(resp.read().decode("utf-8"))
                if resp_data.get("ok"):
                    return resp_data.get("result", {})
                else:
                    logger.warning(f"sendPhoto hatası ({photo_url}), metin mesajına dönülüyor: {resp_data}")
        except Exception as e:
            logger.warning(f"sendPhoto başarısız oldu ({e}), normal metin gönderiliyor...")

        # Graceful fallback to text message
        return self.send_message(
            text=caption,
            parse_mode=parse_mode,
            reply_markup=reply_markup,
            target_chat_id=target_chat_id
        )

    def edit_message_text(self, text: str, chat_id: str, message_id: int, reply_markup: dict = None) -> bool:
        """Edit an existing message text and inline keyboard."""
        endpoint = f"{self.api_base}/editMessageText"
        payload = {
            "chat_id": str(chat_id),
            "message_id": message_id,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        }
        if reply_markup:
            payload["reply_markup"] = reply_markup

        try:
            data = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(endpoint, data=data, headers={"Content-Type": "application/json"})
            ctx = ssl.create_default_context()
            with urllib.request.urlopen(req, context=ctx, timeout=15) as resp:
                resp_data = json.loads(resp.read().decode("utf-8"))
                return resp_data.get("ok", False)
        except Exception as e:
            logger.warning(f"Telegram mesajı düzenlenemedi: {e}")
            return False

    def edit_message_caption(self, caption: str, chat_id: str, message_id: int, reply_markup: dict = None) -> bool:
        """Edit the caption of an existing photo message."""
        endpoint = f"{self.api_base}/editMessageCaption"
        payload = {
            "chat_id": str(chat_id),
            "message_id": message_id,
            "caption": caption,
            "parse_mode": "HTML",
        }
        if reply_markup:
            payload["reply_markup"] = reply_markup

        try:
            data = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(endpoint, data=data, headers={"Content-Type": "application/json"})
            ctx = ssl.create_default_context()
            with urllib.request.urlopen(req, context=ctx, timeout=15) as resp:
                resp_data = json.loads(resp.read().decode("utf-8"))
                if resp_data.get("ok"):
                    return True
        except Exception as e:
            logger.debug(f"editMessageCaption başarısız ({e}), editMessageText deneniyor...")

        # Fallback to edit_message_text in case message was text
        return self.edit_message_text(text=caption, chat_id=chat_id, message_id=message_id, reply_markup=reply_markup)

    def delete_message(self, chat_id: str, message_id: int) -> bool:
        """Delete a message via Telegram API."""
        if not self.is_configured():
            return False
        endpoint = f"{self.api_base}/deleteMessage"
        payload = {
            "chat_id": str(chat_id),
            "message_id": message_id,
        }
        try:
            data = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(endpoint, data=data, headers={"Content-Type": "application/json"})
            ctx = ssl.create_default_context()
            with urllib.request.urlopen(req, context=ctx, timeout=10) as resp:
                resp_data = json.loads(resp.read().decode("utf-8"))
                return resp_data.get("ok", False)
        except Exception as e:
            logger.debug(f"deleteMessage hatası: {e}")
            return False

    def answer_callback_query(self, callback_query_id: str, text: str = None, show_alert: bool = False):
        """Acknowledge Telegram callback query to dismiss button loading spinner."""
        endpoint = f"{self.api_base}/answerCallbackQuery"
        payload = {"callback_query_id": callback_query_id}
        if text:
            payload["text"] = text
            payload["show_alert"] = show_alert

        try:
            data = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(endpoint, data=data, headers={"Content-Type": "application/json"})
            ctx = ssl.create_default_context()
            with urllib.request.urlopen(req, context=ctx, timeout=10) as resp:
                pass
        except Exception:
            pass

    # =========================================================================
    # FORUM & SERVER STATUS NOTIFICATIONS
    # =========================================================================

    def notify_happy_hour(self, item: dict) -> bool:
        """Format and send a decorated Happy Hour announcement message."""
        title = self.escape_html(item.get("title", "Mutlu Saatler"))
        link = self.escape_attr(item.get("link", ""))
        pub_date = self.escape_html(item.get("pub_date", ""))
        bonus = self.escape_html(item.get("bonus", "Belirtilmedi"))
        start_str = self.escape_html(item.get("start_str", "Belirtilmedi"))
        end_str = self.escape_html(item.get("end_str", "Belirtilmedi"))
        desc = item.get("description", "").strip()

        desc_snippet = ""
        if desc:
            if len(desc) > 380:
                desc_snippet = self.escape_html(desc[:380].strip()) + "..."
            else:
                desc_snippet = self.escape_html(desc)

        message = (
            "🔥 <b>METİN2</b> • <i>YENİ MUTLU SAATLER!</i>\n\n"
            f"<blockquote>🎁 <b>Bonus Oranı:</b> <code>{bonus}</code>\n"
            f"⏳ <b>Başlangıç:</b> <code>{start_str}</code>\n"
            f"⌛ <b>Bitiş Tarihi:</b> <code>{end_str}</code></blockquote>\n"
        )

        if pub_date:
            message += f"📅 <i>Duyuru: {pub_date}</i>\n"

        if desc_snippet:
            message += f"\n📝 <i>\"{desc_snippet}\"</i>\n"

        message += (
            "\n⚠️ <i>Market ekranında bonusun aktif olduğunu kontrol ediniz.</i>\n"
            f"🔗 <a href=\"{link}\"><b>Forum Konusunu Görüntüle</b></a>"
        )

        res = self.send_message(message, parse_mode="HTML", disable_preview=False)
        return bool(res)

    def notify_happy_hour_ended(self, item: dict) -> bool:
        """Format and send an alert when a Happy Hour expires."""
        title = self.escape_html(item.get("title", "Mutlu Saatler"))
        link = self.escape_attr(item.get("link", ""))
        bonus = self.escape_html(item.get("bonus", ""))
        end_str = self.escape_html(item.get("end_str", ""))

        header_title = f"{bonus} Mutlu Saatler" if bonus and bonus != "Belirtilmedi" else title

        message = (
            "🛑 <b>MUTLU SAATLER SONA ERDİ</b>\n\n"
            f"<blockquote>📌 <b>Kampanya:</b> <b>{header_title}</b>\n"
            f"⌛ <b>Bitiş Zamanı:</b> <code>{end_str}</code></blockquote>\n\n"
            "ℹ️ <i>Mutlu Saatler bonus süresi dolmuştur. Artık standart oranlar geçerlidir.</i>\n"
            f"🔗 <a href=\"{link}\"><b>İlgili Forum Konusu</b></a>"
        )

        res = self.send_message(message, parse_mode="HTML", disable_preview=False)
        return bool(res)

    def notify_maintenance(self, item: dict) -> bool:
        """Format and send a Maintenance announcement message."""
        title = self.escape_html(item.get("title", "Bakım Duyurusu"))
        link = self.escape_attr(item.get("link", ""))
        pub_date = self.escape_html(item.get("pub_date", ""))
        desc = item.get("description", "").strip()

        desc_snippet = ""
        if desc:
            if len(desc) > 400:
                desc_snippet = self.escape_html(desc[:400].strip()) + "..."
            else:
                desc_snippet = self.escape_html(desc)

        message = (
            "⚙️ <b>METİN2</b> • <i>BAKIM DUYURUSU</i>\n\n"
            f"<blockquote>📌 <b>Başlık:</b> <b>{title}</b>\n"
            f"📅 <b>Duyuru:</b> <code>{pub_date or 'Belirtilmedi'}</code></blockquote>\n"
        )

        if desc_snippet:
            message += f"\n📝 <i>\"{desc_snippet}\"</i>\n"

        message += (
            "\nℹ️ <i>Bakım süresince sunuculara erişim durdurulabilir. G-Status canlı durumu izlemektedir.</i>\n"
            f"🔗 <a href=\"{link}\"><b>Bakım Konusunu Görüntüle</b></a>"
        )

        res = self.send_message(message, parse_mode="HTML", disable_preview=False)
        return bool(res)

    def notify_server_news(self, item: dict, server_name: str = "Bagjanamu") -> bool:
        """Format and send a Server-specific announcement message (e.g. Bagjanamu)."""
        title = self.escape_html(item.get("title", f"{server_name} Duyurusu"))
        link = self.escape_attr(item.get("link", ""))
        pub_date = self.escape_html(item.get("pub_date", ""))
        desc = item.get("description", "").strip()

        desc_snippet = ""
        if desc:
            if len(desc) > 400:
                desc_snippet = self.escape_html(desc[:400].strip()) + "..."
            else:
                desc_snippet = self.escape_html(desc)

        server_upper = server_name.upper()

        message = (
            f"📢 <b>METİN2</b> • <i>{server_upper} DUYURUSU</i>\n\n"
            f"<blockquote>📌 <b>Başlık:</b> <b>{title}</b>\n"
            f"📅 <b>Duyuru:</b> <code>{pub_date or 'Belirtilmedi'}</code></blockquote>\n"
        )

        if desc_snippet:
            message += f"\n📝 <i>\"{desc_snippet}\"</i>\n"

        message += (
            f"\n🛡️ <i>Bu duyuru <b>{server_name}</b> sunucusuna özeldir.</i>\n"
            f"🔗 <a href=\"{link}\"><b>Sunucu Konusunu Görüntüle</b></a>"
        )

        res = self.send_message(message, parse_mode="HTML", disable_preview=False)
        return bool(res)

    def notify_server_status_down(self, info: dict) -> bool:
        """Alert when server goes offline / enters maintenance."""
        server = self.escape_html(info.get("server_name", "Bagjanamu"))
        server_upper = server.upper()
        now_str = self.escape_html(info.get("checked_at", ""))
        online_count = info.get("online_count", 0)
        total_count = info.get("total_count", 0)

        message = (
            f"🔴 <b>SUNUCU KAPANDI</b> • <i>{server_upper}</i>\n\n"
            f"<blockquote>⚠️ <b>Durum:</b> <code>OFFLINE (Çevrimdışı / Kapalı)</code>\n"
            f"📊 <b>Kanal Durumu:</b> <code>{online_count}/{total_count} Açık</code>\n"
            f"🕒 <b>Zaman:</b> <code>{now_str}</code></blockquote>\n\n"
            "⚠️ <i>Sunucu bakıma girdi veya bağlantı kesildi. Tekrar açıldığında anında bildirim gönderilecektir.</i>\n"
            "🌐 <a href=\"https://www.g-status.com/en-gb/game/metin2\"><b>Canlı G-Status Sayfası</b></a>"
        )
        res = self.send_message(message, parse_mode="HTML", disable_preview=False)
        return bool(res)

    def notify_server_status_up(self, info: dict) -> bool:
        """Alert when server comes back online / opens after maintenance."""
        server = self.escape_html(info.get("server_name", "Bagjanamu"))
        server_upper = server.upper()
        now_str = self.escape_html(info.get("checked_at", ""))
        online_count = info.get("online_count", 0)
        total_count = info.get("total_count", 0)

        message = (
            f"🟢 <b>SUNUCU TEKRAR AÇILDI</b> • <i>{server_upper}</i>\n\n"
            f"<blockquote>✅ <b>Durum:</b> <code>ONLINE (Çevrimiçi / Açık)</code>\n"
            f"🌐 <b>Kanal Durumu:</b> <code>{online_count}/{total_count} Kanal Aktif</code>\n"
            f"🕒 <b>Zaman:</b> <code>{now_str}</code></blockquote>\n\n"
            "⚔️ <i>Girişler ve oyun kanalları tekrar aktif! İyi oyunlar dileriz.</i>\n"
            "🌐 <a href=\"https://www.g-status.com/en-gb/game/metin2\"><b>Canlı G-Status Sayfası</b></a>"
        )
        res = self.send_message(message, parse_mode="HTML", disable_preview=False)
        return bool(res)

    # =========================================================================
    # BOSS COOLDOWN EXPIRED ALERT (WITH PHOTO SUPPORT)
    # =========================================================================

    def notify_boss_cooldown_expired(self, chat_id: str, boss_name: str, display_cd: str, photo_url: str = None) -> bool:
        """Alert user when a boss cooldown has finished, with photo."""
        b_name = self.escape_html(boss_name)
        d_cd = self.escape_html(display_cd)

        caption = (
            f"🔔 <b>BOSS HAZIR!</b> • <i>{b_name.upper()}</i>\n\n"
            f"<blockquote>⏳ <b>Bekleme Süresi:</b> <code>{d_cd}</code> tamamlandı!\n"
            f"⚔️ <b>{b_name}</b> şu anda hazır, gidip kesebilirsiniz.</blockquote>\n\n"
            "👉 <i>Tekrar kestiğinizde /bosscd ile yeni sayaç başlatabilirsiniz.</i>"
        )

        if photo_url:
            res = self.send_photo(photo_url=photo_url, caption=caption, parse_mode="HTML", target_chat_id=chat_id)
        else:
            res = self.send_message(text=caption, parse_mode="HTML", target_chat_id=chat_id)

        return bool(res)

    def notify_event_starting(self, event: dict) -> bool:
        """Send an announcement when a scheduled daily event starts."""
        ev_name = self.escape_html(event.get("event_name", ""))
        display_date = self.escape_html(event.get("display_date", ""))
        tsi_time = self.escape_html(event.get("tsi_time", ""))
        cet_time = self.escape_html(event.get("cet_time", ""))

        message = (
            "🎁 <b>METİN2 ETKİNLİK BAŞLADI!</b>\n\n"
            f"<blockquote>🌟 <b>Etkinlik:</b> <b>{ev_name}</b>\n"
            f"📅 <b>Tarih:</b> <code>{display_date}</code>\n"
            f"⏰ <b>Süre (TSİ):</b> <code>{tsi_time}</code>\n"
            f"🌍 <b>Avrupa:</b> <code>{cet_time}</code></blockquote>\n\n"
            "⚔️ <i>Drop etkinliği başladı! İyi droplar ve bol şanslar dileriz!</i>\n"
            "ℹ️ <i>Tüm takvim için /takvim yazabilirsiniz.</i>"
        )
        res = self.send_message(message, parse_mode="HTML")
        return bool(res)

    def send_test_message(self, tracked_server: str = "Bagjanamu") -> bool:
        """Send a test message to verify credentials."""
        text = (
            "🤖 <b>METİN2 BOTU AKTİF</b>\n\n"
            "<blockquote>✅ Telegram bildirim ayarlarınız eksiksiz şekilde çalışıyor.</blockquote>\n\n"
            "🔔 <b>Aktif Takip Başlıkları:</b>\n"
            "• 🔥 <b>Mutlu Saatler:</b> Yeni kampanya ve bitiş alarmı\n"
            "• ⚙️ <b>Tüm Bakım Duyuruları:</b> Forum duyuruları\n"
            f"• 🏰 <b>Sunucu Haberleri:</b> Sadece <b>{tracked_server}</b>\n"
            f"• 🌐 <b>Canlı Sunucu Takibi:</b> <b>{tracked_server}</b> g-status kapandı/açıldı\n"
            "• ⏳ <b>Boss & Sandık Takibi:</b> /bosscd, /kalan, /sandik, /rapor\n"
            "• 📅 <b>Etkinlik Takvimi:</b> /takvim\n\n"
            "🛡️ <i>Sistem hazır, komutları kullanmaya başlayabilirsiniz!</i>"
        )
        res = self.send_message(text, parse_mode="HTML")
        return bool(res)
