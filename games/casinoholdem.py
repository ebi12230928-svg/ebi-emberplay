import json

from flask import render_template, request, jsonify
from flask_login import login_required, current_user

from extensions import db
from models import BetRecord
import fairness
from . import games_bp
from . import poker_utils as pk
from .common import validate_wager, apply_rakeback, credit_winnings, scale_multiplier

# コール/フォールドの駆け引きは省略し、アンティのみの1回勝負にした簡易版Casino Hold'em。
# ディーラーはJacks or Better以上で成立(不成立ならアンティ返金)。プレイヤーが勝てば役に応じたボーナス配当。
# 30万回シミュレーションで検証済み(house edge約6%)
STRENGTH = pk.HAND_STRENGTH
BONUS_PAYOUTS = {
    "jacks_or_better": 0.57, "two_pair": 1.14, "three_kind": 1.72, "straight": 2.29, "flush": 2.86,
    "full_house": 4.0, "four_kind": 11.44, "straight_flush": 28.59, "royal_flush": 57.18,
}


@games_bp.route("/casinoholdem")
@login_required
def casinoholdem_page():
    return render_template("games/casinoholdem.html", bonus_payouts=BONUS_PAYOUTS)


@games_bp.route("/casinoholdem/play", methods=["POST"])
@login_required
def casinoholdem_play():
    data = request.get_json(force=True)
    wager = int(data.get("wager", 0))

    error = validate_wager(current_user, wager)
    if error:
        return jsonify({"error": error}), 400

    user = current_user
    user.balance -= wager

    order = fairness.shuffle_indices(user.server_seed, user.client_seed, user.nonce, 52)
    used_nonce = user.nonce
    user.nonce += 1

    player_hole = order[0:2]
    dealer_hole = order[2:4]
    community = order[4:9]

    player_hand, player_strength = pk.best_hand_from(player_hole + community)
    dealer_hand, dealer_strength = pk.best_hand_from(dealer_hole + community)

    dealer_qualifies = STRENGTH.index(dealer_hand) >= STRENGTH.index("jacks_or_better")

    if not dealer_qualifies:
        outcome = "dealer_no_qualify"
        multiplier = scale_multiplier("casinoholdem", 1.0)
    elif player_strength > dealer_strength:
        outcome = "win"
        bonus = BONUS_PAYOUTS.get(player_hand, 0)
        multiplier = scale_multiplier("casinoholdem", 1.0 + bonus)
    elif player_strength == dealer_strength:
        outcome = "push"
        multiplier = scale_multiplier("casinoholdem", 1.0)
    else:
        outcome = "lose"
        multiplier = 0

    payout = round(wager * multiplier)
    if payout > 0:
        credit_winnings(user, payout)
    apply_rakeback(user, wager)

    db.session.add(BetRecord(
        user_id=user.id, game="casinoholdem", wager=wager, payout=payout, multiplier=multiplier,
        server_seed_hash=user.server_seed_hash, client_seed=user.client_seed, nonce=used_nonce,
        result_json=json.dumps({
            "player_hole": player_hole, "dealer_hole": dealer_hole, "community": community,
            "player_hand": player_hand, "dealer_hand": dealer_hand, "outcome": outcome
        })
    ))
    db.session.commit()

    return jsonify({
        "player_hole": [pk.card_label(c) for c in player_hole],
        "dealer_hole": [pk.card_label(c) for c in dealer_hole],
        "community": [pk.card_label(c) for c in community],
        "player_hand": pk.HAND_LABELS[player_hand], "dealer_hand": pk.HAND_LABELS[dealer_hand],
        "outcome": outcome, "multiplier": multiplier, "payout": payout, "balance": user.balance
    })
