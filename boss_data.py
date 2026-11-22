# Metin2 Boss, Soğuma Süresi ve Görsel Tanımları

DEFAULT_BOSS_IMAGE = "https://www.metin2pvp.com.tr/attachments/1706109278814-png.392/"

BOSS_CATEGORIES = {
    "zindan": {
        "title": "🌋 Zindan & Ejderha Bossları",
        "bosses": ["nemere", "razador", "bagjanamu", "hidra", "cadisi", "kemik_surat"]
    },
    "ochao": {
        "title": "🏯 Ochao & Büyülü Orman",
        "bosses": ["entai", "ochao_muhafiz", "guclu_ochao_muhafiz", "guclu_ochao_duk", "karanlik_lider"]
    },
    "orman_col": {
        "title": "🌲 Orman & Çöl Bossları",
        "bosses": ["alev_krali", "dokuz_kuyruk", "sari_kaplan", "col_kaplumbagasi", "dev_col_kaplumbagasi", "agac_lordu", "zalim_kizil_reis"]
    },
    "general_diger": {
        "title": "💀 Generaller & Diğer Bosslar",
        "bosses": ["general_kappa", "general_istakoz", "lemur_prensi", "gnoll_lordu", "ork_reisi", "vahsi_yuzbasi", "mushu"]
    },
    "maymun": {
        "title": "🐒 Maymun Zindanları",
        "bosses": ["kaya_maymun", "yuruyen_maymun", "maymun_lordu"]
    }
}

BOSSES = {
    # 1. Zindan & Ejderha
    "nemere": {
        "name": "Nemere",
        "icon": "❄️",
        "cooldown_seconds": 4 * 3600,
        "display_cd": "4 saat",
        "image_url": "https://tr-wiki.metin2.gameforge.com/images/thumb/0/05/Nemere.png/300px-Nemere.png",
    },
    "razador": {
        "name": "Razadör",
        "icon": "🔥",
        "cooldown_seconds": 1 * 3600,
        "display_cd": "1 saat",
        "image_url": "https://tr-wiki.metin2.gameforge.com/images/thumb/0/07/Razad%C3%B6r.png/300px-Razad%C3%B6r.png",
    },
    "bagjanamu": {
        "name": "Bagjanamu",
        "icon": "👹",
        "cooldown_seconds": 2 * 3600,
        "display_cd": "2 saat",
        "image_url": "https://tr-wiki.metin2.gameforge.com/images/thumb/9/98/Bagjanamu.png/300px-Bagjanamu.png",
    },
    "hidra": {
        "name": "Hidra",
        "icon": "🐉",
        "cooldown_seconds": 20 * 60,
        "display_cd": "20 dakika",
        "image_url": "https://tr-wiki.metin2.gameforge.com/images/thumb/6/65/Hidra.png/450px-Hidra.png",
    },
    "cadisi": {
        "name": "Güçlü Buz Cadısı",
        "icon": "🧙‍♀️",
        "cooldown_seconds": 1 * 3600,
        "display_cd": "1 saat",
        "image_url": DEFAULT_BOSS_IMAGE,
    },
    "kemik_surat": {
        "name": "Kemik Surat",
        "icon": "💀",
        "cooldown_seconds": 1 * 3600,
        "display_cd": "1 saat",
        "image_url": DEFAULT_BOSS_IMAGE,
    },

    # 2. Ochao & Büyülü Orman
    "entai": {
        "name": "En-Tai Hükümdarı",
        "icon": "👑",
        "cooldown_seconds": 5 * 60,
        "display_cd": "5 dakika",
        "image_url": "https://tr-wiki.metin2.gameforge.com/images/thumb/c/cf/En-Tai_H%C3%BCk%C3%BCmdar%C4%B1.png/300px-En-Tai_H%C3%BCk%C3%BCmdar%C4%B1.png",
    },
    "ochao_muhafiz": {
        "name": "Ochao Muhafızı",
        "icon": "🛡️",
        "cooldown_seconds": 30 * 60,
        "display_cd": "30 dakika",
        "image_url": DEFAULT_BOSS_IMAGE,
    },
    "guclu_ochao_muhafiz": {
        "name": "Güçlü Ochao Muhafızı",
        "icon": "⚔️",
        "cooldown_seconds": 15 * 60,
        "display_cd": "15 dakika",
        "image_url": DEFAULT_BOSS_IMAGE,
    },
    "guclu_ochao_duk": {
        "name": "Güçlü Ochao Dükü",
        "icon": "🎖️",
        "cooldown_seconds": 30 * 60,
        "display_cd": "30 dakika",
        "image_url": DEFAULT_BOSS_IMAGE,
    },
    "karanlik_lider": {
        "name": "Karanlık Lider",
        "icon": "👤",
        "cooldown_seconds": 2 * 3600,
        "display_cd": "2 saat",
        "image_url": "https://tr-wiki.metin2.gameforge.com/images/thumb/c/c5/Karanl%C4%B1k_Lider.png/300px-Karanl%C4%B1k_Lider.png",
    },

    # 3. Orman & Çöl
    "alev_krali": {
        "name": "Alev Kralı",
        "icon": "🔥",
        "cooldown_seconds": 2 * 3600,
        "display_cd": "2 saat",
        "image_url": "https://tr-wiki.metin2.gameforge.com/images/4/4c/Alev_Kral.png",
    },
    "dokuz_kuyruk": {
        "name": "Dokuz Kuyruk",
        "icon": "🦊",
        "cooldown_seconds": 2 * 3600,
        "display_cd": "2 saat",
        "image_url": "https://tr-wiki.metin2.gameforge.com/images/thumb/6/6e/Dokuz_Kuyruk.png/300px-Dokuz_Kuyruk.png",
    },
    "sari_kaplan": {
        "name": "Sarı Kaplan Hayaleti",
        "icon": "🐅",
        "cooldown_seconds": 2 * 3600,
        "display_cd": "2 saat",
        "image_url": "https://tr-wiki.metin2.gameforge.com/images/thumb/2/27/Sar%C4%B1_Kaplan_Hayaleti.png/300px-Sar%C4%B1_Kaplan_Hayaleti.png",
    },
    "col_kaplumbagasi": {
        "name": "Çöl Kaplumbağası",
        "icon": "🐢",
        "cooldown_seconds": 2 * 3600,
        "display_cd": "2 saat",
        "image_url": DEFAULT_BOSS_IMAGE,
    },
    "dev_col_kaplumbagasi": {
        "name": "Dev Çöl Kaplumbağası",
        "icon": "🐢",
        "cooldown_seconds": 2 * 3600,
        "display_cd": "2–4 saat (2s)",
        "image_url": DEFAULT_BOSS_IMAGE,
    },
    "agac_lordu": {
        "name": "Hayalet Ağaç Lordu",
        "icon": "🌲",
        "cooldown_seconds": int(2.5 * 3600),
        "display_cd": "2 saat 30 dk",
        "image_url": DEFAULT_BOSS_IMAGE,
    },
    "zalim_kizil_reis": {
        "name": "Zalim Kızıl Reis",
        "icon": "👺",
        "cooldown_seconds": 1 * 3600,
        "display_cd": "1 saat",
        "image_url": DEFAULT_BOSS_IMAGE,
    },

    # 4. Generaller & Diğer
    "general_kappa": {
        "name": "General Kappa",
        "icon": "🐊",
        "cooldown_seconds": 1 * 3600,
        "display_cd": "1 saat",
        "image_url": DEFAULT_BOSS_IMAGE,
    },
    "general_istakoz": {
        "name": "General Istakoz",
        "icon": "🦞",
        "cooldown_seconds": 1 * 3600,
        "display_cd": "1 saat",
        "image_url": DEFAULT_BOSS_IMAGE,
    },
    "lemur_prensi": {
        "name": "Lemur Prensi",
        "icon": "🐒",
        "cooldown_seconds": 1 * 3600,
        "display_cd": "1 saat",
        "image_url": DEFAULT_BOSS_IMAGE,
    },
    "gnoll_lordu": {
        "name": "Gnoll Lordu",
        "icon": "🐺",
        "cooldown_seconds": 1 * 3600,
        "display_cd": "1 saat",
        "image_url": DEFAULT_BOSS_IMAGE,
    },
    "ork_reisi": {
        "name": "Ork Reisi",
        "icon": "🧌",
        "cooldown_seconds": 30 * 60,
        "display_cd": "30 dakika",
        "image_url": "https://tr-wiki.metin2.gameforge.com/images/thumb/f/f9/Ork_Reisi.png/300px-Ork_Reisi.png",
    },
    "vahsi_yuzbasi": {
        "name": "Vahşi Yüzbaşı",
        "icon": "🏹",
        "cooldown_seconds": 30 * 60,
        "display_cd": "30 dakika",
        "image_url": DEFAULT_BOSS_IMAGE,
    },
    "mushu": {
        "name": "Mu-Shu",
        "icon": "🦎",
        "cooldown_seconds": 60,
        "display_cd": "1 dakika",
        "image_url": DEFAULT_BOSS_IMAGE,
    },

    # 5. Maymun Zindanları
    "kaya_maymun": {
        "name": "Kaya Maymun",
        "icon": "🪨",
        "cooldown_seconds": 30 * 60,
        "display_cd": "30 dakika",
        "image_url": DEFAULT_BOSS_IMAGE,
    },
    "yuruyen_maymun": {
        "name": "Yürüyen Maymun",
        "icon": "🚶‍♂️",
        "cooldown_seconds": 30 * 60,
        "display_cd": "30 dakika",
        "image_url": DEFAULT_BOSS_IMAGE,
    },
    "maymun_lordu": {
        "name": "Maymun Lordu",
        "icon": "👑",
        "cooldown_seconds": 30 * 60,
        "display_cd": "30 dakika",
        "image_url": DEFAULT_BOSS_IMAGE,
    },
}


def get_boss_image(boss_key: str) -> str:
    """Get the image URL for a boss, fallback to default."""
    b = BOSSES.get(boss_key, {})
    return b.get("image_url") or DEFAULT_BOSS_IMAGE


def get_boss_by_name(query: str):
    """Fuzzy or exact match a boss name."""
    if not query:
        return None
    q = query.strip().lower()
    for key, data in BOSSES.items():
        if key == q or data["name"].lower() == q or q in data["name"].lower():
            return key, data
    return None
