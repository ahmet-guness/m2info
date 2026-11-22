import sys
import time
from datetime import datetime, timezone, timedelta

from config import get_config, DEFAULT_TRACKED_EVENTS
from database import (
    init_db,
    add_boss_timer,
    get_active_timers,
    get_expired_timers,
    mark_timer_notified,
    cancel_timer,
    add_chest_drop,
    get_chest_report,
    get_user_favorites,
    toggle_user_favorite,
    save_calendar_events,
    get_today_events,
    get_tomorrow_events,
    get_upcoming_events,
    get_month_events,
    get_latest_calendar_meta,
    get_starting_events_now,
    mark_calendar_event_notified
)
from boss_data import BOSSES, BOSS_CATEGORIES, get_boss_image
from calendar_scraper import discover_latest_calendar_thread, parse_calendar_from_thread, sync_event_calendar, is_tracked_event
from notifier import TelegramNotifier
from telegram_bot import TelegramBotListener
from scraper import classify_board_910_item, parse_happy_hour_details
from server_status import GStatusChecker

TURKEY_TZ = timezone(timedelta(hours=3))

def test_complete_notification_chain():
    print("==================================================================")
    print("🔍 METİN2 BİLDİRİM VE ÇALIŞMA ZİNCİRİ DETAYLI SİSTEM KONTROLÜ")
    print("==================================================================")

    # -------------------------------------------------------------
    # Mocking Notifier for Verification
    # -------------------------------------------------------------
    sent_messages = []
    sent_photos = []
    edited_messages = []

    notifier = TelegramNotifier("TEST_TOKEN", "123456789")

    def mock_send_message(text, parse_mode="HTML", reply_markup=None, target_chat_id=None, disable_preview=True):
        entry = {"text": text, "reply_markup": reply_markup, "target_chat_id": target_chat_id}
        sent_messages.append(entry)
        return {"ok": True, "result": {"message_id": len(sent_messages) + 100}}

    def mock_send_photo(photo_url, caption="", parse_mode="HTML", reply_markup=None, target_chat_id=None):
        entry = {"photo_url": photo_url, "caption": caption, "reply_markup": reply_markup, "target_chat_id": target_chat_id}
        sent_photos.append(entry)
        return {"ok": True, "result": {"message_id": len(sent_photos) + 200}}

    def mock_edit_message_text(text, chat_id, message_id, reply_markup=None):
        entry = {"text": text, "chat_id": chat_id, "message_id": message_id, "reply_markup": reply_markup}
        edited_messages.append(entry)
        return True

    def mock_edit_message_caption(caption, chat_id, message_id, reply_markup=None):
        entry = {"caption": caption, "chat_id": chat_id, "message_id": message_id, "reply_markup": reply_markup}
        edited_messages.append(entry)
        return True

    notifier.send_message = mock_send_message
    notifier.send_photo = mock_send_photo
    notifier.edit_message_text = mock_edit_message_text
    notifier.edit_message_caption = mock_edit_message_caption

    init_db()

    # =============================================================
    # ZİNCİR 1: HAPPY HOUR BİLDİRİMİ VE BİTİŞ ALARMI
    # =============================================================
    print("\n[ZİNCİR 1/7] Mutlu Saatler (Happy Hour) Bildirim Akışı...")
    test_hh = {
        "id": "hh_999",
        "title": "%35 Mutlu Saatler!",
        "link": "https://board.tr.metin2.gameforge.com/thread/test-hh",
        "pub_date": "22.11.2026 14:00",
        "bonus": "%35",
        "start_str": "22 Kasım 2026 14:00",
        "end_str": "22 Kasım 2026 23:59",
        "description": "Markette ekstra %35 bonus fırsatını kaçırmayın!"
    }
    sent_ok = notifier.notify_happy_hour(test_hh)
    assert sent_ok is True
    assert "%35" in sent_messages[-1]["text"]
    assert "MUTLU SAATLER" in sent_messages[-1]["text"]
    print("  ✓ Yeni Happy Hour duyuru mesajı başarıyla formatlandı ve iletildi.")

    sent_ended = notifier.notify_happy_hour_ended(test_hh)
    assert sent_ended is True
    assert "SONA ERDİ" in sent_messages[-1]["text"]
    print("  ✓ Happy Hour bitiş uyarısı başarıyla formatlandı ve iletildi.")

    # =============================================================
    # ZİNCİR 2: BAKIM VE SUNUCU HABERLERİ FİLTRESİ
    # =============================================================
    print("\n[ZİNCİR 2/7] Bakım ve Sunucu Haberleri Filtreleme Akışı...")
    
    # 2.1 Genel Bakım
    cat1 = classify_board_910_item("Haftalık Sunucu Bakımı", "Çarşamba günü bakım yapılacaktır.", "Bagjanamu")
    assert cat1 == "maintenance", f"Bakım sınıflandırılamadı: {cat1}"
    maint_item = {"title": "Haftalık Sunucu Bakımı", "link": "http://board/maint", "pub_date": "22.11.2026 10:00", "description": "Bakım detayları"}
    notifier.notify_maintenance(maint_item)
    assert "BAKIM" in sent_messages[-1]["text"]
    print("  ✓ Genel bakım duyurusu başarıyla algılandı ve bildirildi.")

    # 2.2 Bagjanamu Özel Duyurusu
    cat2 = classify_board_910_item("Bagjanamu Sunucusu Hakkında", "Sunucuya özel droplar aktif edildi.", "Bagjanamu")
    assert cat2 == "tracked_server", f"Bagjanamu duyurusu algılanamadı: {cat2}"
    news_item = {"title": "Bagjanamu Özel", "link": "http://board/bagj", "pub_date": "22.11.2026 12:00", "description": "Özel drop"}
    notifier.notify_server_news(news_item, server_name="Bagjanamu")
    assert "BAGJANAMU" in sent_messages[-1]["text"]
    print("  ✓ Bagjanamu'ya özel sunucu haberi başarıyla algılandı ve bildirildi.")

    # 2.3 Diğer Sunucu (Filtrelenmeli)
    cat3 = classify_board_910_item("Barbaros Sunucusu Birleşimi", "Barbaros sunucusu birleştirilecektir.", "Bagjanamu")
    assert cat3 == "skip", f"Diğer sunucu filtrelenemedi: {cat3}"
    print("  ✓ Diğer sunuculara (Barbaros, Marmara vs.) ait haberler sessizce filtrelendi.")

    # =============================================================
    # ZİNCİR 3: G-STATUS CANLI DURUM TAKİBİ
    # =============================================================
    print("\n[ZİNCİR 3/7] G-Status Canlı Sunucu Durumu Bildirim Akışı...")
    status_sample = {
        "server_name": "Bagjanamu",
        "status": "OFFLINE",
        "login_online": False,
        "online_count": 0,
        "total_count": 6,
        "checked_at": "22.11.2026 15:00",
        "last_offline": "22.11.2026 15:00"
    }
    notifier.notify_server_status_down(status_sample)
    assert "KAPANDI" in sent_messages[-1]["text"]
    print("  ✓ Sunucu kapanma (bakım başlangıç) alarmı iletildi.")

    status_sample["status"] = "ONLINE"
    status_sample["login_online"] = True
    status_sample["online_count"] = 6
    notifier.notify_server_status_up(status_sample)
    assert "TEKRAR AÇILDI" in sent_messages[-1]["text"]
    print("  ✓ Sunucu açılma (bakım bitiş) alarmı iletildi.")

    # =============================================================
    # ZİNCİR 4: BOSS SOĞUMA VE FOTOĞRAFLI SANDIK SİSTEMİ
    # =============================================================
    print("\n[ZİNCİR 4/7] Boss Soğuma Sayacı ve Fotoğraflı Sandık Akışı...")
    chat_id = "test_user_777"
    
    # 4.1 Boss Timer Başlatma
    add_boss_timer(chat_id, "nemere", "Nemere", 14400)
    timers = get_active_timers(chat_id)
    assert len(timers) >= 1
    assert timers[0]["boss_key"] == "nemere"
    print(f"  ✓ Nemere sayacı başlatıldı (Kalan: {timers[0]['remaining_str']}, Bitiş: {timers[0]['end_time_str']}).")

    # 4.2 Sandık Ekleme ve İstatistik Doğrulama
    add_res = add_chest_drop(chat_id, "nemere", "Nemere", 3)
    assert add_res["added"] == 3
    print(f"  ✓ 3 adet Nemere sandığı eklendi (Bugünkü toplam: {add_res['today_total']}).")

    # 4.3 Sandık Raporu Doğrulama
    rep_today = get_chest_report(chat_id, days=0)
    assert rep_today["grand_total"] >= 3
    print(f"  ✓ Günlük rapor başarıyla hesaplandı (Toplam: {rep_today['grand_total']} sandık).")

    # 4.4 Boss Cooldown Süresi Bitti Bildirimi (Fotoğraflı Kart)
    img_nemere = get_boss_image("nemere")
    assert img_nemere is not None and "nemere" in img_nemere.lower()
    notifier.notify_boss_cooldown_expired(chat_id, "Nemere", "4 saat", photo_url=img_nemere)
    assert "BOSS SOĞUMA SÜRESİ BİTTİ" in sent_photos[-1]["caption"]
    assert sent_photos[-1]["target_chat_id"] == chat_id
    print("  ✓ Nemere soğuma süresi bitti alarmı fotoğraflı olarak doğru chat'e iletildi.")

    # =============================================================
    # ZİNCİR 5: FAVORİ BOSS SİSTEMİ
    # =============================================================
    print("\n[ZİNCİR 5/7] Favori Boss Yönetimi ve Hızlı Başlatma Akışı...")
    toggle_user_favorite(chat_id, "razador")
    toggle_user_favorite(chat_id, "bagjanamu")
    favs = get_user_favorites(chat_id)
    assert "razador" in favs and "bagjanamu" in favs
    print(f"  ✓ Favori bosslar kaydedildi: {favs}")

    bot_listener = TelegramBotListener("TEST_TOKEN", notifier)
    bot_listener.cmd_bosscd(chat_id)
    assert "FAVORİ BOSSLARINIZ" in sent_messages[-1]["text"]
    first_row = [btn["text"] for btn in sent_messages[-1]["reply_markup"]["inline_keyboard"][0]]
    assert any("Razadör" in b or "Bagjanamu" in b for b in first_row)
    print("  ✓ /bosscd menüsünde favoriler en üstte tek tıkla başlatma butonu olarak listelendi.")

    # =============================================================
    # ZİNCİR 6: ETKİNLİK TAKVİMİ VE 8 ÖZEL ETKİNLİK FİLTRESİ
    # =============================================================
    print("\n[ZİNCİR 6/7] Etkinlik Takvimi ve 8 Etkinlik Filtre Akışı...")
    cfg = get_config()
    tracked_events = cfg["tracked_events"]
    assert len(tracked_events) == 8, f"Beklenen 8 etkinlik bulunamadı: {len(tracked_events)}"
    print(f"  ✓ Konfigürasyonda tanımlı 8 etkinlik mevcut:")
    for ev in tracked_events:
        print(f"    • {ev}")

    # Whitelist & Blacklist testi
    allowed_list = [
        "Kötü Ruh Kovma Kağıdı", "Cor Draconis", "Küçük Kutsama",
        "Nesneyi Efsunla", "Ay Işığı", "Balıkçılık", "Münzevi Tavsiyesi", "Envanter Genişletme"
    ]
    for name in allowed_list:
        assert is_tracked_event(name, tracked_events) is True, f"İzin verilmesi gereken etkinlik engellendi: {name}"

    blocked_list = [
        "Kırmızı Abanoz Sandık", "Pet Kitabı Sandığı", "Yeşil Ejderha Fasülyesi",
        "Geçit Bileti", "Süper Taş", "Nugget", "İnce Kumaş"
    ]
    for name in blocked_list:
        assert is_tracked_event(name, tracked_events) is False, f"Engellenmesi gereken etkinlik izin aldı: {name}"
    print("  ✓ Etkinlik filtre filtresi kusursuz çalışıyor (%100 doğruluk).")

    # =============================================================
    # ZİNCİR 7: CANLI ETKİNLİK BAŞLANGIÇ UYARISI & GECE DEVİR GÜVENLİĞİ
    # =============================================================
    print("\n[ZİNCİR 7/7] Canlı Etkinlik Başlangıç & Zaman Doğrulama Akışı...")
    
    # Veritabanına test etkinliği ekle (şu an aktif olan)
    now_dt = datetime.now(tz=TURKEY_TZ)
    today_str = now_dt.strftime("%Y-%m-%d")
    sh = now_dt.hour
    eh = (sh + 2) % 24
    
    # 7.1 Filtrelenmesi gereken etkinlik testi (Kırmızı Abanoz Sandık)
    mock_events = [
        {
            "date": today_str,
            "display_date": f"{today_str} Test Günü",
            "event_slot": 1,
            "event_name": "Kırmızı Abanoz Sandık",
            "cet_time": "14:00-16:00",
            "tsi_time": f"{sh:02d}:00-{eh:02d}:00",
            "tsi_start": f"{sh:02d}:00",
            "tsi_end": f"{eh:02d}:00"
        },
        # 7.2 Bildirimi gönderilmesi gereken etkinlik testi (Cor Draconis)
        {
            "date": today_str,
            "display_date": f"{today_str} Test Günü",
            "event_slot": 2,
            "event_name": "Cor Draconis",
            "cet_time": "14:00-16:00",
            "tsi_time": f"{sh:02d}:00-{eh:02d}:00",
            "tsi_start": f"{sh:02d}:00",
            "tsi_end": f"{eh:02d}:00"
        }
    ]
    save_calendar_events("http://board/test-cal", "Test Takvim", mock_events)
    
    # get_starting_events_now fonksiyonunu test et
    active_now = get_starting_events_now()
    assert len(active_now) == 2, f"Aktif etkinlikler bulunamadı: {active_now}"
    
    # Bot simülasyonu: Kırmızı Abanoz elenmeli, Cor Draconis bildirim atmalı
    sent_before = len(sent_messages)
    for ev in active_now:
        ev_name = ev["event_name"]
        if is_tracked_event(ev_name, tracked_events):
            notifier.notify_event_starting(ev)
            mark_calendar_event_notified(ev["id"])
        else:
            mark_calendar_event_notified(ev["id"])

    # Yalnızca Cor Draconis için mesaj gitmeli (+1 mesaj)
    assert len(sent_messages) == sent_before + 1
    assert "Cor Draconis" in sent_messages[-1]["text"]
    assert "Kırmızı Abanoz Sandık" not in sent_messages[-1]["text"]
    print("  ✓ Canlı başlangıçta Kırmızı Abanoz Sandık sessizce elendi, Cor Draconis başarıyla bildirildi.")

    # İkinci döngüde bildirim tekrarlanmamalı (notified = 1)
    active_second_run = get_starting_events_now()
    assert len(active_second_run) == 0
    print("  ✓ Bildirimi gönderilen etkinlikler tekrar bildirilmedi (Mükerrer bildirim engellendi).")

    # Temizlik
    cancel_timer(chat_id, "nemere")
    toggle_user_favorite(chat_id, "razador")
    toggle_user_favorite(chat_id, "bagjanamu")

    # Takvimi resmi foruma geri eşitle
    sync_event_calendar()

    print("\n==================================================================")
    print("🎉 TÜM BİLDİRİM ZİNCİRLERİ VE AKIŞLAR EKSİKSİZ VE HATASIZ DOĞRULANDI!")
    print("==================================================================")

if __name__ == "__main__":
    test_complete_notification_chain()
