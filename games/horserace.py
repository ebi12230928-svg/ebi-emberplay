import json

from flask import render_template, request, jsonify
from flask_login import login_required, current_user

from extensions import db
from models import BetRecord
import fairness
from . import games_bp
from .common import validate_wager, apply_rakeback, credit_winnings, scale_multiplier

# 実際の競馬データを無料で取得する手段がないため、公正な乱数(fairness.py)で結果を決める
# シミュレーションレースとして実装している(実データではないことをUI上にも明記する)。
HORSES = [
    {"key": "h1", "name": "ブレイジングエンバー", "weight": 30, "payout": 3.0},
    {"key": "h2", "name": "ゴールドラッシュ", "weight": 22, "payout": 4.09},
    {"key": "h3", "name": "ミッドナイトダッシュ", "weight": 16, "payout": 5.62},
    {"key": "h4", "name": "シルバーストーム", "weight": 12, "payout": 7.5},
    {"key": "h5", "name": "レッドフューリー", "weight": 8, "payout": 11.25},
    {"key": "h6", "name": "ラッキーセブン", "weight": 6, "payout": 15.0},
    {"key": "h7", "name": "ダークホース", "weight": 4, "payout": 22.5},
    {"key": "h8", "name": "アンダードッグ", "weight": 2, "payout": 45.0},
]


def _pick_winner(total_weight, f):
    r = f * total_weight
    cum = 0
    for h in HORSES:
        cum += h["weight"]
        if r < cum:
            return h
    return HORSES[-1]


@games_bp.route("/horserace")
@login_required
def horserace_page():
    return render_template("games/horserace.html", horses=HORSES)


@games_bp.route("/horserace/play", methods=["POST"])
@login_required
def horserace_play():
    data = request.get_json(force=True)
    wager = int(data.get("wager", 0))
    pick = data.get("pick")

    horse = next((h for h in HORSES if h["key"] == pick), None)
    if not horse:
        return jsonify({"error": "選択した馬が見つかりません。"}), 400

    error = validate_wager(current_user, wager)
    if error:
        return jsonify({"error": error}), 400

    user = current_user
    user.balance -= wager

    total_weight = sum(h["weight"] for h in HORSES)
    f = fairness.get_float(user.server_seed, user.client_seed, user.nonce)
    used_nonce = user.nonce
    user.nonce += 1
    winner = _pick_winner(total_weight, f)

    # 着順演出用に、残りの馬をシャッフルして「順位」を作る(払い戻しには影響しない)
    order_floats = fairness.get_floats(user.server_seed, user.client_seed, user.nonce, len(HORSES) - 1)
    user.nonce += 1
    others = [h for h in HORSES if h["key"] != winner["key"]]
    ranked_others = [h for _, h in sorted(zip(order_floats, others), key=lambda x: x[0])]
    finish_order = [winner] + ranked_others

    won = pick == winner["key"]
    multiplier = scale_multiplier("horserace", horse["payout"]) if won else 0
    payout = round(wager * multiplier) if won else 0

    if payout > 0:
        credit_winnings(user, payout)
    apply_rakeback(user, wager)

    db.session.add(BetRecord(
        user_id=user.id, game="horserace", wager=wager, payout=payout, multiplier=multiplier,
        server_seed_hash=user.server_seed_hash, client_seed=user.client_seed, nonce=used_nonce,
        result_json=json.dumps({"pick": pick, "winner": winner["key"], "order": [h["key"] for h in finish_order]})
    ))
    db.session.commit()

    return jsonify({
        "won": won, "multiplier": multiplier, "payout": payout, "balance": user.balance,
        "finish_order": [{"key": h["key"], "name": h["name"]} for h in finish_order],
    })
