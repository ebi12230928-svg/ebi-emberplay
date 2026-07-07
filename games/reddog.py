import json

from flask import render_template, request, jsonify
from flask_login import login_required, current_user

from extensions import db
from models import BetRecord
import fairness
from . import games_bp
from .common import validate_wager, apply_rakeback, credit_winnings

# spreadごとの配当(house edge目標20%で正規化・全通り総当たりで実測edge約10.6%を確認済み)
SPREAD_PAYOUTS = {
    1: 10.4, 2: 5.2, 3: 3.47, 4: 2.6, 5: 2.08, 6: 1.73, 7: 1.49, 8: 1.3, 9: 1.16, 10: 1.04, 11: 0.95,
}
PAIR_PAYOUT = 5.41

RANK_NAMES = {1: "A", 11: "J", 12: "Q", 13: "K"}


def rank_label(rank):
    return RANK_NAMES.get(rank, str(rank))


def _draw_rank(user):
    f = fairness.get_float(user.server_seed, user.client_seed, user.nonce)
    used_nonce = user.nonce
    user.nonce += 1
    return int(f * 13) + 1, used_nonce


@games_bp.route("/reddog")
@login_required
def reddog_page():
    return render_template("games/reddog.html")


@games_bp.route("/reddog/play", methods=["POST"])
@login_required
def reddog_play():
    data = request.get_json(force=True)
    wager = int(data.get("wager", 0))

    error = validate_wager(current_user, wager)
    if error:
        return jsonify({"error": error}), 400

    user = current_user
    user.balance -= wager

    r1, used_nonce = _draw_rank(user)
    r2, _ = _draw_rank(user)

    outcome = "lose"
    multiplier = 0.0
    third_card = None
    fourth_card = None

    if r1 == r2:
        c3, _ = _draw_rank(user)
        c4, _ = _draw_rank(user)
        third_card, fourth_card = c3, c4
        if c3 == r1 or c4 == r1:
            multiplier = PAIR_PAYOUT
            outcome = "win"
        else:
            multiplier = 1.0
            outcome = "push"
    else:
        lo, hi = sorted([r1, r2])
        if hi - lo == 1:
            multiplier = 1.0
            outcome = "push"
        else:
            spread = hi - lo - 1
            c3, _ = _draw_rank(user)
            third_card = c3
            if lo < c3 < hi:
                multiplier = SPREAD_PAYOUTS[spread]
                outcome = "win"
            else:
                multiplier = 0.0
                outcome = "lose"

    payout = round(wager * multiplier)
    if payout > 0:
        credit_winnings(user, payout)
    apply_rakeback(user, wager)

    db.session.add(BetRecord(
        user_id=user.id, game="reddog", wager=wager, payout=payout, multiplier=multiplier,
        server_seed_hash=user.server_seed_hash, client_seed=user.client_seed, nonce=used_nonce,
        result_json=json.dumps({
            "r1": r1, "r2": r2, "third_card": third_card, "fourth_card": fourth_card, "outcome": outcome
        })
    ))
    db.session.commit()

    return jsonify({
        "card1": rank_label(r1), "card2": rank_label(r2),
        "third_card": rank_label(third_card) if third_card else None,
        "fourth_card": rank_label(fourth_card) if fourth_card else None,
        "outcome": outcome, "multiplier": multiplier, "payout": payout, "balance": user.balance
    })
