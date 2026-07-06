import json

from flask import render_template, request, jsonify
from flask_login import login_required, current_user

from extensions import db
from models import BetRecord
import fairness
from . import games_bp
from .common import validate_wager, apply_rakeback, credit_winnings

PLINKO_HOUSE_EDGE = 0.06
ALLOWED_ROWS = (8, 12, 16)
ALLOWED_RISK = ("low", "medium", "high")


@games_bp.route("/plinko")
@login_required
def plinko_page():
    return render_template("games/plinko.html", rows_options=ALLOWED_ROWS)


@games_bp.route("/plinko/play", methods=["POST"])
@login_required
def plinko_play():
    data = request.get_json(force=True)
    wager = int(data.get("wager", 0))
    rows = int(data.get("rows", 16))
    risk = data.get("risk", "medium")

    error = validate_wager(current_user, wager)
    if error:
        return jsonify({"error": error}), 400
    if rows not in ALLOWED_ROWS:
        return jsonify({"error": "行数が不正です。"}), 400
    if risk not in ALLOWED_RISK:
        return jsonify({"error": "リスクの指定が不正です。"}), 400

    user = current_user
    user.balance -= wager

    path = fairness.binomial_path(user.server_seed, user.client_seed, user.nonce, rows)
    used_nonce = user.nonce
    user.nonce += 1

    bucket = sum(path)
    table = fairness.plinko_table(rows, risk, house_edge=PLINKO_HOUSE_EDGE)
    multiplier = table[bucket]
    payout = round(wager * multiplier)

    credit_winnings(user, payout)
    apply_rakeback(user, wager)

    db.session.add(BetRecord(
        user_id=user.id, game="plinko", wager=wager, payout=payout, multiplier=multiplier,
        server_seed_hash=user.server_seed_hash, client_seed=user.client_seed, nonce=used_nonce,
        result_json=json.dumps({"path": path, "bucket": bucket, "rows": rows, "risk": risk})
    ))
    db.session.commit()

    return jsonify({
        "path": path, "bucket": bucket, "table": table, "multiplier": multiplier,
        "payout": payout, "balance": user.balance
    })
