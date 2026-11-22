import time
from database import (
    init_db,
    add_chest_drop,
    remove_chest_drop,
    undo_chest_drop,
    get_chest_report,
    get_user_recorded_bosses,
    set_user_state,
    get_user_state
)
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

def test_chest_reduction_features():
    init_db()
    mock_notifier = MockNotifier()
    bot = TelegramBotListener("TEST_TOKEN", mock_notifier)
    chat_id = f"test_chest_user_{int(time.time())}"

    print("--- 1. Test add_chest_drop and immediate 1-click Undo ---")
    res1 = add_chest_drop(chat_id, "nemere", "Nemere", 8)
    assert res1["today_total"] == 8
    assert res1["all_time_total"] == 8
    last_id = res1["last_id"]

    # Simulate clicking [ ↩️ Geri Al (-8) ] button
    query_undo = {
        "id": "q_undo",
        "message": {"chat": {"id": chat_id}, "message_id": 101},
        "data": f"undochest:nemere:{last_id}"
    }
    bot.handle_callback_query(query_undo)
    assert len(mock_notifier.edited_captions) >= 1
    assert "8 ADET NEMERE SANDIĞI GERİ ALINDI" in mock_notifier.edited_captions[-1]["caption"]
    assert "0 Adet" in mock_notifier.edited_captions[-1]["caption"] or "0 adet" in mock_notifier.edited_captions[-1]["caption"].lower()
    print("  ✓ [ ↩️ Geri Al (-8) ] butonuyla son eklenen 8 sandık başarıyla silindi ve kart güncellendi.")

    print("\n--- 2. Test /sandik nemere -2 (Negative Count via Command) ---")
    # Add 10 chests first
    add_chest_drop(chat_id, "nemere", "Nemere", 10)
    # User types /sandik nemere -3
    bot.handle_message({"chat": {"id": chat_id}, "text": "/sandik nemere -3"})
    last_msg = mock_notifier.sent_messages[-1]["text"]
    assert "3 ADET NEMERE SANDIĞI DÜŞÜRÜLDÜ" in last_msg
    assert "7 adet" in last_msg.lower()
    print("  ✓ /sandik nemere -3 komutu ile 3 sandık doğrudan düşürüldü.")

    print("\n--- 3. Test /sandiksil nemere 2 (Dedicated Reduction Command) ---")
    bot.handle_message({"chat": {"id": chat_id}, "text": "/sandiksil nemere 2"})
    last_msg = mock_notifier.sent_messages[-1]["text"]
    assert "2 ADET NEMERE SANDIĞI DÜŞÜRÜLDÜ" in last_msg
    assert "5 adet" in last_msg.lower()
    print("  ✓ /sandiksil nemere 2 komutu ile 2 sandık daha düşürüldü.")

    print("\n--- 4. Test interactive /sandiksil menu ---")
    bot.handle_message({"chat": {"id": chat_id}, "text": "/sandiksil"})
    last_msg = mock_notifier.sent_messages[-1]["text"]
    assert "SANDIK DÜŞÜRME / SİLME" in last_msg
    # Click Nemere in list
    bot.handle_callback_query({
        "id": "q_boss",
        "message": {"chat": {"id": chat_id}, "message_id": 102},
        "data": "reduceboss:nemere"
    })
    last_edited = mock_notifier.edited_texts[-1]["text"]
    assert "NEMERE SANDIK DÜŞÜRME" in last_edited
    # Click ➖ 1 Düşür
    bot.handle_callback_query({
        "id": "q_num",
        "message": {"chat": {"id": chat_id}, "message_id": 102},
        "data": "reducenum:nemere:1"
    })
    last_edited = mock_notifier.edited_texts[-1]["text"]
    assert "1 ADET NEMERE SANDIĞI DÜŞÜRÜLDÜ" in last_edited
    assert "4 adet" in last_edited.lower()
    print("  ✓ İnteraktif /sandiksil menüsünden [➖ 1 Düşür] butonuna basılarak sandık düşürüldü.")

    print("\n--- 5. Test floor limit (never negative) ---")
    # Attempt to reduce 100 chests when only 4 remain
    res_floor = remove_chest_drop(chat_id, "nemere", "Nemere", 100)
    assert res_floor["success"] is True
    assert res_floor["removed"] == 4  # capped to available total
    assert res_floor["all_time_total"] == 0
    print("  ✓ Kalan sandıktan fazla düşürülmek istendiğinde 0'ın altına inmesi engellendi.")

    print("\n--- 6. Test report after reduction ---")
    rep = get_chest_report(chat_id)
    assert rep["grand_total"] == 0
    assert len(rep["breakdown"]) == 0
    print("  ✓ Rapor sıfırlanmış sandıkları rapordan gizleyerek temiz toplam gösterdi.")

    print("\n=======================================================")
    print("🎉 SANDIK DÜŞÜRME VE GERİ ALMA TESTLERİ KUSURSUZ GEÇTİ!")
    print("=======================================================")

if __name__ == "__main__":
    test_chest_reduction_features()
