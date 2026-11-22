import time
from database import (
    init_db,
    add_boss_timer,
    get_active_timers,
    set_user_state,
    get_user_state,
    cancel_timer,
    add_chest_drop
)
from boss_data import BOSSES
from notifier import TelegramNotifier
from telegram_bot import TelegramBotListener

class MockNotifier(TelegramNotifier):
    def __init__(self):
        super().__init__("TEST_TOKEN", "12345")
        self.sent_messages = []
        self.sent_photos = []
        self.edited_captions = []
        self.edited_texts = []
        self.deleted_messages = []
        self.answered_callbacks = []

    def is_configured(self):
        return True

    def send_message(self, text, parse_mode="HTML", disable_preview=False, reply_markup=None, target_chat_id=None):
        msg = {
            "message_id": len(self.sent_messages) + len(self.sent_photos) + 1,
            "text": text,
            "target_chat_id": target_chat_id or self.chat_id,
            "reply_markup": reply_markup
        }
        self.sent_messages.append(msg)
        return msg

    def send_photo(self, photo_url, caption, parse_mode="HTML", reply_markup=None, target_chat_id=None):
        msg = {
            "message_id": len(self.sent_messages) + len(self.sent_photos) + 1,
            "photo_url": photo_url,
            "caption": caption,
            "target_chat_id": target_chat_id or self.chat_id,
            "reply_markup": reply_markup
        }
        self.sent_photos.append(msg)
        return msg

    def edit_message_caption(self, caption, chat_id, message_id, reply_markup=None):
        self.edited_captions.append({
            "caption": caption,
            "chat_id": chat_id,
            "message_id": message_id,
            "reply_markup": reply_markup
        })
        return True

    def edit_message_text(self, text, chat_id, message_id, reply_markup=None):
        self.edited_texts.append({
            "text": text,
            "chat_id": chat_id,
            "message_id": message_id,
            "reply_markup": reply_markup
        })
        return True

    def delete_message(self, chat_id, message_id):
        self.deleted_messages.append({"chat_id": chat_id, "message_id": message_id})
        return True

    def answer_callback_query(self, callback_query_id, text=None, show_alert=False):
        self.answered_callbacks.append({"id": callback_query_id, "text": text})
        return True

def run_tests():
    init_db()
    mock_notifier = MockNotifier()
    bot = TelegramBotListener("TEST_TOKEN", mock_notifier)
    chat_id = f"test_ui_{int(time.time())}"

    print("--- TEST 1: Manual Chest Entry & /iptal command ---")
    # Simulate clicking 'manualchest:nemere' on a photo card
    card_msg_id = 99
    query_manual = {
        "id": "q1",
        "message": {"chat": {"id": chat_id}, "message_id": card_msg_id},
        "data": "manualchest:nemere"
    }
    bot.handle_callback_query(query_manual)
    
    # State should be waiting_chest_count
    st, data = get_user_state(chat_id)
    assert st == "waiting_chest_count"
    assert data["boss_key"] == "nemere"
    assert len(mock_notifier.edited_captions) >= 1
    assert "NEMERE SANDIK GİRİŞİ" in mock_notifier.edited_captions[-1]["caption"]
    assert mock_notifier.edited_captions[-1]["reply_markup"]["inline_keyboard"][0][0]["callback_data"] == "cancel_state"

    # User types /iptal
    msg_iptal = {"chat": {"id": chat_id}, "text": "/iptal"}
    bot.handle_message(msg_iptal)

    # State must be cleared
    st2, _ = get_user_state(chat_id)
    assert st2 is None
    assert "iptal edildi" in mock_notifier.edited_captions[-1]["caption"]
    print("  ✓ /iptal text komutu ile sandık girişi başarıyla iptal edildi ve kart güncellendi.")

    print("\n--- TEST 2: Inline [ ❌ İptal Et ] Button Click (cancel_state) ---")
    # Simulate entering manual chest again
    bot.handle_callback_query(query_manual)
    st, _ = get_user_state(chat_id)
    assert st == "waiting_chest_count"

    # User taps inline [ ❌ İptal Et ] button
    query_cancel = {
        "id": "q2",
        "message": {"chat": {"id": chat_id}, "message_id": card_msg_id},
        "data": "cancel_state"
    }
    bot.handle_callback_query(query_cancel)
    st3, _ = get_user_state(chat_id)
    assert st3 is None
    assert "iptal edildi" in mock_notifier.edited_captions[-1]["caption"]
    print("  ✓ Inline [ ❌ İptal Et ] butonuna basılarak sayı girişi tek tıkla iptal edildi.")

    print("\n--- TEST 3: Writing Chest Number updates existing card (no duplicate photo) ---")
    # Simulate entering manual chest again
    bot.handle_callback_query(query_manual)
    msg_number = {"chat": {"id": chat_id}, "text": "8"}
    initial_photo_count = len(mock_notifier.sent_photos)
    bot.handle_message(msg_number)
    st4, _ = get_user_state(chat_id)
    assert st4 is None
    # Verify caption of existing photo was edited rather than sending a new photo
    assert len(mock_notifier.sent_photos) == initial_photo_count
    assert "8 ADET NEMERE SANDIĞI KAYDEDİLDİ" in mock_notifier.edited_captions[-1]["caption"]
    assert "Bugün" in mock_notifier.edited_captions[-1]["caption"]
    print("  ✓ Sayı girildiğinde mevcut fotoğraf kartının başlığı güncellendi (çift fotoğraf atılmadı).")

    print("\n--- TEST 4: Boss Cooldown Cancellation via Button ---")
    add_boss_timer(chat_id, "hidra", "Hidra", 1200)
    timers = get_active_timers(chat_id)
    assert any(t["boss_key"] == "hidra" for t in timers)

    # User taps cancel timer button
    query_canceltimer = {
        "id": "q3",
        "message": {"chat": {"id": chat_id}, "message_id": 105},
        "data": "canceltimer:hidra"
    }
    bot.handle_callback_query(query_canceltimer)
    timers_after = get_active_timers(chat_id)
    assert not any(t["boss_key"] == "hidra" for t in timers_after)
    assert "iptal edildi" in mock_notifier.edited_texts[-1]["text"].lower()
    print("  ✓ Hidra soğuma sayacı tek tıkla iptal edildi.")

    print("\n--- TEST 5: Close Menu Button (close_menu) ---")
    query_close = {
        "id": "q4",
        "message": {"chat": {"id": chat_id}, "message_id": 106},
        "data": "close_menu"
    }
    bot.handle_callback_query(query_close)
    assert any(d["message_id"] == 106 for d in mock_notifier.deleted_messages)
    print("  ✓ [ ❌ Kapat ] butonuna basıldığında menü başarıyla silindi/kapatıldı.")

    print("\n--- TEST 6: Report card has elite blockquote format (no broken horizontal lines) ---")
    bot.send_report(chat_id, days=None)
    last_msg = mock_notifier.sent_messages[-1]["text"]
    assert "<blockquote>" in last_msg
    assert "</blockquote>" in last_msg
    assert "━━━━" not in last_msg
    print("  ✓ Sandık raporu tertemiz, çizgilerden arındırılmış elit blockquote kart formatında üretildi.")

    print("\n=======================================================")
    print("🎉 TÜM UI VE İPTAL TESTLERİ BAŞARIYLA GEÇTİ!")
    print("=======================================================")

if __name__ == "__main__":
    run_tests()
