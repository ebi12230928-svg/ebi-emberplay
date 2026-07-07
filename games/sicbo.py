import json

from flask import render_template, request, jsonify
from flask_login import login_required, current_user

from extensions import db
from models import BetRecord
from . import games_bp
from .common import validate_wager, apply_rakeback, credit_winnings, scale_multiplier

# 合計値ごとの配当(house edge約12%で正規化済み)
TOTAL_PAYOUTS = {
    4: 63.36, 5: 31.68, 6: 19.01, 7: 12.67, 8: 9.05, 9: 7.6, 10: 7.04,
    11: 7.04, 12: 7.6, 13: 9.05, 14: 12.67, 15: 19.01, 16: 31.68, 17: 63.36,
}
BIG_SMALL_PAYOUT = 1.85
ANY_TRIPLE_PAYOUT = 30.6
SPECIFIC_TRIPLE_PAYOUT = 180
DOUBLE_SPECIFIC_PAYOUT = 10
SINGLE_NUMBER_PAYOUTS = {0: 0, 1: 2, 2: 3, 3: 4}  # 一致数ごとのトータルリターン倍率


@games_bp.route("/sicbo")
@login_required
def sicbo_page():
    return render_template("games/sicbo.html", total_payouts=TOTAL_PAYOUTS)


def _roll_three(user):
    import fairness
    floats = fairness.get_floats(user.server_seed, user.client_seed, user.nonce, 3)
    used_nonce = user.nonce
    user.nonce += 1
    dice = [min(int(f * 6) + 1, 6) for f in floats]
    return dice, used_nonce


@games_bp.route("/sicbo/play", methods=["POST"])
@login_required
def sicbo_play():
    data = request.get_json(force=True)
    wager = int(data.get("wager", 0))
    bet_type = data.get("bet_type")
    value = data.get("value")

    error = validate_wager(current_user, wager)
    if error:
        return jsonify({"error": error}), 400
    if bet_type not in ("big", "small", "total", "any_triple", "specific_triple", "double_specific", "single_number"):
        return jsonify({"error": "選択の種類が不正です。"}), 400

    user = current_user
    user.balance -= wager

    dice, used_nonce = _roll_three(user)
    total = sum(dice)
    is_triple = dice[0] == dice[1] == dice[2]

    multiplier = 0

    if bet_type == "big":
        if not is_triple and 11 <= total <= 17:
            multiplier = BIG_SMALL_PAYOUT
    elif bet_type == "small":
        if not is_triple and 4 <= total <= 10:
            multiplier = BIG_SMALL_PAYOUT
    elif bet_type == "total":
        try:
            target = int(value)
        except (TypeError, ValueError):
            return jsonify({"error": "合計値の指定が不正です。"}), 400
        if total == target:
            multiplier = TOTAL_PAYOUTS.get(target, 0)
    elif bet_type == "any_triple":
        if is_triple:
            multiplier = ANY_TRIPLE_PAYOUT
    elif bet_type == "specific_triple":
        try:
            target = int(value)
        except (TypeError, ValueError):
            return jsonify({"error": "数字の指定が不正です。"}), 400
        if is_triple and dice[0] == target:
            multiplier = SPECIFIC_TRIPLE_PAYOUT
    elif bet_type == "double_specific":
        try:
            target = int(value)
        except (TypeError, ValueError):
            return jsonify({"error": "数字の指定が不正です。"}), 400
        if dice.count(target) >= 2:
            multiplier = DOUBLE_SPECIFIC_PAYOUT
    elif bet_type == "single_number":
        try:
            target = int(value)
        except (TypeError, ValueError):
            return jsonify({"error": "数字の指定が不正です。"}), 400
        match_count = dice.count(target)
        multiplier = SINGLE_NUMBER_PAYOUTS.get(match_count, 0)

    multiplier = scale_multiplier("sicbo", multiplier) if multiplier > 0 else 0
    payout = round(wager * multiplier) if multiplier > 0 else 0
    if payout > 0:
        credit_winnings(user, payout)
    apply_rakeback(user, wager)

    db.session.add(BetRecord(
        user_id=user.id, game="sicbo", wager=wager, payout=payout, multiplier=multiplier,
        server_seed_hash=user.server_seed_hash, client_seed=user.client_seed, nonce=used_nonce,
        result_json=json.dumps({"dice": dice, "bet_type": bet_type, "value": value})
    ))
    db.session.commit()

    return jsonify({"dice": dice, "total": total, "multiplier": multiplier, "payout": payout, "balance": user.balance})
