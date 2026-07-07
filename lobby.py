import random

from flask import Blueprint, render_template, abort
from flask_login import login_required, current_user

from models import BetRecord, Announcement
from games.slots import THEMES as SLOT_THEMES

lobby_bp = Blueprint("lobby", __name__)

GAMES = [
    {"slug": "dice", "game_key": "dice", "name": "Dice", "tagline": "ターゲットを決めて即座に勝負", "ready": True, "category": "originals"},
    {"slug": "limbo", "game_key": "limbo", "name": "Limbo", "tagline": "倍率が伸びる前に目標を狙え", "ready": True, "category": "originals"},
    {"slug": "crash", "game_key": "crash", "name": "Crash", "tagline": "上昇する倍率を見極めて手動キャッシュアウト", "ready": True, "category": "originals"},
    {"slug": "mines", "game_key": "mines", "name": "Mines", "tagline": "地雷を避けて倍率を積み上げろ", "ready": True, "category": "originals"},
    {"slug": "plinko", "game_key": "plinko", "name": "Plinko", "tagline": "ボールを落として倍率を狙え", "ready": True, "category": "originals"},
    {"slug": "keno", "game_key": "keno", "name": "Keno", "tagline": "数字を選んで一致数で配当", "ready": True, "category": "originals"},
    {"slug": "wheel", "game_key": "wheel", "name": "Wheel", "tagline": "ホイールを回して配当を狙え", "ready": True, "category": "originals"},
    {"slug": "hilo", "game_key": "hilo", "name": "HiLo", "tagline": "次のカードは上か下か", "ready": True, "category": "originals"},
    {"slug": "tower", "game_key": "tower", "name": "Dragon Tower", "tagline": "塔を登って倍率を積み上げろ", "ready": True, "category": "originals"},
    {"slug": "coinflip", "game_key": "coinflip", "name": "Coin Flip", "tagline": "表か裏か、シンプルな2択勝負", "ready": True, "category": "originals"},
    {"slug": "sicbo", "game_key": "sicbo", "name": "Sic Bo", "tagline": "3つのサイコロの出目を選ぶ", "ready": True, "category": "originals"},
    {"slug": "war", "game_key": "war", "name": "War", "tagline": "1枚勝負、引き分けはWarか降参", "ready": True, "category": "table"},
    {"slug": "roulette", "game_key": "roulette", "name": "Roulette", "tagline": "ヨーロピアンルーレット", "ready": True, "category": "table"},
    {"slug": "blackjack", "game_key": "blackjack", "name": "Blackjack", "tagline": "ディーラーと21を競う定番ゲーム", "ready": True, "category": "table"},
    {"slug": "baccarat", "game_key": "baccarat", "name": "Baccarat", "tagline": "Player・Banker・Tieから選ぶ", "ready": True, "category": "table"},
    {"slug": "videopoker", "game_key": "videopoker", "name": "Video Poker", "tagline": "Jacks or Betterで役を揃えろ", "ready": True, "category": "table"},
    {"slug": "american-roulette", "game_key": "american_roulette", "name": "American Roulette", "tagline": "00ありのアメリカン仕様", "ready": True, "category": "table"},
    {"slug": "reddog", "game_key": "reddog", "name": "Red Dog", "tagline": "2枚の間に3枚目が入るか予想", "ready": True, "category": "table"},
    {"slug": "andarbahar", "game_key": "andarbahar", "name": "Andar Bahar", "tagline": "ジョーカーと同じ数字がどちらに先に出るか", "ready": True, "category": "table"},
    {"slug": "craps", "game_key": "craps", "name": "Craps", "tagline": "Pass/Don't Passでサイコロ勝負", "ready": True, "category": "table"},
    {"slug": "threecardpoker", "game_key": "threecardpoker", "name": "Three Card Poker", "tagline": "3枚勝負でディーラーに挑む", "ready": True, "category": "table"},
]

# スロットはテーマごとに量産されるので、THEMES辞書から自動的に一覧を作る
for theme_id, theme in SLOT_THEMES.items():
    GAMES.append({
        "slug": f"slots/{theme_id}", "game_key": f"slots:{theme_id}", "name": theme["name"],
        "tagline": "リール演出のスロット", "ready": True, "category": "slots", "theme_id": theme_id
    })

GAMES_BY_KEY = {g["game_key"]: g for g in GAMES}

CATEGORY_LABELS = {
    "originals": "EMBERPLAY オリジナル",
    "table": "テーブルゲーム",
    "slots": "スロット",
}

CAROUSEL_PREVIEW_COUNT = 12
RECOMMENDED_COUNT = 8


def _build_categories():
    categories = []
    for key, label in CATEGORY_LABELS.items():
        games_in_cat = [g for g in GAMES if g["category"] == key]
        if games_in_cat:
            categories.append({"key": key, "label": label, "games": games_in_cat[:CAROUSEL_PREVIEW_COUNT]})
    return categories


def _continue_playing(user_id):
    """直近のプレイ履歴から、重複を除いて新しい順にゲームを並べる"""
    recent_bets = (
        BetRecord.query.filter_by(user_id=user_id)
        .order_by(BetRecord.created_at.desc())
        .limit(50).all()
    )
    seen = set()
    result = []
    for bet in recent_bets:
        if bet.game in seen:
            continue
        seen.add(bet.game)
        game = GAMES_BY_KEY.get(bet.game)
        if game:
            result.append(game)
        if len(result) >= CAROUSEL_PREVIEW_COUNT:
            break
    return result


@lobby_bp.route("/")
@login_required
def index():
    recent = (
        BetRecord.query.order_by(BetRecord.created_at.desc()).limit(12).all()
    )
    latest_announcements = (
        Announcement.query.order_by(Announcement.created_at.desc()).limit(3).all()
    )
    continue_playing = _continue_playing(current_user.id)
    recommended = random.sample(GAMES, min(RECOMMENDED_COUNT, len(GAMES)))
    categories = _build_categories()

    return render_template(
        "index.html", games=GAMES, recent=recent, categories=categories,
        latest_announcements=latest_announcements,
        continue_playing=continue_playing, recommended=recommended
    )


@lobby_bp.route("/games/category/<key>")
@login_required
def category(key):
    if key not in CATEGORY_LABELS:
        abort(404)
    games_in_cat = [g for g in GAMES if g["category"] == key]
    return render_template("category.html", label=CATEGORY_LABELS[key], games=games_in_cat)


@lobby_bp.route("/announcements")
@login_required
def announcements():
    items = Announcement.query.order_by(Announcement.created_at.desc()).limit(50).all()
    return render_template("announcements.html", items=items)


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

