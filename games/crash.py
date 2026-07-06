import json
import math

from flask import render_template, request, jsonify
from flask_login import login_required, current_user

from extensions import db
from models import BetRecord, CrashGame, utcnow
import fairness
from . import games_bp
from .common import validate_wager, apply_rakeback, credit_winnings

CRASH_HOUSE_EDGE = 0.08
GROWTH_RATE = math.log(2) / 18  # 18秒ごとに倍率が2倍になるペース(以前より緩やかに)


def _current_multiplier(started_at):
    elapsed = (utcnow() - started_at).total_seconds()
    return round(math.exp(GROWTH_RATE * max(elapsed, 0)), 4)


@games_bp.route("/crash")
@login_required
def crash_page():
    return render_template("games/crash.html", growth_rate=GROWTH_RATE)


@games_bp.route("/crash/start", methods=["POST"])
@login_required
def crash_start():
    data = request.get_json(force=True)
    wager = int(data.get("wager", 0))

    if CrashGame.query.filter_by(user_id=current_user.id).first():
        return jsonify({"error": "すでに進行中のラウンドがあります。"}), 400

    error = validate_wager(current_user, wager)
    if error:
        return jsonify({"error": error}), 400

    user = current_user
    user.balance -= wager

    point = fairness.crash_point(user.server_seed, user.client_seed, user.nonce, house_edge=CRASH_HOUSE_EDGE)
    used_nonce = user.nonce
    user.nonce += 1

    game = CrashGame(
        user_id=user.id, wager=wager, crash_point=point, started_at=utcnow(),
        server_seed_hash=user.server_seed_hash, client_seed=user.client_seed, nonce=used_nonce
    )
    db.session.add(game)
    db.session.commit()

    return jsonify({
        "balance": user.balance,
        "started_at": game.started_at.isoformat() + "Z",
        "growth_rate": GROWTH_RATE,
    })


@games_bp.route("/crash/status")
@login_required
def crash_status():
    game = CrashGame.query.filter_by(user_id=current_user.id).first()
    if not game:
        return jsonify({"active": False})

    current_mult = _current_multiplier(game.started_at)
    busted = current_mult >= game.crash_point

    if busted:
        db.session.add(BetRecord(
            user_id=current_user.id, game="crash", wager=game.wager, payout=0, multiplier=0,
            server_seed_hash=game.server_seed_hash, client_seed=game.client_seed, nonce=game.nonce,
            result_json=json.dumps({"crash_point": game.crash_point})
        ))
        db.session.delete(game)
        db.session.commit()
        return jsonify({"active": False, "busted": True, "crash_point": current_mult, "balance": current_user.balance})

    return jsonify({"active": True, "multiplier": current_mult})


@games_bp.route("/crash/cashout", methods=["POST"])
@login_required
def crash_cashout():
    game = CrashGame.query.filter_by(user_id=current_user.id).first()
    if not game:
        return jsonify({"error": "進行中のラウンドがありません。"}), 400

    current_mult = _current_multiplier(game.started_at)

    if current_mult >= game.crash_point:
        db.session.add(BetRecord(
            user_id=current_user.id, game="crash", wager=game.wager, payout=0, multiplier=0,
            server_seed_hash=game.server_seed_hash, client_seed=game.client_seed, nonce=game.nonce,
            result_json=json.dumps({"crash_point": game.crash_point})
        ))
        db.session.delete(game)
        db.session.commit()
        return jsonify({"busted": True, "crash_point": game.crash_point, "balance": current_user.balance})

    payout = round(game.wager * current_mult)
    user = current_user
    credit_winnings(user, payout)
    apply_rakeback(user, game.wager)

    db.session.add(BetRecord(
        user_id=user.id, game="crash", wager=game.wager, payout=payout, multiplier=current_mult,
        server_seed_hash=game.server_seed_hash, client_seed=game.client_seed, nonce=game.nonce,
        result_json=json.dumps({"cashed_out_at": current_mult, "crash_point": game.crash_point})
    ))
    db.session.delete(game)
    db.session.commit()

    return jsonify({"busted": False, "multiplier": current_mult, "payout": payout, "balance": user.balance})
