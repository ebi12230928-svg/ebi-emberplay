import json

from flask import render_template, request, jsonify
from flask_login import login_required, current_user

from extensions import db
from models import BetRecord, TowerGame
import fairness
from . import games_bp
from .common import validate_wager, apply_rakeback, credit_winnings

TOWER_HOUSE_EDGE = 0.07
TOTAL_ROWS = 9

DIFFICULTIES = {
    "easy":   {"tiles_per_row": 4, "bad_per_row": 1},
    "medium": {"tiles_per_row": 3, "bad_per_row": 1},
    "hard":   {"tiles_per_row": 2, "bad_per_row": 1},
    "expert": {"tiles_per_row": 3, "bad_per_row": 2},
}


def _tower_multiplier(tiles_per_row, bad_per_row, rows_climbed, house_edge=TOWER_HOUSE_EDGE):
    safe = tiles_per_row - bad_per_row
    if rows_climbed <= 0:
        return 1.0
    return round(((tiles_per_row / safe) ** rows_climbed) * (1 - house_edge), 4)


@games_bp.route("/tower")
@login_required
def tower_page():
    return render_template("games/tower.html", total_rows=TOTAL_ROWS, difficulties=list(DIFFICULTIES.keys()))


@games_bp.route("/tower/start", methods=["POST"])
@login_required
def tower_start():
    data = request.get_json(force=True)
    wager = int(data.get("wager", 0))
    difficulty = data.get("difficulty", "medium")

    if TowerGame.query.filter_by(user_id=current_user.id).first():
        return jsonify({"error": "すでに進行中のゲームがあります。"}), 400

    error = validate_wager(current_user, wager)
    if error:
        return jsonify({"error": error}), 400
    if difficulty not in DIFFICULTIES:
        return jsonify({"error": "難易度の指定が不正です。"}), 400

    cfg = DIFFICULTIES[difficulty]
    user = current_user
    user.balance -= wager

    base_nonce = user.nonce
    bad_positions = []
    for i in range(TOTAL_ROWS):
        row_positions = fairness.mines_positions(
            user.server_seed, user.client_seed, base_nonce + i, cfg["tiles_per_row"], cfg["bad_per_row"]
        )
        bad_positions.append(row_positions)
    user.nonce += TOTAL_ROWS

    game = TowerGame(
        user_id=user.id, wager=wager, difficulty=difficulty,
        tiles_per_row=cfg["tiles_per_row"], bad_per_row=cfg["bad_per_row"], total_rows=TOTAL_ROWS,
        bad_positions_json=json.dumps(bad_positions), current_row=0,
        server_seed_hash=user.server_seed_hash, client_seed=user.client_seed, nonce=base_nonce
    )
    db.session.add(game)
    db.session.commit()

    return jsonify({
        "balance": user.balance, "tiles_per_row": cfg["tiles_per_row"],
        "total_rows": TOTAL_ROWS, "multiplier": 1.0
    })


@games_bp.route("/tower/reveal", methods=["POST"])
@login_required
def tower_reveal():
    data = request.get_json(force=True)
    tile = int(data.get("tile", -1))

    game = TowerGame.query.filter_by(user_id=current_user.id).first()
    if not game:
        return jsonify({"error": "進行中のゲームがありません。"}), 400

    bad_positions = json.loads(game.bad_positions_json)
    row_bad = bad_positions[game.current_row]

    if not (0 <= tile < game.tiles_per_row):
        return jsonify({"error": "不正なマスです。"}), 400

    if tile in row_bad:
        db.session.add(BetRecord(
            user_id=current_user.id, game="tower", wager=game.wager, payout=0, multiplier=0,
            server_seed_hash=game.server_seed_hash, client_seed=game.client_seed, nonce=game.nonce,
            result_json=json.dumps({"bad_positions": bad_positions, "died_at_row": game.current_row, "hit": tile})
        ))
        db.session.delete(game)
        db.session.commit()
        return jsonify({
            "hit_bad": True, "row_bad": row_bad, "balance": current_user.balance
        })

    game.current_row += 1
    multiplier = _tower_multiplier(game.tiles_per_row, game.bad_per_row, game.current_row)
    reached_top = game.current_row >= game.total_rows

    if reached_top:
        payout = round(game.wager * multiplier)
        user = current_user
        credit_winnings(user, payout)
        apply_rakeback(user, game.wager)
        db.session.add(BetRecord(
            user_id=user.id, game="tower", wager=game.wager, payout=payout, multiplier=multiplier,
            server_seed_hash=game.server_seed_hash, client_seed=game.client_seed, nonce=game.nonce,
            result_json=json.dumps({"completed": True})
        ))
        db.session.delete(game)
        db.session.commit()
        return jsonify({
            "hit_bad": False, "reached_top": True, "multiplier": multiplier,
            "payout": payout, "balance": user.balance
        })

    db.session.commit()
    return jsonify({"hit_bad": False, "reached_top": False, "multiplier": multiplier, "current_row": game.current_row})


@games_bp.route("/tower/cashout", methods=["POST"])
@login_required
def tower_cashout():
    game = TowerGame.query.filter_by(user_id=current_user.id).first()
    if not game:
        return jsonify({"error": "進行中のゲームがありません。"}), 400
    if game.current_row <= 0:
        return jsonify({"error": "少なくとも1段登ってからキャッシュアウトしてください。"}), 400

    multiplier = _tower_multiplier(game.tiles_per_row, game.bad_per_row, game.current_row)
    payout = round(game.wager * multiplier)

    user = current_user
    credit_winnings(user, payout)
    apply_rakeback(user, game.wager)

    db.session.add(BetRecord(
        user_id=user.id, game="tower", wager=game.wager, payout=payout, multiplier=multiplier,
        server_seed_hash=game.server_seed_hash, client_seed=game.client_seed, nonce=game.nonce,
        result_json=json.dumps({"current_row": game.current_row})
    ))
    db.session.delete(game)
    db.session.commit()

    return jsonify({"payout": payout, "multiplier": multiplier, "balance": user.balance})
