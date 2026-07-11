from datetime import timedelta

from flask import Blueprint, render_template, request
from flask_login import login_required
from sqlalchemy import func

from extensions import db
from models import User, BetRecord, utcnow

leaderboard_bp = Blueprint("leaderboard", __name__)

PERIODS = {"all": "全期間", "weekly": "過去7日間", "monthly": "過去30日間"}


@leaderboard_bp.route("/leaderboard")
@login_required
def index():
    period = request.args.get("period", "all")
    if period not in PERIODS:
        period = "all"

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

    # 期間内の合計損益ランキング(週間/月間で切り替え可能)
    profit_query = db.session.query(
        BetRecord.user_id, func.sum(BetRecord.payout - BetRecord.wager).label("net")
    )
    if period == "weekly":
        profit_query = profit_query.filter(BetRecord.created_at >= utcnow() - timedelta(days=7))
    elif period == "monthly":
        profit_query = profit_query.filter(BetRecord.created_at >= utcnow() - timedelta(days=30))
    profit_rows = (
        profit_query.group_by(BetRecord.user_id).order_by(func.sum(BetRecord.payout - BetRecord.wager).desc())
        .limit(5).all()
    )
    top_profit = []
    for user_id, net in profit_rows:
        user = User.query.get(user_id)
        if user:
            top_profit.append({"username": user.username, "net": int(net or 0)})

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
        "leaderboard.html", top_balance=top_balance, top_gains=top_gains, top_referrers=top_referrers,
        top_profit=top_profit, period=period, periods=PERIODS
    )
