import json

from flask import render_template, request, jsonify
from flask_login import login_required, current_user

from extensions import db
from models import BetRecord
from . import games_bp
from .common import validate_wager, apply_rakeback, next_float, credit_winnings

RED_NUMBERS = {1, 3, 5, 7, 9, 12, 14, 16, 18, 19, 21, 23, 25, 27, 30, 32, 34, 36}

# アメリカンルーレットは00が追加される分ポケット数が38になり、house edgeが自然に上がる(00以外は配当は変えない)
BET_ODDS = {
    "straight": 33, "red": 1.9, "black": 1.9, "odd": 1.9, "even": 1.9, "low": 1.9, "high": 1.9,
    "dozen1": 2.8, "dozen2": 2.8, "dozen3": 2.8, "col1": 2.8, "col2": 2.8, "col3": 2.8,
}


def _is_win(bet_type, value, pocket):
    if bet_type == "straight":
        return pocket == value
    if pocket == 0 or pocket == -1:  # 0 と 00 はストレート以外すべて負け
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


def _pocket_label(pocket):
    return "00" if pocket == -1 else str(pocket)


@games_bp.route("/american-roulette")
@login_required
def american_roulette_page():
    return render_template("games/american_roulette.html", red_numbers=list(RED_NUMBERS))


@games_bp.route("/american-roulette/spin", methods=["POST"])
@login_required
def american_roulette_spin():
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
        if raw_value == "00":
            value = -1
        else:
            try:
                value = int(raw_value)
            except (TypeError, ValueError):
                return jsonify({"error": "ストレート選択には00または0〜36の数字を指定してください。"}), 400
            if not (0 <= value <= 36):
                return jsonify({"error": "ストレート選択には00または0〜36の数字を指定してください。"}), 400

    user = current_user
    user.balance -= wager

    f, used_nonce = next_float(user)
    idx = min(int(f * 38), 37)
    pocket = -1 if idx == 37 else idx  # idx 0-36は通常の数字、37番目が00

    win = _is_win(bet_type, value, pocket)
    multiplier = BET_ODDS[bet_type] if win else 0
    payout = round(wager * multiplier) if win else 0

    credit_winnings(user, payout)
    apply_rakeback(user, wager)

    db.session.add(BetRecord(
        user_id=user.id, game="american_roulette", wager=wager, payout=payout, multiplier=multiplier,
        server_seed_hash=user.server_seed_hash, client_seed=user.client_seed, nonce=used_nonce,
        result_json=json.dumps({"pocket": pocket, "bet_type": bet_type, "value": value})
    ))
    db.session.commit()

    return jsonify({
        "pocket": _pocket_label(pocket), "win": win, "multiplier": multiplier,
        "payout": payout, "balance": user.balance
    })
