"""アンケート機能。管理者が質問と選択肢を作成し、ユーザーは1回だけ投票できる(任意で謝礼Embersあり)。"""
import json

from flask import Blueprint, render_template, jsonify, request
from flask_login import login_required, current_user

from extensions import db
from models import Poll, PollVote, Transaction

polls_bp = Blueprint("polls", __name__)


@polls_bp.route("/polls")
@login_required
def index():
    active_polls = Poll.query.filter_by(is_active=True).order_by(Poll.created_at.desc()).all()
    closed_polls = Poll.query.filter_by(is_active=False).order_by(Poll.created_at.desc()).limit(10).all()

    voted_poll_ids = {
        v.poll_id for v in PollVote.query.filter_by(user_id=current_user.id).all()
    }

    def build_view(poll):
        options = json.loads(poll.options_json)
        votes = PollVote.query.filter_by(poll_id=poll.id).all()
        counts = [0] * len(options)
        for v in votes:
            if 0 <= v.option_index < len(counts):
                counts[v.option_index] += 1
        total = sum(counts) or 1
        my_vote = next((v.option_index for v in votes if v.user_id == current_user.id), None)

        return {
            "id": poll.id, "question": poll.question, "options": options, "reward": poll.reward,
            "is_active": poll.is_active, "voted": poll.id in voted_poll_ids, "my_vote": my_vote,
            "counts": counts, "total": total,
            "percentages": [round(c / total * 100, 1) for c in counts],
        }

    return render_template(
        "polls.html",
        active_polls=[build_view(p) for p in active_polls],
        closed_polls=[build_view(p) for p in closed_polls],
    )


@polls_bp.route("/polls/<int:poll_id>/vote", methods=["POST"])
@login_required
def vote(poll_id):
    poll = Poll.query.get(poll_id)
    if not poll or not poll.is_active:
        return jsonify({"error": "このアンケートは現在投票を受け付けていません。"}), 400

    data = request.get_json(force=True)
    try:
        option_index = int(data.get("option_index"))
    except (TypeError, ValueError):
        return jsonify({"error": "選択が不正です。"}), 400

    options = json.loads(poll.options_json)
    if not (0 <= option_index < len(options)):
        return jsonify({"error": "選択が不正です。"}), 400

    if PollVote.query.filter_by(poll_id=poll_id, user_id=current_user.id).first():
        return jsonify({"error": "すでに投票済みです。"}), 400

    db.session.add(PollVote(poll_id=poll_id, user_id=current_user.id, option_index=option_index))

    if poll.reward > 0:
        current_user.balance += poll.reward
        db.session.add(Transaction(
            user_id=current_user.id, amount=poll.reward, kind="poll_reward",
            description=f"アンケート回答謝礼: {poll.question[:30]}"
        ))
    db.session.commit()

    try:
        from achievements import check_achievements
        check_achievements(current_user)
    except Exception:
        pass

    return jsonify({"ok": True, "balance": current_user.balance, "reward": poll.reward})
