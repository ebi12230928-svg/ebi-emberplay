import json

from flask import render_template, request, jsonify
from flask_login import login_required, current_user

from extensions import db
from models import BetRecord, WarGame
import fairness
from . import games_bp
from .common import validate_wager, apply_rakeback, credit_winnings

RANK_NAMES = {1: "A", 11: "J", 12: "Q", 13: "K"}


def rank_label(rank):
    return RANK_NAMES.get(rank, str(rank))


def war_value(rank):
    """War独自の強さ順(Aを最強とする)に変換する"""
    return 14 if rank == 1 else rank


def _draw_rank(user):
    f = fairness.get_float(user.server_seed, user.client_seed, user.nonce)
    used_nonce = user.nonce
    user.nonce += 1
    return int(f * 13) + 1, used_nonce


@games_bp.route("/war")
@login_required
def war_page():
    return render_template("games/war.html")


@games_bp.route("/war/start", methods=["POST"])
@login_required
def war_start():
    data = request.get_json(force=True)
    wager = int(data.get("wager", 0))

    if WarGame.query.filter_by(user_id=current_user.id).first():
        return jsonify({"error": "すでに進行中のゲームがあります。"}), 400

    error = validate_wager(current_user, wager)
    if error:
        return jsonify({"error": error}), 400

    user = current_user
    user.balance -= wager

    player_rank, used_nonce = _draw_rank(user)
    dealer_rank, _ = _draw_rank(user)

    if war_value(player_rank) == war_value(dealer_rank):
        game = WarGame(
            user_id=user.id, total_wager=wager, player_rank=player_rank, dealer_rank=dealer_rank,
            server_seed_hash=user.server_seed_hash, client_seed=user.client_seed, nonce=used_nonce
        )
        db.session.add(game)
        db.session.commit()
        return jsonify({
            "tie": True, "player_rank": rank_label(player_rank), "dealer_rank": rank_label(dealer_rank),
            "balance": user.balance
        })

    won = war_value(player_rank) > war_value(dealer_rank)
    payout = wager * 2 if won else 0
    if won:
        credit_winnings(user, payout)
    apply_rakeback(user, wager)

    db.session.add(BetRecord(
        user_id=user.id, game="war", wager=wager, payout=payout, multiplier=2 if won else 0,
        server_seed_hash=user.server_seed_hash, client_seed=user.client_seed, nonce=used_nonce,
        result_json=json.dumps({"player": player_rank, "dealer": dealer_rank})
    ))
    db.session.commit()

    return jsonify({
        "tie": False, "won": won, "player_rank": rank_label(player_rank), "dealer_rank": rank_label(dealer_rank),
        "payout": payout, "balance": user.balance
    })


@games_bp.route("/war/go-to-war", methods=["POST"])
@login_required
def war_go_to_war():
    game = WarGame.query.filter_by(user_id=current_user.id).first()
    if not game:
        return jsonify({"error": "進行中のゲームがありません。"}), 400

    user = current_user
    if game.total_wager > user.balance:
        return jsonify({"error": "残高が不足しています。"}), 400

    user.balance -= game.total_wager
    game.total_wager *= 2

    player_rank, used_nonce = _draw_rank(user)
    dealer_rank, _ = _draw_rank(user)

    if war_value(player_rank) == war_value(dealer_rank):
        # 簡易ルール: 再度引き分けの場合は掛け金をそのまま返す(プッシュ)
        payout = game.total_wager
        credit_winnings(user, payout)
        result = "push"
    elif war_value(player_rank) > war_value(dealer_rank):
        payout = game.total_wager * 2
        credit_winnings(user, payout)
        result = "win"
    else:
        payout = 0
        result = "lose"

    db.session.add(BetRecord(
        user_id=user.id, game="war", wager=game.total_wager, payout=payout,
        multiplier=(payout / game.total_wager) if game.total_wager else 0,
        server_seed_hash=game.server_seed_hash, client_seed=game.client_seed, nonce=used_nonce,
        result_json=json.dumps({"player": player_rank, "dealer": dealer_rank, "war": True})
    ))
    db.session.delete(game)
    db.session.commit()

    return jsonify({
        "result": result, "player_rank": rank_label(player_rank), "dealer_rank": rank_label(dealer_rank),
        "payout": payout, "balance": user.balance
    })


@games_bp.route("/war/surrender", methods=["POST"])
@login_required
def war_surrender():
    game = WarGame.query.filter_by(user_id=current_user.id).first()
    if not game:
        return jsonify({"error": "進行中のゲームがありません。"}), 400

    user = current_user
    payout = round(game.total_wager * 0.5)
    credit_winnings(user, payout)

    db.session.add(BetRecord(
        user_id=user.id, game="war", wager=game.total_wager, payout=payout, multiplier=0.5,
        server_seed_hash=game.server_seed_hash, client_seed=game.client_seed, nonce=game.nonce,
        result_json=json.dumps({"surrendered": True})
    ))
    db.session.delete(game)
    db.session.commit()

    return jsonify({"payout": payout, "balance": user.balance})
