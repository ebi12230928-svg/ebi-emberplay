import json

from flask import render_template, request, jsonify
from flask_login import login_required, current_user

from extensions import db
from models import BetRecord
from . import games_bp
from .common import validate_wager, apply_rakeback, next_float, credit_winnings, scale_multiplier
import fairness

WHEEL_HOUSE_EDGE = 0.06
ALLOWED_SEGMENTS = (10, 20, 30, 40, 50)
ALLOWED_RISK = ("low", "medium", "high")


@games_bp.route("/wheel")
@login_required
def wheel_page():
    return render_template("games/wheel.html", segment_options=ALLOWED_SEGMENTS)


@games_bp.route("/wheel/play", methods=["POST"])
@login_required
def wheel_play():
    data = request.get_json(force=True)
    wager = int(data.get("wager", 0))
    segments = int(data.get("segments", 20))
    risk = data.get("risk", "medium")

    error = validate_wager(current_user, wager)
    if error:
        return jsonify({"error": error}), 400
    if segments not in ALLOWED_SEGMENTS:
        return jsonify({"error": "セグメント数が不正です。"}), 400
    if risk not in ALLOWED_RISK:
        return jsonify({"error": "リスクの指定が不正です。"}), 400

    user = current_user
    user.balance -= wager

    f, used_nonce = next_float(user)
    idx = min(int(f * segments), segments - 1)
    table = fairness.wheel_table(segments, risk, house_edge=WHEEL_HOUSE_EDGE)
    multiplier = table[idx]
    multiplier = scale_multiplier("wheel", multiplier)
    payout = round(wager * multiplier)

    credit_winnings(user, payout)
    apply_rakeback(user, wager)

    db.session.add(BetRecord(
        user_id=user.id, game="wheel", wager=wager, payout=payout, multiplier=multiplier,
        server_seed_hash=user.server_seed_hash, client_seed=user.client_seed, nonce=used_nonce,
        result_json=json.dumps({"segments": segments, "risk": risk, "index": idx})
    ))
    db.session.commit()

    return jsonify({
        "index": idx, "table": table, "multiplier": multiplier,
        "payout": payout, "balance": user.balance
    })
