import json

from flask import render_template, request, jsonify
from flask_login import login_required, current_user

from extensions import db
from models import BetRecord
from . import games_bp
from .common import validate_wager, apply_rakeback, next_float, credit_winnings, scale_multiplier

RED_NUMBERS = {1, 3, 5, 7, 9, 12, 14, 16, 18, 19, 21, 23, 25, 27, 30, 32, 34, 36}

BET_ODDS = {
    "straight": 33, "red": 1.9, "black": 1.9, "odd": 1.9, "even": 1.9, "low": 1.9, "high": 1.9,
    "dozen1": 2.8, "dozen2": 2.8, "dozen3": 2.8, "col1": 2.8, "col2": 2.8, "col3": 2.8,
}


def _is_win(bet_type, value, pocket):
    if bet_type == "straight":
        return pocket == value
    if pocket == 0:
        return False
    if bet_type == "red":
        return pocket in RED_NUMBERS
    if bet_type == "black":
        return pocket not in RED_NUMBERS
    if bet_type == "odd":
        return pocket % 2 == 1
    if bet_type == "even":
        return pocket % 2 == 0
    if bet_type == "low":
        return 1 <= pocket <= 18
    if bet_type == "high":
        return 19 <= pocket <= 36
    if bet_type == "dozen1":
        return 1 <= pocket <= 12
    if bet_type == "dozen2":
        return 13 <= pocket <= 24
    if bet_type == "dozen3":
        return 25 <= pocket <= 36
    if bet_type == "col1":
        return pocket % 3 == 1
    if bet_type == "col2":
        return pocket % 3 == 2
    if bet_type == "col3":
        return pocket % 3 == 0
    return False


@games_bp.route("/roulette")
@login_required
def roulette_page():
    return render_template("games/roulette.html", red_numbers=list(RED_NUMBERS))


@games_bp.route("/roulette/spin", methods=["POST"])
@login_required
def roulette_spin():
    data = request.get_json(force=True)
    wager = int(data.get("wager", 0))
    bet_type = data.get("bet_type")
    value = data.get("value")

    error = validate_wager(current_user, wager)
    if error:
        return jsonify({"error": error}), 400
    if bet_type not in BET_ODDS:
        return jsonify({"error": "選択の種類が不正です。"}), 400
    if bet_type == "straight":
        try:
            value = int(value)
        except (TypeError, ValueError):
            return jsonify({"error": "ストレート選択には0〜36の数字を指定してください。"}), 400
        if not (0 <= value <= 36):
            return jsonify({"error": "ストレート選択には0〜36の数字を指定してください。"}), 400

    user = current_user
    user.balance -= wager

    f, used_nonce = next_float(user)
    pocket = min(int(f * 37), 36)

    win = _is_win(bet_type, value, pocket)
    multiplier = scale_multiplier("roulette", BET_ODDS[bet_type]) if win else 0
    payout = round(wager * multiplier) if win else 0

    credit_winnings(user, payout)
    apply_rakeback(user, wager)

    db.session.add(BetRecord(
        user_id=user.id, game="roulette", wager=wager, payout=payout, multiplier=multiplier,
        server_seed_hash=user.server_seed_hash, client_seed=user.client_seed, nonce=used_nonce,
        result_json=json.dumps({"pocket": pocket, "bet_type": bet_type, "value": value})
    ))
    db.session.commit()

    return jsonify({
        "pocket": pocket, "win": win, "multiplier": multiplier,
        "payout": payout, "balance": user.balance
    })
