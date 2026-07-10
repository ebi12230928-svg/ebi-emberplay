import json

from flask import render_template, request, jsonify
from flask_login import login_required, current_user

from extensions import db
from models import BetRecord
import fairness
from . import games_bp
from .common import validate_wager, apply_rakeback, credit_winnings, scale_multiplier

# 2つのサイコロの合計を予想する(全36通りを検証済み・house edge約9%)
PAYOUTS = {"under": 2.18, "over": 2.18, "seven": 5.46}


@games_bp.route("/overunder7")
@login_required
def overunder7_page():
    return render_template("games/overunder7.html", payouts=PAYOUTS)


@games_bp.route("/overunder7/play", methods=["POST"])
@login_required
def overunder7_play():
    data = request.get_json(force=True)
    wager = int(data.get("wager", 0))
    pick = data.get("pick")

    if pick not in PAYOUTS:
        return jsonify({"error": "選択が不正です。"}), 400

    error = validate_wager(current_user, wager)
    if error:
        return jsonify({"error": error}), 400

    user = current_user
    user.balance -= wager

    floats = fairness.get_floats(user.server_seed, user.client_seed, user.nonce, 2)
    used_nonce = user.nonce
    user.nonce += 1
    dice = [min(int(f * 6) + 1, 6) for f in floats]
    total = sum(dice)

    if total == 7:
        outcome = "seven"
    elif total < 7:
        outcome = "under"
    else:
        outcome = "over"

    won = pick == outcome
    multiplier = scale_multiplier("overunder7", PAYOUTS[pick]) if won else 0
    payout = round(wager * multiplier) if won else 0

    if payout > 0:
        credit_winnings(user, payout)
    apply_rakeback(user, wager)

    db.session.add(BetRecord(
        user_id=user.id, game="overunder7", wager=wager, payout=payout, multiplier=multiplier,
        server_seed_hash=user.server_seed_hash, client_seed=user.client_seed, nonce=used_nonce,
        result_json=json.dumps({"dice": dice, "total": total, "pick": pick})
    ))
    db.session.commit()

    return jsonify({
        "dice": dice, "total": total, "won": won, "multiplier": multiplier,
        "payout": payout, "balance": user.balance
    })
