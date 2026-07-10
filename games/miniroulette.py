import json

from flask import render_template, request, jsonify
from flask_login import login_required, current_user

from extensions import db
from models import BetRecord
from . import games_bp
from .common import validate_wager, apply_rakeback, next_float, credit_winnings, scale_multiplier

# 0〜12の13ポケット(シングルゼロ)の小型ルーレット。全て検証済み(house edge約9%)
RED_NUMBERS = {1, 3, 5, 7, 9, 12}
BET_ODDS = {"straight": 11.83, "red": 1.97, "black": 1.97, "even": 1.97, "odd": 1.97, "low": 1.97, "high": 1.97}


def _is_win(bet_type, value, pocket):
    if bet_type == "straight":
        return pocket == value
    if pocket == 0:
        return False
    if bet_type == "red":
        return pocket in RED_NUMBERS
    if bet_type == "black":
        return pocket not in RED_NUMBERS
    if bet_type == "even":
        return pocket % 2 == 0
    if bet_type == "odd":
        return pocket % 2 == 1
    if bet_type == "low":
        return 1 <= pocket <= 6
    if bet_type == "high":
        return 7 <= pocket <= 12
    return False


@games_bp.route("/miniroulette")
@login_required
def miniroulette_page():
    return render_template("games/miniroulette.html", red_numbers=list(RED_NUMBERS))


@games_bp.route("/miniroulette/spin", methods=["POST"])
@login_required
def miniroulette_spin():
    data = request.get_json(force=True)
    wager = int(data.get("wager", 0))
    bet_type = data.get("bet_type")
    raw_value = data.get("value")

    error = validate_wager(current_user, wager)
    if error:
        return jsonify({"error": error}), 400
    if bet_type not in BET_ODDS:
        return jsonify({"error": "選択の種類が不正です。"}), 400

    value = None
    if bet_type == "straight":
        try:
            value = int(raw_value)
        except (TypeError, ValueError):
            return jsonify({"error": "0〜12の数字を指定してください。"}), 400
        if not (0 <= value <= 12):
            return jsonify({"error": "0〜12の数字を指定してください。"}), 400

    user = current_user
    user.balance -= wager

    f, used_nonce = next_float(user)
    pocket = min(int(f * 13), 12)

    win = _is_win(bet_type, value, pocket)
    multiplier = scale_multiplier("miniroulette", BET_ODDS[bet_type]) if win else 0
    payout = round(wager * multiplier) if win else 0

    credit_winnings(user, payout)
    apply_rakeback(user, wager)

    db.session.add(BetRecord(
        user_id=user.id, game="miniroulette", wager=wager, payout=payout, multiplier=multiplier,
        server_seed_hash=user.server_seed_hash, client_seed=user.client_seed, nonce=used_nonce,
        result_json=json.dumps({"pocket": pocket, "bet_type": bet_type, "value": value})
    ))
    db.session.commit()

    return jsonify({"pocket": pocket, "win": win, "multiplier": multiplier, "payout": payout, "balance": user.balance})
