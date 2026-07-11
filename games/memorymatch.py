import json

from flask import render_template, request, jsonify
from flask_login import login_required, current_user

from extensions import db
from models import BetRecord
import fairness
from . import games_bp
from .common import validate_wager, apply_rakeback, credit_winnings, scale_multiplier

# 16マス(8ペア)から2マス選び、一致すれば絵柄に応じた配当。全体をペイテーブルとして正規化済み
# (P(2マスが一致)=1/15、特定の絵柄で一致する確率は1/120・house edge約10%)
SYMBOLS = [
    {"key": "cherry", "label": "🍒", "payout": 1.8},
    {"key": "lemon", "label": "🍋", "payout": 2.4},
    {"key": "bell", "label": "🔔", "payout": 3.0},
    {"key": "star", "label": "⭐", "payout": 4.8},
    {"key": "gem", "label": "💎", "payout": 9.0},
    {"key": "crown", "label": "👑", "payout": 15.0},
    {"key": "clover", "label": "🍀", "payout": 24.0},
    {"key": "seven", "label": "7️⃣", "payout": 48.0},
]
GRID_SIZE = 16


@games_bp.route("/memorymatch")
@login_required
def memorymatch_page():
    return render_template("games/memorymatch.html", grid_size=GRID_SIZE, symbols=SYMBOLS)


@games_bp.route("/memorymatch/play", methods=["POST"])
@login_required
def memorymatch_play():
    data = request.get_json(force=True)
    wager = int(data.get("wager", 0))
    picks = data.get("picks")

    if not isinstance(picks, list) or len(picks) != 2 or len(set(picks)) != 2:
        return jsonify({"error": "2マスを重複なく選んでください。"}), 400
    if not all(isinstance(p, int) and 0 <= p < GRID_SIZE for p in picks):
        return jsonify({"error": "マスの指定が不正です。"}), 400

    error = validate_wager(current_user, wager)
    if error:
        return jsonify({"error": error}), 400

    user = current_user
    user.balance -= wager

    # 16マスに8ペアをランダムに配置する(公正な乱数でシャッフル)
    layout = SYMBOLS * 2
    order = fairness.shuffle_indices(user.server_seed, user.client_seed, user.nonce, GRID_SIZE)
    used_nonce = user.nonce
    user.nonce += 1
    grid = [None] * GRID_SIZE
    for pos, symbol_idx in zip(order, range(GRID_SIZE)):
        grid[pos] = layout[symbol_idx]

    revealed = [grid[p] for p in picks]
    matched = revealed[0]["key"] == revealed[1]["key"]

    multiplier = scale_multiplier("memorymatch", revealed[0]["payout"]) if matched else 0
    payout = round(wager * multiplier) if matched else 0

    if payout > 0:
        credit_winnings(user, payout)
    apply_rakeback(user, wager)

    db.session.add(BetRecord(
        user_id=user.id, game="memorymatch", wager=wager, payout=payout, multiplier=multiplier,
        server_seed_hash=user.server_seed_hash, client_seed=user.client_seed, nonce=used_nonce,
        result_json=json.dumps({"picks": picks, "revealed": [r["key"] for r in revealed], "matched": matched})
    ))
    db.session.commit()

    return jsonify({
        "revealed": [r["label"] for r in revealed], "matched": matched,
        "multiplier": multiplier, "payout": payout, "balance": user.balance
    })
