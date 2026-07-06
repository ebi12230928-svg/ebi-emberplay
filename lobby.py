from flask import Blueprint, render_template
from flask_login import login_required, current_user

from models import BetRecord

lobby_bp = Blueprint("lobby", __name__)

GAMES = [
    {"slug": "dice", "name": "Dice", "tagline": "ターゲットを決めて即座に勝負", "ready": True},
    {"slug": "limbo", "name": "Limbo", "tagline": "倍率が伸びる前に目標を狙え", "ready": True},
    {"slug": "crash", "name": "Crash", "tagline": "上昇する倍率を見極めて手動キャッシュアウト", "ready": True},
    {"slug": "mines", "name": "Mines", "tagline": "地雷を避けて倍率を積み上げろ", "ready": True},
    {"slug": "plinko", "name": "Plinko", "tagline": "ボールを落として倍率を狙え", "ready": True},
    {"slug": "keno", "name": "Keno", "tagline": "数字を選んで一致数で配当", "ready": True},
    {"slug": "wheel", "name": "Wheel", "tagline": "ホイールを回して配当を狙え", "ready": True},
    {"slug": "hilo", "name": "HiLo", "tagline": "次のカードは上か下か", "ready": True},
    {"slug": "tower", "name": "Dragon Tower", "tagline": "塔を登って倍率を積み上げろ", "ready": True},
    {"slug": "coinflip", "name": "Coin Flip", "tagline": "表か裏か、シンプルな2択勝負", "ready": True},
    {"slug": "roulette", "name": "Roulette", "tagline": "ヨーロピアンルーレット", "ready": True},
    {"slug": "blackjack", "name": "Blackjack", "tagline": "ディーラーと21を競う定番ゲーム", "ready": True},
    {"slug": "baccarat", "name": "Baccarat", "tagline": "Player・Banker・Tieから選ぶ", "ready": True},
    {"slug": "videopoker", "name": "Video Poker", "tagline": "Jacks or Betterで役を揃えろ", "ready": True},
    {"slug": "slots", "name": "Slots", "tagline": "リール演出のスロット", "ready": True},
]


@lobby_bp.route("/")
@login_required
def index():
    recent = (
        BetRecord.query.order_by(BetRecord.created_at.desc()).limit(12).all()
    )
    return render_template("index.html", games=GAMES, recent=recent)


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

