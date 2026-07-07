import json

from flask import render_template, request, jsonify
from flask_login import login_required, current_user

from extensions import db
from models import BetRecord, BlackjackGame
import fairness
from . import games_bp
from .common import validate_wager, apply_rakeback, credit_winnings, scale_multiplier

BJ_HOUSE_EDGE_NOTE = "標準ルール(ディーラーは17以上でスタンド、ブラックジャックは3:2配当)"


def _rank(card_index):
    return (card_index % 13) + 1


def _card_label(card_index):
    rank = _rank(card_index)
    suit = "♠♥♦♣"[card_index // 13]
    names = {1: "A", 11: "J", 12: "Q", 13: "K"}
    return f"{names.get(rank, str(rank))}{suit}"


def _hand_value(cards):
    total = 0
    aces = 0
    for c in cards:
        r = _rank(c)
        if r == 1:
            aces += 1
            total += 11
        elif r >= 10:
            total += 10
        else:
            total += r
    while total > 21 and aces > 0:
        total -= 10
        aces -= 1
    return total


def _is_blackjack(cards):
    return len(cards) == 2 and _hand_value(cards) == 21


def _new_deck(user):
    order = fairness.shuffle_indices(user.server_seed, user.client_seed, user.nonce, 52)
    used_nonce = user.nonce
    user.nonce += 1
    return order, used_nonce


def _serialize_hand(cards):
    return [_card_label(c) for c in cards]


def _settle(user, game, player, dealer, base_wager):
    player_total = _hand_value(player)
    dealer_total = _hand_value(dealer)
    player_bj = _is_blackjack(player) and not game.doubled
    dealer_bj = _is_blackjack(dealer)

    if player_total > 21:
        multiplier = 0
    elif player_bj and dealer_bj:
        multiplier = 1.0
    elif player_bj:
        multiplier = 2.3  # ブラックジャック配当を3:2(2.5)から6:5(2.3)に変更
    elif dealer_bj:
        multiplier = 0
    elif dealer_total > 21:
        multiplier = 2.0
    elif player_total > dealer_total:
        multiplier = 2.0
    elif player_total < dealer_total:
        multiplier = 0
    else:
        multiplier = 1.0

    if multiplier > 1.0:
        multiplier = scale_multiplier("blackjack", multiplier)

    payout = round(base_wager * multiplier)
    credit_winnings(user, payout)
    apply_rakeback(user, base_wager)

    db.session.add(BetRecord(
        user_id=user.id, game="blackjack", wager=base_wager, payout=payout, multiplier=multiplier,
        server_seed_hash=game.server_seed_hash, client_seed=game.client_seed, nonce=game.nonce,
        result_json=json.dumps({"player": _serialize_hand(player), "dealer": _serialize_hand(dealer)})
    ))
    db.session.delete(game)
    db.session.commit()

    return {
        "finished": True, "player": _serialize_hand(player), "dealer": _serialize_hand(dealer),
        "player_total": player_total, "dealer_total": dealer_total,
        "multiplier": multiplier, "payout": payout, "balance": user.balance
    }


@games_bp.route("/blackjack")
@login_required
def blackjack_page():
    return render_template("games/blackjack.html")


@games_bp.route("/blackjack/start", methods=["POST"])
@login_required
def blackjack_start():
    data = request.get_json(force=True)
    wager = int(data.get("wager", 0))

    if BlackjackGame.query.filter_by(user_id=current_user.id).first():
        return jsonify({"error": "すでに進行中のゲームがあります。"}), 400

    error = validate_wager(current_user, wager)
    if error:
        return jsonify({"error": error}), 400

    user = current_user
    user.balance -= wager

    deck, used_nonce = _new_deck(user)
    player = [deck.pop(0), deck.pop(0)]
    dealer = [deck.pop(0), deck.pop(0)]

    game = BlackjackGame(
        user_id=user.id, wager=wager, deck_json=json.dumps(deck),
        player_hand_json=json.dumps(player), dealer_hand_json=json.dumps(dealer),
        doubled=False, finished=False,
        server_seed_hash=user.server_seed_hash, client_seed=user.client_seed, nonce=used_nonce
    )
    db.session.add(game)
    db.session.commit()

    if _is_blackjack(player) or _is_blackjack(dealer):
        result = _settle(user, game, player, dealer, wager)
        return jsonify(result)

    return jsonify({
        "finished": False,
        "player": _serialize_hand(player),
        "dealer_upcard": _card_label(dealer[0]),
        "player_total": _hand_value(player),
        "balance": user.balance,
        "can_double": True,
    })


@games_bp.route("/blackjack/hit", methods=["POST"])
@login_required
def blackjack_hit():
    game = BlackjackGame.query.filter_by(user_id=current_user.id).first()
    if not game:
        return jsonify({"error": "進行中のゲームがありません。"}), 400

    deck = json.loads(game.deck_json)
    player = json.loads(game.player_hand_json)
    dealer = json.loads(game.dealer_hand_json)

    player.append(deck.pop(0))
    game.deck_json = json.dumps(deck)
    game.player_hand_json = json.dumps(player)

    if _hand_value(player) > 21:
        result = _settle(current_user, game, player, dealer, game.wager)
        return jsonify(result)

    db.session.commit()
    return jsonify({
        "finished": False, "player": _serialize_hand(player),
        "player_total": _hand_value(player), "can_double": False
    })


@games_bp.route("/blackjack/double", methods=["POST"])
@login_required
def blackjack_double():
    game = BlackjackGame.query.filter_by(user_id=current_user.id).first()
    if not game:
        return jsonify({"error": "進行中のゲームがありません。"}), 400

    player = json.loads(game.player_hand_json)
    if len(player) != 2 or game.doubled:
        return jsonify({"error": "ダブルダウンは最初の1手でのみ行えます。"}), 400

    user = current_user
    if game.wager > user.balance:
        return jsonify({"error": "残高が不足しています。"}), 400

    user.balance -= game.wager
    game.doubled = True
    total_wager = game.wager * 2

    deck = json.loads(game.deck_json)
    dealer = json.loads(game.dealer_hand_json)
    player.append(deck.pop(0))
    game.deck_json = json.dumps(deck)
    game.player_hand_json = json.dumps(player)
    game.wager = total_wager
    db.session.commit()

    if _hand_value(player) > 21:
        result = _settle(user, game, player, dealer, total_wager)
        return jsonify(result)

    return _dealer_play_and_settle(user, game, player, dealer, total_wager)


@games_bp.route("/blackjack/stand", methods=["POST"])
@login_required
def blackjack_stand():
    game = BlackjackGame.query.filter_by(user_id=current_user.id).first()
    if not game:
        return jsonify({"error": "進行中のゲームがありません。"}), 400

    player = json.loads(game.player_hand_json)
    dealer = json.loads(game.dealer_hand_json)
    return _dealer_play_and_settle(current_user, game, player, dealer, game.wager)


def _dealer_play_and_settle(user, game, player, dealer, total_wager):
    deck = json.loads(game.deck_json)
    while _hand_value(dealer) < 17:
        dealer.append(deck.pop(0))
    game.deck_json = json.dumps(deck)
    game.dealer_hand_json = json.dumps(dealer)
    result = _settle(user, game, player, dealer, total_wager)
    return jsonify(result)
