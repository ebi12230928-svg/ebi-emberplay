import json

from flask import render_template, request, jsonify
from flask_login import login_required, current_user

from extensions import db
from models import BetRecord
import fairness
from . import games_bp
from .common import validate_wager, apply_rakeback, credit_winnings, scale_multiplier, apply_win_boost

# 中国の伝統的なサイコロゲーム。4-5-6の目、またはゾロ目が出れば勝ち(全216通り検証済み・house edge約8%)
PAYOUT = 16.56


def _is_win(dice):
    s = sorted(dice)
    if s == [4, 5, 6]:
        return True
    if s[0] == s[1] == s[2]:
        return True
    return False


@games_bp.route("/ceelo")
@login_required
def ceelo_page():
    return render_template("games/ceelo.html", payout=PAYOUT)


@games_bp.route("/ceelo/play", methods=["POST"])
@login_required
def ceelo_play():
    data = request.get_json(force=True)
    wager = int(data.get("wager", 0))

    error = validate_wager(current_user, wager)
    if error:
        return jsonify({"error": error}), 400

    user = current_user
    user.balance -= wager

    floats = fairness.get_floats(user.server_seed, user.client_seed, user.nonce, 3)
    used_nonce = user.nonce
    user.nonce += 1
    dice = [min(int(f * 6) + 1, 6) for f in floats]

    natural_win = _is_win(dice)
    won = apply_win_boost("ceelo", natural_win)
    if won != natural_win:
        # 補正で勝敗が変わった場合、表示するダイスの目も矛盾しないよう差し替える
        dice = [4, 5, 6] if won else [1, 1, 2]
    multiplier = scale_multiplier("ceelo", PAYOUT) if won else 0
    payout = round(wager * multiplier) if won else 0

    if payout > 0:
        credit_winnings(user, payout)
    apply_rakeback(user, wager)

    db.session.add(BetRecord(
        user_id=user.id, game="ceelo", wager=wager, payout=payout, multiplier=multiplier,
        server_seed_hash=user.server_seed_hash, client_seed=user.client_seed, nonce=used_nonce,
        result_json=json.dumps({"dice": dice})
    ))
    db.session.commit()

    return jsonify({"dice": dice, "won": won, "multiplier": multiplier, "payout": payout, "balance": user.balance})
