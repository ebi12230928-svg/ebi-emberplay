import json
from collections import Counter

from flask import render_template, request, jsonify
from flask_login import login_required, current_user

from extensions import db
from models import BetRecord, ThreeCardPokerGame
import fairness
from . import games_bp
from .common import validate_wager, apply_rakeback, credit_winnings, scale_multiplier

ANTE_BONUS = {6: 5.0, 5: 4.0, 4: 1.0}  # カテゴリ番号 -> Anteに追加で払うボーナス倍率
CATEGORY_NAMES = {
    6: "Straight Flush", 5: "Three of a Kind", 4: "Straight",
    3: "Flush", 2: "Pair", 1: "High Card",
}


def _rank(card_idx):
    return (card_idx % 13) + 1


def _suit(card_idx):
    return card_idx // 13


def _card_label(card_idx):
    rank = _rank(card_idx)
    suit = "♠♥♦♣"[_suit(card_idx)]
    names = {1: "A", 11: "J", 12: "Q", 13: "K"}
    return f"{names.get(rank, str(rank))}{suit}"


def _classify(cards):
    ranks = sorted((_rank(c) for c in cards), reverse=True)
    suits = [_suit(c) for c in cards]
    is_flush = len(set(suits)) == 1

    unique = sorted(set(ranks))
    is_straight = False
    straight_high = None
    if len(unique) == 3 and unique[2] - unique[0] == 2:
        is_straight = True
        straight_high = unique[2]
    if not is_straight and set(ranks) == {1, 12, 13}:  # Q,K,A
        is_straight = True
        straight_high = 14

    counts = Counter(ranks)
    count_values = sorted(counts.values(), reverse=True)

    if is_straight and is_flush:
        return (6, straight_high)
    if count_values[0] == 3:
        return (5, ranks[0])
    if is_straight:
        return (4, straight_high)
    if is_flush:
        return (3, tuple(ranks))
    if count_values[0] == 2:
        pair_rank = next(r for r, c in counts.items() if c == 2)
        kicker = next(r for r, c in counts.items() if c == 1)
        return (2, pair_rank, kicker)
    return (1, tuple(ranks))


def _dealer_qualifies(dealer_hand_class):
    """Queen-high以上でクオリファイ(ペア以上は自動的にクオリファイ、High Cardの場合はQ以上が必要)"""
    if dealer_hand_class[0] >= 2:
        return True
    top_rank = dealer_hand_class[1][0]
    return top_rank >= 12


def _new_deck(user):
    order = fairness.shuffle_indices(user.server_seed, user.client_seed, user.nonce, 52)
    used_nonce = user.nonce
    user.nonce += 1
    return order, used_nonce


@games_bp.route("/threecardpoker")
@login_required
def threecardpoker_page():
    return render_template("games/threecardpoker.html")


@games_bp.route("/threecardpoker/deal", methods=["POST"])
@login_required
def threecardpoker_deal():
    data = request.get_json(force=True)
    ante = int(data.get("ante", 0))

    if ThreeCardPokerGame.query.filter_by(user_id=current_user.id).first():
        return jsonify({"error": "すでに進行中のゲームがあります。"}), 400

    error = validate_wager(current_user, ante)
    if error:
        return jsonify({"error": error}), 400

    user = current_user
    user.balance -= ante

    deck, used_nonce = _new_deck(user)
    player_hand = [deck.pop(0), deck.pop(0), deck.pop(0)]
    dealer_hand = [deck.pop(0), deck.pop(0), deck.pop(0)]

    game = ThreeCardPokerGame(
        user_id=user.id, ante=ante,
        player_hand_json=json.dumps(player_hand), dealer_hand_json=json.dumps(dealer_hand),
        server_seed_hash=user.server_seed_hash, client_seed=user.client_seed, nonce=used_nonce
    )
    db.session.add(game)
    db.session.commit()

    player_class = _classify(player_hand)
    return jsonify({
        "balance": user.balance,
        "player_hand": [_card_label(c) for c in player_hand],
        "player_hand_name": CATEGORY_NAMES[player_class[0]],
    })


def _resolve(user, game, folded):
    player_hand = json.loads(game.player_hand_json)
    dealer_hand = json.loads(game.dealer_hand_json)

    player_class = _classify(player_hand)
    dealer_class = _classify(dealer_hand)

    ante_bonus_multiplier = ANTE_BONUS.get(player_class[0], 0)
    if ante_bonus_multiplier > 0:
        ante_bonus_multiplier = scale_multiplier("threecardpoker", ante_bonus_multiplier)
    ante_bonus_payout = round(game.ante * ante_bonus_multiplier)

    win_multiplier = scale_multiplier("threecardpoker", 2.0)

    play_wager = 0
    if folded:
        ante_payout = 0
        play_payout = 0
        result = "folded"
    else:
        play_wager = game.ante
        user.balance -= play_wager  # Playベットの追加投資

        qualifies = _dealer_qualifies(dealer_class)
        if not qualifies:
            ante_payout = round(game.ante * win_multiplier)  # Anteは1:1相当
            play_payout = play_wager                          # Playはプッシュ
            result = "dealer_not_qualified"
        elif player_class > dealer_class:
            ante_payout = round(game.ante * win_multiplier)
            play_payout = round(play_wager * win_multiplier)
            result = "win"
        elif player_class < dealer_class:
            ante_payout = 0
            play_payout = 0
            result = "lose"
        else:
            ante_payout = game.ante
            play_payout = play_wager
            result = "push"

    total_payout = ante_payout + play_payout + ante_bonus_payout
    if total_payout > 0:
        credit_winnings(user, total_payout)
    apply_rakeback(user, game.ante + play_wager)

    db.session.add(BetRecord(
        user_id=user.id, game="threecardpoker", wager=game.ante + play_wager,
        payout=total_payout,
        multiplier=(total_payout / game.ante) if game.ante else 0,
        server_seed_hash=game.server_seed_hash, client_seed=game.client_seed, nonce=game.nonce,
        result_json=json.dumps({
            "player_hand": [_card_label(c) for c in player_hand],
            "dealer_hand": [_card_label(c) for c in dealer_hand],
            "result": result, "folded": folded,
        })
    ))
    db.session.delete(game)
    db.session.commit()

    return {
        "dealer_hand": [_card_label(c) for c in dealer_hand],
        "dealer_hand_name": CATEGORY_NAMES[dealer_class[0]],
        "player_hand_name": CATEGORY_NAMES[player_class[0]],
        "result": result,
        "ante_payout": ante_payout, "play_payout": play_payout, "ante_bonus_payout": ante_bonus_payout,
        "total_payout": total_payout, "balance": user.balance,
    }


@games_bp.route("/threecardpoker/play", methods=["POST"])
@login_required
def threecardpoker_play():
    game = ThreeCardPokerGame.query.filter_by(user_id=current_user.id).first()
    if not game:
        return jsonify({"error": "進行中のゲームがありません。"}), 400

    user = current_user
    if game.ante > user.balance:
        return jsonify({"error": "残高が不足しています(Playベットにはante分の残高が必要です)。"}), 400

    return jsonify(_resolve(user, game, folded=False))


@games_bp.route("/threecardpoker/fold", methods=["POST"])
@login_required
def threecardpoker_fold():
    game = ThreeCardPokerGame.query.filter_by(user_id=current_user.id).first()
    if not game:
        return jsonify({"error": "進行中のゲームがありません。"}), 400

    return jsonify(_resolve(current_user, game, folded=True))
