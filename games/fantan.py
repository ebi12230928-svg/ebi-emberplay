import json

from flask import render_template, request, jsonify
from flask_login import login_required, current_user

from extensions import db
from models import BetRecord
import fairness
from . import games_bp
from .common import validate_wager, apply_rakeback, credit_winnings, scale_multiplier, apply_win_boost

# ボタンの山を4つずつ取り除き、最後に残る数(0〜3)を当てる中国の伝統ゲーム
FAN_TAN_PAYOUT = 3.68  # house edge 8%で正規化済み(的中確率1/4)


@games_bp.route("/fantan")
@login_required
def fantan_page():
    return render_template("games/fantan.html", payout=FAN_TAN_PAYOUT)


@games_bp.route("/fantan/play", methods=["POST"])
@login_required
def fantan_play():
    data = request.get_json(force=True)
    wager = int(data.get("wager", 0))
    try:
        pick = int(data.get("pick"))
    except (TypeError, ValueError):
        pick = -1

    if pick not in (0, 1, 2, 3):
        return jsonify({"error": "0〜3の数字を選んでください。"}), 400

    error = validate_wager(current_user, wager)
    if error:
        return jsonify({"error": error}), 400

    user = current_user
    user.balance -= wager

    f = fairness.get_float(user.server_seed, user.client_seed, user.nonce)
    used_nonce = user.nonce
    user.nonce += 1
    result = int(f * 4)

    won = apply_win_boost("fantan", pick == result)
    if won and result != pick:
        result = pick
    elif not won and result == pick:
        result = (pick + 1) % 4
    multiplier = scale_multiplier("fantan", FAN_TAN_PAYOUT) if won else 0
    payout = round(wager * multiplier) if won else 0

    if payout > 0:
        credit_winnings(user, payout)
    apply_rakeback(user, wager)

    db.session.add(BetRecord(
        user_id=user.id, game="fantan", wager=wager, payout=payout, multiplier=multiplier,
        server_seed_hash=user.server_seed_hash, client_seed=user.client_seed, nonce=used_nonce,
        result_json=json.dumps({"pick": pick, "result": result})
    ))
    db.session.commit()

    return jsonify({"result": result, "won": won, "multiplier": multiplier, "payout": payout, "balance": user.balance})
