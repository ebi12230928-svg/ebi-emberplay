import json

from flask import render_template, request, jsonify
from flask_login import login_required, current_user

from extensions import db
from models import BetRecord
from . import games_bp
from .common import validate_wager, apply_rakeback, next_float, credit_winnings

COINFLIP_HOUSE_EDGE = 0.05
MULTIPLIER = round((1 - COINFLIP_HOUSE_EDGE) * 2, 4)


@games_bp.route("/coinflip")
@login_required
def coinflip_page():
    return render_template("games/coinflip.html", multiplier=MULTIPLIER)


@games_bp.route("/coinflip/play", methods=["POST"])
@login_required
def coinflip_play():
    data = request.get_json(force=True)
    wager = int(data.get("wager", 0))
    side = data.get("side", "heads")

    error = validate_wager(current_user, wager)
    if error:
        return jsonify({"error": error}), 400
    if side not in ("heads", "tails"):
        return jsonify({"error": "表裏の指定が不正です。"}), 400

    user = current_user
    user.balance -= wager

    f, used_nonce = next_float(user)
    result = "heads" if f < 0.5 else "tails"
    win = result == side
    payout = round(wager * MULTIPLIER) if win else 0

    credit_winnings(user, payout)
    apply_rakeback(user, wager)

    db.session.add(BetRecord(
        user_id=user.id, game="coinflip", wager=wager, payout=payout, multiplier=MULTIPLIER if win else 0,
        server_seed_hash=user.server_seed_hash, client_seed=user.client_seed, nonce=used_nonce,
        result_json=json.dumps({"result": result, "side": side})
    ))
    db.session.commit()

    return jsonify({"result": result, "win": win, "multiplier": MULTIPLIER, "payout": payout, "balance": user.balance})
