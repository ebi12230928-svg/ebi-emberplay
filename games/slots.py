import json

from flask import render_template, request, jsonify
from flask_login import login_required, current_user

from extensions import db
from models import BetRecord
import fairness
from . import games_bp
from .common import validate_wager, apply_rakeback, credit_winnings

SYMBOLS = [
    {"key": "cherry", "label": "🍒", "weight": 40, "pay3": 4.75, "pay2": 0.95},
    {"key": "lemon",  "label": "🍋", "weight": 30, "pay3": 7.92, "pay2": 0},
    {"key": "bell",   "label": "🔔", "weight": 15, "pay3": 19.01, "pay2": 0},
    {"key": "star",   "label": "⭐", "weight": 10, "pay3": 38.03, "pay2": 0},
    {"key": "seven",  "label": "7️⃣", "weight": 5,  "pay3": 126.76, "pay2": 0},
]
TOTAL_WEIGHT = sum(s["weight"] for s in SYMBOLS)


def _pick_symbol(f):
    r = f * TOTAL_WEIGHT
    cum = 0
    for s in SYMBOLS:
        cum += s["weight"]
        if r < cum:
            return s
    return SYMBOLS[-1]


def _payout_multiplier(reels):
    keys = [r["key"] for r in reels]
    if keys[0] == keys[1] == keys[2]:
        return reels[0]["pay3"]
    for i in range(3):
        for j in range(i + 1, 3):
            if keys[i] == keys[j]:
                return reels[i]["pay2"]
    return 0


@games_bp.route("/slots")
@login_required
def slots_page():
    return render_template("games/slots.html", symbols=SYMBOLS)


@games_bp.route("/slots/spin", methods=["POST"])
@login_required
def slots_spin():
    data = request.get_json(force=True)
    wager = int(data.get("wager", 0))

    error = validate_wager(current_user, wager)
    if error:
        return jsonify({"error": error}), 400

    user = current_user
    user.balance -= wager

    floats = fairness.get_floats(user.server_seed, user.client_seed, user.nonce, 3)
    used_nonce = user.nonce
    user.nonce += 1

    reels = [_pick_symbol(f) for f in floats]
    multiplier = _payout_multiplier(reels)
    payout = round(wager * multiplier)

    credit_winnings(user, payout)
    apply_rakeback(user, wager)

    db.session.add(BetRecord(
        user_id=user.id, game="slots", wager=wager, payout=payout, multiplier=multiplier,
        server_seed_hash=user.server_seed_hash, client_seed=user.client_seed, nonce=used_nonce,
        result_json=json.dumps({"reels": [r["key"] for r in reels]})
    ))
    db.session.commit()

    return jsonify({
        "reels": [r["key"] for r in reels], "labels": [r["label"] for r in reels],
        "multiplier": multiplier, "payout": payout, "balance": user.balance
    })
