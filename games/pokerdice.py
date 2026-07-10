import json
from collections import Counter

from flask import render_template, request, jsonify
from flask_login import login_required, current_user

from extensions import db
from models import BetRecord
import fairness
from . import games_bp
from .common import validate_wager, apply_rakeback, credit_winnings, scale_multiplier

FACES = {1: "9", 2: "10", 3: "J", 4: "Q", 5: "K", 6: "A"}

# 全7776通りを総当たりで検証済み(house edge約8%)。three of a kind未満はハズレ扱い(実際のJacks or Betterと同じ考え方)
PAYOUTS = {
    "nothing": 0, "one_pair": 0, "two_pair": 0, "three_kind": 1.64,
    "full_house": 4.93, "four_kind": 19.19, "five_kind": 137.05,
}
CATEGORY_NAMES = {
    "nothing": "役なし", "one_pair": "ワンペア", "two_pair": "ツーペア", "three_kind": "スリーカード",
    "full_house": "フルハウス", "four_kind": "フォーカード", "five_kind": "ファイブカード",
}


def _classify(dice):
    counts = sorted(Counter(dice).values(), reverse=True)
    if counts == [5]:
        return "five_kind"
    if counts == [4, 1]:
        return "four_kind"
    if counts == [3, 2]:
        return "full_house"
    if counts == [3, 1, 1]:
        return "three_kind"
    if counts == [2, 2, 1]:
        return "two_pair"
    if counts == [2, 1, 1, 1]:
        return "one_pair"
    return "nothing"


@games_bp.route("/pokerdice")
@login_required
def pokerdice_page():
    return render_template("games/pokerdice.html", payouts=PAYOUTS, names=CATEGORY_NAMES)


@games_bp.route("/pokerdice/play", methods=["POST"])
@login_required
def pokerdice_play():
    data = request.get_json(force=True)
    wager = int(data.get("wager", 0))

    error = validate_wager(current_user, wager)
    if error:
        return jsonify({"error": error}), 400

    user = current_user
    user.balance -= wager

    floats = fairness.get_floats(user.server_seed, user.client_seed, user.nonce, 5)
    used_nonce = user.nonce
    user.nonce += 1
    dice = [min(int(f * 6) + 1, 6) for f in floats]

    category = _classify(dice)
    multiplier = scale_multiplier("pokerdice", PAYOUTS[category]) if PAYOUTS[category] > 0 else 0
    payout = round(wager * multiplier) if multiplier > 0 else 0

    if payout > 0:
        credit_winnings(user, payout)
    apply_rakeback(user, wager)

    db.session.add(BetRecord(
        user_id=user.id, game="pokerdice", wager=wager, payout=payout, multiplier=multiplier,
        server_seed_hash=user.server_seed_hash, client_seed=user.client_seed, nonce=used_nonce,
        result_json=json.dumps({"dice": dice, "category": category})
    ))
    db.session.commit()

    return jsonify({
        "dice": [FACES[d] for d in dice], "category": CATEGORY_NAMES[category],
        "multiplier": multiplier, "payout": payout, "balance": user.balance
    })
