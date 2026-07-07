import json

from flask import render_template, request, jsonify
from flask_login import login_required, current_user

from extensions import db
from models import BetRecord, CrapsGame
import fairness
from . import games_bp
from .common import validate_wager, apply_rakeback, credit_winnings, scale_multiplier


def _roll_dice(user):
    floats = fairness.get_floats(user.server_seed, user.client_seed, user.nonce, 2)
    used_nonce = user.nonce
    user.nonce += 1
    dice = [min(int(f * 6) + 1, 6) for f in floats]
    return dice, used_nonce


@games_bp.route("/craps")
@login_required
def craps_page():
    return render_template("games/craps.html")


def _settle(user, bet_type, wager, won, is_push, dice, used_nonce):
    if is_push:
        payout = wager
        credit_winnings(user, payout)
    elif won:
        multiplier = scale_multiplier("craps", 2.0)
        payout = round(wager * multiplier)
        credit_winnings(user, payout)
    else:
        payout = 0

    apply_rakeback(user, wager)
    db.session.add(BetRecord(
        user_id=user.id, game="craps", wager=wager, payout=payout,
        multiplier=(payout / wager) if wager else 0,
        server_seed_hash=user.server_seed_hash, client_seed=user.client_seed, nonce=used_nonce,
        result_json=json.dumps({"bet_type": bet_type, "dice": dice, "won": won, "push": is_push})
    ))
    db.session.commit()
    return payout


@games_bp.route("/craps/start", methods=["POST"])
@login_required
def craps_start():
    data = request.get_json(force=True)
    wager = int(data.get("wager", 0))
    bet_type = data.get("bet_type")

    if CrapsGame.query.filter_by(user_id=current_user.id).first():
        return jsonify({"error": "すでに進行中のゲームがあります。"}), 400

    error = validate_wager(current_user, wager)
    if error:
        return jsonify({"error": error}), 400
    if bet_type not in ("pass", "dont_pass"):
        return jsonify({"error": "選択が不正です。"}), 400

    user = current_user
    user.balance -= wager

    dice, used_nonce = _roll_dice(user)
    total = sum(dice)

    if bet_type == "pass":
        if total in (7, 11):
            payout = _settle(user, bet_type, wager, True, False, dice, used_nonce)
            return jsonify({"resolved": True, "dice": dice, "won": True, "payout": payout, "balance": user.balance})
        if total in (2, 3, 12):
            payout = _settle(user, bet_type, wager, False, False, dice, used_nonce)
            return jsonify({"resolved": True, "dice": dice, "won": False, "payout": payout, "balance": user.balance})
    else:  # dont_pass
        if total in (7, 11):
            payout = _settle(user, bet_type, wager, False, False, dice, used_nonce)
            return jsonify({"resolved": True, "dice": dice, "won": False, "payout": payout, "balance": user.balance})
        if total in (2, 3):
            payout = _settle(user, bet_type, wager, True, False, dice, used_nonce)
            return jsonify({"resolved": True, "dice": dice, "won": True, "payout": payout, "balance": user.balance})
        if total == 12:
            payout = _settle(user, bet_type, wager, False, True, dice, used_nonce)  # bar12: プッシュ
            return jsonify({"resolved": True, "dice": dice, "push": True, "payout": payout, "balance": user.balance})

    # ポイント確定
    game = CrapsGame(
        user_id=user.id, bet_type=bet_type, wager=wager, point=total,
        server_seed_hash=user.server_seed_hash, client_seed=user.client_seed, nonce=used_nonce
    )
    db.session.add(game)
    db.session.commit()

    return jsonify({"resolved": False, "dice": dice, "point": total, "balance": user.balance})


@games_bp.route("/craps/roll", methods=["POST"])
@login_required
def craps_roll():
    game = CrapsGame.query.filter_by(user_id=current_user.id).first()
    if not game:
        return jsonify({"error": "進行中のゲームがありません。"}), 400

    user = current_user
    dice, used_nonce = _roll_dice(user)
    total = sum(dice)

    resolved = False
    won = False
    payout = 0

    if total == game.point:
        won = game.bet_type == "pass"
        resolved = True
    elif total == 7:
        won = game.bet_type == "dont_pass"
        resolved = True

    if resolved:
        payout = _settle(user, game.bet_type, game.wager, won, False, dice, used_nonce)
        db.session.delete(game)
        db.session.commit()
        return jsonify({"resolved": True, "dice": dice, "won": won, "payout": payout, "balance": user.balance})

    db.session.commit()
    return jsonify({"resolved": False, "dice": dice, "point": game.point, "balance": user.balance})
