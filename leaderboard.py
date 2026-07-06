from flask import Blueprint, render_template
from flask_login import login_required

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

    return render_template("leaderboard.html", top_balance=top_balance, top_gains=top_gains)
