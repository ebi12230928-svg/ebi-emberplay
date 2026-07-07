import json

from flask import render_template, request, jsonify
from flask_login import login_required, current_user

from extensions import db
from models import BetRecord
import fairness
from . import games_bp
from .common import validate_wager, apply_rakeback, credit_winnings, scale_multiplier


def _card_value(rank):
    return rank if rank <= 9 else 0


def _hand_total(cards):
    return sum(_card_value(c) for c in cards) % 10


def _draw_ranks(user, count):
    floats = fairness.get_floats(user.server_seed, user.client_seed, user.nonce, count)
    used_nonce = user.nonce
    user.nonce += 1
    return [int(f * 13) + 1 for f in floats], used_nonce


@games_bp.route("/baccarat")
@login_required
def baccarat_page():
    return render_template("games/baccarat.html")


@games_bp.route("/baccarat/play", methods=["POST"])
@login_required
def baccarat_play():
    data = request.get_json(force=True)
    wager = int(data.get("wager", 0))
    bet_on = data.get("bet_on")  # player / banker / tie

    error = validate_wager(current_user, wager)
    if error:
        return jsonify({"error": error}), 400
    if bet_on not in ("player", "banker", "tie"):
        return jsonify({"error": "選択対象が不正です。"}), 400

    user = current_user
    user.balance -= wager

    ranks, used_nonce = _draw_ranks(user, 6)
    player = [ranks[0], ranks[1]]
    banker = [ranks[2], ranks[3]]
    extra_pool = ranks[4:]

    player_total = _hand_total(player)
    banker_total = _hand_total(banker)

    player_drew_third = False
    player_third_value = None

    if player_total <= 7 and banker_total <= 7:  # ナチュラル(8,9)以外
        if player_total <= 5:
            third = extra_pool.pop(0)
            player.append(third)
            player_drew_third = True
            player_third_value = _card_value(third)
            player_total = _hand_total(player)

        # バンカーのドロー判定
        if not player_drew_third:
            if banker_total <= 5:
                banker.append(extra_pool.pop(0))
        else:
            draw_banker = False
            if banker_total <= 2:
                draw_banker = True
            elif banker_total == 3:
                draw_banker = player_third_value != 8
            elif banker_total == 4:
                draw_banker = player_third_value in (2, 3, 4, 5, 6, 7)
            elif banker_total == 5:
                draw_banker = player_third_value in (4, 5, 6, 7)
            elif banker_total == 6:
                draw_banker = player_third_value in (6, 7)
            if draw_banker:
                banker.append(extra_pool.pop(0))

        banker_total = _hand_total(banker)

    if player_total > banker_total:
        winner = "player"
    elif banker_total > player_total:
        winner = "banker"
    else:
        winner = "tie"

    if bet_on == winner == "tie":
        multiplier = 8.0
    elif bet_on == "tie":
        multiplier = 0
    elif winner == "tie":
        multiplier = 1.0  # プッシュ(プレイ料を返す)
    elif bet_on == winner == "player":
        multiplier = 2.0
    elif bet_on == winner == "banker":
        multiplier = 1.95  # 5%のコミッション控除
    else:
        multiplier = 0

    if multiplier > 1.0:
        multiplier = scale_multiplier("baccarat", multiplier)

    payout = round(wager * multiplier)
    credit_winnings(user, payout)
    apply_rakeback(user, wager)

    db.session.add(BetRecord(
        user_id=user.id, game="baccarat", wager=wager, payout=payout, multiplier=multiplier,
        server_seed_hash=user.server_seed_hash, client_seed=user.client_seed, nonce=used_nonce,
        result_json=json.dumps({
            "player": player, "banker": banker, "player_total": player_total,
            "banker_total": banker_total, "winner": winner, "bet_on": bet_on
        })
    ))
    db.session.commit()

    return jsonify({
        "player": player, "banker": banker, "player_total": player_total, "banker_total": banker_total,
        "winner": winner, "multiplier": multiplier, "payout": payout, "balance": user.balance
    })
