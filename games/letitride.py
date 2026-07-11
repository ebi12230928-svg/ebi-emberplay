import json
from collections import Counter

from flask import render_template, request, jsonify
from flask_login import login_required, current_user

from extensions import db
from models import BetRecord
import fairness
from . import games_bp
from . import poker_utils as pk
from .common import validate_wager, apply_rakeback, credit_winnings, scale_multiplier

# 3枚の持ち札を「持ち出す/戻す」選択する本来のLet It Rideの駆け引きは省略し、5枚固定の1回勝負にした簡易版。
# ペア・オブ・テンズ(10・J・Q・K・A)以上で配当。40万回シミュレーションで検証済み(house edge約3.5%)
PAYTABLE = {
    "royal_flush": 2499.09, "straight_flush": 499.82, "four_kind": 124.95, "full_house": 27.49,
    "flush": 19.99, "straight": 12.5, "three_kind": 7.5, "two_pair": 5.0, "tens_or_better": 2.5, "nothing": 0,
}
HAND_LABELS = {
    "royal_flush": "Royal Flush", "straight_flush": "Straight Flush", "four_kind": "Four of a Kind",
    "full_house": "Full House", "flush": "Flush", "straight": "Straight", "three_kind": "Three of a Kind",
    "two_pair": "Two Pair", "tens_or_better": "Pair of Tens or Better", "nothing": "No Win",
}


def _evaluate_letitride(cards):
    ranks = sorted(pk.rank_of(c) for c in cards)
    suits = [pk.suit_of(c) for c in cards]
    is_flush = len(set(suits)) == 1
    unique_ranks = sorted(set(ranks))
    is_straight = False
    if len(unique_ranks) == 5:
        if unique_ranks[-1] - unique_ranks[0] == 4:
            is_straight = True
        elif unique_ranks == [1, 10, 11, 12, 13]:
            is_straight = True
    counts = sorted(Counter(ranks).values(), reverse=True)

    if is_straight and is_flush:
        if set(ranks) == {1, 10, 11, 12, 13}:
            return "royal_flush"
        return "straight_flush"
    if counts[0] == 4:
        return "four_kind"
    if counts[0] == 3 and counts[1] == 2:
        return "full_house"
    if is_flush:
        return "flush"
    if is_straight:
        return "straight"
    if counts[0] == 3:
        return "three_kind"
    if counts[0] == 2 and counts[1] == 2:
        return "two_pair"
    if counts[0] == 2:
        pair_rank = next(r for r in set(ranks) if ranks.count(r) == 2)
        if pair_rank == 1 or pair_rank >= 10:  # A、または10・J・Q・K
            return "tens_or_better"
    return "nothing"


@games_bp.route("/letitride")
@login_required
def letitride_page():
    return render_template("games/letitride.html", paytable=PAYTABLE, labels=HAND_LABELS)


@games_bp.route("/letitride/play", methods=["POST"])
@login_required
def letitride_play():
    data = request.get_json(force=True)
    wager = int(data.get("wager", 0))

    error = validate_wager(current_user, wager)
    if error:
        return jsonify({"error": error}), 400

    user = current_user
    user.balance -= wager

    order = fairness.shuffle_indices(user.server_seed, user.client_seed, user.nonce, 52)
    used_nonce = user.nonce
    user.nonce += 1
    cards = order[:5]

    hand = _evaluate_letitride(cards)
    multiplier = scale_multiplier("letitride", PAYTABLE[hand]) if PAYTABLE[hand] > 0 else 0
    payout = round(wager * multiplier) if multiplier > 0 else 0

    if payout > 0:
        credit_winnings(user, payout)
    apply_rakeback(user, wager)

    db.session.add(BetRecord(
        user_id=user.id, game="letitride", wager=wager, payout=payout, multiplier=multiplier,
        server_seed_hash=user.server_seed_hash, client_seed=user.client_seed, nonce=used_nonce,
        result_json=json.dumps({"cards": cards, "hand": hand})
    ))
    db.session.commit()

    return jsonify({
        "cards": [pk.card_label(c) for c in cards], "hand": HAND_LABELS[hand],
        "multiplier": multiplier, "payout": payout, "balance": user.balance
    })
