"""
ガチャ・タワーディフェンス共通のキャラクターカタログ。
静的データとしてここに定義し、所持状況だけをUserCharacterテーブルに保存する(achievements.pyと同じ設計方針)。
"""

RARITY_NAMES = {"common": "コモン", "rare": "レア", "epic": "エピック", "legendary": "レジェンダリー"}
RARITY_COLORS = {
    "common": ["#64748b", "#1e293b"],
    "rare": ["#2563eb", "#0c1a3d"],
    "epic": ["#9333ea", "#2e1065"],
    "legendary": ["#f59e0b", "#78350f"],
}
RARITY_WEIGHTS = {"common": 60, "rare": 27, "epic": 10, "legendary": 3}

ELEMENT_NAMES = {"fire": "火", "water": "水", "earth": "土", "wind": "風", "light": "光", "dark": "闇"}

# key: (表示名, レアリティ, 属性, アイコン, 攻撃力, 射程, 攻撃間隔(秒・小さいほど速い), 配置コスト, スプラッシュ範囲(0=単体), 説明)
CHARACTERS = {
    # ── コモン ──
    "flame_imp":    ("フレイムインプ", "common", "fire", "😈", 9, 2, 1.0, 20, 0, "小さな炎の悪魔。素直な火力が魅力。"),
    "aqua_sprite":  ("アクアスプライト", "common", "water", "💧", 7, 2, 0.8, 18, 0, "水の妖精。攻撃が速い。"),
    "rock_golem":   ("ロックゴーレム", "common", "earth", "🪨", 14, 1, 1.6, 25, 0, "岩の巨人。遅いが一撃が重い。"),
    "wind_fairy":   ("ウィンドフェアリー", "common", "wind", "🧚", 6, 2, 0.6, 16, 0, "風の妖精。とにかく手数が多い。"),
    "stone_archer": ("ストーンアーチャー", "common", "earth", "🏹", 10, 3, 1.1, 22, 0, "遠距離からの狙撃が得意。"),
    "forest_wolf":  ("フォレストウルフ", "common", "earth", "🐺", 11, 1, 0.9, 20, 0, "俊敏な狼。近距離で牙を剥く。"),
    "spark_bat":    ("スパークバット", "common", "wind", "🦇", 8, 2, 0.7, 18, 0, "電撃を帯びたコウモリ。"),
    "mud_crab":     ("マッドクラブ", "common", "water", "🦀", 12, 1, 1.3, 22, 0, "硬い甲羅で粘り強く戦う。"),

    # ── レア ──
    "flame_knight": ("フレイムナイト", "rare", "fire", "🔥", 18, 2, 1.0, 40, 0, "炎を纏う騎士。安定した火力。"),
    "ice_mage":     ("アイスメイジ", "rare", "water", "🧙", 16, 3, 1.2, 42, 1, "氷の魔法で範囲攻撃を放つ。"),
    "thunder_hawk": ("サンダーホーク", "rare", "wind", "🦅", 20, 2, 0.8, 45, 0, "雷を纏う鷹。素早く強い。"),
    "vine_witch":   ("ヴァインウィッチ", "rare", "earth", "🌿", 15, 2, 1.0, 38, 1, "つる草の魔女。絡め取って攻撃。"),
    "shadow_cat":   ("シャドウキャット", "rare", "dark", "🐈‍⬛", 19, 1, 0.7, 40, 0, "闇に紛れる俊敏な猫。"),
    "coral_guardian": ("コーラルガーディアン", "rare", "water", "🐚", 22, 1, 1.4, 44, 0, "サンゴの守護者。硬く重い一撃。"),

    # ── エピック ──
    "dragon_rider": ("ドラゴンライダー", "epic", "fire", "🐉", 32, 3, 1.0, 70, 1, "竜に乗る戦士。範囲炎攻撃。"),
    "phoenix":      ("フェニックス", "epic", "fire", "🦅", 30, 3, 0.8, 75, 0, "不死の炎鳥。高速で燃え盛る。"),
    "frost_titan":  ("フロストタイタン", "epic", "water", "🧊", 35, 2, 1.5, 72, 1, "氷の巨人。周囲を凍てつかせる。"),
    "storm_lord":   ("ストームロード", "epic", "wind", "🌩️", 33, 3, 0.9, 78, 1, "嵐を操る支配者。"),

    # ── レジェンダリー ──
    "celestial_empress": ("セレスティアルエンプレス", "legendary", "light", "👑", 50, 4, 1.0, 130, 1, "天を統べる女帝。全てを見通す一撃。"),
    "abyssal_king":      ("アビサルキング", "legendary", "dark", "👹", 55, 3, 1.2, 135, 1, "深淵より来たる王。絶大な力を誇る。"),
}


def rarity_of(key):
    return CHARACTERS[key][1]


def all_keys_by_rarity(rarity):
    return [k for k, v in CHARACTERS.items() if v[1] == rarity]


def character_info(key):
    """辞書形式でキャラクター情報を返す(テンプレート・JSONで扱いやすくするため)"""
    if key not in CHARACTERS:
        return None
    name, rarity, element, icon, atk, rng, speed, cost, splash, desc = CHARACTERS[key]
    return {
        "key": key, "name": name, "rarity": rarity, "rarity_label": RARITY_NAMES[rarity],
        "element": element, "element_label": ELEMENT_NAMES[element], "icon": icon,
        "attack": atk, "range": rng, "speed": speed, "cost": cost, "splash": splash, "description": desc,
        "colors": RARITY_COLORS[rarity],
    }


def stats_at_level(key, level):
    """重複取得によるレベルアップで、攻撃力が緩やかに強化される(レベルごとに+8%)"""
    info = character_info(key)
    if not info:
        return None
    multiplier = 1 + (level - 1) * 0.08
    info = dict(info)
    info["level"] = level
    info["attack"] = round(info["attack"] * multiplier, 1)
    return info
