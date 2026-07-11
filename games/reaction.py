"""カジノ要素とは無関係のミニゲーム。反応速度に応じてEmbersを直接獲得できる(賭け金なし)。"""
from flask import render_template, request, jsonify
from flask_login import login_required, current_user

from extensions import db
from models import Transaction
from . import games_bp

MIN_VALID_MS = 150   # これより速い申告は物理的に不自然なため無効扱い(不正対策)
MAX_REWARD = 150
MIN_REWARD = 20
FAST_MS = 200         # このタイム以下で最大報酬
SLOW_MS = 2000        # このタイム以上で最低報酬


@games_bp.route("/reaction")
@login_required
def reaction_page():
    return render_template("games/reaction.html", max_reward=MAX_REWARD, min_reward=MIN_REWARD)


@games_bp.route("/reaction/submit", methods=["POST"])
@login_required
def reaction_submit():
    data = request.get_json(force=True)
    try:
        elapsed_ms = float(data.get("elapsed_ms"))
    except (TypeError, ValueError):
        return jsonify({"error": "計測データが不正です。"}), 400

    if elapsed_ms < MIN_VALID_MS:
        return jsonify({"error": "速すぎる反応は無効です(不正防止のため)。もう一度お試しください。", "invalid": True}), 400

    if elapsed_ms <= FAST_MS:
        reward = MAX_REWARD
    elif elapsed_ms >= SLOW_MS:
        reward = MIN_REWARD
    else:
        ratio = (elapsed_ms - FAST_MS) / (SLOW_MS - FAST_MS)
        reward = round(MAX_REWARD - ratio * (MAX_REWARD - MIN_REWARD))

    current_user.balance += reward
    db.session.add(Transaction(
        user_id=current_user.id, amount=reward, kind="reaction", description=f"反射神経テスト({elapsed_ms:.0f}ms)"
    ))
    db.session.commit()

    try:
        from achievements import check_achievements
        check_achievements(current_user)
    except Exception:
        pass

    return jsonify({"reward": reward, "balance": current_user.balance})
