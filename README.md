# Metin2 Türkiye - Telegram Bildirim & Farm Asistanı Botu ⚡

Bu bot, [Metin2 Türkiye Resmi Forumu](https://board.tr.metin2.gameforge.com/)'ndaki duyuruları, **[G-Status Canlı Durum Sayfası](https://www.g-status.com/en-gb/game/metin2)**'nı ve **Boss Soğuma & Sandık Takip Sistemini** tek çatı altında birleştiren hepsi bir arada bir yardımcıdır.

---

## 🎯 Bot Neleri Yapar?

### 1. ⚔️ Boss Soğuma Süresi (Cooldown) & Favori Boss Takibi
- Sohbete `/bosscd` yazdığınızda interaktif butonlarla bosslar listelenir.
- ⭐ **Favori Bosslar:** Sık kestiğiniz bossları `/favori` komutuyla favorilere ekleyebilirsiniz. Favorileriniz `/bosscd` menüsünün en üstünde tek tıkla başlatma butonu olarak yer alır.
- Kestiğiniz bossu seçtiğiniz an bossun wiki görseliyle sayaç başlar.
- Soğuma süresi bittiğinde Telegram'dan anında fotoğraflı **"BOSS HAZIR!"** alarmı gelir.
- `/kalan` komutuyla dilediğiniz an bekleyen sayaçların ne kadar süresi kaldığını görebilirsiniz.

### 2. 📅 Marmara & Bagjanamu Resmi Etkinlik Takvimi
- Forumun **Oyun Event (Board 688)** bölümündeki güncel ayın Marmara & Bagjanamu etkinlik konusu otomatik olarak taranır ve HTML tablosu %100 doğrulukla okunur.
- `/takvim` komutuyla:
  - 🌟 **Bugünün Etkinlikleri:** Günün dropları, saatleri (TSİ ve Avrupa saati)
  - ➡️ **Yarının Etkinlikleri:** Bir sonraki günün programı
  - 🗓️ **Bu Hafta (7 Gün):** Yaklaşan haftalık etkinlik akışı
  - 📋 **Tüm Ay:** Ayın tamamındaki etkinlik listesi
- 📢 **Canlı Etkinlik Başlangıç Uyarısı:** Etkinlik saati geldiğinde (örn: 18:00 veya 22:00 TSİ) bot otomatik olarak *"METİN2 ETKİNLİK BAŞLADI!"* bildirimi gönderir.
  - 🎯 **Filtreli Bildirim:** Yalnızca seçtiğiniz değerli etkinlikler başladığında bildirim atılır (diğer etkinlikler spam yapmaz):
    1. **Kötü Ruh Kovma Kağıdı**
    2. **Cor Draconis**
    3. **Küçük Kutsama**
    4. **Nesneyi Efsunla**
    5. **Ay Işığı**
    6. **Balıkçılık**
    7. **Münzevi Tavsiyesi**
    8. **Envanter Genişletme**
- Dilediğinizde `/takvim yenile` ile anında foruma bağlanıp en güncel takvimi çekebilir, gerekirse `/takvim link <url>` ile özel konu linki tanımlayabilirsiniz.

### 3. 📦 Düşen Sandıkları Kaydetme & Raporlama
- Boss kesildikten sonra sayaç başlarken tek dokunuşla sandık ekleyebilirsiniz (`[+1]`, `[+2]`, `[+3]`, `[Sayı Yaz]`).
- İstediğiniz zaman `/sandik nemere 3` gibi kısayolla da sandık ekleyebilirsiniz.
- `/rapor` komutu ile:
  - 📅 **Bugün** düşen sandıklar
  - 🗓️ **Bu Hafta (Son 7 Gün)** düşen sandıklar
  - 📆 **Bu Ay (Son 30 Gün)** düşen sandıklar
  - 📊 **Tüm Zamanlar** toplamı
  - 🔢 **Özel Gün Sayısı** (Örn: `/rapor 3` yazarak son 3 günün raporu)  
  anında boss bazında sıralı döküm olarak listelenir.

### 3. 🔥 Mutlu Saatler (Happy Hour) Takibi
- Forumda yeni Happy Hour açıldığında başlangıç, bitiş ve bonus oranını bildirir.
- Happy Hour süresi dolduğunda otomatik olarak *"MUTLU SAATLER SONA ERDİ!"* uyarısı gönderir.

### 4. ⚙️ Bakım & Bagjanamu Sunucu Haberleri
- Forumdaki tüm bakım duyurularını bildirir.
- Sunucu haberlerinde yalnızca **Bagjanamu** sunucusunu ilgilendiren duyuruları iletir; diğerlerini filtreler.

### 5. 🌐 G-Status Canlı Sunucu Durumu
- `g-status.com` üzerinden Bagjanamu Login ve CH1-CH6 kanallarını düzenli izler.
- Sunucu bakıma girdiğinde (`🔴 KAPANDI`), bakım bitip açıldığında (`🟢 TEKRAR AÇILDI`) gecikmeden bildirim atar.

---

## 📋 Telegram Komut Listesi

| Komut | Açıklama |
| :--- | :--- |
| `/bosscd` | Boss seçim menüsünü açar (Favoriler en üstte tek tıkla başlar). |
| `/favori` | Sık kestiğiniz bossları favorilere ekleme/çıkarma menüsünü açar. |
| `/takvim` | Marmara & Bagjanamu günün ve haftanın etkinlik takvimini gösterir. |
| `/kalan` | Aktif tüm boss sayaçlarını ve kalan süreleri gösterir. |
| `/sandik` | Sandık ekleme menüsünü açar (veya `/sandik nemere 2`). |
| `/rapor` | Sandık raporu menüsünü açar (veya `/rapor 7`, `/rapor tum`). |
| `/yardim` | Tüm komutları ve kullanım rehberini listeler. |
| `/iptal` | Bekleyen sayı girişini iptal eder veya aktif boss sayacını sonlandırma menüsü sunar. |

---

## ⏱️ Tanımlı Bosslar ve Soğuma Süreleri

- **Nemere:** 4 saat
- **Bagjanamu:** 2 saat
- **Razadör:** 1 saat
- **Hidra:** 20 dakika
- **Güçlü Buz Cadısı:** 1 saat
- **Kemik Surat:** 1 saat
- **En-Tai Hükümdarı:** 5 dakika
- **Ochao Muhafızı:** 30 dakika
- **Güçlü Ochao Muhafızı:** 15 dakika
- **Güçlü Ochao Dükü:** 30 dakika
- **Karanlık Lider:** 2 saat
- **Alev Kralı:** 2 saat
- **Dokuz Kuyruk:** 2 saat
- **Sarı Kaplan Hayaleti:** 2 saat
- **Çöl Kaplumbağası:** 2 saat
- **Dev Çöl Kaplumbağası:** 2–4 saat (2s)
- **Hayalet Ağaç Lordu:** 2 saat 30 dakika
- **Zalim Kızıl Reis:** 1 saat
- **General Kappa:** 1 saat
- **General Istakoz:** 1 saat
- **Lemur Prensi:** 1 saat
- **Gnoll Lordu:** 1 saat
- **Ork Reisi:** 30 dakika
- **Vahşi Yüzbaşı:** 30 dakika
- **Mu-Shu:** 1 dakika
- **Kaya Maymun:** 30 dakika
- **Yürüyen Maymun:** 30 dakika
- **Maymun Lordu:** 30 dakika

---

## 💾 Veritabanı Güvenliği (SQLite)

- Tüm sayaçlar ve sandık düşüşleri `data/metin2.db` dosyasında SQLite ile tutulur.
- Tablolar `CREATE TABLE IF NOT EXISTS` mantığıyla oluşturulduğu için **verileriniz asla silinmez veya sıfırlanmaz.**
- Docker'da `./data:/app/data` volume bağlı olduğundan container güncellense bile verileriniz VPS diskinizde güvende kalır.

---

## 🚀 Çalıştırma

### Docker ile (Önerilen)
```bash
docker compose up -d
```

### Windows'ta Doğrudan
- `start.bat` dosyasına çift tıklayın.
