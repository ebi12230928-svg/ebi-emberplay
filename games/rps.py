import json

from flask import render_template, request, jsonify
from flask_login import login_required, current_user

from extensions import db
from models import BetRecord
import fairness
from . import games_bp
from .common import validate_wager, apply_rakeback, credit_winnings, scale_multiplier

RPS_HOUSE_EDGE = 0.05
MULTIPLIER = round((1 - RPS_HOUSE_EDGE) * 2, 4)
CHOICES = ["rock", "paper", "scissors"]
BEATS = {"rock": "scissors", "paper": "rock", "scissors": "paper"}


@games_bp.route("/rps")
@login_required
def rps_page():
    return render_template("games/rps.html", multiplier=scale_multiplier("rps", MULTIPLIER))


@games_bp.route("/rps/play", methods=["POST"])
@login_required
def rps_play():
    data = request.get_json(force=True)
    wager = int(data.get("wager", 0))
    pick = data.get("pick")

    error = validate_wager(current_user, wager)
    if error:
        return jsonify({"error": error}), 400
    if pick not in CHOICES:
        return jsonify({"error": "選択が不正です。"}), 400

    user = current_user
    user.balance -= wager

    f = fairness.get_float(user.server_seed, user.client_seed, user.nonce)
    used_nonce = user.nonce
    user.nonce += 1
    house_pick = CHOICES[min(int(f * 3), 2)]

    if house_pick == pick:
        outcome = "push"
        multiplier = 1.0
        payout = wager
    elif BEATS[pick] == house_pick:
        outcome = "win"
        multiplier = scale_multiplier("rps", MULTIPLIER)
        payout = round(wager * multiplier)
    else:
        outcome = "lose"
        multiplier = 0
        payout = 0

    if payout > 0:
        credit_winnings(user, payout)
    apply_rakeback(user, wager)

    db.session.add(BetRecord(
        user_id=user.id, game="rps", wager=wager, payout=payout, multiplier=multiplier,
        server_seed_hash=user.server_seed_hash, client_seed=user.client_seed, nonce=used_nonce,
        result_json=json.dumps({"pick": pick, "house_pick": house_pick, "outcome": outcome})
    ))
    db.session.commit()

    return jsonify({
        "pick": pick, "house_pick": house_pick, "outcome": outcome,
        "multiplier": multiplier, "payout": payout, "balance": user.balance
    })
