"""釣りゲーム。タイミングよくボタンを押して魚を釣る、シンプルなミニゲーム。"""
import random

from flask import Blueprint, render_template, jsonify, request
from flask_login import login_required, current_user

from extensions import db
from models import FishingCatch

fishing_bp = Blueprint("fishing", __name__)

FISH = [
    {"key": "small_fish", "name": "小魚", "icon": "🐟", "weight": 50, "reward": (5, 15)},
    {"key": "medium_fish", "name": "中くらいの魚", "icon": "🐠", "weight": 30, "reward": (15, 35)},
    {"key": "big_fish", "name": "大きな魚", "icon": "🐡", "weight": 13, "reward": (40, 80)},
    {"key": "treasure_chest", "name": "宝箱", "icon": "🎁", "weight": 5, "reward": (100, 200)},
    {"key": "legendary_fish", "name": "伝説の魚", "icon": "🐋", "weight": 2, "reward": (300, 600)},
]
CAST_COST = 10


@fishing_bp.route("/fishing")
@login_required
def index():
    recent = FishingCatch.query.filter_by(user_id=current_user.id).order_by(FishingCatch.created_at.desc()).limit(10).all()
    return render_template("fishing.html", fish_list=FISH, cast_cost=CAST_COST, recent=recent)


@fishing_bp.route("/fishing/cast", methods=["POST"])
@login_required
def cast():
    """竿を投げる。サーバー側でターゲットゾーンの位置と幅を決めて返す"""
    if current_user.balance < CAST_COST:
        return jsonify({"error": "Embersが足りません。"}), 400
    current_user.balance -= CAST_COST
    db.session.commit()

    target_start = random.uniform(30, 65)
    target_width = random.uniform(10, 22)
    return jsonify({"balance": current_user.balance, "target_start": target_start, "target_width": target_width})


@fishing_bp.route("/fishing/reel", methods=["POST"])
@login_required
def reel():
    """タイミング(0-100のインジケーター位置)を受け取り、当たり判定を行う"""
    data = request.get_json(force=True)
    try:
        position = float(data.get("position", 0))
        target_start = float(data.get("target_start", 0))
        target_width = float(data.get("target_width", 0))
    except (TypeError, ValueError):
        return jsonify({"error": "不正なリクエストです。"}), 400

    hit = target_start <= position <= target_start + target_width
    if not hit:
        return jsonify({"success": False, "message": "逃げられてしまった…"})

    center = target_start + target_width / 2
    accuracy = max(0, 1 - abs(position - center) / (target_width / 2 + 0.001))

    weighted = [(f, f["weight"] * (1 + accuracy * 2 if f["key"] in ("treasure_chest", "legendary_fish") else 1)) for f in FISH]
    total = sum(w for _, w in weighted)
    r = random.uniform(0, total)
    upto = 0
    chosen = FISH[0]
    for f, w in weighted:
        upto += w
        if r <= upto:
            chosen = f
            break

    reward = random.randint(*chosen["reward"])
    from games.common import credit_reward
    credit_reward(current_user, reward)
    db.session.add(FishingCatch(user_id=current_user.id, fish_key=chosen["key"], reward=reward))
    db.session.commit()

    return jsonify({
        "success": True, "fish": chosen, "reward": reward, "balance": current_user.balance,
    })
