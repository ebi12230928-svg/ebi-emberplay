"""
トーナメント機能。管理者が対象ゲーム・優勝賞品を設定して開催する。
スコアは、既存のTransaction記録(各ゲームプレイ時の勝敗記録)からトーナメント期間中の合計勝利額を
集計する方式で算出するため、個々のゲームのコードを変更する必要がない。
"""
from flask import Blueprint, render_template
from flask_login import login_required, current_user

from extensions import db
from models import Tournament, TournamentScore, Transaction, User

tournament_bp = Blueprint("tournament", __name__)


def compute_scores(tournament):
    """トーナメント対象ゲームの、参加期間中の勝利額合計をユーザーごとに集計する"""
    rows = (
        db.session.query(Transaction.user_id, db.func.sum(Transaction.amount))
        .filter(
            Transaction.kind == tournament.game_key,
            Transaction.amount > 0,
            Transaction.created_at >= tournament.created_at,
        )
        .group_by(Transaction.user_id)
        .all()
    )
    return {uid: int(total) for uid, total in rows}


@tournament_bp.route("/tournament")
@login_required
def index():
    active = Tournament.query.filter_by(status="active").order_by(Tournament.created_at.desc()).all()
    finished = Tournament.query.filter_by(status="finished").order_by(Tournament.created_at.desc()).limit(10).all()

    leaderboards = {}
    for t in active + finished:
        scores = compute_scores(t)
        ranked = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)[:10]
        users = {u.id: u.username for u in User.query.filter(User.id.in_([uid for uid, _ in ranked])).all()} if ranked else {}
        leaderboards[t.id] = [{"username": users.get(uid, "?"), "score": score} for uid, score in ranked]

    return render_template("tournament.html", active=active, finished=finished, leaderboards=leaderboards)
