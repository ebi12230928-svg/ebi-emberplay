import json
from collections import Counter

from flask import render_template, request, jsonify
from flask_login import login_required, current_user

from extensions import db
from models import BetRecord, VideoPokerGame
import fairness
from . import games_bp
from .common import validate_wager, apply_rakeback, credit_winnings, scale_multiplier

# Jacks or Better 配当表を通常より引き下げた高難易度版(トータルリターン倍率)
PAYTABLE = [
    ("royal_flush", 500),
    ("straight_flush", 35),
    ("four_kind", 20),
    ("full_house", 6),
    ("flush", 5),
    ("straight", 3.5),
    ("three_kind", 2.5),
    ("two_pair", 1.5),
    ("jacks_or_better", 1),
    ("nothing", 0),
]
HAND_LABELS = {
    "royal_flush": "Royal Flush", "straight_flush": "Straight Flush", "four_kind": "Four of a Kind",
    "full_house": "Full House", "flush": "Flush", "straight": "Straight", "three_kind": "Three of a Kind",
    "two_pair": "Two Pair", "jacks_or_better": "Jacks or Better", "nothing": "No Win",
}


def _rank(card_index):
    return (card_index % 13) + 1


def _suit(card_index):
    return card_index // 13


def _card_label(card_index):
    rank = _rank(card_index)
    suit = "♠♥♦♣"[_suit(card_index)]
    names = {1: "A", 11: "J", 12: "Q", 13: "K"}
    return f"{names.get(rank, str(rank))}{suit}"


def _evaluate(cards):
    ranks = sorted(_rank(c) for c in cards)
    suits = [_suit(c) for c in cards]
    is_flush = len(set(suits)) == 1

    unique_ranks = sorted(set(ranks))
    is_straight = False
    if len(unique_ranks) == 5:
        if unique_ranks[-1] - unique_ranks[0] == 4:
            is_straight = True
        elif unique_ranks == [1, 10, 11, 12, 13]:  # A-10-J-Q-K(ブロードウェイ)
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
        if pair_rank in (1, 11, 12, 13):
            return "jacks_or_better"
    return "nothing"


PAYOUT_MAP = dict(PAYTABLE)


@games_bp.route("/videopoker")
@login_required
def videopoker_page():
    return render_template("games/videopoker.html", paytable=[(HAND_LABELS[k], v) for k, v in PAYTABLE])


@games_bp.route("/videopoker/deal", methods=["POST"])
@login_required
def videopoker_deal():
    data = request.get_json(force=True)
    wager = int(data.get("wager", 0))

    if VideoPokerGame.query.filter_by(user_id=current_user.id).first():
        return jsonify({"error": "すでに進行中のゲームがあります。"}), 400

    error = validate_wager(current_user, wager)
    if error:
        return jsonify({"error": error}), 400

    user = current_user
    user.balance -= wager

    order = fairness.shuffle_indices(user.server_seed, user.client_seed, user.nonce, 52)
    used_nonce = user.nonce
    user.nonce += 1

    hand = order[:5]
    deck = order[5:]

    game = VideoPokerGame(
        user_id=user.id, wager=wager, hand_json=json.dumps(hand), deck_json=json.dumps(deck),
        server_seed_hash=user.server_seed_hash, client_seed=user.client_seed, nonce=used_nonce
    )
    db.session.add(game)
    db.session.commit()

    return jsonify({"balance": user.balance, "hand": [_card_label(c) for c in hand]})


@games_bp.route("/videopoker/draw", methods=["POST"])
@login_required
def videopoker_draw():
    data = request.get_json(force=True)
    holds = data.get("holds", [False] * 5)

    game = VideoPokerGame.query.filter_by(user_id=current_user.id).first()
    if not game:
        return jsonify({"error": "進行中のゲームがありません。"}), 400
    if not isinstance(holds, list) or len(holds) != 5:
        return jsonify({"error": "ホールドの指定が不正です。"}), 400

    hand = json.loads(game.hand_json)
    deck = json.loads(game.deck_json)

    final_hand = []
    for i in range(5):
        if holds[i]:
            final_hand.append(hand[i])
        else:
            final_hand.append(deck.pop(0))

    hand_type = _evaluate(final_hand)
    multiplier = PAYOUT_MAP[hand_type]
    multiplier = scale_multiplier("videopoker", multiplier)
    payout = round(game.wager * multiplier)

    user = current_user
    credit_winnings(user, payout)
    apply_rakeback(user, game.wager)

    db.session.add(BetRecord(
        user_id=user.id, game="videopoker", wager=game.wager, payout=payout, multiplier=multiplier,
        server_seed_hash=game.server_seed_hash, client_seed=game.client_seed, nonce=game.nonce,
        result_json=json.dumps({"hand": [_card_label(c) for c in final_hand], "hand_type": hand_type})
    ))
    db.session.delete(game)
    db.session.commit()

    return jsonify({
        "hand": [_card_label(c) for c in final_hand], "hand_type": HAND_LABELS[hand_type],
        "multiplier": multiplier, "payout": payout, "balance": user.balance
    })
