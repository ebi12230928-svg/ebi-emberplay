"""
カジノ要素とは無関係のミニゲーム。賭け金は使わず、勝敗に応じて直接Embersを獲得する。
"""
import json
import random

from flask import render_template, request, jsonify
from flask_login import login_required, current_user

from extensions import db
from models import BetRecord, TicTacToeGame, Transaction
from . import games_bp
from .common import clear_stale_game

WIN_LINES = [
    (0, 1, 2), (3, 4, 5), (6, 7, 8),  # 横
    (0, 3, 6), (1, 4, 7), (2, 5, 8),  # 縦
    (0, 4, 8), (2, 4, 6),             # 斜め
]

REWARD_WIN = 300
REWARD_DRAW = 50
AI_MISTAKE_CHANCE = 0.25  # AIがたまにベストではない手を打つ確率(プレイヤーにも勝機を残すため)


def _winner(board):
    for a, b, c in WIN_LINES:
        if board[a] and board[a] == board[b] == board[c]:
            return board[a]
    if all(board):
        return "draw"
    return None


def _minimax(board, player):
    winner = _winner(board)
    if winner == "O":
        return 1, None
    if winner == "X":
        return -1, None
    if winner == "draw":
        return 0, None

    moves = [i for i, v in enumerate(board) if not v]
    best_move = moves[0]
    if player == "O":
        best_score = -2
        for m in moves:
            board[m] = "O"
            score, _ = _minimax(board, "X")
            board[m] = ""
            if score > best_score:
                best_score = score
                best_move = m
        return best_score, best_move
    else:
        best_score = 2
        for m in moves:
            board[m] = "X"
            score, _ = _minimax(board, "O")
            board[m] = ""
            if score < best_score:
                best_score = score
                best_move = m
        return best_score, best_move


def _ai_move(board):
    empty = [i for i, v in enumerate(board) if not v]
    if random.random() < AI_MISTAKE_CHANCE and len(empty) > 1:
        return random.choice(empty)
    _, move = _minimax(board[:], "O")
    return move if move is not None else random.choice(empty)


@games_bp.route("/tictactoe")
@login_required
def tictactoe_page():
    clear_stale_game(TicTacToeGame, current_user, wager_field=None, timeout_minutes=15)
    game = TicTacToeGame.query.filter_by(user_id=current_user.id).first()
    return render_template("games/tictactoe.html", game=game, reward_win=REWARD_WIN, reward_draw=REWARD_DRAW)


@games_bp.route("/tictactoe/cancel", methods=["POST"])
@login_required
def tictactoe_cancel():
    game = TicTacToeGame.query.filter_by(user_id=current_user.id).first()
    if not game:
        return jsonify({"error": "進行中のゲームがありません。"}), 400
    db.session.delete(game)
    db.session.commit()
    return jsonify({"ok": True})


@games_bp.route("/tictactoe/start", methods=["POST"])
@login_required
def tictactoe_start():
    existing = TicTacToeGame.query.filter_by(user_id=current_user.id).first()
    if existing:
        db.session.delete(existing)
        db.session.commit()

    game = TicTacToeGame(user_id=current_user.id, board_json=json.dumps([""] * 9), status="playing")
    db.session.add(game)
    db.session.commit()

    return jsonify({"board": [""] * 9, "status": "playing"})


@games_bp.route("/tictactoe/move", methods=["POST"])
@login_required
def tictactoe_move():
    data = request.get_json(force=True)
    try:
        cell = int(data.get("cell"))
    except (TypeError, ValueError):
        return jsonify({"error": "マスの指定が不正です。"}), 400

    game = TicTacToeGame.query.filter_by(user_id=current_user.id).first()
    if not game or game.status != "playing":
        return jsonify({"error": "進行中のゲームがありません。「新しく始める」を押してください。"}), 400

    board = json.loads(game.board_json)
    if not (0 <= cell < 9) or board[cell]:
        return jsonify({"error": "そのマスは選べません。"}), 400

    board[cell] = "X"
    result = _winner(board)

    reward = 0
    status = "playing"
    if result == "X":
        status = "won"
        reward = REWARD_WIN
    elif result == "draw":
        status = "draw"
        reward = REWARD_DRAW
    else:
        ai_cell = _ai_move(board)
        board[ai_cell] = "O"
        result2 = _winner(board)
        if result2 == "O":
            status = "lost"
        elif result2 == "draw":
            status = "draw"
            reward = REWARD_DRAW

    game.board_json = json.dumps(board)
    game.status = status

    user = current_user
    if reward > 0:
        user.balance += reward
        db.session.add(Transaction(
            user_id=user.id, amount=reward, kind="tictactoe",
            description="三目並べ" + ("勝利" if status == "won" else "引き分け")
        ))

    if status != "playing":
        db.session.add(BetRecord(
            user_id=user.id, game="tictactoe", wager=0, payout=reward,
            multiplier=0,
            server_seed_hash=user.server_seed_hash, client_seed=user.client_seed, nonce=user.nonce,
            result_json=json.dumps({"board": board, "status": status})
        ))
        try:
            from achievements import check_achievements
            check_achievements(user)
        except Exception:
            pass
        db.session.delete(game)

    db.session.commit()

    return jsonify({"board": board, "status": status, "reward": reward, "balance": user.balance})
