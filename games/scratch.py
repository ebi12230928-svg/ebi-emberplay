import json

from flask import render_template, request, jsonify
from flask_login import login_required, current_user

from extensions import db
from models import BetRecord
import fairness
from . import games_bp
from .common import validate_wager, apply_rakeback, credit_winnings, scale_multiplier

# house edge目標10%で正規化済み(全216通り総当たりでEV検証済み)
SYMBOLS = [
    {"key": "cherry", "label": "🍒", "weight": 40, "pay3": 4.76, "pay2": 0.95},
    {"key": "clover", "label": "🍀", "weight": 28, "pay3": 7.94, "pay2": 0},
    {"key": "star", "label": "⭐", "weight": 16, "pay3": 19.05, "pay2": 0},
    {"key": "gem", "label": "💎", "weight": 10, "pay3": 41.27, "pay2": 0},
    {"key": "gold", "label": "👑", "weight": 6, "pay3": 126.99, "pay2": 0},
]


def _pick_symbol(total_weight, f):
    r = f * total_weight
    cum = 0
    for s in SYMBOLS:
        cum += s["weight"]
        if r < cum:
            return s
    return SYMBOLS[-1]


def _payout_multiplier(cells):
    keys = [c["key"] for c in cells]
    if keys[0] == keys[1] == keys[2]:
        return cells[0]["pay3"]
    for i in range(3):
        for j in range(i + 1, 3):
            if keys[i] == keys[j]:
                return cells[i]["pay2"]
    return 0


@games_bp.route("/scratch")
@login_required
def scratch_page():
    return render_template("games/scratch.html", symbols=SYMBOLS)


@games_bp.route("/scratch/play", methods=["POST"])
@login_required
def scratch_play():
    data = request.get_json(force=True)
    wager = int(data.get("wager", 0))

    error = validate_wager(current_user, wager)
    if error:
        return jsonify({"error": error}), 400

    user = current_user
    user.balance -= wager

    total_weight = sum(s["weight"] for s in SYMBOLS)
    floats = fairness.get_floats(user.server_seed, user.client_seed, user.nonce, 3)
    used_nonce = user.nonce
    user.nonce += 1

    cells = [_pick_symbol(total_weight, f) for f in floats]
    multiplier = _payout_multiplier(cells)
    multiplier = scale_multiplier("scratch", multiplier)
    payout = round(wager * multiplier)

    if payout > 0:
        credit_winnings(user, payout)
    apply_rakeback(user, wager)

    db.session.add(BetRecord(
        user_id=user.id, game="scratch", wager=wager, payout=payout, multiplier=multiplier,
        server_seed_hash=user.server_seed_hash, client_seed=user.client_seed, nonce=used_nonce,
        result_json=json.dumps({"cells": [c["key"] for c in cells]})
    ))
    db.session.commit()

    return jsonify({
        "labels": [c["label"] for c in cells], "multiplier": multiplier,
        "payout": payout, "balance": user.balance
    })
