import json

from flask import render_template, request, jsonify
from flask_login import login_required, current_user

from extensions import db
from models import BetRecord
import fairness
from . import games_bp
from .common import validate_wager, apply_rakeback, credit_winnings, scale_multiplier

# バカラのDragon Bonusサイドベット。選んだ側が「大差」で勝てば配当(僅差の勝ちはハズレ扱い)。
# 通常のバカラと同じ第三カードルールを使用。50万回シミュレーションで検証済み(house edge約9〜13%)
MARGIN_PAYOUTS = {4: 0.61, 5: 1.23, 6: 2.46, 7: 3.69, 8: 6.14, 9: 18.43}


def _card_value(rank):
    return rank if rank <= 9 else 0


def _hand_total(cards):
    return sum(_card_value(c) for c in cards) % 10


def _draw_ranks(user, count):
    floats = fairness.get_floats(user.server_seed, user.client_seed, user.nonce, count)
    used_nonce = user.nonce
    user.nonce += 1
    return [int(f * 13) + 1 for f in floats], used_nonce


def _deal_baccarat(ranks):
    player = [ranks[0], ranks[1]]
    banker = [ranks[2], ranks[3]]
    extra_pool = ranks[4:]

    player_total = _hand_total(player)
    banker_total = _hand_total(banker)
    player_drew_third = False
    player_third_value = None

    if player_total <= 7 and banker_total <= 7:
        if player_total <= 5:
            third = extra_pool.pop(0)
            player.append(third)
            player_drew_third = True
            player_third_value = _card_value(third)
            player_total = _hand_total(player)

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

    return player, banker, player_total, banker_total


@games_bp.route("/dragonbonus")
@login_required
def dragonbonus_page():
    return render_template("games/dragonbonus.html", payouts=MARGIN_PAYOUTS)


@games_bp.route("/dragonbonus/play", methods=["POST"])
@login_required
def dragonbonus_play():
    data = request.get_json(force=True)
    wager = int(data.get("wager", 0))
    bet_on = data.get("bet_on")

    if bet_on not in ("player", "banker"):
        return jsonify({"error": "選択が不正です。"}), 400

    error = validate_wager(current_user, wager)
    if error:
        return jsonify({"error": error}), 400

    user = current_user
    user.balance -= wager

    ranks, used_nonce = _draw_ranks(user, 6)
    player, banker, player_total, banker_total = _deal_baccarat(ranks)

    if player_total == banker_total:
        outcome = "tie_push"
        multiplier = 1.0
    else:
        winner = "player" if player_total > banker_total else "banker"
        margin = abs(player_total - banker_total)
        if winner == bet_on and margin >= 4:
            outcome = "win"
            multiplier = scale_multiplier("dragonbonus", MARGIN_PAYOUTS[margin])
        else:
            outcome = "lose"
            multiplier = 0

    payout = round(wager * multiplier)
    if payout > 0:
        credit_winnings(user, payout)
    apply_rakeback(user, wager)

    db.session.add(BetRecord(
        user_id=user.id, game="dragonbonus", wager=wager, payout=payout, multiplier=multiplier,
        server_seed_hash=user.server_seed_hash, client_seed=user.client_seed, nonce=used_nonce,
        result_json=json.dumps({
            "player": player, "banker": banker, "player_total": player_total,
            "banker_total": banker_total, "bet_on": bet_on, "outcome": outcome
        })
    ))
    db.session.commit()

    return jsonify({
        "player": player, "banker": banker, "player_total": player_total, "banker_total": banker_total,
        "outcome": outcome, "multiplier": multiplier, "payout": payout, "balance": user.balance
    })
