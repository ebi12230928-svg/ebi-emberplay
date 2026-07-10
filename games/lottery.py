import json

from flask import render_template, request, jsonify
from flask_login import login_required, current_user

from extensions import db
from models import BetRecord
import fairness
from . import games_bp
from .common import validate_wager, apply_rakeback, credit_winnings, scale_multiplier

# 3桁(各0〜9)を予想し、同じ位置で何桁一致したかで配当が決まる(二項分布で全パターン検証済み・house edge約10%)
PAYOUTS = {0: 0, 1: 0, 2: 11.69, 3: 584.42}


@games_bp.route("/lottery")
@login_required
def lottery_page():
    return render_template("games/lottery.html", payouts=PAYOUTS)


@games_bp.route("/lottery/play", methods=["POST"])
@login_required
def lottery_play():
    data = request.get_json(force=True)
    wager = int(data.get("wager", 0))
    pick = data.get("pick")  # 例: [1, 2, 3]

    if not isinstance(pick, list) or len(pick) != 3 or not all(isinstance(n, int) and 0 <= n <= 9 for n in pick):
        return jsonify({"error": "0〜9の数字を3つ選んでください。"}), 400

    error = validate_wager(current_user, wager)
    if error:
        return jsonify({"error": error}), 400

    user = current_user
    user.balance -= wager

    floats = fairness.get_floats(user.server_seed, user.client_seed, user.nonce, 3)
    used_nonce = user.nonce
    user.nonce += 1
    drawn = [min(int(f * 10), 9) for f in floats]

    matches = sum(1 for p, d in zip(pick, drawn) if p == d)
    multiplier = scale_multiplier("lottery", PAYOUTS.get(matches, 0)) if PAYOUTS.get(matches, 0) > 0 else 0
    payout = round(wager * multiplier) if multiplier > 0 else 0

    if payout > 0:
        credit_winnings(user, payout)
    apply_rakeback(user, wager)

    db.session.add(BetRecord(
        user_id=user.id, game="lottery", wager=wager, payout=payout, multiplier=multiplier,
        server_seed_hash=user.server_seed_hash, client_seed=user.client_seed, nonce=used_nonce,
        result_json=json.dumps({"pick": pick, "drawn": drawn, "matches": matches})
    ))
    db.session.commit()

    return jsonify({
        "drawn": drawn, "matches": matches, "multiplier": multiplier,
        "payout": payout, "balance": user.balance
    })
