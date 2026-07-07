import json

from flask import render_template, request, jsonify
from flask_login import login_required, current_user

from extensions import db
from models import BetRecord, HiLoGame
import fairness
from . import games_bp
from .common import validate_wager, apply_rakeback, credit_winnings, scale_multiplier

HILO_HOUSE_EDGE = 0.07
MAX_PASSES = 2
RANK_NAMES = {1: "A", 11: "J", 12: "Q", 13: "K"}


def rank_label(rank):
    return RANK_NAMES.get(rank, str(rank))


def _draw_rank(user):
    f = fairness.get_float(user.server_seed, user.client_seed, user.nonce)
    used_nonce = user.nonce
    user.nonce += 1
    rank = int(f * 13) + 1
    return rank, used_nonce


@games_bp.route("/hilo")
@login_required
def hilo_page():
    return render_template("games/hilo.html", max_passes=MAX_PASSES)


@games_bp.route("/hilo/start", methods=["POST"])
@login_required
def hilo_start():
    data = request.get_json(force=True)
    wager = int(data.get("wager", 0))

    if HiLoGame.query.filter_by(user_id=current_user.id).first():
        return jsonify({"error": "すでに進行中のゲームがあります。"}), 400

    error = validate_wager(current_user, wager)
    if error:
        return jsonify({"error": error}), 400

    user = current_user
    user.balance -= wager

    rank, used_nonce = _draw_rank(user)
    game = HiLoGame(
        user_id=user.id, wager=wager, current_rank=rank, multiplier=1.0, rounds_played=0, passes_used=0,
        server_seed_hash=user.server_seed_hash, client_seed=user.client_seed, nonce=used_nonce
    )
    db.session.add(game)
    db.session.commit()

    return jsonify({"balance": user.balance, "rank": rank, "rank_label": rank_label(rank), "multiplier": 1.0})


@games_bp.route("/hilo/pass", methods=["POST"])
@login_required
def hilo_pass():
    """現在のカードを賭けずにスキップし、新しいカードを引き直す(回数制限あり)"""
    game = HiLoGame.query.filter_by(user_id=current_user.id).first()
    if not game:
        return jsonify({"error": "進行中のゲームがありません。"}), 400
    if game.passes_used >= MAX_PASSES:
        return jsonify({"error": f"パスは1ゲームにつき{MAX_PASSES}回までです。"}), 400

    user = current_user
    next_rank, used_nonce = _draw_rank(user)

    game.current_rank = next_rank
    game.passes_used += 1
    db.session.commit()

    return jsonify({
        "rank": next_rank, "rank_label": rank_label(next_rank),
        "passes_left": MAX_PASSES - game.passes_used
    })


@games_bp.route("/hilo/guess", methods=["POST"])
@login_required
def hilo_guess():
    data = request.get_json(force=True)
    direction = data.get("direction")

    game = HiLoGame.query.filter_by(user_id=current_user.id).first()
    if not game:
        return jsonify({"error": "進行中のゲームがありません。"}), 400
    if direction not in ("higher", "lower"):
        return jsonify({"error": "予想の指定が不正です。"}), 400

    higher_count = 13 - game.current_rank
    lower_count = game.current_rank - 1
    prob = (higher_count if direction == "higher" else lower_count) / 13

    if prob <= 0:
        return jsonify({"error": "そのカードからはその方向を選べません。"}), 400

    user = current_user
    next_rank, used_nonce = _draw_rank(user)

    if next_rank == game.current_rank:
        db.session.commit()
        return jsonify({
            "push": True, "rank": next_rank, "rank_label": rank_label(next_rank),
            "multiplier": round(game.multiplier, 4)
        })

    won = (direction == "higher" and next_rank > game.current_rank) or \
          (direction == "lower" and next_rank < game.current_rank)

    if not won:
        db.session.add(BetRecord(
            user_id=user.id, game="hilo", wager=game.wager, payout=0, multiplier=0,
            server_seed_hash=game.server_seed_hash, client_seed=game.client_seed, nonce=used_nonce,
            result_json=json.dumps({"from": game.current_rank, "to": next_rank, "direction": direction})
        ))
        db.session.delete(game)
        db.session.commit()
        return jsonify({
            "won": False, "rank": next_rank, "rank_label": rank_label(next_rank), "balance": user.balance
        })

    step_multiplier = (1 - HILO_HOUSE_EDGE) / prob
    game.multiplier = round(game.multiplier * step_multiplier, 4)
    game.current_rank = next_rank
    game.rounds_played += 1
    db.session.commit()

    return jsonify({
        "won": True, "rank": next_rank, "rank_label": rank_label(next_rank),
        "multiplier": game.multiplier
    })


@games_bp.route("/hilo/cashout", methods=["POST"])
@login_required
def hilo_cashout():
    game = HiLoGame.query.filter_by(user_id=current_user.id).first()
    if not game:
        return jsonify({"error": "進行中のゲームがありません。"}), 400
    if game.rounds_played <= 0:
        return jsonify({"error": "少なくとも1回正解してからキャッシュアウトしてください。"}), 400

    final_multiplier = scale_multiplier("hilo", game.multiplier)
    payout = round(game.wager * final_multiplier)
    user = current_user
    credit_winnings(user, payout)
    apply_rakeback(user, game.wager)

    db.session.add(BetRecord(
        user_id=user.id, game="hilo", wager=game.wager, payout=payout, multiplier=final_multiplier,
        server_seed_hash=game.server_seed_hash, client_seed=game.client_seed, nonce=game.nonce,
        result_json=json.dumps({"rounds_played": game.rounds_played})
    ))
    db.session.delete(game)
    db.session.commit()

    return jsonify({"payout": payout, "multiplier": final_multiplier, "balance": user.balance})
