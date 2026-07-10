import json

from flask import render_template, request, jsonify
from flask_login import login_required, current_user

from extensions import db
from models import BetRecord
import fairness
from . import games_bp
from .common import validate_wager, apply_rakeback, credit_winnings, scale_multiplier

# 1枚勝負のシンプルなカードゲーム。引き分けは賭け金の半分を回収(全169通り検証済み)
WIN_PAYOUT = 1.85
TIE_REFUND = 0.5
RANK_NAMES = {1: "A", 11: "J", 12: "Q", 13: "K"}


def rank_label(rank):
    return RANK_NAMES.get(rank, str(rank))


@games_bp.route("/dragontiger")
@login_required
def dragontiger_page():
    return render_template("games/dragontiger.html", payout=WIN_PAYOUT)


@games_bp.route("/dragontiger/play", methods=["POST"])
@login_required
def dragontiger_play():
    data = request.get_json(force=True)
    wager = int(data.get("wager", 0))
    pick = data.get("pick")

    if pick not in ("dragon", "tiger"):
        return jsonify({"error": "選択が不正です。"}), 400

    error = validate_wager(current_user, wager)
    if error:
        return jsonify({"error": error}), 400

    user = current_user
    user.balance -= wager

    floats = fairness.get_floats(user.server_seed, user.client_seed, user.nonce, 2)
    used_nonce = user.nonce
    user.nonce += 1
    dragon_rank = int(floats[0] * 13) + 1
    tiger_rank = int(floats[1] * 13) + 1

    if dragon_rank == tiger_rank:
        outcome = "tie"
        multiplier = TIE_REFUND
    elif (dragon_rank > tiger_rank) == (pick == "dragon"):
        outcome = "win"
        multiplier = scale_multiplier("dragontiger", WIN_PAYOUT)
    else:
        outcome = "lose"
        multiplier = 0

    payout = round(wager * multiplier)
    if payout > 0:
        credit_winnings(user, payout)
    apply_rakeback(user, wager)

    db.session.add(BetRecord(
        user_id=user.id, game="dragontiger", wager=wager, payout=payout, multiplier=multiplier,
        server_seed_hash=user.server_seed_hash, client_seed=user.client_seed, nonce=used_nonce,
        result_json=json.dumps({"dragon": dragon_rank, "tiger": tiger_rank, "pick": pick, "outcome": outcome})
    ))
    db.session.commit()

    return jsonify({
        "dragon": rank_label(dragon_rank), "tiger": rank_label(tiger_rank), "outcome": outcome,
        "multiplier": multiplier, "payout": payout, "balance": user.balance
    })
