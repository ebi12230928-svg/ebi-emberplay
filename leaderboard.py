from flask import Blueprint, render_template
from flask_login import login_required
from sqlalchemy import func

from extensions import db
from models import User, BetRecord

leaderboard_bp = Blueprint("leaderboard", __name__)


@leaderboard_bp.route("/leaderboard")
@login_required
def index():
    top_balance = User.query.order_by(User.balance.desc()).limit(3).all()

    # 「最大の増えた数」= 1回のプレイでの最大純利益(payout - wager)。
    # ユーザーごとの最大値を求め、その上位3人を表示する。
    best_per_user = {}
    candidates = (
        BetRecord.query.order_by((BetRecord.payout - BetRecord.wager).desc()).limit(200).all()
    )
    for bet in candidates:
        net = bet.payout - bet.wager
        if bet.user_id not in best_per_user or net > best_per_user[bet.user_id][0]:
            best_per_user[bet.user_id] = (net, bet)

    top_gains = sorted(best_per_user.values(), key=lambda x: x[0], reverse=True)[:3]

    referral_counts = (
        db.session.query(User.referred_by_id, func.count(User.id))
        .filter(User.referred_by_id.isnot(None))
        .group_by(User.referred_by_id)
        .order_by(func.count(User.id).desc())
        .limit(5)
        .all()
    )
    top_referrers = []
    for referrer_id, count in referral_counts:
        referrer = User.query.get(referrer_id)
        if referrer:
            top_referrers.append({"username": referrer.username, "count": count})

    return render_template(
        "leaderboard.html", top_balance=top_balance, top_gains=top_gains, top_referrers=top_referrers
    )
