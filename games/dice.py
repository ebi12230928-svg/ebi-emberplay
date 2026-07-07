import json

from flask import render_template, request, jsonify
from flask_login import login_required, current_user

from extensions import db
from models import BetRecord
import fairness
from . import games_bp
from .common import validate_wager, apply_rakeback, credit_winnings, scale_multiplier

DICE_HOUSE_EDGE = 0.04


@games_bp.route("/dice")
@login_required
def dice_page():
    return render_template("games/dice.html")


@games_bp.route("/dice/roll", methods=["POST"])
@login_required
def dice_roll():
    data = request.get_json(force=True)
    wager = int(data.get("wager", 0))
    target = float(data.get("target", 50))
    direction = data.get("direction", "under")

    error = validate_wager(current_user, wager)
    if error:
        return jsonify({"error": error}), 400
    if not (0.01 <= target <= 98.0):
        return jsonify({"error": "ターゲットは0.01〜98.00の範囲で指定してください。"}), 400

    user = current_user
    user.balance -= wager

    roll = fairness.roll_dice_100(user.server_seed, user.client_seed, user.nonce)
    used_nonce = user.nonce
    user.nonce += 1

    if direction == "under":
        win = roll < target
        multiplier = round((100 / target) * (1 - DICE_HOUSE_EDGE), 4) if win else 0
    else:
        win = roll > target
        multiplier = round((100 / (100 - target)) * (1 - DICE_HOUSE_EDGE), 4) if win else 0

    multiplier = scale_multiplier("dice", multiplier) if win else 0
    payout = round(wager * multiplier) if win else 0
    credit_winnings(user, payout)
    apply_rakeback(user, wager)

    db.session.add(BetRecord(
        user_id=user.id, game="dice", wager=wager, payout=payout, multiplier=multiplier if win else 0,
        server_seed_hash=user.server_seed_hash, client_seed=user.client_seed, nonce=used_nonce,
        result_json=json.dumps({"roll": roll, "target": target, "direction": direction})
    ))
    db.session.commit()

    return jsonify({
        "roll": roll, "win": win, "payout": payout, "multiplier": multiplier,
        "balance": user.balance, "nonce": used_nonce
    })
