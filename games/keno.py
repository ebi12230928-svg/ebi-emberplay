import json

from flask import render_template, request, jsonify
from flask_login import login_required, current_user

from extensions import db
from models import BetRecord
import fairness
from . import games_bp
from .common import validate_wager, apply_rakeback, credit_winnings

KENO_HOUSE_EDGE = 0.09
KENO_TOTAL = 40
KENO_DRAWN = 10
KENO_MAX_PICKS = 10


@games_bp.route("/keno")
@login_required
def keno_page():
    return render_template("games/keno.html", total=KENO_TOTAL, max_picks=KENO_MAX_PICKS)


@games_bp.route("/keno/play", methods=["POST"])
@login_required
def keno_play():
    data = request.get_json(force=True)
    wager = int(data.get("wager", 0))
    picks = data.get("picks", [])

    error = validate_wager(current_user, wager)
    if error:
        return jsonify({"error": error}), 400

    if not isinstance(picks, list) or not (1 <= len(picks) <= KENO_MAX_PICKS):
        return jsonify({"error": f"1〜{KENO_MAX_PICKS}個の数字を選んでください。"}), 400
    picks = [int(p) for p in picks]
    if len(set(picks)) != len(picks) or any(p < 1 or p > KENO_TOTAL for p in picks):
        return jsonify({"error": "数字の指定が不正です。"}), 400

    user = current_user
    user.balance -= wager

    picks_zero_indexed = {p - 1 for p in picks}
    drawn_zero_indexed = fairness.draw_keno_numbers(
        user.server_seed, user.client_seed, user.nonce, KENO_DRAWN, KENO_TOTAL
    )
    used_nonce = user.nonce
    user.nonce += 1

    matches = len(picks_zero_indexed & set(drawn_zero_indexed))
    table = fairness.keno_paytable(len(picks), drawn=KENO_DRAWN, total=KENO_TOTAL, house_edge=KENO_HOUSE_EDGE)
    multiplier = table[matches]
    payout = round(wager * multiplier)

    credit_winnings(user, payout)
    apply_rakeback(user, wager)

    drawn_display = sorted(i + 1 for i in drawn_zero_indexed)

    db.session.add(BetRecord(
        user_id=user.id, game="keno", wager=wager, payout=payout, multiplier=multiplier,
        server_seed_hash=user.server_seed_hash, client_seed=user.client_seed, nonce=used_nonce,
        result_json=json.dumps({"picks": picks, "drawn": drawn_display, "matches": matches})
    ))
    db.session.commit()

    return jsonify({
        "drawn": drawn_display, "matches": matches, "multiplier": multiplier,
        "payout": payout, "balance": user.balance
    })
