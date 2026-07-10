import json

from flask import render_template, request, jsonify
from flask_login import login_required, current_user

from extensions import db
from models import BetRecord
import fairness
from . import games_bp
from .common import validate_wager, apply_rakeback, credit_winnings, scale_multiplier

# 1〜10の数字を1つ選んで的中させるシンプルなゲーム(house edge 10%)
PAYOUT = 9.0


@games_bp.route("/numbermatch")
@login_required
def numbermatch_page():
    return render_template("games/numbermatch.html", payout=PAYOUT)


@games_bp.route("/numbermatch/play", methods=["POST"])
@login_required
def numbermatch_play():
    data = request.get_json(force=True)
    wager = int(data.get("wager", 0))
    try:
        pick = int(data.get("pick"))
    except (TypeError, ValueError):
        pick = -1

    if not (1 <= pick <= 10):
        return jsonify({"error": "1〜10の数字を選んでください。"}), 400

    error = validate_wager(current_user, wager)
    if error:
        return jsonify({"error": error}), 400

    user = current_user
    user.balance -= wager

    f = fairness.get_float(user.server_seed, user.client_seed, user.nonce)
    used_nonce = user.nonce
    user.nonce += 1
    result = min(int(f * 10), 9) + 1

    won = pick == result
    multiplier = scale_multiplier("numbermatch", PAYOUT) if won else 0
    payout = round(wager * multiplier) if won else 0

    if payout > 0:
        credit_winnings(user, payout)
    apply_rakeback(user, wager)

    db.session.add(BetRecord(
        user_id=user.id, game="numbermatch", wager=wager, payout=payout, multiplier=multiplier,
        server_seed_hash=user.server_seed_hash, client_seed=user.client_seed, nonce=used_nonce,
        result_json=json.dumps({"pick": pick, "result": result})
    ))
    db.session.commit()

    return jsonify({"result": result, "won": won, "multiplier": multiplier, "payout": payout, "balance": user.balance})
