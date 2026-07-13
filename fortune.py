"""おみくじ。1日1回引ける運勢占い。大吉ほど当選確率は低いが、もらえるEmbersも多い。"""
import random
from datetime import datetime, timezone

from flask import Blueprint, render_template, jsonify
from flask_login import login_required, current_user

from extensions import db
from models import FortuneDraw

fortune_bp = Blueprint("fortune", __name__)

RESULTS = [
    {"key": "daikichi", "label": "大吉", "weight": 5, "reward": (100, 200), "message": "最高の1日になりそう!大きなチャンスを逃さないで。"},
    {"key": "kichi", "label": "吉", "weight": 20, "reward": (50, 90), "message": "良いことがありそうな予感。積極的に動いてみよう。"},
    {"key": "chukichi", "label": "中吉", "weight": 30, "reward": (25, 45), "message": "まずまずの運勢。焦らずマイペースに。"},
    {"key": "shokichi", "label": "小吉", "weight": 30, "reward": (10, 20), "message": "小さな幸運がありそう。見逃さないように。"},
    {"key": "kyo", "label": "凶", "weight": 15, "reward": (5, 10), "message": "今日は慎重に。無理は禁物です。"},
]


def _today_str():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


@fortune_bp.route("/fortune")
@login_required
def index():
    today = _today_str()
    drawn_today = FortuneDraw.query.filter_by(user_id=current_user.id, drawn_date=today).first()
    return render_template("fortune.html", drawn_today=drawn_today, results=RESULTS)


@fortune_bp.route("/fortune/draw", methods=["POST"])
@login_required
def draw():
    today = _today_str()
    if FortuneDraw.query.filter_by(user_id=current_user.id, drawn_date=today).first():
        return jsonify({"error": "今日はもう引いています。また明日どうぞ。"}), 400

    total = sum(r["weight"] for r in RESULTS)
    roll = random.uniform(0, total)
    upto = 0
    chosen = RESULTS[0]
    for r in RESULTS:
        upto += r["weight"]
        if roll <= upto:
            chosen = r
            break

    reward = random.randint(*chosen["reward"])
    from games.common import credit_reward
    credit_reward(current_user, reward)
    db.session.add(FortuneDraw(user_id=current_user.id, result=chosen["key"], reward=reward, drawn_date=today))
    db.session.commit()

    return jsonify({
        "ok": True, "label": chosen["label"], "message": chosen["message"],
        "reward": reward, "balance": current_user.balance,
    })
