import json

from flask import render_template, request, jsonify
from flask_login import login_required, current_user

from extensions import db
from models import BetRecord, MinesGame
import fairness
from . import games_bp
from .common import validate_wager, apply_rakeback, credit_winnings

MINES_HOUSE_EDGE = 0.07
MINES_GRID_SIZE = 25


@games_bp.route("/mines")
@login_required
def mines_page():
    return render_template("games/mines.html", grid_size=MINES_GRID_SIZE)


def _mines_multiplier(grid_size, mine_count, revealed_count):
    mult = 1.0
    for i in range(revealed_count):
        remaining_cells = grid_size - i
        remaining_safe = remaining_cells - mine_count
        if remaining_safe <= 0:
            break
        mult *= remaining_cells / remaining_safe
    return round(mult * (1 - MINES_HOUSE_EDGE), 4)


@games_bp.route("/mines/start", methods=["POST"])
@login_required
def mines_start():
    data = request.get_json(force=True)
    wager = int(data.get("wager", 0))
    mine_count = int(data.get("mine_count", 3))

    if MinesGame.query.filter_by(user_id=current_user.id).first():
        return jsonify({"error": "すでに進行中のゲームがあります。"}), 400

    error = validate_wager(current_user, wager)
    if error:
        return jsonify({"error": error}), 400
    if not (1 <= mine_count <= MINES_GRID_SIZE - 1):
        return jsonify({"error": "地雷の数が不正です。"}), 400

    user = current_user
    user.balance -= wager

    mine_positions = fairness.mines_positions(
        user.server_seed, user.client_seed, user.nonce, MINES_GRID_SIZE, mine_count
    )
    game = MinesGame(
        user_id=user.id, wager=wager, grid_size=MINES_GRID_SIZE, mine_count=mine_count,
        mine_positions_json=json.dumps(mine_positions), revealed_json="[]",
        server_seed_hash=user.server_seed_hash, client_seed=user.client_seed, nonce=user.nonce
    )
    user.nonce += 1
    db.session.add(game)
    db.session.commit()

    return jsonify({"balance": user.balance, "multiplier": 1.0, "grid_size": MINES_GRID_SIZE})


@games_bp.route("/mines/reveal", methods=["POST"])
@login_required
def mines_reveal():
    data = request.get_json(force=True)
    tile = int(data.get("tile", -1))

    game = MinesGame.query.filter_by(user_id=current_user.id).first()
    if not game:
        return jsonify({"error": "進行中のゲームがありません。"}), 400

    mine_positions = json.loads(game.mine_positions_json)
    revealed = json.loads(game.revealed_json)

    if tile in revealed or not (0 <= tile < game.grid_size):
        return jsonify({"error": "不正なマスです。"}), 400

    if tile in mine_positions:
        db.session.add(BetRecord(
            user_id=current_user.id, game="mines", wager=game.wager, payout=0, multiplier=0,
            server_seed_hash=game.server_seed_hash, client_seed=game.client_seed, nonce=game.nonce,
            result_json=json.dumps({"mine_positions": mine_positions, "revealed": revealed, "hit": tile})
        ))
        db.session.delete(game)
        db.session.commit()
        return jsonify({"hit_mine": True, "mine_positions": mine_positions, "balance": current_user.balance})

    revealed.append(tile)
    game.revealed_json = json.dumps(revealed)
    db.session.commit()

    multiplier = _mines_multiplier(game.grid_size, game.mine_count, len(revealed))
    safe_tiles_left = game.grid_size - game.mine_count - len(revealed)

    return jsonify({
        "hit_mine": False, "revealed": revealed, "multiplier": multiplier,
        "safe_tiles_left": safe_tiles_left
    })


@games_bp.route("/mines/cashout", methods=["POST"])
@login_required
def mines_cashout():
    game = MinesGame.query.filter_by(user_id=current_user.id).first()
    if not game:
        return jsonify({"error": "進行中のゲームがありません。"}), 400

    revealed = json.loads(game.revealed_json)
    if not revealed:
        return jsonify({"error": "1マス以上開けてからキャッシュアウトしてください。"}), 400

    multiplier = _mines_multiplier(game.grid_size, game.mine_count, len(revealed))
    payout = round(game.wager * multiplier)

    user = current_user
    credit_winnings(user, payout)
    apply_rakeback(user, game.wager)

    db.session.add(BetRecord(
        user_id=user.id, game="mines", wager=game.wager, payout=payout, multiplier=multiplier,
        server_seed_hash=game.server_seed_hash, client_seed=game.client_seed, nonce=game.nonce,
        result_json=json.dumps({"mine_positions": json.loads(game.mine_positions_json), "revealed": revealed})
    ))
    db.session.delete(game)
    db.session.commit()

    return jsonify({"payout": payout, "multiplier": multiplier, "balance": user.balance})
