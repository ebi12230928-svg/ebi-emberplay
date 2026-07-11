import json

from flask import render_template, request, jsonify
from flask_login import login_required, current_user

from extensions import db
from models import BetRecord
import fairness
from . import games_bp
from .common import validate_wager, apply_rakeback, credit_winnings, scale_multiplier

# 2つのサイコロを振り、合計が2,3,4,9,10,11,12なら勝ち(2,12は特別配当)。全36通り検証済み・house edge約8%
FIELD_DOUBLE = {3, 4, 9, 10, 11}
FIELD_TRIPLE = {2, 12}
DOUBLE_PAYOUT = 1.95
TRIPLE_PAYOUT = 2.92


@games_bp.route("/field")
@login_required
def field_page():
    return render_template("games/field.html", double_payout=DOUBLE_PAYOUT, triple_payout=TRIPLE_PAYOUT)


@games_bp.route("/field/play", methods=["POST"])
@login_required
def field_play():
    data = request.get_json(force=True)
    wager = int(data.get("wager", 0))

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

    if total in FIELD_TRIPLE:
        multiplier = scale_multiplier("field", TRIPLE_PAYOUT)
    elif total in FIELD_DOUBLE:
        multiplier = scale_multiplier("field", DOUBLE_PAYOUT)
    else:
        multiplier = 0

    payout = round(wager * multiplier) if multiplier > 0 else 0
    if payout > 0:
        credit_winnings(user, payout)
    apply_rakeback(user, wager)

    db.session.add(BetRecord(
        user_id=user.id, game="field", wager=wager, payout=payout, multiplier=multiplier,
        server_seed_hash=user.server_seed_hash, client_seed=user.client_seed, nonce=used_nonce,
        result_json=json.dumps({"dice": dice, "total": total})
    ))
    db.session.commit()

    return jsonify({
        "dice": dice, "total": total, "multiplier": multiplier, "payout": payout, "balance": user.balance
    })
