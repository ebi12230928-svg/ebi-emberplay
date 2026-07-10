import json

from flask import render_template, request, jsonify
from flask_login import login_required, current_user

from extensions import db
from models import BetRecord
import fairness
from . import games_bp
from .common import validate_wager, apply_rakeback, credit_winnings, scale_multiplier

# 1匹だけ選んで釣り上げる。魚ごとに出やすさと配当が違う(ペイテーブルとして全体を正規化済み・house edge約10%)
FISH = [
    {"key": "small", "label": "🐟", "weight": 35, "payout": 0.14},
    {"key": "medium", "label": "🐠", "weight": 25, "payout": 0.28},
    {"key": "tropical", "label": "🐡", "weight": 18, "payout": 0.57},
    {"key": "big", "label": "🦈", "weight": 12, "payout": 1.14},
    {"key": "rare", "label": "🐙", "weight": 7, "payout": 2.84},
    {"key": "golden", "label": "🧜", "weight": 3, "payout": 11.37},
]


def _pick(total_weight, f):
    r = f * total_weight
    cum = 0
    for fish in FISH:
        cum += fish["weight"]
        if r < cum:
            return fish
    return FISH[-1]


@games_bp.route("/fishing")
@login_required
def fishing_page():
    return render_template("games/fishing.html", fish=FISH)


@games_bp.route("/fishing/play", methods=["POST"])
@login_required
def fishing_play():
    data = request.get_json(force=True)
    wager = int(data.get("wager", 0))

    error = validate_wager(current_user, wager)
    if error:
        return jsonify({"error": error}), 400

    user = current_user
    user.balance -= wager

    total_weight = sum(f["weight"] for f in FISH)
    f_val = fairness.get_float(user.server_seed, user.client_seed, user.nonce)
    used_nonce = user.nonce
    user.nonce += 1
    caught = _pick(total_weight, f_val)

    multiplier = scale_multiplier("fishing", caught["payout"])
    payout = round(wager * multiplier)

    if payout > 0:
        credit_winnings(user, payout)
    apply_rakeback(user, wager)

    db.session.add(BetRecord(
        user_id=user.id, game="fishing", wager=wager, payout=payout, multiplier=multiplier,
        server_seed_hash=user.server_seed_hash, client_seed=user.client_seed, nonce=used_nonce,
        result_json=json.dumps({"caught": caught["key"]})
    ))
    db.session.commit()

    return jsonify({
        "label": caught["label"], "multiplier": multiplier, "payout": payout, "balance": user.balance
    })
