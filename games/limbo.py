import json

from flask import render_template, request, jsonify
from flask_login import login_required, current_user

from extensions import db
from models import BetRecord
import fairness
from . import games_bp
from .common import validate_wager, apply_rakeback, credit_winnings

LIMBO_HOUSE_EDGE = 0.07


@games_bp.route("/limbo")
@login_required
def limbo_page():
    return render_template("games/limbo.html")


@games_bp.route("/limbo/play", methods=["POST"])
@login_required
def limbo_play():
    data = request.get_json(force=True)
    wager = int(data.get("wager", 0))
    target = float(data.get("target", 2.0))

    error = validate_wager(current_user, wager)
    if error:
        return jsonify({"error": error}), 400
    if target < 1.01:
        return jsonify({"error": "目標倍率は1.01倍以上で指定してください。"}), 400

    user = current_user
    user.balance -= wager

    result = fairness.crash_point(user.server_seed, user.client_seed, user.nonce, house_edge=LIMBO_HOUSE_EDGE)
    used_nonce = user.nonce
    user.nonce += 1

    win = result >= target
    payout = round(wager * target) if win else 0
    credit_winnings(user, payout)
    apply_rakeback(user, wager)

    db.session.add(BetRecord(
        user_id=user.id, game="limbo", wager=wager, payout=payout, multiplier=target if win else 0,
        server_seed_hash=user.server_seed_hash, client_seed=user.client_seed, nonce=used_nonce,
        result_json=json.dumps({"result": result, "target": target})
    ))
    db.session.commit()

    return jsonify({
        "result": result, "win": win, "payout": payout, "target": target,
        "balance": user.balance, "nonce": used_nonce
    })
