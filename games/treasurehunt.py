import json

from flask import render_template, request, jsonify
from flask_login import login_required, current_user

from extensions import db
from models import BetRecord
import fairness
from . import games_bp
from .common import validate_wager, apply_rakeback, credit_winnings, scale_multiplier

# 9マス中2つがトラップ。3マス選んで全て安全なら勝ち(超幾何分布で検証済み・house edge約8%)
GRID_SIZE = 9
TRAP_COUNT = 2
PICK_COUNT = 3
PAYOUT = 2.21


@games_bp.route("/treasurehunt")
@login_required
def treasurehunt_page():
    return render_template("games/treasurehunt.html", payout=PAYOUT, grid_size=GRID_SIZE, pick_count=PICK_COUNT)


@games_bp.route("/treasurehunt/play", methods=["POST"])
@login_required
def treasurehunt_play():
    data = request.get_json(force=True)
    wager = int(data.get("wager", 0))
    picks = data.get("picks")

    if not isinstance(picks, list) or len(picks) != PICK_COUNT or len(set(picks)) != PICK_COUNT:
        return jsonify({"error": f"{PICK_COUNT}マスを重複なく選んでください。"}), 400
    if not all(isinstance(p, int) and 0 <= p < GRID_SIZE for p in picks):
        return jsonify({"error": "マスの指定が不正です。"}), 400

    error = validate_wager(current_user, wager)
    if error:
        return jsonify({"error": error}), 400

    user = current_user
    user.balance -= wager

    # フィッシャー–イェーツ風に、公正な乱数でトラップの位置を決める
    order = fairness.shuffle_indices(user.server_seed, user.client_seed, user.nonce, GRID_SIZE)
    used_nonce = user.nonce
    user.nonce += 1
    traps = set(order[:TRAP_COUNT])

    hit_trap = any(p in traps for p in picks)
    won = not hit_trap
    multiplier = scale_multiplier("treasurehunt", PAYOUT) if won else 0
    payout = round(wager * multiplier) if won else 0

    if payout > 0:
        credit_winnings(user, payout)
    apply_rakeback(user, wager)

    db.session.add(BetRecord(
        user_id=user.id, game="treasurehunt", wager=wager, payout=payout, multiplier=multiplier,
        server_seed_hash=user.server_seed_hash, client_seed=user.client_seed, nonce=used_nonce,
        result_json=json.dumps({"picks": picks, "traps": list(traps)})
    ))
    db.session.commit()

    return jsonify({
        "won": won, "traps": list(traps), "multiplier": multiplier, "payout": payout, "balance": user.balance
    })
