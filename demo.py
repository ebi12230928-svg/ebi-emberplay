"""
デモプレイ機能。実際の残高・データベースには一切触れず、
セッション内だけで完結する仮想残高(初期10,000)でゲームを試せる。
"""
import random

from flask import Blueprint, render_template, session, jsonify, request
from flask_login import login_required

demo_bp = Blueprint("demo", __name__)

STARTING_BALANCE = 10000
DICE_HOUSE_EDGE = 0.04
LIMBO_HOUSE_EDGE = 0.07
COINFLIP_MULTIPLIER = 1.9

SLOT_SYMBOLS = [
    {"key": "cherry", "label": "🍒", "weight": 40, "pay3": 4.75, "pay2": 0.95},
    {"key": "lemon", "label": "🍋", "weight": 30, "pay3": 7.92, "pay2": 0},
    {"key": "bell", "label": "🔔", "weight": 15, "pay3": 19.01, "pay2": 0},
    {"key": "star", "label": "⭐", "weight": 10, "pay3": 38.03, "pay2": 0},
    {"key": "seven", "label": "7️⃣", "weight": 5, "pay3": 126.76, "pay2": 0},
]


def _get_balance():
    if "demo_balance" not in session:
        session["demo_balance"] = STARTING_BALANCE
    return session["demo_balance"]


def _set_balance(value):
    session["demo_balance"] = max(0, round(value))


@demo_bp.route("/demo")
@login_required
def index():
    return render_template("demo.html", balance=_get_balance(), starting_balance=STARTING_BALANCE)


@demo_bp.route("/demo/reset", methods=["POST"])
@login_required
def reset():
    session["demo_balance"] = STARTING_BALANCE
    return jsonify({"balance": STARTING_BALANCE})


def _validate(wager, balance):
    if wager <= 0:
        return "プレイ料は1以上にしてください。"
    if wager > balance:
        return "デモ残高が不足しています。「リセット」から残高を初期化できます。"
    return None


@demo_bp.route("/demo/dice", methods=["POST"])
@login_required
def demo_dice():
    data = request.get_json(force=True)
    wager = int(data.get("wager", 0))
    target = max(2, min(98, int(data.get("target", 50))))
    direction = data.get("direction", "under")

    balance = _get_balance()
    error = _validate(wager, balance)
    if error:
        return jsonify({"error": error}), 400

    roll = round(random.uniform(0, 100), 2)
    if direction == "under":
        win = roll < target
        multiplier = round((100 / target) * (1 - DICE_HOUSE_EDGE), 4) if win else 0
    else:
        win = roll > target
        multiplier = round((100 / (100 - target)) * (1 - DICE_HOUSE_EDGE), 4) if win else 0

    payout = round(wager * multiplier) if win else 0
    balance = balance - wager + payout
    _set_balance(balance)

    return jsonify({"roll": roll, "win": win, "multiplier": multiplier, "payout": payout, "balance": balance})


@demo_bp.route("/demo/limbo", methods=["POST"])
@login_required
def demo_limbo():
    data = request.get_json(force=True)
    wager = int(data.get("wager", 0))
    target = max(1.01, float(data.get("target", 2.0)))

    balance = _get_balance()
    error = _validate(wager, balance)
    if error:
        return jsonify({"error": error}), 400

    # limbo.pyと同じ分布(1/(1-r)の逆関数)で結果を生成
    r = random.random()
    result = round(max(1.0, (1 - LIMBO_HOUSE_EDGE) / (1 - r)), 2)

    win = result >= target
    payout = round(wager * target) if win else 0
    balance = balance - wager + payout
    _set_balance(balance)

    return jsonify({"result": result, "win": win, "payout": payout, "balance": balance})


@demo_bp.route("/demo/coinflip", methods=["POST"])
@login_required
def demo_coinflip():
    data = request.get_json(force=True)
    wager = int(data.get("wager", 0))
    side = data.get("side")

    balance = _get_balance()
    error = _validate(wager, balance)
    if error:
        return jsonify({"error": error}), 400
    if side not in ("heads", "tails"):
        return jsonify({"error": "選択が不正です。"}), 400

    result = random.choice(["heads", "tails"])
    win = result == side
    payout = round(wager * COINFLIP_MULTIPLIER) if win else 0
    balance = balance - wager + payout
    _set_balance(balance)

    return jsonify({"result": result, "win": win, "multiplier": COINFLIP_MULTIPLIER, "payout": payout, "balance": balance})


@demo_bp.route("/demo/slots", methods=["POST"])
@login_required
def demo_slots():
    data = request.get_json(force=True)
    wager = int(data.get("wager", 0))

    balance = _get_balance()
    error = _validate(wager, balance)
    if error:
        return jsonify({"error": error}), 400

    total_weight = sum(s["weight"] for s in SLOT_SYMBOLS)

    def pick():
        r = random.uniform(0, total_weight)
        cum = 0
        for s in SLOT_SYMBOLS:
            cum += s["weight"]
            if r < cum:
                return s
        return SLOT_SYMBOLS[-1]

    reels = [pick() for _ in range(3)]
    keys = [r["key"] for r in reels]
    if keys[0] == keys[1] == keys[2]:
        multiplier = reels[0]["pay3"]
    elif keys[0] == keys[1] or keys[1] == keys[2] or keys[0] == keys[2]:
        idx = 0 if keys[0] == keys[1] else 1
        multiplier = reels[idx]["pay2"]
    else:
        multiplier = 0

    payout = round(wager * multiplier)
    balance = balance - wager + payout
    _set_balance(balance)

    return jsonify({
        "labels": [r["label"] for r in reels], "multiplier": multiplier, "payout": payout, "balance": balance
    })
