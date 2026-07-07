from flask import Blueprint, render_template
from flask_login import login_required, current_user

from models import BetRecord
from games.slots import THEMES as SLOT_THEMES

lobby_bp = Blueprint("lobby", __name__)

GAMES = [
    {"slug": "dice", "name": "Dice", "tagline": "ターゲットを決めて即座に勝負", "ready": True, "category": "originals"},
    {"slug": "limbo", "name": "Limbo", "tagline": "倍率が伸びる前に目標を狙え", "ready": True, "category": "originals"},
    {"slug": "crash", "name": "Crash", "tagline": "上昇する倍率を見極めて手動キャッシュアウト", "ready": True, "category": "originals"},
    {"slug": "mines", "name": "Mines", "tagline": "地雷を避けて倍率を積み上げろ", "ready": True, "category": "originals"},
    {"slug": "plinko", "name": "Plinko", "tagline": "ボールを落として倍率を狙え", "ready": True, "category": "originals"},
    {"slug": "keno", "name": "Keno", "tagline": "数字を選んで一致数で配当", "ready": True, "category": "originals"},
    {"slug": "wheel", "name": "Wheel", "tagline": "ホイールを回して配当を狙え", "ready": True, "category": "originals"},
    {"slug": "hilo", "name": "HiLo", "tagline": "次のカードは上か下か", "ready": True, "category": "originals"},
    {"slug": "tower", "name": "Dragon Tower", "tagline": "塔を登って倍率を積み上げろ", "ready": True, "category": "originals"},
    {"slug": "coinflip", "name": "Coin Flip", "tagline": "表か裏か、シンプルな2択勝負", "ready": True, "category": "originals"},
    {"slug": "sicbo", "name": "Sic Bo", "tagline": "3つのサイコロの出目を選ぶ", "ready": True, "category": "originals"},
    {"slug": "war", "name": "War", "tagline": "1枚勝負、引き分けはWarか降参", "ready": True, "category": "table"},
    {"slug": "roulette", "name": "Roulette", "tagline": "ヨーロピアンルーレット", "ready": True, "category": "table"},
    {"slug": "blackjack", "name": "Blackjack", "tagline": "ディーラーと21を競う定番ゲーム", "ready": True, "category": "table"},
    {"slug": "baccarat", "name": "Baccarat", "tagline": "Player・Banker・Tieから選ぶ", "ready": True, "category": "table"},
    {"slug": "videopoker", "name": "Video Poker", "tagline": "Jacks or Betterで役を揃えろ", "ready": True, "category": "table"},
]

# スロットはテーマごとに量産されるので、THEMES辞書から自動的に一覧を作る
for theme_id, theme in SLOT_THEMES.items():
    GAMES.append({
        "slug": f"slots/{theme_id}", "name": theme["name"], "tagline": "リール演出のスロット",
        "ready": True, "category": "slots", "theme_id": theme_id
    })

CATEGORY_LABELS = {
    "originals": "EMBERPLAY オリジナル",
    "table": "テーブルゲーム",
    "slots": "スロット",
}


@lobby_bp.route("/")
@login_required
def index():
    recent = (
        BetRecord.query.order_by(BetRecord.created_at.desc()).limit(12).all()
    )
    categories = []
    for key, label in CATEGORY_LABELS.items():
        games_in_cat = [g for g in GAMES if g["category"] == key]
        if games_in_cat:
            categories.append({"key": key, "label": label, "games": games_in_cat})
    return render_template("index.html", games=GAMES, recent=recent, categories=categories)


@lobby_bp.route("/history")
@login_required
def history():
    items = (
        BetRecord.query.filter_by(user_id=current_user.id)
        .order_by(BetRecord.created_at.desc())
        .limit(100)
        .all()
    )
    return render_template("history.html", items=items)

