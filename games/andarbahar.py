import json

from flask import render_template, request, jsonify
from flask_login import login_required, current_user

from extensions import db
from models import BetRecord
import fairness
from . import games_bp
from .common import validate_wager, apply_rakeback, credit_winnings

ANDAR_PAYOUT = 1.81
BAHAR_PAYOUT = 1.96
MAX_CARDS = 200  # 安全装置(到達確率は約0.00001%で実質発生しない)

RANK_NAMES = {1: "A", 11: "J", 12: "Q", 13: "K"}


def rank_label(rank):
    return RANK_NAMES.get(rank, str(rank))


def _draw_rank(user):
    f = fairness.get_float(user.server_seed, user.client_seed, user.nonce)
    used_nonce = user.nonce
    user.nonce += 1
    return int(f * 13) + 1, used_nonce


@games_bp.route("/andarbahar")
@login_required
def andarbahar_page():
    return render_template("games/andarbahar.html")


@games_bp.route("/andarbahar/play", methods=["POST"])
@login_required
def andarbahar_play():
    data = request.get_json(force=True)
    wager = int(data.get("wager", 0))
    pick = data.get("pick")  # "andar" or "bahar"

    error = validate_wager(current_user, wager)
    if error:
        return jsonify({"error": error}), 400
    if pick not in ("andar", "bahar"):
        return jsonify({"error": "選択が不正です。"}), 400

    user = current_user
    user.balance -= wager

    joker, used_nonce = _draw_rank(user)

    andar_cards, bahar_cards = [], []
    winner = None
    side = "andar"
    for _ in range(MAX_CARDS):
        card, _ = _draw_rank(user)
        if side == "andar":
            andar_cards.append(card)
        else:
            bahar_cards.append(card)
        if card == joker:
            winner = side
            break
        side = "bahar" if side == "andar" else "andar"

    if winner is None:
        winner = "andar" if len(andar_cards) <= len(bahar_cards) else "bahar"  # 実質起こらない保険

    won = pick == winner
    multiplier = (ANDAR_PAYOUT if pick == "andar" else BAHAR_PAYOUT) if won else 0
    payout = round(wager * multiplier) if won else 0

    if payout > 0:
        credit_winnings(user, payout)
    apply_rakeback(user, wager)

    db.session.add(BetRecord(
        user_id=user.id, game="andarbahar", wager=wager, payout=payout, multiplier=multiplier,
        server_seed_hash=user.server_seed_hash, client_seed=user.client_seed, nonce=used_nonce,
        result_json=json.dumps({
            "joker": joker, "andar_cards": andar_cards, "bahar_cards": bahar_cards, "winner": winner, "pick": pick
        })
    ))
    db.session.commit()

    return jsonify({
        "joker": rank_label(joker),
        "andar_cards": [rank_label(c) for c in andar_cards],
        "bahar_cards": [rank_label(c) for c in bahar_cards],
        "winner": winner, "won": won, "multiplier": multiplier, "payout": payout, "balance": user.balance
    })
